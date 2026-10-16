"""Background-removal accuracy, non-destructive history, portable save and conflict protection."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from pixel_workbench.cutout import render, validate_settings
from pixel_workbench.model import Document, PixelError
from pixel_workbench.reference import decoded_asset, adjusted_subject, make_draft
from pixel_workbench.service import DocumentService


def specimen():
    image = Image.new("RGBA", (80, 96), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 6, 59, 45), fill="#9a603a")
    draw.ellipse((26, 16, 53, 41), fill="#f6cb9e")
    draw.polygon([(25,40),(54,40),(64,82),(15,82)], fill="#345cab")
    draw.rectangle((33,51,46,68), fill="white")  # Same color as BG, enclosed within subject.
    draw.rectangle((23,83,33,93), fill="#4c3350")
    draw.rectangle((47,83,57,93), fill="#4c3350")
    return image


class CutoutAlgorithmTests(unittest.TestCase):
    def test_connected_background_preserves_enclosed_same_color_foreground(self):
        image = specimen()
        output, mask, stats = render(image, {})
        self.assertEqual(output.getpixel((0,0)), (0,0,0,0))
        self.assertEqual(output.getpixel((38,58)), (255,255,255,255))
        for point in [(30,10),(40,28),(26,60),(28,88)]:
            self.assertEqual(output.getpixel(point), image.getpixel(point))
        self.assertEqual(mask.getpixel((38,58)),0)
        self.assertFalse(stats["semantic_segmentation"])
        global_output = render(image, {"connected":False})[0]
        self.assertEqual(global_output.getpixel((38,58))[3],0)

    def test_seeds_reach_enclosed_holes_and_protection_wins(self):
        image = specimen()
        settings = {"points":[[0,0],[38,58]]}
        self.assertEqual(render(image,settings)[0].getpixel((38,58))[3],0)
        settings["protect_regions"] = [[33,51,14,18]]
        self.assertEqual(render(image,settings)[0].getpixel((38,58))[3],255)
        settings["remove_polygons"] = [[[30,48],[50,48],[50,72],[30,72]]]
        self.assertEqual(render(image,settings)[0].getpixel((38,58))[3],255)

    def test_soft_edge_unmatting_and_existing_alpha_never_increase(self):
        image = Image.new("RGBA", (5,1), "white")
        image.putpixel((1,0),(255,240,240,255))
        image.putpixel((2,0),(240,0,0,180))
        image.putpixel((3,0),(50,10,10,0))
        output = render(image,{"background_color":"#ffffff","tolerance":10,"softness":10})[0]
        self.assertEqual(output.getpixel((1,0))[3],128)
        self.assertLess(output.getpixel((1,0))[1],240)
        self.assertEqual(output.getpixel((2,0)),image.getpixel((2,0)))
        self.assertEqual(output.getpixel((3,0))[3],0)
        self.assertEqual(render(image,{"tolerance":10})[0].getpixel((1,0)),image.getpixel((1,0)))

    def test_masks_can_remove_busy_background_without_model_and_keep_wins(self):
        image = Image.new("RGBA", (30,30), "#6e5c48")
        draw = ImageDraw.Draw(image)
        draw.rectangle((3,3,26,26),fill="#3a7c58")
        draw.rectangle((10,10,19,19),fill="#9d6847")
        settings={"tolerance":0,"keep_polygons":[[[10,10],[19,10],[19,19],[10,19]]],
                  "remove_polygons":[[[0,0],[29,0],[29,29],[0,29]]]}
        result=render(image,settings)[0]
        self.assertEqual(result.getpixel((5,5))[3],0)
        self.assertEqual(result.getpixel((15,15)),image.getpixel((15,15)))

    def test_strict_bounds_and_limits(self):
        bad = [{"tolerance":True},{"softness":float('nan')},{"connected":1},{"points":[[80,0]]},
               {"points":[[0,-1]]},{"protect_regions":[[79,0,2,1]]},{"keep_polygons":[[[1,1]]]},
               {"points":[[0,0]]*17},{"background_color":"#ffffff80"},{"invented":1}]
        for settings in bad:
            with self.subTest(settings=settings), self.assertRaises(PixelError):
                validate_settings(settings,(80,96))


class CutoutServiceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.source=self.root/'source.png'
        specimen().save(self.source)
        self.service=DocumentService(workspace=self.root/'work',runtime=self.root/'runtime')
        self.call('/reference/setup',action='load',path=str(self.source),include_images=False)

    def call(self,endpoint,**fields):
        service=self.service
        return service.dispatch('POST',endpoint,payload={"expected_document_id":service.doc.id,"expected_revision":service.doc.revision,
            "expected_reference_revision":service.references.revision,"include_images":False,**fields})[0]

    def preview(self,settings=None):
        return self.call('/reference/cutout/preview',settings=settings or {})

    def apply(self,settings=None):
        preview=self.preview(settings)
        return self.call('/reference/cutout',action='apply',preview_id=preview['preview_id'])

    def test_preview_is_read_only_apply_requires_exact_current_ticket(self):
        service=self.service
        before=(deepcopy(service.references.context),service.references.revision,service.doc.to_dict())
        result=self.call('/reference/cutout/preview',settings={},include_images=True)
        self.assertEqual(len(result['images_png']),3)
        self.assertEqual(before,(service.references.context,service.references.revision,service.doc.to_dict()))
        self.call('/reference/setup',action='configure',settings={"colors":8},include_images=False)
        with self.assertRaises(PixelError) as error:
            self.call('/reference/cutout',action='apply',preview_id=result['preview_id'])
        self.assertEqual(error.exception.code,'CUTOUT_PREVIEW_STALE')
        with self.assertRaises(PixelError):
            self.call('/reference/cutout',action='apply',preview_id='missing')

    def test_unbound_apply_undo_redo_and_reset_preserve_source_and_other_art(self):
        service=self.service
        self.call('/command',ops=[{"op":"pixel","x":1,"y":1,"color":7}])
        art=deepcopy(service.doc.to_dict())
        context=deepcopy(service.references.context)
        original_bytes=self.source.read_bytes()
        self.apply()
        self.assertEqual(adjusted_subject(service.references.context).getpixel((0,0))[3],0)
        self.assertEqual(decoded_asset(service.references.context['subject']['png']).getpixel((0,0))[3],255)
        self.assertEqual(service.doc.to_dict(),art)
        self.call('/reference/setup',action='configure',settings={"colors":8},include_images=False)
        self.call('/reference/cutout',action='undo')
        self.assertNotIn('cutout',service.references.context)
        self.assertEqual(service.references.context['settings']['colors'],8)
        self.call('/reference/cutout',action='redo')
        self.assertIn('cutout',service.references.context)
        self.call('/reference/cutout',action='reset')
        self.assertNotIn('cutout',service.references.context)
        self.assertEqual(service.references.context['subject'],context['subject'])
        self.assertEqual(self.source.read_bytes(),original_bytes)

    def test_bound_cutout_is_portable_and_canvas_undo_restores_reference(self):
        service=self.service
        self.call('/redraw/begin')
        canvas=service.doc.composite().tobytes()
        self.apply()
        self.assertEqual(service.doc.composite().tobytes(),canvas)
        self.assertIn('cutout',service.doc.reference)
        self.call('/undo')
        self.assertNotIn('cutout',service.references.context)
        self.call('/redo')
        self.assertIn('cutout',service.references.context)
        target=self.root/'portable.pixloom'
        self.call('/save',path=str(target))
        self.source.unlink()
        reopened=Document.open(target)
        self.assertEqual(adjusted_subject(reopened.reference).getpixel((0,0))[3],0)
        self.assertEqual(decoded_asset(reopened.reference['subject']['png']).getpixel((0,0))[3],255)
        self.assertEqual(reopened.composite().tobytes(),canvas)

    def test_repreview_does_not_accumulate_erasure_and_new_source_clears_cutout(self):
        self.apply({"tolerance":60,"connected":False})
        expected=render(specimen(),{"tolerance":0,"connected":False})[0]
        ticket=self.preview({"tolerance":0})
        actual=self.service.cutouts.tickets[ticket['preview_id']]['output']
        self.assertEqual(actual.tobytes(),expected.tobytes())
        second=self.root/'second.png'
        Image.new('RGBA',(20,20),'red').save(second)
        self.call('/reference/setup',action='load',path=str(second))
        self.assertNotIn('cutout',self.service.references.context)
        self.assertFalse(self.service.cutouts.status(self.service.doc.id,self.service.references.context)['can_undo'])

    def test_export_and_new_draft_use_cutout_and_protect_existing_files(self):
        self.apply()
        result=self.call('/reference/cutout',action='export',path='exports/cut.png')
        with Image.open(result['path']) as image:
            self.assertEqual(image.getpixel((0,0))[3],0)
            self.assertEqual(image.size,(80,96))
        with self.assertRaises(PixelError) as error:
            self.call('/reference/cutout',action='export',path='exports/cut.png')
        self.assertEqual(error.exception.code,'FILE_EXISTS')
        draft=make_draft(self.service.references.context)[0].tobytes()
        self.call('/redraw/begin')
        self.assertEqual(self.service.doc.composite().tobytes(),draft)
        self.assertIn('cutout',self.service.doc.reference)

    def test_wrong_doc_reference_revision_and_active_gesture_cannot_apply(self):
        ticket=self.preview()
        for fields in ({'expected_document_id':'wrong'},{'expected_reference_revision':-1},{'expected_revision':-1}):
            with self.subTest(fields=fields),self.assertRaises(PixelError):
                self.call('/reference/cutout',action='apply',preview_id=ticket['preview_id'],**fields)
        self.service.view['gesture_active']=True
        with self.assertRaises(PixelError):
            self.call('/reference/cutout',action='apply',preview_id=ticket['preview_id'])

    def test_opt_in_import_and_conversion_never_remove_background(self):
        self.assertNotIn('cutout',self.service.references.context)
        self.assertEqual(adjusted_subject(self.service.references.context).getpixel((0,0))[3],255)
        expected=make_draft(self.service.references.context)[0].tobytes()
        self.call('/redraw/begin')
        self.assertNotIn('cutout',self.service.doc.reference)
        self.assertEqual(self.service.doc.composite().tobytes(),expected)

    def test_partial_preview_adjustment_retains_protection_and_is_read_only(self):
        first=self.preview({"protect_regions":[[33,51,14,18]],"connected":False})
        second=self.call('/reference/cutout/preview',settings={"tolerance":36},base_preview_id=first['preview_id'])
        self.assertEqual(second['settings']['protect_regions'],[[33,51,14,18]])
        self.assertFalse(second['settings']['connected'])
        self.assertNotIn('cutout',self.service.references.context)
        self.call('/reference/cutout',action='apply',preview_id=second['preview_id'])
        third=self.preview({"softness":8})
        self.assertEqual(third['settings']['protect_regions'],[[33,51,14,18]])
        self.assertEqual(third['settings']['tolerance'],36)
        cleared=self.call('/reference/cutout/preview',settings={"protect_regions":[]},base_preview_id=third['preview_id'])
        self.assertEqual(cleared['settings']['protect_regions'],[])


if __name__=='__main__':
    unittest.main()
