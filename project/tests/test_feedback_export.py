"""Feedback must block certified delivery without blocking the human's own export."""
from pathlib import Path
import tempfile
import unittest

from pixel_workbench.model import Document, PixelError
from pixel_workbench.quality import content_digest
from pixel_workbench.service import DocumentService


class FeedbackExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.service=DocumentService(Document(12,12),workspace=root/'w',runtime=root/'r')
        self.call('/command',ops=[{'op':'pixel','x':3,'y':4,'color':7}])

    def call(self,endpoint,**payload):
        d=self.service.doc
        return self.service.dispatch('POST',endpoint,payload={
            'expected_document_id':d.id,'expected_revision':d.revision,**payload})[0]

    def approve_fixture(self):
        evidence=self.call('/review/evidence')
        return self.call('/review/submit',review_id=evidence['review_id'],method='frames_and_timing',
            summary='Protocol test fixture only',
            visual_checks=[{'criterion_id':c['id'],'verdict':'pass','reason':'Explicit test fixture observation'} for c in evidence['criteria']],
            warning_resolutions=[{'warning_id':w['id'],'verdict':'acceptable','reason':'Intentional fixture'} for w in evidence['warnings']])

    def report(self,frames=None):
        return self.call('/feedback',action='create',shape={'kind':'ellipse','rect':[1,1,8,8]},
                         frames=frames or [0],description='Look at this edge',source='手动')['issue']

    def test_open_issue_blocks_old_pass_but_current_version_is_exportable(self):
        self.approve_fixture()
        digest=content_digest(self.service.doc)
        issue=self.report()
        self.assertEqual(digest,content_digest(self.service.doc))
        self.assertEqual(self.service.quality.summary(self.service.doc)['status'],'needs_changes')
        with self.assertRaises(PixelError) as caught:
            self.call('/export',path='exports/blocked.png')
        self.assertEqual(caught.exception.code,'FEEDBACK_PENDING')
        draft=self.call('/export',path='exports/current.png',draft=True)
        self.assertEqual(draft['delivery_status'],'unreviewed_draft')
        evidence=self.call('/review/evidence')
        self.assertFalse(next(c for c in evidence['technical_checks'] if c['id']=='feedback_resolved')['passed'])
        self.call('/feedback',action='dismiss',issue_id=issue['id'],text='User intentionally closed this issue',source='手动')
        self.assertEqual(self.call('/export',path='exports/final.png')['delivery_status'],'reviewed_final')

    def test_resolve_and_clarification_do_not_change_pixels_or_forge_a_pass(self):
        self.approve_fixture()
        issue=self.report()
        before=self.service.doc.composite().tobytes()
        self.call('/feedback',action='ask',issue_id=issue['id'],text='Which color should replace this pixel?')
        self.call('/feedback',action='reply',issue_id=issue['id'],text='Keep it; I was asking about the border.',source='手动')
        inspected=self.call('/feedback',action='inspect',issue_id=issue['id'])
        self.call('/feedback',action='resolve',issue_id=issue['id'],inspection_id=inspected['inspection_id'],
                  text='The human clarified that this color should remain.')
        self.assertEqual(before,self.service.doc.composite().tobytes())
        self.assertEqual(self.service.quality.summary(self.service.doc)['status'],'passed')
        self.call('/command',ops=[{'op':'pixel','x':4,'y':4,'color':1}])
        self.assertTrue(self.service.state()['feedback']['issues'][0]['resolution_stale'])
        with self.assertRaises(PixelError) as caught:
            self.call('/export',path='exports/stale.png')
        self.assertEqual(caught.exception.code,'FEEDBACK_PENDING')

    def test_unrelated_frame_export_is_not_blocked_by_other_frame_issue(self):
        self.call('/command',ops=[{'op':'frame_add'},{'op':'tag_set','name':'first','start':0,'end':0}])
        self.approve_fixture()
        self.report([1])
        self.call('/command',ops=[{'op':'select','frame':0}])
        self.assertEqual(self.call('/export',path='exports/first.png',tag='first')['delivery_status'],'reviewed_final')
        with self.assertRaises(PixelError):
            self.call('/export',path='exports/all.gif',kind='gif')
