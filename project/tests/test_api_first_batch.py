import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from pixel_workbench.model import Document,PixelError
from pixel_workbench.service import DocumentService
from pixel_workbench.quality import DEFAULT_POLICY,criteria_verdicts
from pixel_workbench.workflow import compact_action_reply


class ApiFirstBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.service=DocumentService(Document(16,16),workspace=root/'work',runtime=root/'data')
        self.call('/command',ops=[{'op':'rect','x':4,'y':3,'width':6,'height':10,'color':18}])

    def call(self,endpoint,**fields):
        doc=self.service.doc
        return self.service.dispatch('POST',endpoint,payload={'expected_document_id':doc.id,'expected_revision':doc.revision,**fields})[0]

    def test_unknown_quality_fields_are_rejected_atomically_with_allowed_fields(self):
        for settings in ({'width':16},{'frame_count':1},{'brief':'valid','unknown':123}):
            before=self.service.doc.to_dict();undo=len(self.service.doc.undo_stack)
            with self.assertRaises(PixelError) as error:self.call('/review/settings',settings=settings)
            self.assertTrue(error.exception.details['unknown_fields'])
            self.assertIn('expected_width',error.exception.details['allowed_fields'])
            self.assertEqual(self.service.doc.to_dict(),before)
            self.assertEqual(len(self.service.doc.undo_stack),undo)

    def test_merge_replace_null_and_undo_keep_their_distinct_semantics(self):
        self.call('/review/settings',settings={'expected_width':16,'expected_frames':8,'criteria':['Retain shape']})
        merged=self.call('/review/settings',settings={'brief':'new brief'})
        self.assertEqual(merged['settings_mode'],'merge')
        self.assertEqual(merged['updated_fields'],['brief'])
        self.assertEqual(merged['effective_policy']['expected_frames'],8)
        cleared=self.call('/review/settings',settings={'expected_frames':None,'criteria':[]})
        self.assertIsNone(cleared['effective_policy']['expected_frames'])
        self.assertEqual(cleared['effective_policy']['criteria'],[])
        old=self.service.doc.quality_policy.copy()
        replaced=self.call('/review/settings',mode='replace',settings={'brief':'fresh policy'})
        self.assertEqual(replaced['effective_policy'],{**DEFAULT_POLICY,'brief':'fresh policy'})
        self.call('/undo');self.assertEqual(self.service.doc.quality_policy,old)
        self.call('/redo');self.assertEqual(self.service.doc.quality_policy,replaced['effective_policy'])

    def test_mismatched_ids_report_missing_unknown_duplicates_and_do_not_submit(self):
        self.call('/review/settings',settings={'loop':False})
        evidence=self.call('/review/evidence');required={v['id'] for v in evidence['criteria']}
        checks=[{'criterion_id':v,'verdict':'pass','reason':'Protocol fixture'} for v in required]
        before=self.service.doc.to_dict()
        for changed,missing,unknown,duplicate in (
            (checks+[{'criterion_id':'motion','verdict':'pass','reason':'Extra static id'}],[],['motion'],[]),
            (checks[1:],[checks[0]['criterion_id']],[],[]),
            (checks+[checks[0]],[],[],[checks[0]['criterion_id']])):
            with self.assertRaises(PixelError) as error:
                self.call('/review/submit',review_id=evidence['review_id'],visual_checks=changed,
                    warning_resolutions=[],method='frames_and_timing',summary='Invalid fixture')
            self.assertEqual(error.exception.code,'REVIEW_INCOMPLETE')
            for key,value in [('missing_ids',missing),('unknown_ids',unknown),('duplicate_ids',duplicate)]:
                self.assertEqual(error.exception.details[key],value)
            self.assertEqual(self.service.doc.to_dict(),before)

    def test_verdict_aliases_normalize_without_weakening_failures(self):
        for incoming,visual,warning in [('pass','pass','acceptable'),('acceptable','pass','acceptable'),
            ('fail','fail','needs_fix'),('needs_fix','fail','needs_fix'),('uncertain','uncertain','uncertain')]:
            self.assertEqual(criteria_verdicts([{'criterion_id':'shape','verdict':incoming,'reason':'Fixture'}],{'shape'})[0]['verdict'],visual)
            self.assertEqual(criteria_verdicts([{'warning_id':'rigid','verdict':incoming,'reason':'Fixture'}],{'rigid'},
                'warning_id',('acceptable','needs_fix','uncertain'))[0]['verdict'],warning)
        with self.assertRaises(PixelError):criteria_verdicts([{'criterion_id':'shape','verdict':[],'reason':'x'}],{'shape'})

    def test_compact_feedback_has_one_issue_copy_and_retains_questions(self):
        self.call('/feedback',action='create',shape={'kind':'rect','rect':[1,1,3,3]},frames=[0],description='Fixture corner')
        issue=self.service.doc.feedback[0]['id']
        self.call('/feedback',action='ask',issue_id=issue,text='Which edge needs correction?')
        full=self.call('/feedback',action='list');receipt=compact_action_reply(full,'list')
        self.assertEqual(receipt['document_id'],full['document_id']);self.assertEqual(receipt['revision'],full['revision'])
        self.assertEqual(receipt['issues'],full['issues']);self.assertNotIn('issues',receipt['feedback'])
        self.assertEqual(receipt['feedback']['needs_clarification_count'],1)
        self.assertIn('questions',receipt['issues'][0]);self.assertNotIn('layers',receipt)
        self.assertLess(len(json.dumps(receipt)),len(json.dumps(full))*.65)

    def test_compact_review_retains_failed_findings_and_export_remains_blocked(self):
        self.call('/review/settings',settings={'loop':False})
        e=self.call('/review/evidence')
        full=self.call('/review/submit',review_id=e['review_id'],
            visual_checks=[{'criterion_id':v['id'],'verdict':'fail' if i==0 else 'pass','reason':'Concrete protocol fixture'}
                for i,v in enumerate(e['criteria'])],warning_resolutions=[],method='frames_and_timing',summary='Needs correction')
        receipt=compact_action_reply(full)
        self.assertEqual(receipt['review']['status'],'needs_changes')
        self.assertEqual(len(receipt['review']['remaining_findings']),1)
        self.assertEqual(receipt['review']['next_action'],'edit_then_recheck')
        self.assertIn('visual_checks',full['review'])
        with self.assertRaises(PixelError):self.call('/export',path='blocked.png')

    def test_mcp_schema_and_validation_reject_unknown_top_level_and_nested_keys(self):
        from pixel_workbench.mcp_server import server
        model=server._tool_manager.get_tool('pixel_review_settings').fn_metadata.arg_model
        for values in ({'settings':{'width':16}},{'settings':{'expected_width':'16'}},
                       {'settings':{},'invented_argument':True}):
            with self.assertRaises(ValidationError):
                model.model_validate({'expected_document_id':'fixture','expected_revision':0,**values})
        value=model.model_validate({'settings':{'brief':'partial'},'expected_document_id':'fixture','expected_revision':0})
        self.assertEqual(value.settings,{'brief':'partial'})
        for tool in server._tool_manager.list_tools():self.assertIs(tool.parameters['additionalProperties'],False)
        self.assertIs(model.model_json_schema()['$defs']['QualitySettings']['additionalProperties'],False)


class VersionHandshakeTests(unittest.TestCase):
    def setUp(self):
        from pixel_workbench import lifecycle
        self.lifecycle=lifecycle;lifecycle._verified_sessions.clear()
        self.addCleanup(lifecycle._verified_sessions.clear)

    def fake(self,health,version,token='fixture'):
        class Client:
            url='http://127.0.0.1:12345'
            def request(self,path,**kwargs):
                self.calls.append(path)
                return {'version':health} if path=='/health' else {'app_version':version}
        client=Client();client.token=token;client.calls=[];return client

    def test_mismatch_reports_both_versions_and_never_opens_or_closes_a_document(self):
        current=self.lifecycle.__version__;old='0.0.0'
        for health,version in [(old,old),(current,old),(current,None)]:
            client=self.fake(health,version)
            with patch.object(self.lifecycle,'Client',return_value=client),self.assertRaises(PixelError) as error:
                self.lifecycle.live_client()
            self.assertEqual(error.exception.code,'VERSION_MISMATCH')
            self.assertEqual(error.exception.details['requested_version'],current)
            self.assertTrue(set(client.calls)<={'/health','/state'})

    def test_actual_editor_check_is_cached_only_for_the_same_process_token(self):
        client=self.fake(self.lifecycle.__version__,self.lifecycle.__version__)
        with patch.object(self.lifecycle,'Client',return_value=client):
            self.assertIs(self.lifecycle.live_client(),client);self.lifecycle.live_client()
            self.assertEqual(client.calls.count('/health'),2);self.assertEqual(client.calls.count('/state'),1)
            client.token='new-process';self.lifecycle.live_client()
            self.assertEqual(client.calls.count('/state'),2)

    def test_manual_launch_shows_version_notice_before_open_or_activate(self):
        from pixel_workbench import app
        client=self.fake(self.lifecycle.__version__,'0.0.0')
        with patch.object(self.lifecycle,'live_client',return_value=client),patch.object(app.messagebox,'showerror') as notice:
            app.main(project='another-project.pixloom')
        notice.assert_called_once()
        message=notice.call_args.args[1]
        self.assertIn('0.0.0',message);self.assertIn(self.lifecycle.__version__,message)
        self.assertEqual(client.calls,['/state'])


if __name__=='__main__':unittest.main()
