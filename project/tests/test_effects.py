"""Editable native VFX, deterministic recipes and preservation across project creation."""
from pathlib import Path
import tempfile
import unittest

from pixel_workbench.effects import PRESETS, make_effect, settings
from pixel_workbench.model import Document, PixelError, pixels
from pixel_workbench.service import DocumentService


class EffectTests(unittest.TestCase):
    def test_presets_are_layered_transparent_and_animated(self):
        for preset in PRESETS:
            with self.subTest(preset=preset):
                doc, config = make_effect({"preset": preset, "size": 32, "frames": 16, "duration_ms": 80})
                self.assertEqual(len(doc.layers), 3)
                self.assertEqual(doc.durations, [80] * 16)
                self.assertEqual(doc.tags[preset]["end"], 15)
                images = [doc.composite(f) for f in range(16)]
                self.assertTrue(all(image.getbbox() for image in images))
                self.assertGreater(len({im.tobytes() for im in images}), 12)
                self.assertTrue(all(im.getpixel((0, 0))[3] == 0 for im in images))
                allowed = {tuple(bytes.fromhex(c[1:])) for c in doc.palette}
                self.assertTrue(all(p in allowed for image in images for p in pixels(image)))
                self.assertTrue(all(p[3] in (0, 255) for image in images for p in pixels(image)))
                self.assertEqual(doc.effect_recipe["settings"], config)

    def test_recipe_roundtrip_and_native_undo(self):
        doc, _ = make_effect({"size": 32, "frames": 8})
        after = [doc.composite(f).tobytes() for f in range(8)]
        reopened = Document.from_dict(doc.to_dict())
        self.assertEqual(reopened.effect_recipe, doc.effect_recipe)
        doc.undo()
        self.assertEqual(len(doc.durations), 1)
        self.assertFalse(doc.composite().getbbox())
        doc.redo()
        self.assertEqual([doc.composite(f).tobytes() for f in range(8)], after)
        doc.apply([{"op": "pixel", "x": 0, "y": 0, "color": 2, "frame": 2}])
        self.assertEqual(doc.composite(2).getpixel((0, 0))[3], 255)
        doc.undo()
        self.assertEqual([doc.composite(f).tobytes() for f in range(8)], after)

    def test_seed_strength_and_tint_have_visible_effect(self):
        a, _ = make_effect({"preset": "fire", "size": 32, "frames": 8})
        same, _ = make_effect({"preset": "fire", "size": 32, "frames": 8})
        self.assertEqual(a.composite(3).tobytes(), same.composite(3).tobytes())
        for change in ({"seed": 8}, {"strength": 100}, {"color": "#3388ff"}):
            different, _ = make_effect({"preset": "fire", "size": 32, "frames": 8, **change})
            self.assertNotEqual(a.composite(3).tobytes(), different.composite(3).tobytes())

    def test_input_bounds_are_strict(self):
        self.assertEqual((settings()["preset"], settings()["frames"], settings()["duration_ms"]), ("slash", 12, 30))
        self.assertEqual((settings({"preset": "magic"})["frames"], settings({"preset": "magic"})["duration_ms"]), (24, 80))
        # A user tint may duplicate a ramp/smoke color; palette dedup must not shift stamp colors.
        tinted, _ = make_effect({"preset": "burst", "size": 24, "frames": 8, "color": "#8b91a5"})
        self.assertEqual(len(tinted.durations), 8)
        for value in ({"preset": []}, {"size": True}, {"size": 129}, {"frames": 7},
                      {"frames": 33}, {"duration_ms": 29}, {"strength": 101},
                      {"seed": -1}, {"color": "#11223300"}, {"unknown": 1}):
            with self.subTest(value=value), self.assertRaises(PixelError):
                settings(value)

    def test_preview_readonly_create_preserves_source_and_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = Document(24, 24, "Human artwork")
            source.apply([{"op": "pixel", "x": 3, "y": 4, "color": 7}])
            service = DocumentService(source, workspace=root / "work", runtime=root / "runtime")
            before, revision = source.fingerprint(), source.revision
            preview, _ = service.dispatch("POST", "/effects", payload={"action": "preview", "settings": {"size": 32, "frames": 8}})
            self.assertEqual((source.fingerprint(), source.revision), (before, revision))
            self.assertTrue(preview["images_png"])
            self.assertTrue(Path(preview["preview_animation"]["path"]).is_file())
            with self.assertRaises(PixelError):
                service.dispatch("POST", "/effects", payload={"action": "create", "expected_revision": -1})
            def create(value):
                return service.dispatch("POST", "/effects", payload={"action": "create", "settings": value,
                    "expected_document_id": service.doc.id, "expected_revision": service.doc.revision, "include_images": False})[0]
            first = create({"preset": "fire", "size": 32, "frames": 8})
            source_entry = next(p for p in service.projects.listing() if p["document_id"] == source.id)
            self.assertEqual(Document.open(source_entry["path"]).composite().tobytes(), source.composite().tobytes())
            first_path = Path(first["project_path"])
            first_bytes = first_path.read_bytes()
            second = create({"preset": "slash", "size": 32, "frames": 8})
            self.assertNotEqual(first["document_id"], second["document_id"])
            self.assertEqual(first_path.read_bytes(), first_bytes)
            self.assertEqual(len(service.projects.listing()), 3)

    def test_gif_and_sheet_preserve_frame_count_timing(self):
        from PIL import Image
        import json
        with tempfile.TemporaryDirectory() as folder:
            doc, _ = make_effect({"preset": "slash", "frames": 8, "size": 32, "duration_ms": 100})
            gif, sheet = Path(folder) / "effect.gif", Path(folder) / "effect.png"
            doc.export(gif, "gif")
            with Image.open(gif) as image:
                self.assertEqual(image.n_frames, 8)
                self.assertEqual(image.info["duration"], 100)
            doc.export(sheet, "sheet")
            metadata = json.loads(sheet.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(len(metadata["frames"]), 8)


if __name__ == "__main__":
    unittest.main()
