"""Regression coverage for portable specs, guarded diagnostics and exact reversible repairs."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_workbench.character import capture, configure, validate_profile
from pixel_workbench.model import Document, PixelError
from pixel_workbench.motion import MotionManager, analyze_motion
from pixel_workbench.quality import DEFAULT_POLICY, content_digest, required_criteria
from pixel_workbench.reference import decoded_asset
from pixel_workbench.service import DocumentService


def sprite():
    doc = Document(32, 32, "Character")
    doc.apply([{"op": "rect", "x": 10, "y": 5, "width": 10, "height": 22, "color": 7},
               {"op": "region_define", "name": "face", "rect": [12, 6, 6, 5]}])
    doc.apply([{"op": "character_profile", "data": capture(doc, {"fixed_regions": ["face"]})}])
    doc.apply([{"op": "frame_add", "copy_from": 0}, {"op": "frame_add", "copy_from": 0}])
    return doc


class CharacterMotionTests(unittest.TestCase):
    def test_portable_roundtrip_and_metadata_undo(self):
        doc = sprite()
        before = doc.composite().tobytes()
        spec = deepcopy(doc.character)
        changed = configure(doc, spec, {"name": "New name", "notes": "same face"})
        doc.apply([{"op": "character_profile", "data": changed}])
        self.assertEqual(doc.character["pose"], spec["pose"])
        self.assertEqual(doc.composite().tobytes(), before)
        doc.undo()
        self.assertEqual(doc.character, spec)
        doc.redo()
        copy = Document.from_dict(doc.to_dict())
        self.assertEqual(copy.character, changed)
        self.assertNotIn("png", str(copy.state()["character"]))

    def test_old_project_still_loads(self):
        old = Document().to_dict()
        self.assertNotIn("character_profile", old)
        self.assertIsNone(Document.from_dict(old).character)

    def test_strict_profile_validation(self):
        doc = sprite()
        for mutate in (lambda v: v.update(width=33), lambda v: v.update(baseline_y=True),
                       lambda v: v.update(pose=None), lambda v: v.update(palette=["#00000000"]),
                       lambda v: v.update(fixed_parts=[{"name": "bad", "rect": [31, 0, 2, 2]}]),
                       lambda v: v["pose"].update(name="C:\\private\\pose.png"),
                       lambda v: v["views"].update(diagonal=v["pose"])):
            value = deepcopy(doc.character)
            mutate(value)
            with self.assertRaises((PixelError, ValueError)):
                validate_profile(value, doc.width, doc.height)

    def test_resize_reprojects_pose_regions_and_baseline(self):
        for operation in ("canvas_resize", "sprite_scale"):
            doc = sprite()
            before = deepcopy(doc.character)
            doc.apply([{"op": operation, "width": 48, "height": 48, "anchor": "bottom_center"}] if operation == "canvas_resize"
                      else [{"op": operation, "width": 48, "height": 48}])
            self.assertEqual(doc.character["pose"]["size"], [48, 48])
            self.assertEqual(Document.from_dict(doc.to_dict()).character, doc.character)
            self.assertEqual(doc.character["baseline_y"], 43 if operation == "canvas_resize" else 40)
            doc.undo()
            self.assertEqual(doc.character, before)

    def test_clear_and_recapture_are_explicit(self):
        doc = sprite()
        old = deepcopy(doc.character)
        doc.apply([{"op": "pixel", "frame": 0, "x": 10, "y": 5, "color": 1}])
        self.assertEqual(doc.character, old)
        doc.apply([{"op": "select", "frame": 0}])
        self.assertNotEqual(capture(doc)["pose"], old["pose"])
        doc.apply([{"op": "character_profile", "data": None}])
        self.assertIsNone(doc.character)
        doc.undo()
        self.assertEqual(doc.character, old)

    def test_service_portable_import_export_and_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            service = DocumentService(sprite(), workspace=Path(folder) / "workspace", runtime=Path(folder) / "runtime")
            def call(verb, **kwargs):
                return service.dispatch("POST", "/character", payload={"action": verb,
                    "expected_document_id": service.doc.id, "expected_revision": service.doc.revision,
                    "include_images": False, **kwargs})[0]
            path = Path(folder) / "hero.pixelchar"
            call("save", path=str(path))
            with self.assertRaises(PixelError):
                call("save", path=str(path))
            image_path = Path(folder) / "left.png"
            Image.new("RGBA", (40, 50), "red").save(image_path)
            call("reference_load", role="left", path=str(image_path))
            image_path.unlink()
            self.assertEqual(service.doc.character["views"]["left"]["size"], [40, 50])
            call("reference_clear", role="left")
            self.assertFalse(service.doc.character["views"])
            before = service.doc.composite().tobytes()
            call("clear")
            call("load", path=str(path))
            self.assertEqual(service.doc.composite().tobytes(), before)
            with self.assertRaises(PixelError):
                call("configure", expected_revision=-1, settings={"name": "stale"})
            self.assertTrue(call("status")["character"]["configured"])

    def test_exact_orphan_repair_bypasses_selection_and_undo(self):
        doc = sprite()
        doc.apply([{"op": "pixel", "frame": 1, "x": 23, "y": 24, "color": 7},
                   {"op": "pixel", "frame": 1, "x": 25, "y": 25, "color": 7},
                   {"op": "selection_set", "rect": [0, 0, 1, 1]}])
        before = doc.to_dict()
        report = analyze_motion(doc)
        finding = next(f for f in report["findings"] if f["kind"] == "orphan_pixels")
        x, y, _, _ = finding["rect"]
        doc.apply(finding["repair_ops"])
        self.assertEqual(doc.composite(1).getpixel((x, y))[3], 0)
        other = (25, 25) if (x, y) == (23, 24) else (23, 24)
        self.assertEqual(doc.composite(1).getpixel(other)[3], 255)
        doc.undo()
        self.assertEqual(doc.layers[0].cels[1].tobytes(), Document.from_dict(before).layers[0].cels[1].tobytes())

    def test_existing_tiny_decoration_not_reported(self):
        doc = sprite()
        doc.apply([{"op": "pixel", "frame": f, "x": 23, "y": 24, "color": 7} for f in range(3)])
        doc.active_frame = 0
        doc.apply([{"op": "character_profile", "data": capture(doc)}])
        self.assertNotIn("orphan_pixels", analyze_motion(doc)["counts"])

    def test_locked_layers_never_repaired(self):
        doc = sprite()
        doc.apply([{"op": "pixel", "frame": 1, "x": 23, "y": 24, "color": 7}])
        doc.layers[0].locked = True
        findings = analyze_motion(doc)["findings"]
        orphan = next(f for f in findings if f["kind"] == "orphan_pixels")
        self.assertEqual(orphan["repair_ops"], [])

    def test_fixed_color_and_baseline_findings(self):
        doc = sprite()
        doc.apply([{"op": "palette_add", "colors": ["#f10203ff"]},
                   {"op": "pixel", "frame": 1, "x": 13, "y": 7, "color": "#f10203ff"},
                   {"op": "pixel", "frame": 1, "x": 12, "y": 27, "color": 7}])
        report = analyze_motion(doc, mode="grounded")
        self.assertTrue({"fixed_region", "palette_drift", "baseline"} <= set(report["counts"]))
        self.assertNotIn("baseline", analyze_motion(doc)["counts"])
        fixed = next(f for f in report["findings"] if f["kind"] == "fixed_region")
        self.assertEqual(fixed["rect"], [13, 7, 1, 1])  # RGB-only difference, same alpha.

    def test_report_pages_readonly_stale_and_evidence(self):
        doc = sprite()
        doc.apply([{"op": "pixel", "frame": f, "x": x, "y": 24, "color": 7}
                   for f in (1, 2) for x in (23, 26, 29)])
        manager = MotionManager()
        before, revision = content_digest(doc), doc.revision
        report = manager.check(doc, {})
        self.assertGreater(report["pages"], 1)
        self.assertEqual((content_digest(doc), doc.revision), (before, revision))
        self.assertEqual(len(report["images_png"]), len(report["findings"]))
        self.assertGreater(decoded_asset(report["images_png"][0]).width, 10)
        doc.apply([{"op": "select", "frame": 2}])
        self.assertEqual(manager.check(doc, {"report_id": report["report_id"], "page": 1})["page"], 1)
        doc.apply([{"op": "pixel", "frame": 0, "x": 11, "y": 6, "color": 1}])
        with self.assertRaises(PixelError) as caught:
            manager.check(doc, {"report_id": report["report_id"]})
        self.assertEqual(caught.exception.code, "MOTION_STALE")

    def test_character_becomes_visual_acceptance_criterion(self):
        doc = sprite()
        self.assertIn("character_consistency", [c["id"] for c in required_criteria(doc, DEFAULT_POLICY, [0, 1, 2])])

    def test_scope_and_blank_frame(self):
        doc = sprite()
        doc.apply([{"op": "frame_add", "blank": True}, {"op": "tag_set", "name": "first", "start": 0, "end": 1}])
        self.assertIn(3, [f["frame"] for f in analyze_motion(doc)["findings"] if f["kind"] == "empty_frame"])
        report = analyze_motion(doc, tag="first")
        self.assertEqual(report["frames"], [0, 1])
        with self.assertRaises(PixelError):
            analyze_motion(doc, tag="missing")

    def test_multiple_layers_clear_only_the_component(self):
        doc = sprite()
        doc.apply([{"op": "layer_add", "id": "extra", "name": "Extra"},
                   {"op": "pixel", "layer": "extra", "frame": 1, "x": 24, "y": 24, "color": 1},
                   {"op": "pixel", "layer": doc.layers[0].id, "frame": 1, "x": 24, "y": 24, "color": 7}])
        finding = next(f for f in analyze_motion(doc)["findings"] if f["kind"] == "orphan_pixels")
        self.assertEqual(len(finding["repair_ops"]), 2)
        before = doc.composite(1).tobytes()
        doc.apply(finding["repair_ops"])
        self.assertEqual(doc.composite(1).getpixel((24, 24))[3], 0)
        doc.undo()
        self.assertEqual(doc.composite(1).tobytes(), before)

    def test_abrupt_change_and_loop_seam_include_source_frame(self):
        doc = sprite()
        doc.apply([{"op": "frame_add", "copy_from": 0} for _ in range(5)] + [{"op": "clear", "frame": 7}])
        report = analyze_motion(doc)
        self.assertIn("abrupt_change", report["counts"])
        seam = next(f for f in report["findings"] if f["kind"] == "loop_jump")
        self.assertEqual((seam["frame"], seam["previous_frame"]), (0, 7))


if __name__ == "__main__":
    unittest.main()
