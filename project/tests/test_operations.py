import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pydantic import TypeAdapter, ValidationError

from pixel_workbench.guidance import STARTER, ANIMATION
from pixel_workbench.model import Document, PixelError, rgba, pixels
from pixel_workbench.operations import EditOperation, SPECS, validate


class NativeOperationsTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document(32, 32)

    def edit(self, *ops):
        self.doc.apply(list(ops))

    def test_every_documented_example_matches_its_machine_schema(self):
        for name, item in SPECS.items():
            with self.subTest(name=name):
                validate(item["example"])
                TypeAdapter(EditOperation).validate_python(item["example"])

    def test_unknown_fields_and_non_integer_coordinates_fail_before_any_edit(self):
        for op in [{"op": "pixel", "x": 1.5, "y": 2}, {"op": "rect", "x": 1, "y": 1, "width": 4, "height": 4, "colour": 7}]:
            before = self.doc.to_dict()
            with self.assertRaises(PixelError):
                self.edit(op)
            self.assertEqual(self.doc.to_dict(), before)
            with self.assertRaises(ValidationError):
                TypeAdapter(EditOperation).validate_python(op)

    def test_onboarding_recipe_is_executable_without_external_drawing_code(self):
        self.doc.apply(STARTER)
        self.doc.apply(ANIMATION)
        self.assertEqual(len(self.doc.durations), 3)
        self.assertEqual(self.doc.tags["idle"]["direction"], "pingpong")
        self.assertIsNotNone(self.doc.composite(0).getbbox())
        self.assertNotEqual(self.doc.composite(0).tobytes(), self.doc.composite(1).tobytes())

    def test_polygon_and_bezier_keep_integer_palette_pixels(self):
        self.edit({"op": "polygon", "points": [[4, 20], [12, 4], [20, 20]], "color": 18},
                  {"op": "bezier", "points": [[2, 2], [2, 16], [20, 16], [20, 2]], "color": 22})
        image = self.doc.composite()
        self.assertEqual(image.getpixel((2, 2)), rgba(self.doc.palette[22]))
        self.assertEqual(image.getpixel((20, 2)), rgba(self.doc.palette[22]))
        self.assertTrue({p for p in pixels(image)} <= {(0, 0, 0, 0), rgba(self.doc.palette[18]), rgba(self.doc.palette[22])})

    def test_region_move_preserves_neighbors_and_updates_named_region(self):
        self.edit({"op": "pixel", "x": 4, "y": 4, "color": 22},
                  {"op": "pixel", "x": 9, "y": 9, "color": 10},
                  {"op": "region_define", "name": "eye", "rect": [3, 3, 3, 3]},
                  {"op": "region_transform", "rect": "eye", "kind": "translate", "dx": 3, "dy": 0, "update_region": True})
        image = self.doc.composite()
        self.assertEqual(image.getpixel((4, 4))[3], 0)
        self.assertEqual(image.getpixel((7, 4)), rgba(self.doc.palette[22]))
        self.assertEqual(image.getpixel((9, 9)), rgba(self.doc.palette[10]))
        self.assertEqual(self.doc.regions["eye"], [6, 3, 3, 3])

    def test_selection_rotation_and_cross_frame_copy(self):
        self.edit({"op": "rect", "x": 2, "y": 2, "width": 3, "height": 1, "color": 22},
                  {"op": "selection_set", "rect": [2, 2, 3, 1]},
                  {"op": "region_transform", "kind": "rotate_cw"})
        self.assertEqual(self.doc.composite().getbbox(), (2, 2, 3, 5))
        self.assertEqual(self.doc.selection, [2, 2, 1, 3])
        self.edit({"op": "frame_add", "blank": True},
                  {"op": "region_copy", "source_frame": 0, "frame": 1, "rect": [2, 2, 1, 3], "x": 10, "y": 10})
        self.assertEqual(self.doc.composite(1).getbbox(), (10, 10, 11, 13))

    def test_locked_transform_rolls_back_entire_batch(self):
        self.edit({"op": "layer_set", "locked": True})
        before = self.doc.to_dict()
        with self.assertRaises(PixelError):
            self.edit({"op": "frame_add"}, {"op": "region_transform", "rect": [1, 1, 4, 4], "kind": "translate", "dx": 1})
        self.assertEqual(self.doc.to_dict(), before)

    def test_duplicate_layers_are_independent_and_merge_preserves_composite(self):
        self.edit({"op": "pixel", "x": 3, "y": 3, "color": 22},
                  {"op": "layer_duplicate", "id": "copy"},
                  {"op": "pixel", "x": 6, "y": 6, "color": 10},
                  {"op": "layer_set", "opacity": 128})
        self.assertEqual(self.doc.layers[0].cels[0].getpixel((6, 6))[3], 0)
        before = self.doc.composite().tobytes()
        self.edit({"op": "layer_merge_down"})
        self.assertEqual(len(self.doc.layers), 1)
        self.assertEqual(self.doc.composite().tobytes(), before)

    def test_tags_follow_frame_insertion_and_deletion(self):
        self.edit({"op": "frame_add"}, {"op": "tag_set", "name": "idle", "start": 0, "end": 1},
                  {"op": "frame_add", "after": 0}, {"op": "frame_delete", "frame": 1})
        self.assertEqual(self.doc.tags["idle"]["end"], 1)
        self.edit({"op": "frame_delete", "frame": 0})
        self.assertEqual(self.doc.tags["idle"], {"start": 0, "end": 0, "direction": "forward"})

    def test_duplicate_range_copies_pixels_and_timings_in_order(self):
        self.edit({"op": "pixel", "x": 2, "y": 2, "color": 22},
                  {"op": "frame_add", "blank": True, "duration_ms": 240},
                  {"op": "pixel", "x": 4, "y": 4, "color": 10},
                  {"op": "frame_duplicate_range", "start": 0, "end": 1, "after": 1})
        self.assertEqual(self.doc.durations, [160, 240, 160, 240])
        self.assertEqual(self.doc.composite(0).tobytes(), self.doc.composite(2).tobytes())
        self.assertEqual(self.doc.composite(1).tobytes(), self.doc.composite(3).tobytes())

    def test_frame_move_keeps_cels_and_timings_together(self):
        self.edit({"op": "pixel", "x": 2, "y": 2, "color": 22},
                  {"op": "frame_add", "blank": True, "duration_ms": 240},
                  {"op": "pixel", "x": 4, "y": 4, "color": 10})
        original = [self.doc.composite(i).tobytes() for i in range(2)]
        self.edit({"op": "frame_move", "frame": 1, "index": 0})
        self.assertEqual(self.doc.durations, [240, 160])
        self.assertEqual(self.doc.composite(0).tobytes(), original[1])
        self.assertEqual(self.doc.composite(1).tobytes(), original[0])

    def test_canvas_resize_keeps_anchor_and_round_trips_through_undo(self):
        self.edit({"op": "pixel", "x": 4, "y": 4, "color": 22},
                  {"op": "region_define", "name": "eye", "rect": [3, 3, 3, 3]})
        before = self.doc.fingerprint()
        self.edit({"op": "canvas_resize", "width": 40, "height": 40, "anchor": "center"})
        self.assertEqual(self.doc.composite().getpixel((8, 8)), rgba(self.doc.palette[22]))
        self.assertEqual(self.doc.regions["eye"], [7, 7, 3, 3])
        self.doc.undo()
        self.assertEqual(self.doc.fingerprint(), before)

    def test_sprite_scale_uses_nearest_neighbor_and_scales_regions(self):
        self.edit({"op": "pixel", "x": 2, "y": 2, "color": 22},
                  {"op": "region_define", "name": "point", "rect": [2, 2, 1, 1]},
                  {"op": "sprite_scale", "width": 64, "height": 64})
        self.assertEqual(self.doc.composite().getbbox(), (4, 4, 6, 6))
        self.assertEqual(self.doc.regions["point"], [4, 4, 2, 2])

    def test_resize_batch_reports_pixels_outside_previous_canvas(self):
        self.edit({"op": "canvas_resize", "width": 64, "height": 64},
                  {"op": "pixel", "x": 50, "y": 50, "color": 22})
        self.assertEqual(self.doc.last_change["visible_pixels_changed"], 1)

    def test_selection_constrains_painting(self):
        self.edit({"op": "selection_set", "rect": [3, 3, 2, 2]},
                  {"op": "rect", "x": 0, "y": 0, "width": 32, "height": 32, "color": 22})
        self.assertEqual(self.doc.composite().getbbox(), (3, 3, 5, 5))

    def test_view_selection_does_not_dirty_saved_artwork(self):
        before = self.doc.fingerprint()
        self.edit({"op": "selection_set", "rect": [1, 1, 3, 3]})
        self.assertEqual(before, self.doc.fingerprint())

    def test_palette_remap_preserves_transparency(self):
        self.edit({"op": "pixel", "x": 2, "y": 2, "color": 22},
                  {"op": "palette_set", "colors": ["#00000000", "#5fb7b8ff"], "remap": True})
        self.assertEqual(self.doc.composite().getpixel((2, 2)), (95, 183, 184, 255))
        self.assertEqual(self.doc.composite().getpixel((0, 0))[3], 0)

    def test_contact_sheet_and_tag_exports(self):
        self.doc.apply(STARTER)
        self.doc.apply(ANIMATION)
        self.assertEqual(self.doc.contact_sheet(tag="idle", scale=2).width, 192)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "idle.png"
            self.doc.export(path, "sheet", tag="idle")
            import json
            data = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(data["tags"][0]["name"], "idle")
            self.assertEqual(len(data["frames"]), 3)

    def test_png_always_exports_selected_frame_even_with_animation_tag(self):
        self.edit({"op": "pixel", "x": 1, "y": 1, "color": 22},
                  {"op": "frame_add", "blank": True},
                  {"op": "pixel", "x": 3, "y": 3, "color": 10},
                  {"op": "tag_set", "name": "first", "start": 0, "end": 0})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame.png"
            self.doc.export(path, "png", tag="first")
            with Image.open(path) as image:
                self.assertEqual(image.getpixel((3, 3)), rgba(self.doc.palette[10]))


if __name__ == "__main__":
    unittest.main()
