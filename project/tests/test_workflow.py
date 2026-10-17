"""Scope, original-pixel masks, evidence invalidation and compact compatibility."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from pixel_workbench.model import Document, PixelError
from pixel_workbench.service import DocumentService
from pixel_workbench.workflow import compact_state
from pixel_workbench import mcp_server


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.s=DocumentService(Document(16,16),workspace=self.root/'work',runtime=self.root/'runtime')
        self.call('/command',ops=[{'op':'layer_set','name':'source'},
                                 {'op':'rect','x':2,'y':2,'width':10,'height':10,'color':18}])

    def call(self,endpoint,**fields):
        return self.s.dispatch('POST',endpoint,payload={'expected_document_id':self.s.doc.id,'expected_revision':self.s.doc.revision,**fields})[0]

    def read(self,path,**query):return self.s.dispatch('GET',path,query={k:[str(v)] for k,v in query.items()})[0]

    def task(self,action='update',**fields):
        return self.call('/task',action=action,expected_task_revision=self.s.tasks.load(self.s.doc)['revision'],**fields)

    def plan(self,task='image_static',**fields):return self.task('plan',task=task,brief='Protocol fixture; preserve original visible pixels',**fields)

    def part(self,layer=None,hidden='unfilled',**fields):
        return {'layer':layer or self.s.doc.layers[0].id,'extraction':'clean','hidden':hidden,**fields}

    def inspect(self,layer=None,**query):
        return self.read('/snapshot',layers=json.dumps([layer or self.s.doc.layers[0].id]),scale=2,**query)

    def test_notes_persist_without_art_revision_dirty_undo_or_iteration_changes(self):
        before=self.s.doc.to_dict();undo=len(self.s.doc.undo_stack);dirty=self.s.dirty
        self.plan();self.task(next_action='Inspect object boundaries')
        self.assertEqual(before,self.s.doc.to_dict());self.assertEqual(undo,len(self.s.doc.undo_stack));self.assertEqual(dirty,self.s.dirty)
        fresh=DocumentService(self.s.doc,workspace=self.root/'other',runtime=self.s.runtime)
        self.assertEqual(fresh.tasks.status(fresh.doc)['context']['next_action'],'Inspect object boundaries')
        with self.assertRaises(PixelError) as error:self.call('/task',action='clear',expected_task_revision=0)
        self.assertEqual(error.exception.code,'TASK_REVISION_CONFLICT')
        self.task('clear');self.assertIsNone(self.s.tasks.status(self.s.doc)['context'])

    def test_part_needs_complete_current_isolated_image_not_crop_or_composite(self):
        self.plan();self.read('/snapshot');self.inspect(rect='2,2,2,2')
        with self.assertRaises(PixelError) as error:self.task(parts=[self.part()])
        self.assertEqual(error.exception.code,'PART_PREVIEW_REQUIRED')
        self.inspect();self.task(parts=[self.part()]);self.s.tasks.check_delivery(self.s.doc)
        self.call('/command',ops=[{'op':'pixel','x':2,'y':2,'color':17}])
        self.assertFalse(self.s.tasks.status(self.s.doc)['context']['parts'][0]['current'])
        with self.assertRaises(PixelError):self.task(parts=[self.part()])
        self.call('/undo');self.assertTrue(self.s.tasks.status(self.s.doc)['context']['parts'][0]['current'])

    def test_unrequested_hidden_fill_and_animation_blocked_by_task_scope(self):
        self.plan();self.inspect()
        with self.assertRaises(PixelError):self.task(parts=[self.part(hidden='complete')])
        with self.assertRaises(PixelError):self.task(stage='animate')
        self.task(parts=[self.part()]);self.s.tasks.check_delivery(self.s.doc)
        self.call('/command',ops=[{'op':'frame_add'}])
        with self.assertRaises(PixelError) as error:self.s.tasks.check_delivery(self.s.doc)
        self.assertEqual(error.exception.code,'TASK_SCOPE_CONFLICT')

    def test_requested_completion_normalizes_names_and_requires_all_scoped_layers(self):
        self.call('/command',ops=[{'op':'layer_duplicate','name':'second'}])
        self.plan('layer_completion',completion_scope=['source','second'])
        first=self.s.doc.layers[0].id;second=self.s.doc.layers[1].id
        self.inspect(first);self.inspect(second)
        self.task(parts=[self.part('source',hidden='complete')])
        self.assertIn(second,self.s.tasks.status(self.s.doc,brief=True)['context']['needs_check'])
        with self.assertRaises(PixelError):self.s.tasks.check_delivery(self.s.doc)
        self.task(parts=[self.part('source',hidden='complete'),self.part('second',hidden='complete')])
        self.s.tasks.check_delivery(self.s.doc)
        self.assertEqual(self.s.tasks.load(self.s.doc)['context']['completion_scope'],[first,second])

    def test_image_baseline_rejects_changed_dimensions_palette_or_visible_pixels(self):
        for op in [{'op':'pixel','x':2,'y':2,'color':17}, {'op':'palette_add','colors':['#123456ff']},
                   {'op':'canvas_resize','width':17,'height':16}]:
            self.plan();self.inspect();self.task(parts=[self.part()])
            self.call('/command',ops=[op])
            with self.assertRaises(PixelError) as error:self.s.tasks.check_delivery(self.s.doc)
            self.assertEqual(error.exception.code,'DRAFT_FIDELITY_CHANGED')
            self.call('/undo')

    def test_masked_copy_preserves_original_and_separates_object_plus_background(self):
        self.plan();source=self.s.doc.layers[0].id;before=self.s.doc.composite(0).tobytes()
        polygon=[[4,4],[9,4],[9,9],[4,9]]
        self.call('/command',ops=[{'op':'layer_set','layer':source,'visible':False,'locked':True},
            {'op':'layer_add','id':'object','name':'object'},
            {'op':'region_copy','source_layer':source,'layer':'object','rect':[0,0,16,16],'x':0,'y':0,'polygon':polygon},
            {'op':'layer_add','id':'background','name':'background'},
            {'op':'region_copy','source_layer':source,'layer':'background','rect':[0,0,16,16],'x':0,'y':0,'holes':[polygon]}])
        self.assertEqual(before,self.s.doc.composite(0).tobytes())
        self.assertEqual(self.s.doc.layer('object').cels[0].getpixel((2,2)),(0,0,0,0))
        self.assertEqual(self.s.doc.layer('background').cels[0].getpixel((5,5)),(0,0,0,0))
        self.inspect('object');self.inspect('background');self.task(parts=[self.part('object'),self.part('background')])
        self.s.tasks.check_delivery(self.s.doc)
        self.call('/undo');self.assertEqual(before,self.s.doc.composite(0).tobytes())
        self.call('/redo');self.assertEqual(before,self.s.doc.composite(0).tobytes())

    def test_invalid_mask_fails_atomically(self):
        before=self.s.doc.to_dict()
        with self.assertRaises(PixelError):
            self.call('/command',ops=[{'op':'pixel','x':1,'y':1,'color':9},
                {'op':'region_copy','rect':[0,0,16,16],'x':0,'y':0,'holes':[[[1,1],[2,2]]]}])
        self.assertEqual(before,self.s.doc.to_dict())

    def test_preview_cache_scope_and_changed_content_invalidation(self):
        first=self.inspect();key=first['image_key'];before=self.s.doc.to_dict()
        cached=self.inspect(if_image_key=key)
        self.assertTrue(cached['unchanged']);self.assertNotIn('preview_png',cached)
        self.assertEqual(before,self.s.doc.to_dict())
        self.assertFalse(self.read('/snapshot',scale=3,layers=json.dumps([self.s.doc.layers[0].id]),if_image_key=key)['unchanged'])
        self.call('/command',ops=[{'op':'pixel','x':1,'y':1,'color':9}])
        self.assertFalse(self.inspect(if_image_key=key)['unchanged'])

    def test_conditional_state_includes_changed_notes_and_compact_keeps_tokens(self):
        before=self.s.state();small=compact_state(before)
        self.assertEqual(small['workspace'],before['workspace']);self.assertNotIn('palette',small)
        self.assertEqual(small['palette_size'],len(before['palette']))
        self.plan()
        state=self.read('/state',if_revision=before['revision'],document_id=before['document_id'])
        self.assertTrue(state['unchanged']);self.assertEqual(state['workflow_context']['task_revision'],1)
        self.assertNotIn('unchanged',self.read('/state',if_revision=before['revision'],document_id='wrong'))

    def test_compact_validation_and_comparison_keep_requested_evidence_metadata(self):
        proposed=self.call('/validate',ops=[{'op':'pixel','x':1,'y':1,'color':9}],include_preview=False)
        small=compact_state(proposed)
        self.assertEqual(small['base_revision'],self.s.doc.revision)
        self.assertEqual(small['changes'],proposed['changes'])
        self.assertEqual(small['proposed_state']['frame_count'],1)
        comparison={'items':[{'role':'current','frames':[0],'durations':[120]}],
                    'version_id':'test','page':0,'pages':1,'view':'contact','read_only':True}
        self.assertEqual(compact_state(comparison)['items'],comparison['items'])

    def test_legacy_project_never_gets_an_implicit_task_or_new_export_requirement(self):
        self.s.tasks.check_delivery(self.s.doc)
        self.assertIsNone(self.s.tasks.status(self.s.doc)['context'])
        with self.assertRaises(PixelError) as error:self.call('/export',path='exports/final.png')
        self.assertEqual(error.exception.code,'REVIEW_REQUIRED')
        self.call('/export',path='exports/draft.png',draft=True)

    def test_corrupt_notes_dont_prevent_opening_artwork(self):
        path=self.s.tasks.path(self.s.doc);path.parent.mkdir();path.write_text('{}',encoding='utf-8')
        self.assertEqual(self.s.state()['workflow_context']['code'],'TASK_CONTEXT_INVALID')
        self.assertEqual(self.s.state()['width'],16)

    def test_malformed_part_notes_are_reported_without_breaking_artwork_state(self):
        self.plan();value=self.s.tasks.load(self.s.doc)
        value['context']['parts']=[{'layer':[],'frame':0,'extraction':'pending','hidden':'unfilled'}]
        self.s.tasks.path(self.s.doc).write_text(json.dumps(value),encoding='utf-8')
        self.assertEqual(self.s.state()['workflow_context']['code'],'TASK_CONTEXT_INVALID')

    def test_missing_project_identity_explains_how_to_recover(self):
        with self.assertRaises(PixelError) as error:self.call('/projects',action='versions')
        self.assertEqual(error.exception.code,'PROJECT_NOT_FOUND')
        self.assertIn('project_library.active.id',error.exception.recovery)

    def test_deliver_uses_existing_visual_review_in_addition_to_part_checks(self):
        self.plan();self.inspect();self.task(parts=[self.part()])
        with self.assertRaises(PixelError) as error:self.task(stage='deliver')
        self.assertEqual(error.exception.code,'QUALITY_REVIEW_REQUIRED')

    def test_mcp_compact_edit_keeps_images_and_conditional_preview_omits_only_duplicate(self):
        client=Mock();state=self.s.state();state['preview_png']='dGVzdA=='
        client.request.return_value=state
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            response=mcp_server.pixel_edit([],0,self.s.doc.id,compact=True)
        self.assertFalse(response.isError);self.assertEqual(response.structuredContent['detail'],'summary')
        self.assertEqual(len([x for x in response.content if x.type=='image']),1)
        client.request.return_value={'unchanged':True,'image_key':'known','layers':None}
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            response=mcp_server.pixel_preview(if_image_key='known')
        self.assertFalse(response.isError);self.assertEqual(len(response.content),1)


if __name__=='__main__':unittest.main()
