import unittest

from PIL import Image

from pixel_workbench.model import Document, PixelError
from pixel_workbench.workflows import animation_plan, symmetric_ops


class WorkflowTests(unittest.TestCase):
    def sprite(self):
        doc = Document(16, 16)
        doc.apply([{"op": "frame_set", "duration_ms": 100},
                   {"op": "rect", "x": 5, "y": 5, "width": 3, "height": 3, "color": 7},
                   {"op": "layer_add", "name": "static"},
                   {"op": "pixel", "x": 0, "y": 0, "color": 3},
                   {"op": "select", "layer": doc.layers[0].id}])
        return doc

    def test_float_is_a_read_only_plan_then_one_undoable_transaction(self):
        doc = self.sprite()
        before, revision, history = doc.to_dict(), doc.revision, len(doc.undo_stack)
        ops = animation_plan(doc, "float", count=8, dy=2, duration=80, name="float")
        self.assertEqual(doc.to_dict(), before)
        doc.apply(ops, expected_revision=revision, expected_document_id=doc.id)
        self.assertEqual(len(doc.undo_stack), history+1)
        self.assertEqual(doc.durations, [100]+[80]*8)
        self.assertEqual(doc.tags["float"], {"start": 1, "end": 8, "direction": "forward"})
        self.assertEqual(doc.layers[0].cels[0].getbbox(), (5, 5, 8, 8))
        self.assertEqual(doc.layers[0].cels[3].getbbox(), (5, 7, 8, 10))
        self.assertEqual(doc.layers[0].cels[7].getbbox(), (5, 3, 8, 6))
        for cel in doc.layers[1].cels:
            self.assertEqual(cel.getpixel((0, 0)), (80, 89, 119, 255))
        self.assertTrue(doc.undo())
        restored = doc.to_dict()
        restored["revision"] = before["revision"]
        self.assertEqual(restored, before)

    def test_selection_loop_uses_original_region_for_every_frame(self):
        doc = self.sprite()
        doc.apply([{"op": "pixel", "x": 12, "y": 12, "color": 2},
                   {"op": "selection_set", "rect": [5, 5, 3, 3]}])
        doc.apply(animation_plan(doc, "travel", count=3, dx=4, dy=0, name="walk"))
        self.assertEqual(doc.selection, [5, 5, 3, 3])
        self.assertEqual(doc.tags["walk"]["direction"], "pingpong")
        for n, cel in enumerate(doc.layer().cels[1:]):
            self.assertEqual(cel.getpixel((12, 12)), (48, 54, 79, 255))
            self.assertEqual(cel.getpixel((5+2*n, 5)), (255, 255, 255, 255))
        self.assertEqual(doc.layer().cels[3].getpixel((5, 5)), (0, 0, 0, 0))

    def test_range_duration_and_duplication_preserve_frame_content(self):
        doc = self.sprite()
        doc.apply([{"op": "frame_add"}, {"op": "frame_add"}])
        before = [cel.tobytes() for cel in doc.layer().cels]
        doc.apply(animation_plan(doc, "duration", first=1, last=2, duration=160))
        self.assertEqual(doc.durations, [100, 160, 160])
        doc.apply(animation_plan(doc, "duplicate", first=0, last=1))
        self.assertEqual(doc.durations, [100, 160, 100, 160, 160])
        self.assertEqual(doc.layer().cels[2].tobytes(), before[0])
        self.assertEqual(doc.layer().cels[3].tobytes(), before[1])

    def test_invalid_and_locked_plan_never_changes_original(self):
        doc = self.sprite()
        doc.apply([{"op": "layer_set", "locked": True}])
        before = doc.to_dict()
        with self.assertRaises(PixelError):
            animation_plan(doc, "float")
        with self.assertRaises(PixelError):
            animation_plan(doc, "duration", first=2)
        self.assertEqual(doc.to_dict(), before)

    def test_capacity_failure_rolls_back_generated_frames(self):
        doc = Document(512, 512)
        before = doc.to_dict()
        with self.assertRaises(PixelError):
            doc.apply(animation_plan(doc, "float", count=32))
        self.assertEqual(doc.to_dict(), before)

    def test_four_way_pixels_and_box_mirror_exactly(self):
        for op in [{"op": "pixel", "x": 2, "y": 3, "color": 7},
                   {"op": "rect", "x": 1, "y": 2, "width": 3, "height": 4, "color": 7},
                   {"op": "stroke", "points": [[1, 2], [3, 5]], "size": 1, "color": 7},
                   {"op": "stroke", "points": [[1, 2], [3, 5]], "size": 2, "color": 7},
                   {"op": "bezier", "points": [[2, 2], [3, 8], [6, 4]], "size": 2, "color": 7}]:
            doc = Document(16, 16)
            doc.apply(symmetric_ops(op, 16, 16, "xy"))
            im = doc.composite()
            self.assertEqual(im.tobytes(), im.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())
            self.assertEqual(im.tobytes(), im.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes())

    def test_center_pixel_not_duplicated_and_fill_is_not_mirrored(self):
        self.assertEqual(len(symmetric_ops({"op": "pixel", "x": 4, "y": 4, "color": 1}, 9, 9, "xy")), 1)
        self.assertEqual(len(symmetric_ops({"op": "fill", "x": 0, "y": 0, "color": 1}, 16, 16, "xy")), 1)


if __name__ == "__main__":
    unittest.main()
