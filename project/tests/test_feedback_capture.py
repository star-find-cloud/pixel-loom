import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image

from pixel_workbench.feedback_capture import capture_feedback,FORMAT,PNG_KEY,GUIDE_PATH
from pixel_workbench.image_clipboard import dib_bytes
from pixel_workbench.model import Document,PixelError


class FeedbackCaptureTests(unittest.TestCase):
    def make_doc(self):
        doc=Document(32,40,'角色待机')
        doc.apply([{'op':'rect','x':9,'y':7,'width':12,'height':22,'color':7},
                   {'op':'frame_add','copy_from':0},
                   {'op':'pixel','frame':1,'x':24,'y':24,'color':7}])
        return doc

    def test_full_canvas_png_is_identifiable_without_a_ticket_or_project_mutation(self):
        doc=self.make_doc()
        before=doc.to_dict()
        history=len(doc.undo_stack)
        capture=capture_feedback(doc,frame=1)
        decoded=Image.open(io.BytesIO(capture.png_bytes()))
        data=json.loads(decoded.info[PNG_KEY])
        self.assertEqual(data['format'],FORMAT)
        self.assertEqual(data['kind'],'problem_feedback')
        self.assertTrue(data['needs_attention'])
        self.assertEqual(data['frame'],1)
        self.assertEqual(data['frame_number'],2)
        self.assertEqual(data['canvas_size'],[32,40])
        self.assertEqual(data['rect'],[0,0,32,40])
        self.assertIsNone(data['annotation'])
        self.assertFalse(data['is_legacy_issue_id'])
        self.assertEqual(doc.to_dict(),before)
        self.assertEqual(len(doc.undo_stack),history)
        self.assertFalse(doc.feedback)

    def test_lasso_coordinates_stay_in_canvas_pixels_and_outline_is_only_in_capture(self):
        doc=self.make_doc()
        original=doc.composite(1).tobytes()
        shape={'kind':'lasso','points':[[22,21],[27,21],[27,27],[22,27]]}
        capture=capture_feedback(doc,1,shape)
        self.assertEqual(capture.metadata['rect'],[22,21,6,7])
        self.assertEqual(capture.metadata['annotation']['points'],shape['points'])
        self.assertEqual(doc.composite(1).tobytes(),original)
        self.assertTrue(any(capture.image.getpixel((x,y))==(255,184,135)
                            for y in range(150,400) for x in range(capture.image.width)))
        # The isolated source error pixel must remain a crisp 20×20 block in the
        # right-hand detail, separate from the full-canvas preview on the left.
        whites=sum(capture.image.getpixel((x,y))==(255,255,255)
                   for y in range(150,capture.image.height-76)
                   for x in range(capture.image.width//2,capture.image.width))
        self.assertEqual(whites,400)

    def test_rectangle_and_ellipse_marking_and_edge_canvas_are_bounded(self):
        doc=Document(512,512)
        for kind in ('rect','ellipse'):
            capture=capture_feedback(doc,0,{'kind':kind,'rect':[500,500,12,12]})
            self.assertLessEqual(capture.image.width,1000)
            self.assertLessEqual(capture.image.height,900)
            self.assertEqual(capture.metadata['rect'],[500,500,12,12])
        with self.assertRaises(PixelError):
            capture_feedback(doc,0,{'kind':'ellipse','rect':[500,500,13,13]})

    def test_saved_png_has_embedded_metadata_and_no_sidecar_form(self):
        with tempfile.TemporaryDirectory() as folder:
            capture=capture_feedback(self.make_doc())
            path=capture.save(folder)
            self.assertTrue(path.name.startswith('pixel-loom-issue-'))
            self.assertEqual(list(Path(folder).iterdir()),[path])
            with Image.open(path) as image:
                self.assertEqual(json.loads(image.info[PNG_KEY]),capture.metadata)
            self.assertIn('PROBLEM FEEDBACK',GUIDE_PATH.read_text(encoding='utf-8'))

    def test_clipboard_dib_is_a_standard_bgr_bottom_up_bitmap(self):
        image=Image.new('RGB',(2,2))
        image.putpixel((0,0),(255,0,0))
        image.putpixel((0,1),(0,255,0))
        dib=dib_bytes(image)
        header=struct.unpack('<IiiHH',dib[:16])
        self.assertEqual(header,(40,2,2,1,24))
        self.assertEqual(dib[40:43],b'\x00\xff\x00')
        self.assertEqual(dib[48:51],b'\x00\x00\xff')
