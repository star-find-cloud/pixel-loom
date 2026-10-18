"""Acceptance scope/coverage regressions, not automatic aesthetic judgments."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import re
from PIL import Image

from pixel_workbench.model import Document,PixelError
from pixel_workbench.service import DocumentService
from pixel_workbench.quality import content_digest,effective_policy,tiled_evidence


class TagQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.s=DocumentService(Document(16,16),workspace=self.root/'work',runtime=self.root/'data')
        ops=[{'op':'rect','x':4,'y':4,'width':4,'height':6,'color':18}]
        for i in range(1,8):ops += [{'op':'frame_add','copy_from':0},{'op':'pixel','frame':i,'x':i,'y':2,'color':7}]
        ops += [{'op':'tag_set','name':'idle','start':0,'end':3},
                {'op':'tag_set','name':'run','start':4,'end':7}]
        self.call('/command',ops=ops)
        self.call('/review/settings',settings={'expected_frames':8,'expected_width':16,'max_rounds':2})

    def call(self,endpoint,**fields):
        return self.s.dispatch('POST',endpoint,payload={'expected_document_id':self.s.doc.id,'expected_revision':self.s.doc.revision,**fields})[0]

    def review(self,tag=None,**fields):return self.call('/review/evidence',tag=tag,**fields)

    def submit(self,e,verdict='pass'):
        return self.call('/review/submit',review_id=e['review_id'],method='frames_and_timing',summary='Explicit protocol fixture',
            visual_checks=[{'criterion_id':c['id'],'verdict':verdict,'reason':'Explicit test fixture observation'} for c in e['criteria']],
            warning_resolutions=[{'warning_id':w['id'],'verdict':'acceptable','reason':'Intentional test fixture'} for w in e['warnings']])['review']

    def both(self):return [self.submit(self.review(t)) for t in ['idle','run']]

    def test_evidence_labels_match_zero_based_source_frames_in_every_role(self):
        self.s.doc.regions['face']=[4,4,4,4]
        for tag in [None,'run']:
            with patch('pixel_workbench.quality.tiled_evidence',wraps=tiled_evidence) as rendered:
                evidence=self.review(tag)
            self.assertIn('detail:face',evidence['image_roles'])
            self.assertTrue(any(role.endswith('two_loop_timing') for role in evidence['image_roles']))
            self.assertTrue(any(role.endswith('loop_seam') for role in evidence['image_roles']))
            for draw in rendered.call_args_list:
                frames,labels=draw.args[1:3]
                self.assertEqual([int(re.search(r'#(\d+)',label).group(1)) for label in labels],frames)

    def test_global_count_is_not_misapplied_to_tag_and_overrides_are_scoped(self):
        e=self.review('run');self.assertTrue(e['technical_passed']);self.assertIsNone(e['policy']['expected_frames'])
        self.call('/review/settings',tag='run',settings={'expected_frames':4,'loop':False})
        self.assertEqual(effective_policy(self.s.doc,'idle')['loop'],True)
        e=self.review('run');self.assertTrue(e['technical_passed']);self.assertEqual(e['policy']['expected_frames'],4)
        self.assertNotIn('loop_seam',e['image_roles']);self.assertIn('one_shot_timing',e['image_roles'])
        self.assertFalse(e['playback_asset']['loop'])
        self.call('/review/settings',tag='run',settings={'brief':'running'})
        self.assertFalse(effective_policy(self.s.doc,'run')['loop'])
        self.call('/review/settings',settings={'expected_frames':8},mode='replace')
        self.assertFalse(effective_policy(self.s.doc,'run')['loop'])
        self.call('/review/settings',tag='run',settings={},mode='replace')
        self.assertTrue(effective_policy(self.s.doc,'run')['loop'])

    def test_independent_reviews_combine_for_whole_sheet_and_reopen(self):
        idle=self.submit(self.review('idle'))
        self.assertEqual(self.s.quality.summary(self.s.doc)['status'],'partial')
        with self.assertRaises(PixelError) as err:self.call('/export',path='too-early.png',kind='sheet')
        self.assertEqual(err.exception.details['missing_tags'],['run'])
        run=self.submit(self.review('run'))
        exported=self.call('/export',path='complete.png',kind='sheet',columns=4)
        self.assertEqual(set(exported['review_ids']),{idle['review_id'],run['review_id']})
        self.assertEqual(self.s.quality.summary(self.s.doc)['status'],'passed')
        self.call('/save',path='complete.pixloom')
        reopened=Document.open(self.root/'work/complete.pixloom')
        s=DocumentService(reopened,workspace=self.root/'again',runtime=self.root/'again-data')
        self.assertTrue(s.quality.coverage(reopened)['passed'])
        self.assertEqual(len(reopened.quality_reviews),2)

    def test_unrelated_action_edit_preserves_idle_and_only_run_evidence_stales(self):
        idle,run=self.both();e_idle=self.review('idle');e_run=self.review('run')
        self.call('/command',ops=[{'op':'pixel','frame':5,'x':15,'y':15,'color':7}])
        self.assertTrue(self.s.quality.is_current(self.s.doc,idle));self.assertFalse(self.s.quality.is_current(self.s.doc,run))
        self.submit(e_idle)
        with self.assertRaises(PixelError) as err:self.submit(e_run)
        self.assertEqual(err.exception.code,'REVIEW_STALE')
        self.call('/export',path='idle.png',kind='sheet',tag='idle')
        with self.assertRaises(PixelError):self.call('/export',path='atlas.png',kind='sheet')
        self.submit(self.review('run'));self.call('/export',path='rechecked.png',kind='sheet')

    def test_policy_changes_and_undo_affect_only_dependent_actions(self):
        idle,run=self.both()
        self.call('/review/settings',tag='run',settings={'loop':False})
        self.assertTrue(self.s.quality.is_current(self.s.doc,idle));self.assertFalse(self.s.quality.is_current(self.s.doc,run))
        self.call('/undo');self.assertTrue(self.s.quality.coverage(self.s.doc)['passed'])
        self.call('/review/settings',settings={'brief':'new global requirement'})
        self.assertFalse(self.s.quality.is_current(self.s.doc,idle))

    def test_latest_failed_or_uncertain_review_cannot_be_hidden_by_old_pass(self):
        self.both()
        self.submit(self.review('run'),'uncertain')
        self.assertFalse(self.s.quality.coverage(self.s.doc)['passed'])
        self.assertTrue(self.s.quality.coverage(self.s.doc)['blocked_review_ids'])
        self.submit(self.review('run'),'fail')
        with self.assertRaises(PixelError):self.call('/export',path='no.png',kind='sheet')
        self.assertEqual(self.call('/export',path='draft.png',kind='sheet',draft=True)['delivery_status'],'unreviewed_draft')

    def test_overlapping_tags_require_their_own_direction_and_policy(self):
        self.call('/command',ops=[{'op':'tag_set','name':'reverse','start':0,'end':3,'direction':'reverse'}])
        self.both();coverage=self.s.quality.coverage(self.s.doc)
        self.assertEqual(coverage['missing_tags'],['reverse'])
        e=self.review('reverse');self.assertEqual(e['metrics']['playback_frames'],[3,2,1,0]);self.submit(e)
        self.assertTrue(self.s.quality.coverage(self.s.doc)['passed'])

    def test_unnamed_frames_are_not_silently_skipped(self):
        self.call('/command',ops=[{'op':'tag_set','name':'run','start':4,'end':6}])
        self.both();coverage=self.s.quality.coverage(self.s.doc)
        self.assertEqual(coverage['missing_frames'],[7])
        with self.assertRaises(PixelError):self.call('/export',path='gap.png',kind='sheet')
        # Whole-document inspection includes unnamed frames and keeps each action independent.
        e=self.review();self.submit(e);self.call('/export',path='whole.png',kind='sheet')

    def test_full_review_evidence_never_builds_a_cross_action_seam(self):
        self.call('/review/settings',tag='run',settings={'loop':False,'criteria':['Run-specific fixture criterion']})
        e=self.review();roles=e['image_roles']
        self.assertIn('tag:idle:loop_seam',roles)
        self.assertIn('tag:run:one_shot_timing',roles)
        self.assertNotIn('loop_seam',roles);self.assertNotIn('tag:run:loop_seam',roles)
        self.assertEqual([a['tag'] for a in e['playback_assets']],['idle','run'])
        self.assertIn('tag:run:custom_1',[c['id'] for c in e['criteria']])
        self.submit(e);self.call('/export',path='legacy-whole.png',kind='sheet')

    def test_layers_cannot_be_unioned_into_an_unreviewed_composite(self):
        self.call('/command',ops=[{'op':'layer_add','id':'other','name':'other'},
                                  {'op':'pixel','layer':'other','x':0,'y':0,'color':7}])
        self.submit(self.review('idle',layers=['other']))
        self.submit(self.review('run'))
        self.assertFalse(self.s.quality.coverage(self.s.doc)['passed'])

    def test_tag_direction_or_range_changes_invalidate_only_that_action(self):
        idle,run=self.both()
        self.call('/command',ops=[{'op':'tag_set','name':'run','start':4,'end':7,'direction':'pingpong'}])
        self.assertTrue(self.s.quality.is_current(self.s.doc,idle));self.assertFalse(self.s.quality.is_current(self.s.doc,run))

    def test_global_count_and_union_palette_are_still_enforced_for_atlas(self):
        self.call('/review/settings',settings={'expected_frames':9})
        self.both()
        self.assertEqual(self.s.quality.coverage(self.s.doc)['technical_failures'][0]['id'],'expected_frames')
        self.call('/review/settings',settings={'expected_frames':8,'max_colors':1})
        for tag in ['idle','run']:self.call('/review/settings',tag=tag,settings={'max_colors':4})
        self.both()
        self.assertEqual(self.s.quality.coverage(self.s.doc)['technical_failures'][0]['id'],'palette')

    def test_old_full_document_record_keeps_its_original_digest_semantics(self):
        record=deepcopy(self.submit(self.review()));record.pop('digest_version')
        record['content_digest']=content_digest(self.s.doc)
        self.s.doc.quality_reviews=[record]
        reopened=Document.from_dict(self.s.doc.to_dict())
        self.assertTrue(self.s.quality.coverage(reopened)['passed'])
        reopened.apply([{'op':'pixel','frame':5,'x':15,'y':15,'color':7}])
        self.assertFalse(self.s.quality.coverage(reopened)['passed'])

    def test_invalid_tag_and_nested_policy_fail_without_mutation(self):
        before=self.s.doc.to_dict()
        for tag,settings in [('rnu',{}),('run',{'tag_policies':{}})]:
            with self.assertRaises(PixelError):self.call('/review/settings',tag=tag,settings=settings)
            self.assertEqual(self.s.doc.to_dict(),before)

    def test_more_than_sixteen_action_reviews_are_retained(self):
        names=['action-'+str(i) for i in range(18)]
        self.call('/command',ops=[{'op':'tag_set','name':t,'start':0,'end':7} for t in names])
        for tag in names:self.submit(self.review(tag))
        self.assertEqual(len(self.s.doc.quality_reviews),18)
        restored=Document.from_dict(self.s.doc.to_dict())
        self.assertEqual(len(restored.quality_reviews),18)

    def test_combined_atlas_pass_does_not_certify_a_cross_action_gif_loop(self):
        self.both()
        with self.assertRaises(PixelError) as error:self.call('/export',path='combined.gif',kind='gif')
        self.assertEqual(error.exception.code,'ANIMATION_TAG_REQUIRED')
        self.call('/export',path='idle.gif',kind='gif',tag='idle')
        self.call('/export',path='preview.gif',kind='gif',draft=True)

    def test_whole_review_respects_action_transparency_override(self):
        self.call('/review/settings',settings={'transparent_background':True})
        self.call('/review/settings',tag='run',settings={'transparent_background':False})
        self.call('/command',ops=[{'op':'rect','frame':f,'x':0,'y':0,'width':16,'height':16,'color':18} for f in range(4,8)])
        self.both()
        self.assertTrue(self.s.quality.coverage(self.s.doc)['passed'])
        self.assertTrue(self.review()['technical_passed'])

    def test_one_shot_gif_export_does_not_repeat_and_default_loop_remains(self):
        self.call('/review/settings',tag='run',settings={'loop':False})
        self.both()
        for tag,loop in [('idle',0),('run',None)]:
            result=self.call('/export',path=tag+'.gif',kind='gif',tag=tag)
            with Image.open(result['path']) as image:self.assertEqual(image.info.get('loop'),loop)

    def test_gif_cannot_replace_reviewed_reverse_playback_with_forward_order(self):
        self.call('/command',ops=[{'op':'tag_delete','name':'run'},
                                  {'op':'tag_set','name':'idle','start':0,'end':7,'direction':'reverse'}])
        self.submit(self.review('idle'))
        with self.assertRaises(PixelError) as error:self.call('/export',path='forward.gif',kind='gif')
        self.assertEqual(error.exception.code,'ANIMATION_TAG_REQUIRED')
        self.call('/export',path='reverse.gif',kind='gif',tag='idle')


if __name__=='__main__':unittest.main()
