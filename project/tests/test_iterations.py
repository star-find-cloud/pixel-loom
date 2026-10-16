"""Automatic editable iterations survive retries, restart and non-destructive selection."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from pixel_workbench.model import Document, PixelError
from pixel_workbench.service import DocumentService


class IterationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = DocumentService(Document(16,16,'Artwork'),workspace=self.root/'work',runtime=self.root/'data')

    def call(self,endpoint,**fields):
        return self.service.dispatch('POST',endpoint,payload={'expected_document_id':self.service.doc.id,
            'expected_revision':self.service.doc.revision,**fields})[0]

    def edit(self,color=7,**fields):
        return self.call('/command',ops=[{'op':'pixel','x':2,'y':3,'color':color}],label='修改轮廓',**fields)

    def versions(self):
        entry = self.service.projects.by_path(self.service.path)
        return self.call('/projects',action='versions',project_id=entry['id'])['versions']

    def test_unsaved_batches_attach_to_first_saved_project_and_survive_restart(self):
        self.edit()
        self.edit(8)
        self.assertTrue(self.service.dirty)
        self.call('/save',path='projects/art.pixloom')
        versions = self.versions()
        self.assertEqual(len(versions),3)
        self.assertEqual(versions[0]['label'],'修改轮廓')
        self.assertEqual(versions[0]['source'],'AI')
        self.assertEqual(Document.open(versions[-1]['path']).composite().getpixel((2,3))[3],0)
        restarted = DocumentService(workspace=self.service.workspace,runtime=self.service.runtime)
        entry = restarted.projects.entries[0]
        self.assertEqual(restarted.projects.versions(entry['id']),versions)

    def test_select_retry_validation_and_repeated_save_do_not_create_iterations(self):
        self.call('/save',path='projects/art.pixloom')
        state = self.service.state()
        payload = {'expected_document_id':state['document_id'],'expected_revision':state['revision'],
                   'ops':[{'op':'pixel','x':2,'y':3,'color':7}],'request_id':'unique-batch'}
        self.service.dispatch('POST','/command',payload=payload)
        count = len(self.versions())
        self.service.dispatch('POST','/command',payload=payload)
        self.call('/command',ops=[{'op':'select','frame':0}])
        self.call('/validate',ops=[{'op':'pixel','x':3,'y':3,'color':8}])
        self.call('/save')
        self.call('/save')
        self.assertEqual(len(self.versions()),count)

    def test_choose_old_version_preserves_project_pixels_history_and_undo(self):
        self.call('/save',path='projects/art.pixloom')
        self.edit()
        self.edit(8)
        old = self.versions()[-2]
        entry = self.service.projects.by_path(self.service.path)
        before = self.service.doc.composite().tobytes()
        tokens = self.service.state()
        count = len(self.versions())
        chosen = self.call('/projects',action='use_version',project_id=entry['id'],version_id=old['id'])
        self.assertEqual(chosen['document_id'],tokens['document_id'])
        self.assertEqual(len(self.service.projects.entries),1)
        self.assertGreater(chosen['revision'],tokens['revision'])
        self.assertEqual(self.service.doc.composite().tobytes(),Document.open(old['path']).composite().tobytes())
        self.assertGreater(len(self.versions()),count)
        self.call('/undo')
        self.assertEqual(self.service.doc.composite().tobytes(),before)
        with self.assertRaises(PixelError):
            self.service.projects_action({'action':'use_version','project_id':entry['id'],'version_id':old['id'],
                'expected_document_id':tokens['document_id'],'expected_revision':tokens['revision']})

    def test_version_comparison_is_paged_read_only_and_includes_unsaved_current(self):
        self.call('/save',path='projects/art.pixloom')
        self.call('/command',ops=[{'op':'frame_add'} for _ in range(10)])
        self.edit()
        before = self.service.doc.to_dict()
        entry = self.service.projects.by_path(self.service.path)
        old = self.versions()[-1]
        reply = self.call('/projects',action='version_preview',project_id=entry['id'],version_id=old['id'],page=1)
        self.assertEqual(reply['pages'],2)
        self.assertEqual(reply['items'][1]['frames'],[8,9,10])
        self.assertEqual(len(reply['images_png']),2)
        self.assertEqual(self.service.doc.to_dict(),before)
        self.assertTrue(self.service.dirty)
        with self.assertRaises(PixelError):
            self.call('/projects',action='version_preview',project_id=entry['id'],version_id='../../escape')

    def test_removed_generator_and_legacy_project_roundtrip(self):
        doc = self.service.doc
        doc.apply([{'op':'pixel','x':1,'y':1,'color':7},{'op':'frame_add','duration_ms':150}])
        data = doc.to_dict()
        data['effect_recipe'] = {'format':'pixel-loom/effect/v1','settings':{'preset':'magic','frames':12}}
        reopened = Document.from_dict(data)
        self.assertEqual(reopened.to_dict(),data)
        self.assertNotIn('effect_recipe',reopened.state())
        reopened.apply([{'op':'pixel','x':1,'y':1,'color':8}])
        reopened.undo()
        self.assertEqual(reopened.effect_recipe,data['effect_recipe'])
        self.assertEqual(reopened.composite().tobytes(),doc.composite().tobytes())
        self.assertIsNone(importlib.util.find_spec('pixel_workbench.effects'))
        before = self.service.doc.to_dict()
        with self.assertRaises(PixelError) as error:self.call('/effects',action='create')
        self.assertEqual(error.exception.code,'NOT_FOUND')
        self.assertEqual(self.service.doc.to_dict(),before)
        for value in (float('nan'),object(),'x'*17000):
            invalid = deepcopy(data)
            invalid['effect_recipe']['settings']['bad'] = value
            with self.assertRaises(PixelError):Document.from_dict(invalid)
        json.dumps(data)
