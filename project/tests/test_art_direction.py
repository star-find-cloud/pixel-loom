"""Plan/evidence and generated-candidate invariants, not assertions of artistic quality."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from PIL import Image

from pixel_workbench.art_direction import validate_direction
from pixel_workbench.model import Document, PixelError
from pixel_workbench.reference import decoded_asset
from pixel_workbench.service import DocumentService


class ArtDirectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.s = DocumentService(Document(16, 16), workspace=self.root/'work', runtime=self.root/'runtime')
        self.call('/command', ops=[{'op': 'rect', 'x': 3, 'y': 3, 'width': 6, 'height': 8, 'color': 18}])
        self.source = self.root/'generated.png'
        image = Image.new('RGBA', (64, 48), 'white')
        for y in range(10, 39):
            for x in range(14, 50):
                image.putpixel((x, y), (20, 130, 190, 255))
        image.save(self.source)

    def call(self, endpoint, **fields):
        payload = {'expected_document_id': self.s.doc.id, 'expected_revision': self.s.doc.revision, **fields}
        return self.s.dispatch('POST', endpoint, payload=payload)[0]

    def plan(self, route='native', **changes):
        return self.call('/task', action='plan', task='text_static', brief='One isolated protocol fixture, not a finished design',
                         direction={'route': route, 'style_goals': ['Observed color relationships'],
                                    'lighting': 'Upper left', 'regions': [{'id': 'detail', 'rect': [2, 2, 10, 10],
                                    'goal': 'Check the border', 'layers': [self.s.doc.layers[0].id]}], **changes},
                         expected_task_revision=self.s.tasks.load(self.s.doc)['revision'])

    def preview(self, **changes):
        return self.call('/generation', **{'action':'preview','path':str(self.source),
                         'settings':{'width':16,'height':16,'colors':12,'fit':'cover'},**changes})

    def test_plan_and_board_preserve_art_history_and_return_conditional_evidence(self):
        before = self.s.doc.to_dict();history = deepcopy(self.s.doc.undo_stack)
        self.plan()
        self.assertEqual(self.s.doc.to_dict(), before)
        self.assertEqual(self.s.doc.undo_stack, history)
        board = self.call('/art/board', region_id='detail')
        self.assertEqual(board['focus_rect'], [2, 2, 10, 10])
        self.assertEqual(board['image_roles'], ['WHOLE / current', 'DETAIL / current'])
        self.assertEqual(len(board['images_png']), 1)
        self.assertEqual(self.s.part_receipts, {})
        same = self.call('/art/board', region_id='detail', if_image_key=board['image_key'])
        self.assertTrue(same['unchanged']);self.assertNotIn('images_png', same)
        self.assertNotIn('detail_statistics', same)
        self.assertLess(len(json.dumps(same)), len(json.dumps(board))/2)
        self.call('/command', ops=[{'op': 'pixel', 'x': 4, 'y': 4, 'color': 17}])
        changed = self.call('/art/board', region_id='detail', if_image_key=board['image_key'])
        self.assertFalse(changed['unchanged'])
        self.assertTrue(self.s.state()['workflow_context']['context']['direction']['canvas_current'])

    def test_plan_rejects_typos_coordinates_missing_layers_and_duplicate_ids(self):
        for bad in [{'route': 'typo'}, {'route': 'native', 'typo': 1}, {'route': 'native', 'lighting': []},
                    {'route': 'native', 'canvas': [True, 16]},
                    {'route': 'native', 'regions': [{'id': 'x', 'rect': [0, 0, 20, 1], 'goal': 'x'}]},
                    {'route': 'native', 'regions': [{'id': 'x', 'rect': [0, 0, 1, 1], 'goal': 'x', 'layers': ['missing']}]},
                    {'route': 'native', 'regions': [{'id': 'x', 'rect': [0, 0, 1, 1], 'goal': 'x'}]*2}]:
            with self.subTest(bad=bad), self.assertRaises(PixelError):
                validate_direction(bad, self.s.doc)
        self.plan()
        loaded = DocumentService(self.s.doc, workspace=self.s.workspace, runtime=self.s.runtime)
        self.assertEqual(loaded.tasks.load(loaded.doc)['context']['direction']['route'], 'native')
        self.call('/task', action='update', direction={}, expected_task_revision=1)
        self.assertNotIn('direction', self.s.tasks.load(self.s.doc)['context'])

    def test_whole_and_detail_reference_are_read_only_and_bounds_are_checked(self):
        self.call('/reference/setup', action='load', role='style', path=str(self.source), expected_reference_revision=self.s.references.revision,
                  include_images=False)
        self.plan(regions=[{'id': 'detail', 'rect': [0, 0, 16, 16], 'goal': 'Compare material',
                           'reference_role': 'style', 'reference_rect': [2, 2, 30, 30]}])
        data = self.call('/art/board', region_id='detail')
        self.assertEqual(data['image_roles'], ['WHOLE / current', 'STYLE / reference', 'DETAIL / reference'])
        before = self.s.doc.to_dict()
        with self.assertRaises(PixelError):self.call('/art/board', region_id='unknown')
        self.plan(regions=[{'id': 'detail', 'rect': [0, 0, 16, 16], 'goal': 'Compare material',
                           'reference_role': 'style', 'reference_rect': [63, 47, 4, 4]}])
        with self.assertRaises(PixelError):self.call('/art/board', region_id='detail')
        self.assertEqual(self.s.doc.to_dict(), before)

    def test_duplicate_whole_panel_is_omitted_but_distinct_layer_evidence_remains(self):
        self.plan()
        whole = self.call('/art/board')
        self.assertEqual(whole['image_roles'], ['WHOLE / current'])
        self.assertEqual(decoded_asset(whole['images_png'][0]).size, (404, 426))
        first = self.s.doc.layers[0].id
        self.call('/command', ops=[{'op':'layer_add','id':'overlay','name':'Overlay'},
                                   {'op':'pixel','x':0,'y':0,'color':17}])
        self.plan(regions=[{'id':'part','rect':[0,0,16,16],'goal':'Inspect actual isolated content','layers':[first]}])
        isolated = self.call('/art/board', region_id='part')
        self.assertEqual(isolated['image_roles'], ['WHOLE / current', 'DETAIL / current'])
        self.assertEqual(self.s.part_receipts, {})

    def test_canvas_changes_make_plan_stale_without_hiding_the_artwork(self):
        self.plan()
        self.call('/command', ops=[{'op': 'canvas_resize', 'width': 20, 'height': 20}])
        self.assertFalse(self.s.state()['workflow_context']['context']['direction']['canvas_current'])
        self.assertEqual(self.s.state()['width'], 20)
        with self.assertRaises(PixelError) as error:self.call('/art/board')
        self.assertEqual(error.exception.code, 'ART_CANVAS_CONFLICT')

    def test_host_handoff_does_not_fabricate_generation_or_call_network(self):
        self.plan('generated')
        before = self.s.doc.to_dict()
        with patch('socket.create_connection', side_effect=AssertionError('No network allowed')):
            unavailable = self.call('/generation', action='request')
            request = self.call('/generation', action='request', generator_available=True)
            draft = self.preview()
        self.assertEqual(unavailable['status'], 'generator_unavailable')
        self.assertFalse(request['image_generated']);self.assertFalse(request['network_called'])
        self.assertIn('Upper left', request['prompt'])
        self.assertEqual(self.s.doc.to_dict(), before)
        self.assertTrue(draft['dry_run']);self.assertEqual(draft['candidate_size'], [16, 16])
        self.assertEqual(list((self.s.workspace/'projects').glob('*.pixloom')), [])
        self.plan('native')
        with self.assertRaises(PixelError) as error:self.call('/generation', action='request')
        self.assertEqual(error.exception.code, 'ART_ROUTE_CONFLICT')

    def test_apply_uses_viewed_snapshot_preserves_outgoing_and_still_requires_review(self):
        self.plan('generated')
        previous = self.s.doc.to_dict()
        draft = self.preview();ticket = self.s.generation.tickets[draft['preview_id']]
        expected = ticket['candidate'].composite(0).tobytes()
        self.assertEqual(ticket['candidate'].composite(0).getchannel('A').getextrema(), (255, 255))
        original_tokens = {'expected_document_id': self.s.doc.id, 'expected_revision': self.s.doc.revision}
        applied = self.call('/generation', action='apply', preview_id=draft['preview_id'])
        self.assertNotEqual(self.s.doc.id, previous['document_id'])
        self.assertEqual(self.s.doc.composite(0).tobytes(), expected)
        self.assertFalse(applied['semantic_layers_ready']);self.assertTrue(self.source.exists())
        self.assertEqual(len(self.s.projects.entries), 2)
        old = self.s.projects.get(applied['outgoing_project_id'])
        self.assertEqual(Document.open(old['path']).composite(0).tobytes(), Document.from_dict(previous).composite(0).tobytes())
        self.assertEqual(self.s.tasks.load(self.s.doc)['context']['task'], 'image_static')
        self.assertNotIn('layers', self.s.tasks.load(self.s.doc)['context']['direction']['regions'][0])
        count = len(self.s.projects.entries)
        replay = self.call('/generation', action='apply', preview_id=draft['preview_id'], **original_tokens)
        self.assertTrue(replay['replayed']);self.assertEqual(len(self.s.projects.entries), count)
        with self.assertRaises(PixelError):self.call('/export', path='exports/final.png')

    def test_source_plan_and_reference_changes_reject_without_art_changes(self):
        self.plan('generated');draft = self.preview();before = self.s.doc.to_dict()
        Image.new('RGBA', (64, 48), 'red').save(self.source)
        with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=draft['preview_id'])
        self.assertEqual(error.exception.code, 'GENERATION_SOURCE_CHANGED')
        self.assertEqual(before, self.s.doc.to_dict())
        draft = self.preview();self.plan('generated', lighting='Changed light')
        with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=draft['preview_id'])
        self.assertEqual(error.exception.code, 'GENERATION_PREVIEW_STALE')
        draft = self.preview()
        self.call('/reference/setup', action='load', role='style', path=str(self.source),
                  expected_reference_revision=self.s.references.revision, include_images=False)
        with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=draft['preview_id'])
        self.assertEqual(error.exception.code, 'GENERATION_PREVIEW_STALE')

    def test_ticket_limit_expiry_busy_guard_and_explicit_conversion(self):
        self.plan('generated')
        with self.assertRaises(PixelError):self.call('/generation', action='preview', path=str(self.source))
        with self.assertRaises(PixelError):self.call('/generation', action='preview', path=str(self.source), settings={'width': 16, 'typo': 5})
        a = self.preview();self.preview();c = self.preview()
        self.assertEqual(len(self.s.generation.tickets), 2)
        with self.assertRaises(PixelError):self.call('/generation', action='apply', preview_id=a['preview_id'])
        self.s.view['gesture_active'] = True
        with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=c['preview_id'])
        self.assertEqual(error.exception.code, 'EDITOR_BUSY')
        self.s.view['gesture_active'] = False
        self.s.generation.tickets[c['preview_id']]['created'] -= 301
        with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=c['preview_id'])
        self.assertEqual(error.exception.code, 'GENERATION_PREVIEW_EXPIRED')

    def test_save_failure_is_explicit_and_does_not_reapply(self):
        self.plan('generated');self.call('/save', path='projects/outgoing.pixloom')
        draft = self.preview();old = {'expected_document_id': self.s.doc.id, 'expected_revision': self.s.doc.revision}
        with patch.object(self.s, 'save_project', side_effect=OSError('disk fixture failure')):
            with self.assertRaises(PixelError) as error:self.call('/generation', action='apply', preview_id=draft['preview_id'])
        self.assertEqual(error.exception.code, 'GENERATION_APPLIED_NOT_SAVED')
        self.assertTrue(error.exception.details['applied'])
        applied_id = self.s.doc.id
        with self.assertRaises(PixelError) as retry:self.call('/generation', action='apply', preview_id=draft['preview_id'], **old)
        self.assertTrue(retry.exception.details['applied']);self.assertTrue(retry.exception.details['replayed'])
        self.assertEqual(applied_id, self.s.doc.id)
        self.call('/save', path='projects/recovered.pixloom')

    def test_updated_mcp_rejects_old_backend_instead_of_silently_ignoring_plan(self):
        from pixel_workbench import mcp_server
        client=Mock();client.request.return_value={'app_version':'old','capabilities':{'api_revision':2,'features':[]}}
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            responses=[mcp_server.pixel_task(action='plan',direction={'route':'native'}),
                       mcp_server.pixel_art_board(),mcp_server.pixel_generation()]
        self.assertTrue(all(r.isError and r.structuredContent['code']=='BACKEND_UPGRADE_REQUIRED' for r in responses))
        self.assertTrue(all(call.args[0]=='/state' for call in client.request.call_args_list))

    def test_replacement_reference_io_failure_reports_the_applied_document(self):
        self.plan('generated');self.call('/save', path='projects/outgoing.pixloom')
        draft=self.preview();previous_id=self.s.doc.id
        with patch.object(self.s,'restore_reference',side_effect=OSError('reference disk fixture failure')):
            with self.assertRaises(PixelError) as error:self.call('/generation',action='apply',preview_id=draft['preview_id'])
        self.assertEqual(error.exception.code,'GENERATION_APPLIED_NOT_SAVED')
        self.assertTrue(error.exception.details['applied'])
        self.assertTrue(error.exception.details['reference_sync_pending'])
        self.assertNotEqual(self.s.doc.id,previous_id)
        self.assertTrue(self.s.dirty)

    def test_replace_failure_before_switch_keeps_original_and_candidate_retryable(self):
        self.plan('generated');self.call('/save',path='projects/outgoing.pixloom')
        draft=self.preview();before=self.s.doc.to_dict()
        with patch.object(self.s,'replace',side_effect=OSError('pre-switch disk fixture failure')):
            with self.assertRaises(OSError):self.call('/generation',action='apply',preview_id=draft['preview_id'])
        self.assertEqual(before,self.s.doc.to_dict())
        self.assertIsNone(self.s.generation.tickets[draft['preview_id']]['applied'])
        self.assertTrue(self.call('/generation',action='apply',preview_id=draft['preview_id'])['applied'])

    def test_preview_decodes_the_exact_source_bytes_it_hashed(self):
        self.plan('generated')
        expected=Image.open(self.source).convert('RGBA').tobytes()
        alternate=io.BytesIO();Image.new('RGBA',(64,48),'red').save(alternate,'PNG')
        open_image=Image.open
        def changed_path_read(source,*args,**kwargs):
            if isinstance(source,(str,Path)) and Path(source)==self.source:
                return open_image(io.BytesIO(alternate.getvalue()),*args,**kwargs)
            return open_image(source,*args,**kwargs)
        with patch('pixel_workbench.reference.Image.open',side_effect=changed_path_read):
            preview=self.preview()
        ticket=self.s.generation.tickets[preview['preview_id']]
        self.assertEqual(decoded_asset(ticket['candidate'].reference['subject']['png']).tobytes(),expected)

    def test_generation_rejects_fields_for_the_wrong_action_before_changes(self):
        self.plan('generated');proposal=self.preview();before=self.s.doc.to_dict()
        invalid=[{'action':'request','path':str(self.source)},
                 {'action':'request','settings':{'width':16,'height':16,'colors':12}},
                 {'action':'apply','preview_id':proposal['preview_id'],'settings':{'width':16}},
                 {'action':'preview','path':str(self.source),'settings':{'brief':'No size decision'}},
                 {'action':'preview','path':str(self.source),'settings':{'width':16,'height':16,'colors':12},'name':''}]
        for payload in invalid:
            with self.subTest(payload=payload),self.assertRaises(PixelError):self.call('/generation',**payload)
        self.assertEqual(self.s.doc.to_dict(),before)

    def test_default_generated_name_fits_a_valid_long_project_name(self):
        self.plan('generated');self.s.doc.name='长'*120
        preview=self.preview()
        self.assertLessEqual(len(self.s.generation.tickets[preview['preview_id']]['candidate'].name),120)

    def test_new_subject_does_not_reuse_old_subject_crop_mapping(self):
        self.call('/reference/setup',action='load',role='subject',path=str(self.source),expected_reference_revision=self.s.references.revision,include_images=False)
        self.plan('generated',regions=[{'id':'detail','rect':[0,0,16,16],'goal':'Inspect the subject',
                                       'reference_role':'subject','reference_rect':[10,10,16,16]}])
        other=self.root/'other.png';Image.new('RGBA',(32,32),'red').save(other)
        proposal=self.preview(path=str(other))
        applied=self.call('/generation',action='apply',preview_id=proposal['preview_id'])
        self.assertEqual(applied['reference_regions_need_replanning'],['detail'])
        region=self.s.tasks.load(self.s.doc)['context']['direction']['regions'][0]
        self.assertNotIn('reference_rect',region)
        self.assertNotIn('reference_role',region)

    def test_failed_switch_has_emergency_recovery_and_a_replayable_task_plan(self):
        self.plan('generated');self.call('/save',path='projects/outgoing.pixloom')
        proposal=self.preview()
        with patch.object(self.s,'restore_reference',side_effect=OSError('reference disk fixture failure')):
            with self.assertRaises(PixelError) as error:self.call('/generation',action='apply',preview_id=proposal['preview_id'])
        details=error.exception.details
        self.assertTrue(Path(details['recovery_path']).is_file())
        self.assertTrue(details['task_plan_pending'])
        self.assertEqual(Document.open(details['recovery_path']).composite(0).tobytes(),self.s.doc.composite(0).tobytes())
        self.call('/reference/setup',action='use_project',expected_reference_revision=self.s.references.revision,include_images=False)
        self.call('/task',**details['task_recovery'])
        self.call('/save',path='projects/recovered-with-task.pixloom')
        reopened=DocumentService(Document.open(self.s.path),workspace=self.s.workspace,runtime=self.s.runtime)
        self.assertEqual(reopened.tasks.load(reopened.doc)['context']['task'],'image_static')

    def test_applied_ticket_releases_document_and_retry_never_reverts_later_edits(self):
        self.plan('generated');proposal=self.preview()
        original={'expected_document_id':self.s.doc.id,'expected_revision':self.s.doc.revision}
        self.call('/generation',action='apply',preview_id=proposal['preview_id'])
        self.assertNotIn('candidate',self.s.generation.tickets[proposal['preview_id']])
        self.call('/command',ops=[{'op':'pixel','x':0,'y':0,'color':1}])
        after=self.s.doc.to_dict()
        replay=self.call('/generation',action='apply',preview_id=proposal['preview_id'],**original)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['current_revision'],self.s.doc.revision)
        self.assertEqual(after,self.s.doc.to_dict())

    def test_emergency_save_failure_does_not_hide_the_original_outcome(self):
        self.plan('generated');self.call('/save',path='projects/outgoing.pixloom');proposal=self.preview()
        previous=self.s.doc.id
        with patch.object(self.s,'restore_reference',side_effect=OSError('reference disk failure')),patch.object(Document,'save',side_effect=OSError('disk full')):
            # Avoid forcing a failure while checkpointing the unchanged outgoing file.
            with patch.object(self.s,'autosave',return_value=None):
                with self.assertRaises(PixelError) as error:self.call('/generation',action='apply',preview_id=proposal['preview_id'])
        self.assertEqual(error.exception.code,'GENERATION_APPLIED_NOT_SAVED')
        self.assertTrue(error.exception.details['applied']);self.assertIsNone(error.exception.details['recovery_path'])
        self.assertNotEqual(previous,self.s.doc.id);self.assertTrue(self.s.dirty)

    def test_backend_restart_invalidates_candidates_without_overwriting_saved_work(self):
        self.plan('generated');self.call('/save',path='projects/original.pixloom');proposal=self.preview()
        self.s=DocumentService(Document.open(self.s.path),workspace=self.s.workspace,runtime=self.s.runtime)
        before=self.s.doc.to_dict()
        with self.assertRaises(PixelError) as error:self.call('/generation',action='apply',preview_id=proposal['preview_id'])
        self.assertEqual(error.exception.code,'GENERATION_PREVIEW_EXPIRED')
        self.assertEqual(before,self.s.doc.to_dict())

    def test_animated_source_explicitly_reports_first_frame_only(self):
        self.plan('generated');animated=self.root/'animation.gif'
        Image.new('RGB',(16,16),'red').save(animated,save_all=True,append_images=[Image.new('RGB',(16,16),'blue')],duration=100,loop=0)
        proposal=self.preview(path=str(animated))
        self.assertTrue(proposal['first_frame_only']);self.assertTrue(animated.exists())

    def test_settings_are_validated_before_mcp_numeric_coercion(self):
        from pixel_workbench.generation import check_generation_settings
        from pydantic import TypeAdapter,BeforeValidator,ValidationError
        from typing import Annotated
        from pixel_workbench.reference import ReferenceSettings
        adapter=TypeAdapter(Annotated[ReferenceSettings,BeforeValidator(check_generation_settings)])
        for settings in [{'width':True,'height':16,'colors':12},{'width':'16','height':16,'colors':12},
                         {'width':16,'height':16,'colors':12,'brightness':True}]:
            with self.subTest(settings=settings),self.assertRaises((ValidationError,PixelError)):adapter.validate_python(settings)

    def test_generation_requires_updated_capability_even_when_preview_version_matches(self):
        from pixel_workbench import mcp_server
        client=Mock();client.request.return_value={'app_version':'0.7.16','capabilities':{
            'api_revision':2,'features':['art_direction','generation_handoff']}}
        with patch.object(mcp_server,'ensure_editor',return_value=client):response=mcp_server.pixel_generation()
        self.assertTrue(response.isError)
        self.assertEqual(response.structuredContent['details']['required_feature'],'generation_handoff_v2')
        self.assertEqual(client.request.call_args.args[0],'/state')

    def test_repeated_conversion_omits_only_an_explicitly_viewed_unchanged_source(self):
        self.plan('generated')
        before = self.s.doc.to_dict()
        first = self.preview()
        adjusted = self.preview(if_source_sha256=first['source_sha256'],
                                settings={'width':16,'height':16,'colors':8,'fit':'cover'})
        self.assertFalse(first['source_image_omitted'])
        self.assertTrue(adjusted['source_image_omitted'])
        self.assertEqual(adjusted['image_roles'], ['proposed_automatic_pixel_draft'])
        self.assertEqual(len(adjusted['images_png']), 1)
        self.assertEqual(adjusted['conversion_settings']['colors'], 8)
        self.assertEqual(decoded_asset(adjusted['images_png'][0]).size, (128,128))
        Image.new('RGBA',(64,48),'#b1a251ff').save(self.source)
        changed = self.preview(if_source_sha256=first['source_sha256'])
        self.assertFalse(changed['source_image_omitted'])
        self.assertEqual(len(changed['images_png']), 2)
        self.assertNotEqual(changed['source_sha256'], first['source_sha256'])
        fresh_client = self.preview()
        self.assertFalse(fresh_client['source_image_omitted'])
        self.assertEqual(self.s.doc.to_dict(), before)
        for bad in ('not-a-hash', True, 1):
            with self.subTest(bad=bad), self.assertRaises(PixelError):self.preview(if_source_sha256=bad)
        with self.assertRaises(PixelError) as error:
            self.call('/generation', action='request', if_source_sha256=first['source_sha256'])
        self.assertEqual(error.exception.code,'GENERATION_ARGUMENT_CONFLICT')

    def test_conditional_source_checks_compatibility_in_one_backend_read(self):
        from pixel_workbench import mcp_server
        client=Mock();client.request.return_value={'app_version':'0.7.16','capabilities':{
            'features':['generation_handoff_v2']}}
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            response=mcp_server.pixel_generation(action='preview',if_source_sha256='a'*64)
        self.assertTrue(response.isError)
        self.assertEqual(response.structuredContent['details']['required_feature'],'conditional_generation_source')
        self.assertEqual(client.request.call_count,1)


if __name__ == '__main__':unittest.main()
