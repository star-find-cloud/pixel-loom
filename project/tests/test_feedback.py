import base64
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_workbench.feedback import summary, validate_shape
from pixel_workbench.model import Document, PixelError, pixels
from pixel_workbench.service import DocumentService


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = DocumentService(Document(16, 16), self.root/"work", self.root/"runtime")
        self.call("/command", ops=[{"op": "rect", "x": 4, "y": 5, "width": 5, "height": 7, "color": 18}])

    def call(self, endpoint="/feedback", **fields):
        doc = self.service.doc
        return self.service.dispatch("POST", endpoint, payload={"expected_document_id": doc.id,
            "expected_revision": doc.revision, **fields})[0]

    def create(self, **fields):
        return self.call(action="create", shape={"kind": "lasso", "points": [[4, 5], [9, 5], [8, 12], [4, 12]]},
                         frames=[0], description="衣摆右边有残留像素，请逐帧检查。", source="手动", **fields)["issue"]

    def inspect(self, issue, **fields):
        return self.call(action="inspect", issue_id=issue["id"], **fields)

    def test_shapes_are_exact_bounded_pixel_geometry(self):
        valid = validate_shape({"kind": "lasso", "points": [[0, 0], [15, 0], [15, 15], [0, 15]]}, 16, 16)
        self.assertEqual(valid["rect"], [0, 0, 16, 16])
        for shape in ({"kind": "lasso", "points": [[1, 1], [2, 2], [3, 3]]},
                      {"kind": "lasso", "points": [[0, 0]]*513},
                      {"kind": "lasso", "points": [[-1, 0], [2, 0], [1, 4]]},
                      {"kind": "rect", "rect": [0, 0, 17, 1]},
                      {"kind": "ellipse", "rect": [0, 0, 0, 1]},
                      {"kind": "rect", "rect": [True, 0, 1, 1]},
                      {"kind": "unknown", "rect": [0, 0, 2, 2]}):
            with self.subTest(shape=shape), self.assertRaises(PixelError):
                validate_shape(shape, 16, 16)

    def test_frame_ranges_and_observed_tokens_are_required(self):
        before = self.service.doc.to_dict()
        for frames in ([], [1], [-1], [True], list(range(65))):
            with self.subTest(frames=frames), self.assertRaises(PixelError):
                self.call(action="create", shape={"kind": "rect", "rect": [0, 0, 1, 1]}, frames=frames, description="test")
        self.assertEqual(before, self.service.doc.to_dict())
        with self.assertRaises(PixelError) as error:
            self.service.feedback_action({"action": "create", "expected_document_id": self.service.doc.id,
                "expected_revision": self.service.doc.revision-1})
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        with self.assertRaises(PixelError) as error:
            self.call(action="create", expected_document_id="wrong")
        self.assertEqual(error.exception.code, "DOCUMENT_CONFLICT")

    def test_old_projects_and_saved_portable_original_images(self):
        old = self.service.doc.to_dict()
        self.assertNotIn("feedback", old)
        self.assertEqual(Document.from_dict(old).feedback, [])
        issue = self.create()
        self.call("/save", path="projects/feedback.pixloom")
        restored = Document.open(self.root/"work/projects/feedback.pixloom")
        self.assertEqual(restored.feedback[0]["id"], issue["id"])
        self.assertEqual(restored.feedback[0]["source"], "手动")
        self.assertNotIn(str(self.root), str(restored.feedback))
        self.assertTrue(restored.feedback[0]["original"]["frames"][0]["crop_png"])

    def test_metadata_never_paints_and_undo_preserves_new_question(self):
        art = self.service.doc.composite().tobytes()
        issue = self.create()
        self.call(action="ask", issue_id=issue["id"], text="你指的是哪一侧的白色小点？")
        self.assertEqual(self.service.doc.composite().tobytes(), art)
        self.call("/undo")
        self.assertEqual(len(self.service.doc.feedback), 1)
        self.assertEqual(self.service.doc.feedback[0]["questions"][0]["question"], "你指的是哪一侧的白色小点？")
        self.call("/redo")
        self.assertEqual(len(self.service.doc.feedback), 1)
        self.assertEqual(summary(self.service.doc)["needs_clarification_count"], 1)

    def test_clarification_waits_for_real_reply_and_resolution_requires_evidence(self):
        issue = self.create()
        evidence = self.inspect(issue)
        asked = self.call(action="ask", issue_id=issue["id"], text="是独立的亮点，还是裙边的凹口？")["issue"]
        self.assertEqual(asked["status"], "needs_clarification")
        for action in ("start", "resolve"):
            with self.assertRaises(PixelError) as error:
                self.call(action=action, issue_id=issue["id"], text="done", inspection_id=evidence["inspection_id"])
            self.assertEqual(error.exception.code, "FEEDBACK_NEEDS_REPLY")
        with self.assertRaises(PixelError):
            self.call(action="reply", issue_id=issue["id"], text="AI guessed answer")
        with self.assertRaises(PixelError):
            self.call(action="reply", issue_id=issue["id"], text="changed answer", direct_user_quote="独立亮点")
        answered = self.call(action="reply", issue_id=issue["id"], direct_user_quote="独立亮点")["issue"]
        self.assertEqual(answered["status"], "open")
        self.assertEqual(answered["questions"][0]["answer"], "独立亮点")
        with self.assertRaises(PixelError):
            self.call(action="resolve", issue_id=issue["id"], inspection_id=evidence["inspection_id"], text="fixed")
        self.call(action="start", issue_id=issue["id"])
        fresh = self.inspect(issue)
        result = self.call(action="resolve", issue_id=issue["id"], inspection_id=fresh["inspection_id"], text="检查指定帧，已确认标注内没有独立亮点。")
        self.assertEqual(result["issue"]["status"], "resolved")
        self.assertEqual(result["feedback"]["pending_count"], 0)

    def test_current_pixels_invalidate_inspection_and_existing_resolution(self):
        issue = self.create()
        evidence = self.inspect(issue)
        self.call("/command", ops=[{"op": "pixel", "x": 7, "y": 7, "color": 7}])
        with self.assertRaises(PixelError) as error:
            self.call(action="resolve", issue_id=issue["id"], inspection_id=evidence["inspection_id"], text="fixed")
        self.assertEqual(error.exception.code, "FEEDBACK_INSPECTION_STALE")
        current = self.inspect(issue)
        self.assertEqual(current["differences"][0]["changed_pixels_in_shape"], 1)
        self.call(action="resolve", issue_id=issue["id"], inspection_id=current["inspection_id"], text="Test fixture: inspected repaired pixel")
        self.call("/command", ops=[{"op": "pixel", "x": 0, "y": 0, "color": 7}])
        state = summary(self.service.doc)
        self.assertEqual(state["pending_count"], 1)
        self.assertTrue(state["issues"][0]["resolution_stale"])

    def test_evidence_contains_actual_original_current_and_mask_images(self):
        issue = self.create()
        evidence = self.inspect(issue)
        self.assertEqual(len(evidence["images_png"]), 5)
        self.assertIn("frame:0:current_crop", evidence["image_roles"])
        self.assertIn("frame:0:current_annotated_context", evidence["image_roles"])
        images = [Image.open(io.BytesIO(base64.b64decode(png))).convert("RGBA") for png in evidence["images_png"]]
        self.assertGreater(len(images[0].getcolors()), 1)  # lasso, not an all-white bounding rect
        self.assertTrue(any((108, 188, 139, 255) in pixels(image) for image in images))
        self.assertEqual(self.service.doc.feedback[0]["original"]["revision"], 1)

    def test_all_annotated_frames_must_be_inspected_and_deleted_scope_cannot_resolve(self):
        self.call("/command", ops=[{"op": "frame_add", "copy_from": 0} for _ in range(8)])
        issue = self.call(action="create", shape={"kind": "ellipse", "rect": [3, 3, 5, 6]}, frames=list(range(9)), description="检查所有帧")["issue"]
        first = self.inspect(issue)
        self.assertEqual(first["page_count"], 2)
        with self.assertRaises(PixelError) as error:
            self.call(action="resolve", issue_id=issue["id"], inspection_id=first["inspection_id"], text="fixture")
        self.assertEqual(error.exception.code, "FEEDBACK_PAGES_REQUIRED")
        self.inspect(issue, inspection_id=first["inspection_id"], page=1)
        self.call(action="resolve", issue_id=issue["id"], inspection_id=first["inspection_id"], text="Protocol fixture inspected nine images")
        self.call("/command", ops=[{"op": "frame_delete", "frame": 8}])
        missing = self.inspect(issue)
        self.assertEqual(missing["missing_frames"], [8])
        self.inspect(issue, inspection_id=missing["inspection_id"], page=1)
        with self.assertRaises(PixelError) as error:
            self.call(action="resolve", issue_id=issue["id"], inspection_id=missing["inspection_id"], text="fixture")
        self.assertEqual(error.exception.code, "FEEDBACK_SCOPE_CHANGED")

    def test_corrupt_portable_snapshot_and_duplicate_ids_are_rejected(self):
        self.create()
        data = self.service.doc.to_dict()
        corrupted = deepcopy(data)
        corrupted["feedback"][0]["original"]["frames"][0]["crop_png"] = "not a PNG"
        with self.assertRaises(PixelError):
            Document.from_dict(corrupted)
        data["feedback"].append(deepcopy(data["feedback"][0]))
        with self.assertRaises(PixelError):
            Document.from_dict(data)

    def test_budget_and_corrupt_frame_types_fail_without_losing_existing_issues(self):
        for _ in range(32):
            self.create()
        before = self.service.doc.to_dict()
        with self.assertRaises(PixelError):
            self.create()
        self.assertEqual(before, self.service.doc.to_dict())
        corrupted = deepcopy(before)
        corrupted["feedback"][0]["frames"] = [[0]]
        with self.assertRaises(PixelError):
            Document.from_dict(corrupted)
        corrupted = deepcopy(before)
        corrupted["feedback"][0]["status"] = "resolved"
        corrupted["feedback"][0]["resolution"] = None
        with self.assertRaises(PixelError):
            Document.from_dict(corrupted)

    def test_user_can_dismiss_obsolete_scope_without_fabricating_ai_repair(self):
        issue = self.create()
        self.call(action="ask", issue_id=issue["id"], text="Fixture unanswered question")
        with self.assertRaises(PixelError):
            self.call(action="dismiss", issue_id=issue["id"], text="AI wants to stop")
        with self.assertRaises(PixelError):
            self.call(action="dismiss", issue_id=issue["id"], text="made-up cause", direct_user_quote="close it")
        closed = self.call(action="dismiss", issue_id=issue["id"], text="已改画布，我会重新圈选。", source="手动")
        self.assertEqual(closed["issue"]["status"], "dismissed")
        self.assertIsNone(closed["issue"]["resolution"])
        self.assertEqual(closed["issue"]["dismissal"]["reason"], "已改画布，我会重新圈选。")
        self.assertEqual(closed["feedback"]["pending_count"], 0)
        self.assertEqual(closed["feedback"]["resolved_count"], 0)
        self.assertEqual(closed["feedback"]["dismissed_count"], 1)
        self.assertEqual(closed["feedback"]["needs_clarification_count"], 0)
        self.call("/command", ops=[{"op": "pixel", "x": 0, "y": 0, "color": 7}])
        self.assertEqual(summary(self.service.doc)["pending_count"], 0)
        restored = Document.from_dict(self.service.doc.to_dict())
        self.assertEqual(restored.feedback[0]["questions"][0]["answer"], None)
        second = self.create()
        quoted = self.call(action="dismiss", issue_id=second["id"], direct_user_quote="This issue is obsolete, please close it.")
        self.assertEqual(quoted["issue"]["dismissal"]["user_quote"], "This issue is obsolete, please close it.")


if __name__ == "__main__":
    unittest.main()
