from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_workbench.model import Document, PixelError
from pixel_workbench.service import DocumentService


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.service=DocumentService(doc=Document(16,16),workspace=self.root/"workspace",runtime=self.root/"runtime")
        self.call("/command",ops=[{"op":"rect","x":4,"y":5,"width":5,"height":7,"color":18}])

    def call(self,endpoint,**fields):
        doc=self.service.doc
        return self.service.dispatch("POST",endpoint,payload={"expected_document_id":doc.id,"expected_revision":doc.revision,**fields})[0]

    def review(self,**fields):
        return self.call("/review/evidence",**fields)

    def submit(self,evidence,verdict="pass",**fields):
        return self.call("/review/submit",review_id=evidence["review_id"],method="frames_and_timing",summary="Test review fixture",
            visual_checks=[{"criterion_id":c["id"],"verdict":verdict,"reason":"Explicit test fixture conclusion"} for c in evidence["criteria"]],
            warning_resolutions=[{"warning_id":w["id"],"verdict":"acceptable","reason":"Intentional protocol fixture warning"} for w in evidence["warnings"]],**fields)

    def test_numeric_pass_still_requires_visual_review_and_draft_is_labeled(self):
        before=self.service.doc.to_dict()
        evidence=self.review()
        self.assertTrue(evidence["technical_passed"])
        self.assertEqual(evidence["review_status"],"visual_review_required")
        self.assertEqual(self.service.doc.to_dict(),before)
        with self.assertRaises(PixelError) as error:
            self.call("/export",path="exports/final.png")
        self.assertEqual(error.exception.code,"REVIEW_REQUIRED")
        draft=self.call("/export",path="exports/draft.png",draft=True)
        self.assertEqual(draft["delivery_status"],"unreviewed_draft")
        self.assertTrue(Path(draft["path"]).exists())

    def test_real_evidence_contains_timing_seam_and_playable_artifact(self):
        self.call("/command",ops=[{"op":"frame_add"},{"op":"translate","dx":1,"dy":0}])
        evidence=self.review()
        self.assertEqual(evidence["image_roles"],["frame_contact","two_loop_timing","loop_seam"])
        self.assertEqual(len(evidence["images_png"]),3)
        self.assertTrue(Path(evidence["playback_asset"]["path"]).is_file())
        with Image.open(evidence["playback_asset"]["path"]) as gif:
            self.assertEqual(gif.n_frames,2)

    def test_passing_review_unlocks_final_and_round_trips_with_project(self):
        evidence=self.review()
        result=self.submit(evidence)
        self.assertEqual(result["review"]["status"],"passed")
        self.assertEqual(self.service.doc.revision,result["revision"])
        self.call("/save",path="projects/reviewed.pixloom")
        exported=self.call("/export",path="exports/final.png")
        self.assertEqual(exported["delivery_status"],"reviewed_final")
        self.assertEqual(exported["review_id"],evidence["review_id"])
        reopened=Document.open(self.root/"workspace/projects/reviewed.pixloom")
        fresh=DocumentService(doc=reopened,workspace=self.root/"second",runtime=self.root/"second-runtime")
        self.assertEqual(fresh.quality.summary(reopened)["status"],"passed")
        self.assertNotIn(str(self.root),str(reopened.quality_reviews))

    def test_artwork_edit_makes_certificate_stale_and_old_evidence_unusable(self):
        evidence=self.review()
        self.submit(evidence)
        self.call("/command",ops=[{"op":"pixel","x":1,"y":1,"color":7}])
        self.assertEqual(self.service.quality.summary(self.service.doc)["status"],"stale")
        with self.assertRaises(PixelError) as error:
            self.submit(evidence)
        self.assertEqual(error.exception.code,"REVIEW_STALE")
        with self.assertRaises(PixelError):
            self.call("/export",path="exports/stale.png")

    def test_visual_fail_or_uncertainty_cannot_be_delivered_as_pass(self):
        for verdict,status in (("fail","needs_changes"),("uncertain","uncertain")):
            evidence=self.review()
            result=self.submit(evidence,verdict)
            self.assertEqual(result["review"]["status"],status)
            self.assertEqual(result["review"]["next_action"],"edit_then_recheck")
            with self.assertRaises(PixelError):
                self.call("/export",path=f"exports/{verdict}.png")

    def test_technical_failure_overrides_visual_pass_and_fixed_parts_are_checked(self):
        self.call("/command",ops=[{"op":"region_define","name":"feet","rect":[4,10,5,2]},
                                 {"op":"frame_add"},{"op":"translate","dx":1,"dy":0}])
        self.call("/review/settings",settings={"expected_frames":8,"fixed_regions":["feet"]})
        evidence=self.review()
        failed={c["id"] for c in evidence["technical_checks"] if not c["passed"]}
        self.assertEqual(failed,{"expected_frames","fixed_feet"})
        self.assertEqual(self.submit(evidence)["review"]["status"],"needs_changes")

    def test_rigid_cutout_and_uneven_timing_get_targeted_warnings(self):
        self.call("/command",ops=[{"op":"frame_set","frame":0,"duration_ms":800},
                                 {"op":"frame_add","duration_ms":60},{"op":"translate","dx":1,"dy":0}])
        evidence=self.review()
        ids={w["id"] for w in evidence["warnings"]}
        self.assertIn("rigid_translation",ids)
        self.assertIn("uneven_timing",ids)
        self.assertTrue(evidence["technical_passed"])

    def test_every_page_and_every_criterion_must_be_reviewed(self):
        self.call("/command",ops=[{"op":"frame_add"} for _ in range(32)])
        evidence=self.review()
        self.assertEqual(evidence["pages"],2)
        with self.assertRaises(PixelError) as error:
            self.submit(evidence)
        self.assertEqual(error.exception.code,"REVIEW_INCOMPLETE")
        self.review(review_id=evidence["review_id"],page=1)
        with self.assertRaises(PixelError):
            self.call("/review/submit",review_id=evidence["review_id"],method="frames_and_timing",summary="Missing checks",visual_checks=[])
        self.assertEqual(self.submit(evidence)["review"]["status"],"passed")

    def test_layer_scope_cannot_certify_other_outputs(self):
        self.call("/command",ops=[{"op":"layer_add","id":"other","name":"other"},{"op":"pixel","x":0,"y":0,"color":7}])
        evidence=self.review(layers=["other"])
        self.submit(evidence)
        self.call("/export",path="exports/other.png",layers=["other"])
        with self.assertRaises(PixelError):
            self.call("/export",path="exports/all.png")

    def test_requirements_invalidate_evidence_but_selection_does_not(self):
        evidence=self.review()
        self.call("/command",ops=[{"op":"selection_set","rect":[0,0,2,2]}])
        self.assertEqual(self.submit(evidence)["review"]["status"],"passed")
        second=self.review()
        self.call("/review/settings",settings={"brief":"New task requirement"})
        with self.assertRaises(PixelError) as error:
            self.submit(second)
        self.assertEqual(error.exception.code,"REVIEW_STALE")

    def test_pingpong_review_uses_actual_playback_timing(self):
        self.call("/command",ops=[{"op":"frame_add","duration_ms":100},{"op":"translate","dx":1,"dy":0},
                                 {"op":"frame_add","duration_ms":200},{"op":"translate","dx":1,"dy":0},
                                 {"op":"tag_set","name":"idle","start":0,"end":2,"direction":"pingpong"}])
        evidence=self.review(tag="idle")
        self.assertEqual(evidence["metrics"]["playback_frames"],[0,1,2,1])
        self.assertEqual(evidence["metrics"]["duration_ms"],560)
        self.assertEqual(evidence["playback_asset"]["duration_ms"],560)

    def test_rgba_preview_uses_lossless_apng_and_review_is_not_an_art_undo_step(self):
        self.call("/command",ops=[{"op":"palette_add","colors":["#ff000080"]},
                                 {"op":"pixel","x":0,"y":0,"color":"#ff000080"}])
        evidence=self.review()
        self.assertTrue(evidence["playback_asset"]["path"].endswith(".png"))
        history=len(self.service.doc.undo_stack)
        self.submit(evidence)
        self.assertEqual(len(self.service.doc.undo_stack),history)
        self.call("/undo")
        self.assertNotEqual(self.service.quality.summary(self.service.doc)["status"],"passed")

    def test_repeated_failures_stop_with_remaining_issues_not_a_fake_pass(self):
        self.call("/review/settings",settings={"max_rounds":2})
        first=self.submit(self.review(),"fail")
        second=self.submit(self.review(),"fail")
        self.assertFalse(first["review"]["round_budget_reached"])
        self.assertTrue(second["review"]["round_budget_reached"])
        self.assertEqual(second["review"]["next_action"],"report_remaining_issues")
        self.assertEqual(second["review"]["status"],"needs_changes")

    def test_named_details_are_returned_as_actual_zoomed_evidence(self):
        self.call("/command",ops=[{"op":"region_define","name":"face","rect":[4,5,5,5]}])
        self.call("/review/settings",settings={"detail_regions":["face"]})
        evidence=self.review()
        self.assertEqual(evidence["image_roles"],["frame_contact","detail:face"])


if __name__=="__main__":
    unittest.main()
