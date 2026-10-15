from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_workbench.model import Document, PixelError, pixels
from pixel_workbench.reference import decoded_asset, load_asset, make_draft, validate_context
from pixel_workbench.service import DocumentService


def ordinary_image(path):
    """A smooth, ordinary illustration fixture (not a pixel sprite)."""
    image = Image.new("RGBA", (240, 360))
    draw = ImageDraw.Draw(image)
    for y in range(360):
        draw.line((0, y, 239, y), fill=(30+y//8, 45+y//7, 80+y//5, 255))
    draw.ellipse((65, 28, 179, 152), fill="#e6ba67")
    draw.ellipse((81, 62, 165, 149), fill="#ffe3be")
    draw.polygon([(89, 145), (155, 145), (179, 287), (64, 287)], fill="#e8edf2")
    draw.line((102, 283, 96, 344), fill="#e2b47e", width=17)
    draw.line((143, 283, 151, 344), fill="#e2b47e", width=17)
    image.save(path)
    return image


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "ordinary.png"
        ordinary_image(self.source)
        self.service = DocumentService(workspace=self.root / "work", runtime=self.root / "runtime")

    def call(self, endpoint, **fields):
        s = self.service
        return s.dispatch("POST", endpoint, payload={"expected_document_id": s.doc.id, "expected_revision": s.doc.revision,
                           "expected_reference_revision": s.references.revision, **fields})[0]

    def load(self):
        return self.call("/reference/setup", action="load", path=str(self.source), settings={"width": 32, "height": 48, "colors": 12})

    def test_import_keeps_current_artwork_and_returns_actual_images(self):
        self.call("/command", ops=[{"op": "pixel", "x": 2, "y": 3, "color": 22}])
        before = self.service.doc.to_dict()
        result = self.load()
        self.assertEqual(self.service.doc.to_dict(), before)
        self.assertEqual(result["image_roles"], ["subject_reference", "automatic_draft_NOT_AI_redraw", "current_artwork"])
        self.assertEqual(len(result["images_png"]), 3)
        self.assertEqual(result["subject"]["name"], "ordinary.png")
        self.assertNotIn("png", result["subject"])
        self.assertFalse(result["current_project_has_same_subject"])

    def test_settings_change_draft_size_palette_and_keep_binary_transparency(self):
        self.load()
        first = make_draft(self.service.references.context)[0]
        self.call("/reference/setup", action="configure", settings={"width": 48, "height": 64, "colors": 8,
                  "saturation": 0.4, "contrast": 1.4, "crop": [60, 20, 130, 330]})
        image, palette = make_draft(self.service.references.context)
        self.assertEqual(image.size, (48, 64))
        self.assertLessEqual(len(palette), 9)
        self.assertTrue(all(c[3] in (0, 255) for c in pixels(image)))
        self.assertNotEqual(first.tobytes(), image.tobytes())

    def test_invalid_crop_setting_and_stale_reference_are_atomic(self):
        self.load()
        before = deepcopy(self.service.references.context)
        revision = self.service.references.revision
        for settings in ({"width": 0}, {"crop": [0, 0, 999, 999]}, {"saturation": float("nan")}, {"colors": True}, {"unknown": 1}):
            with self.assertRaises(PixelError):
                self.call("/reference/setup", action="configure", settings=settings)
            self.assertEqual(self.service.references.context, before)
            self.assertEqual(self.service.references.revision, revision)
        with self.assertRaises(PixelError) as error:
            self.call("/reference/setup", action="configure", settings={"colors": 4}, expected_reference_revision=revision-1)
        self.assertEqual(error.exception.code, "REFERENCE_CONFLICT")

    def test_begin_protects_unsaved_work_then_embeds_portable_references(self):
        self.load()
        self.call("/command", ops=[{"op": "pixel", "x": 1, "y": 1, "color": 1}])
        before = self.service.doc.to_dict()
        with self.assertRaises(PixelError) as error:
            self.call("/redraw/begin")
        self.assertEqual(error.exception.code, "UNSAVED_CHANGES")
        self.assertEqual(self.service.doc.to_dict(), before)
        self.call("/save", path="projects/old.pixloom")
        result = self.call("/redraw/begin", seed=True, mode="redraw")
        self.assertTrue(result["unsaved_changes"])
        self.assertEqual((self.service.doc.width, self.service.doc.height), (32, 48))
        self.assertTrue(self.service.doc.layers[0].locked)
        self.assertEqual([l.id for l in self.service.doc.layers[1:]], ["silhouette", "base-colors", "details"])
        self.assertTrue(self.service.doc.layers[0].cels[0].getbbox())
        self.call("/save", path="projects/redraw.pixloom")
        reopened = Document.open(self.root / "work/projects/redraw.pixloom")
        # The reference survives without a link to the source path or a sidecar file.
        self.source.unlink()
        self.assertEqual(reopened.reference["subject"]["name"], "ordinary.png")
        self.assertEqual(make_draft(reopened.reference)[0].size, (32, 48))
        self.assertEqual(Document.open(self.root / "work/projects/old.pixloom").layer().cels[0].getpixel((1, 1)), (24, 28, 46, 255))

    def test_blank_redraw_is_protected_even_before_any_painting(self):
        self.load()
        self.call("/redraw/begin", seed=False, mode="redraw")
        self.assertFalse(self.service.doc.composite().getbbox())
        self.assertTrue(self.service.dirty)
        with self.assertRaises(PixelError):
            self.call("/new", width=16, height=16)

    def test_proposed_redraw_is_read_only_and_uses_observed_tokens(self):
        self.load()
        self.call("/redraw/begin", mode="redraw")
        before = self.service.doc.to_dict()
        history = len(self.service.doc.undo_stack)
        result = self.call("/reference/preview", ops=[{"op": "rect", "layer": "silhouette", "x": 4, "y": 6, "width": 12, "height": 18, "color": 1}])
        self.assertTrue(result["dry_run"])
        self.assertIn("proposed_redraw", result["image_roles"])
        self.assertEqual(self.service.doc.to_dict(), before)
        self.assertEqual(len(self.service.doc.undo_stack), history)

    def test_default_conversion_preserves_exact_automatic_draft_and_is_editable(self):
        self.load()
        # A prepared brief/style is not a request to redesign the source.
        self.call("/reference/setup", action="configure", settings={"brief": "重绘为三头身", "style": "chibi"})
        expected, _ = make_draft(self.service.references.context)
        self.call("/redraw/begin")
        doc = self.service.doc
        self.assertEqual(doc.composite().tobytes(), expected.tobytes())
        self.assertEqual([layer.id for layer in doc.layers], ["sampling-draft"])
        self.assertFalse(doc.layer().locked)
        self.call("/command", ops=[{"op": "pixel", "x": 0, "y": 0, "color": 1}])
        self.call("/undo")
        self.assertEqual(doc.composite().tobytes(), expected.tobytes())
        self.call("/save", path="projects/automatic.pixloom")
        reopened = Document.open(self.root / "work/projects/automatic.pixloom")
        self.assertEqual(reopened.composite().tobytes(), expected.tobytes())

    def test_invalid_conversion_mode_preserves_existing_artwork(self):
        self.load()
        before = self.service.doc.to_dict()
        with self.assertRaises(PixelError):
            self.call("/redraw/begin", mode="invented")
        self.assertEqual(self.service.doc.to_dict(), before)

    def test_optional_style_can_be_replaced_cleared_undone_and_saved_without_repainting(self):
        self.assertIsNone(self.service.references.context["style"])
        self.load()
        draft = make_draft(self.service.references.context)[0].tobytes()
        style = self.root / "my-style.png"
        Image.new("RGB", (24, 24), "blue").save(style)
        imported = self.call("/reference/setup", action="load", role="style", path=str(style))
        self.assertEqual(imported["style_reference_source"], "imported")
        first_id = imported["style_reference"]["id"]
        self.assertEqual(make_draft(self.service.references.context)[0].tobytes(), draft)
        self.call("/redraw/begin")
        self.call("/save", path="projects/style.pixloom")
        self.assertEqual(self.service.references.summary(self.service.doc)["style_reference_source"], "project_embedded")
        Image.new("RGB", (24, 24), "green").save(style)
        replaced = self.call("/reference/setup", action="load", role="style", path=str(style))
        self.assertNotEqual(replaced["style_reference"]["id"], first_id)
        subject = deepcopy(self.service.references.context["subject"])
        cleared = self.call("/reference/setup", action="clear", role="style")
        self.assertIsNone(cleared["style_reference"])
        self.assertIsNone(cleared["style_reference_source"])
        self.assertEqual(self.service.references.context["subject"], subject)
        self.assertEqual(self.service.doc.composite().tobytes(), draft)
        self.call("/undo")
        self.assertEqual(self.service.doc.reference["style"]["id"], replaced["style_reference"]["id"])
        self.call("/reference/setup", action="clear", role="style")
        self.call("/save")
        reopened = Document.open(self.root / "work/projects/style.pixloom")
        self.assertIsNone(reopened.reference["style"])
        self.assertEqual(reopened.composite().tobytes(), draft)

    def test_different_subject_does_not_inherit_previous_style_or_retarget_old_project(self):
        self.load()
        style = self.root / "style.png"
        Image.new("RGB", (16, 16), "purple").save(style)
        self.call("/reference/setup", action="load", role="style", path=str(style))
        self.call("/redraw/begin")
        self.call("/save", path="projects/original.pixloom")
        original = deepcopy(self.service.doc.reference)
        self.call("/reference/setup", action="load", path=str(self.source))
        self.assertEqual(self.service.references.context["style"], original["style"])
        other = self.root / "other.png"
        Image.new("RGB", (20, 20), "red").save(other)
        self.call("/reference/setup", action="load", path=str(other))
        self.assertIsNone(self.service.references.context["style"])
        self.assertEqual(self.service.doc.reference, original)
        self.call("/reference/setup", action="use_project")
        self.assertEqual(self.service.references.context, original)
        self.assertEqual(Document.open(self.root / "work/projects/original.pixloom").reference, original)

    def test_bound_settings_are_undoable_and_other_subject_does_not_retarget_art(self):
        self.load()
        self.call("/redraw/begin")
        self.call("/save", path="projects/redraw.pixloom")
        original = deepcopy(self.service.doc.reference)
        self.call("/reference/setup", action="configure", settings={"colors": 6})
        self.assertEqual(self.service.doc.reference["settings"]["colors"], 6)
        self.assertTrue(self.service.dirty)
        self.call("/undo")
        self.assertEqual(self.service.doc.reference, original)
        self.assertEqual(self.service.references.context, original)
        other = self.root / "other.png"
        Image.new("RGB", (20, 20), "red").save(other)
        self.call("/reference/setup", action="load", path=str(other))
        self.assertEqual(self.service.doc.reference, original)
        self.call("/reference/setup", action="use_project")
        self.assertEqual(self.service.references.context, original)

    def test_bad_reference_context_rolls_back_and_exif_is_normalized(self):
        self.load()
        context = deepcopy(self.service.references.context)
        context["subject"]["png"] = "not a PNG"
        before = self.service.doc.to_dict()
        with self.assertRaises(PixelError):
            self.call("/command", ops=[{"op": "reference_context", "data": context}])
        self.assertEqual(self.service.doc.to_dict(), before)
        path = self.root / "rotated.jpg"
        image = Image.new("RGB", (30, 50), "red")
        exif = image.getexif()
        exif[274] = 6
        image.save(path, exif=exif)
        asset = load_asset(path)
        self.assertEqual(asset["size"], [50, 30])
        self.assertEqual(validate_context({"subject": asset})["subject"]["size"], [50, 30])
        self.assertFalse(decoded_asset(asset["png"]).getexif())

    def test_tiny_targets_and_transparent_source_keep_valid_palette(self):
        self.load()
        self.call("/reference/setup", action="configure", settings={"width": 1, "height": 1})
        self.assertEqual(make_draft(self.service.references.context)[0].size, (1, 1))
        transparent = self.root/"transparent.png"
        Image.new("RGBA", (16, 80)).save(transparent)
        self.call("/reference/setup", action="load", path=str(transparent))
        draft, palette = make_draft(self.service.references.context)
        self.assertFalse(draft.getbbox())
        self.assertEqual(palette, ["#00000000"])


if __name__ == "__main__":
    unittest.main()
