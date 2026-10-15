import base64
import json
import tempfile
import unittest
import zlib
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from pixel_workbench.model import Document, PixelError, rgba, pixels


class PixelModelTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document(16, 16)

    def edit(self, *ops):
        return self.doc.apply(list(ops))

    def test_shapes_use_size_not_inclusive_endpoint(self):
        self.edit({"op": "rect", "x": 2, "y": 3, "width": 4, "height": 2, "color": 22})
        image = self.doc.composite()
        self.assertEqual(image.getbbox(), (2, 3, 6, 5))
        self.assertEqual(sum(p[3] > 0 for p in pixels(image)), 8)

    def test_entire_batch_rolls_back_on_failure(self):
        before = self.doc.to_dict()
        with self.assertRaises(PixelError):
            self.edit({"op": "layer_add", "name": "eyes"},
                      {"op": "rect", "x": 1, "y": 1, "width": 3, "height": 3, "color": 22},
                      {"op": "pixel", "x": 99, "y": 99, "color": 22})
        self.assertEqual(self.doc.to_dict(), before)
        self.assertFalse(self.doc.undo_stack)

    def test_stale_revision_and_wrong_document_are_rejected(self):
        self.edit({"op": "pixel", "x": 0, "y": 0, "color": 7})
        for arguments in ({"expected_revision": 0}, {"expected_document_id": "other"}):
            with self.assertRaises(PixelError):
                self.doc.apply([{"op": "clear"}], **arguments)
        self.assertEqual(self.doc.revision, 1)
        self.assertEqual(self.doc.composite().getpixel((0, 0)), rgba(self.doc.palette[7]))

    def test_undo_redo_are_atomic_and_revision_is_monotonic(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 7}, {"op": "pixel", "x": 2, "y": 1, "color": 7})
        self.assertTrue(self.doc.undo())
        self.assertIsNone(self.doc.composite().getbbox())
        self.assertEqual(self.doc.revision, 2)
        self.assertTrue(self.doc.redo())
        self.assertEqual(self.doc.composite().getbbox(), (1, 1, 3, 2))
        self.assertEqual(self.doc.revision, 3)

    def test_edit_after_undo_discards_redo(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 7})
        self.doc.undo()
        self.edit({"op": "pixel", "x": 2, "y": 2, "color": 7})
        self.assertFalse(self.doc.redo())

    def test_browsing_does_not_evict_paint_history_or_clear_redo(self):
        self.edit({"op": "frame_add", "blank": True}, {"op": "select", "frame": 0})
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 7})
        self.doc.undo()
        for index in range(60):
            self.edit({"op": "select", "frame": index % 2},
                      {"op": "selection_set", "rect": [0, 0, 2, 2]})
        self.assertTrue(self.doc.redo())
        self.assertEqual(self.doc.composite(0).getpixel((1, 1))[3], 255)
        for index in range(60):
            self.edit({"op": "select", "frame": index % 2})
        self.assertTrue(self.doc.undo())
        self.assertEqual(self.doc.composite(0).getpixel((1, 1))[3], 0)

    def test_view_batch_is_atomic_and_never_serializes_pixel_buffers(self):
        self.edit({"op": "frame_add"})
        fingerprint = self.doc.fingerprint()
        image = self.doc.layer().cels[0]
        serial = self.doc.content_serial
        with patch.object(Document, "to_dict", side_effect=AssertionError("view serialized pixels")):
            self.edit({"op": "select", "frame": 0}, {"op": "selection_set", "rect": [1, 1, 2, 2]})
            self.assertEqual(self.doc.fingerprint(), fingerprint)
        self.assertIs(self.doc.layer().cels[0], image)
        self.assertEqual(self.doc.content_serial, serial)
        before = self.doc.to_dict()
        with self.assertRaises(PixelError):
            self.edit({"op": "select", "frame": 1}, {"op": "select", "layer": "missing"})
        self.assertEqual(self.doc.to_dict(), before)

    def test_transparent_erasing_is_independent_of_palette_order_and_membership(self):
        for colors in (["#ff0000ff", "#00000000"], ["#ff0000ff"]):
            with self.subTest(colors=colors):
                self.edit({"op": "palette_set", "colors": colors},
                          {"op": "pixel", "x": 1, "y": 1, "color": 0})
                self.edit({"op": "stroke", "points": [[1, 1]], "color": "#00000000"})
                self.assertEqual(self.doc.composite().getpixel((1, 1)), (0, 0, 0, 0))

    def test_layer_order_visibility_opacity_and_lock(self):
        bottom = self.doc.active_layer
        self.edit({"op": "rect", "x": 0, "y": 0, "width": 3, "height": 3, "color": 22},
                  {"op": "layer_add", "name": "top", "id": "top"},
                  {"op": "pixel", "x": 1, "y": 1, "color": 10})
        self.assertEqual(self.doc.composite().getpixel((1, 1)), rgba(self.doc.palette[10]))
        self.edit({"op": "layer_set", "visible": False})
        self.assertEqual(self.doc.composite().getpixel((1, 1)), rgba(self.doc.palette[22]))
        self.edit({"op": "layer_set", "visible": True, "opacity": 128, "locked": True})
        self.assertNotEqual(self.doc.composite().getpixel((1, 1)), rgba(self.doc.palette[10]))
        with self.assertRaises(PixelError):
            self.edit({"op": "clear"})
        with self.assertRaises(PixelError):
            self.edit({"op": "layer_delete"})
        self.edit({"op": "layer_move", "index": 0})
        self.assertEqual(self.doc.composite().getpixel((1, 1)), rgba(self.doc.palette[22]))
        self.assertEqual(self.doc.layers[1].id, bottom)

    def test_frame_copy_is_independent_and_all_layers_stay_aligned(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 7},
                  {"op": "layer_add", "name": "second"},
                  {"op": "frame_add", "duration_ms": 310},
                  {"op": "pixel", "x": 2, "y": 2, "color": 22})
        self.assertEqual(self.doc.durations, [160, 310])
        self.assertEqual(self.doc.composite(0).getpixel((2, 2))[3], 0)
        self.assertEqual(self.doc.composite(1).getpixel((2, 2))[3], 255)
        self.edit({"op": "frame_delete", "frame": 0})
        self.assertTrue(all(len(layer.cels) == 1 for layer in self.doc.layers))

    def test_palette_constraint_and_addition(self):
        with self.assertRaises(PixelError):
            self.edit({"op": "pixel", "x": 0, "y": 0, "color": "#123456"})
        self.edit({"op": "palette_add", "colors": ["#123456"]},
                  {"op": "pixel", "x": 0, "y": 0, "color": "#123456"})
        self.assertEqual(self.doc.composite().getpixel((0, 0)), (18, 52, 86, 255))

    def test_named_clip_preserves_surrounding_pixels(self):
        self.edit({"op": "region_define", "name": "eyes", "rect": [2, 2, 3, 2]},
                  {"op": "rect", "x": 0, "y": 0, "width": 16, "height": 16, "color": 22, "clip": "eyes"})
        self.assertEqual(self.doc.composite().getbbox(), (2, 2, 5, 4))
        self.edit({"op": "clear", "clip": [3, 2, 1, 1]})
        self.assertEqual(self.doc.composite().getpixel((3, 2))[3], 0)
        self.assertEqual(self.doc.composite().getpixel((2, 2))[3], 255)

    def test_clipped_flood_fill_stays_inside_region(self):
        self.edit({"op": "fill", "x": 4, "y": 4, "color": 22, "clip": [3, 3, 4, 4]})
        self.assertEqual(self.doc.composite().getbbox(), (3, 3, 7, 7))
        with self.assertRaises(PixelError):
            self.edit({"op": "fill", "x": 0, "y": 0, "color": 7, "clip": [3, 3, 4, 4]})

    def test_stamps_skip_dots_and_use_local_symbols(self):
        self.edit({"op": "stamp_define", "name": "eye", "rows": [".a.", "aaa"], "colors": {"a": 22}},
                  {"op": "stamp", "name": "eye", "x": 2, "y": 3, "scale": 2})
        image = self.doc.composite()
        self.assertEqual(image.getpixel((2, 3))[3], 0)
        self.assertEqual(image.getpixel((4, 3)), rgba(self.doc.palette[22]))
        self.assertEqual(sum(p[3] > 0 for p in pixels(image)), 16)

    def test_translation_does_not_wrap_and_outline_is_one_pixel(self):
        self.edit({"op": "pixel", "x": 0, "y": 0, "color": 22},
                  {"op": "translate", "dx": -1, "dy": 0})
        self.assertIsNone(self.doc.composite().getbbox())
        self.edit({"op": "pixel", "x": 8, "y": 8, "color": 22}, {"op": "outline", "color": 1})
        self.assertEqual(sum(p[3] > 0 for p in pixels(self.doc.composite())), 5)

    def test_change_summary_detects_rgb_and_alpha_changes(self):
        self.edit({"op": "pixel", "x": 4, "y": 5, "color": 22})
        self.assertEqual(self.doc.last_change["frames"][0]["rect"], [4, 5, 1, 1])
        self.edit({"op": "pixel", "x": 4, "y": 5, "color": 10})
        self.assertEqual(self.doc.last_change["visible_pixels_changed"], 1)
        self.edit({"op": "pixel", "x": 4, "y": 5, "color": 0})
        self.assertEqual(self.doc.last_change["visible_pixels_changed"], 1)

    def test_preview_rejects_oversized_output_before_resize(self):
        doc = Document(512, 512)
        with self.assertRaises(PixelError):
            doc.preview(scale=32)
        self.assertEqual(doc.preview(scale=8, rect=[0, 0, 8, 8]).size, (64, 64))

    def test_export_rejects_oversized_output(self):
        doc = Document(512, 512)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(PixelError):
                doc.export(Path(folder) / "big.png", scale=16)

    def test_inspection_returns_exact_pixel_grid(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 22})
        result = self.doc.inspect([0, 0, 3, 3])
        self.assertEqual(result["rows"][0], "...")
        symbol = result["rows"][1][1]
        self.assertEqual(result["legend"][symbol]["color"], self.doc.palette[22])

    def test_save_round_trip_preserves_cels_and_regions(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 22},
                  {"op": "region_define", "name": "head", "rect": [0, 0, 8, 8]},
                  {"op": "frame_add"}, {"op": "layer_add", "name": "second"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "作品.pixloom"
            self.doc.save(path)
            restored = Document.open(path)
            self.assertEqual(restored.to_dict(), self.doc.to_dict())
            self.assertFalse(path.with_name(path.name + ".writing").exists())

    def test_reject_corrupt_and_oversized_cel_data(self):
        data = self.doc.to_dict()
        data["layers"][0]["cels"][0] = base64.b64encode(zlib.compress(b"0" * 100_000)).decode()
        with self.assertRaises(PixelError):
            Document.from_dict(data)

    def test_png_sheet_and_gif_preserve_frame_order_and_transparency(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 22},
                  {"op": "frame_add", "blank": True, "duration_ms": 300},
                  {"op": "pixel", "x": 2, "y": 1, "color": 10})
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            self.doc.export(folder / "frame.png")
            self.doc.export(folder / "sheet.png", "sheet", columns=2)
            self.doc.export(folder / "anim.gif", "gif")
            with Image.open(folder / "frame.png") as image:
                self.assertEqual(image.getpixel((2, 1)), rgba(self.doc.palette[10]))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
            with Image.open(folder / "sheet.png") as image:
                self.assertEqual(image.size, (32, 16))
                self.assertEqual(image.getpixel((1, 1)), rgba(self.doc.palette[22]))
                self.assertEqual(image.getpixel((18, 1)), rgba(self.doc.palette[10]))
            metadata = json.loads((folder / "sheet.json").read_text())
            self.assertEqual(metadata["frames"][1]["duration_ms"], 300)
            with Image.open(folder / "anim.gif") as image:
                self.assertEqual(image.n_frames, 2)
                self.assertEqual(image.convert("RGBA").getpixel((1, 1)), rgba(self.doc.palette[22]))
                image.seek(1)
                self.assertEqual(image.convert("RGBA").getpixel((2, 1)), rgba(self.doc.palette[10]))
                self.assertEqual(image.convert("RGBA").getpixel((1, 1))[3], 0)


if __name__ == "__main__":
    unittest.main()
