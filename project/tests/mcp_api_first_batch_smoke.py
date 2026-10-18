"""Two actual stdio clients: strict inputs, actionable errors and opt-in small receipts."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile


def data(response):
    assert not response.isError,response.structuredContent or response.content
    return response.structuredContent


def tokens(state):return {'expected_document_id':state['document_id'],'expected_revision':state['revision']}


async def run(server_executable=None):
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    with tempfile.TemporaryDirectory(prefix='pixel-loom-api-first-') as folder:
        root=Path(folder);home=root/'data';work=root/'work';work.mkdir()
        prefix=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),args=[*prefix,
            '--headless','--data-dir',str(home),'--workspace',str(work)],cwd=str(work))
        # Source subprocess imports the checkout through the existing editable install.
        async with stdio_client(params) as (ra,wa),stdio_client(params) as (rb,wb):
            async with ClientSession(ra,wa) as a,ClientSession(rb,wb) as b:
                await a.initialize();await b.initialize()
                tools=await a.list_tools()
                assert all(t.inputSchema['additionalProperties'] is False for t in tools.tools)
                s=data(await a.call_tool('pixel_project',{'action':'new','width':16,'height':16,'name':'Strict API fixture','compact':True}))
                assert s['detail']=='receipt' and s['active_layer'] and 'layers' not in s
                for settings in [{'width':16},{'frame_count':1},{'fake':True},{'expected_width':'16'}]:
                    r=await b.call_tool('pixel_review_settings',{'settings':settings,**tokens(s)})
                    assert r.isError
                    message=' '.join(c.text for c in r.content if c.type=='text')
                    assert 'expected_width' in message
                    current=data(await a.call_tool('pixel_status',{'compact':True}))
                    assert current['document_id']==s['document_id'] and current['revision']==s['revision']
                r=await b.call_tool('pixel_project',{'action':'new','invented':True})
                assert r.isError and data(await a.call_tool('pixel_status',{'compact':True}))['document_id']==s['document_id']
                s=data(await a.call_tool('pixel_edit',{'ops':[{'op':'rect','x':4,'y':3,'width':6,'height':10,'color':18},
                    {'op':'frame_add','copy_from':0},{'op':'translate','frame':1,'dx':1,'dy':0}],**tokens(s),'compact':True,'include_preview':False}))
                s=data(await a.call_tool('pixel_review_settings',{'settings':{'expected_width':16,'expected_frames':2,'loop':True},**tokens(s),'compact':True}))
                assert s['effective_policy']['expected_frames']==2 and s['settings_mode']=='merge'
                s=data(await b.call_tool('pixel_review_settings',{'settings':{'brief':'Partial update'},**tokens(s),'compact':True}))
                assert s['effective_policy']['expected_frames']==2
                s=data(await a.call_tool('pixel_review_settings',{'settings':{'expected_frames':None},**tokens(s),'compact':True}))
                assert s['effective_policy']['expected_frames'] is None
                s=data(await a.call_tool('pixel_review_settings',{'settings':{'brief':'Replaced fixture'},'mode':'replace',**tokens(s),'compact':True}))
                assert s['effective_policy']['expected_width'] is None and s['settings_mode']=='replace'
                stale=await b.call_tool('pixel_review_settings',{'settings':{},'expected_revision':0,'expected_document_id':s['document_id'],'compact':True})
                assert stale.isError and stale.structuredContent['code']=='REVISION_CONFLICT'
                e=data(await a.call_tool('pixel_review',{'show_in_editor':False}))
                assert e['warnings']
                checks=[{'criterion_id':c['id'],'verdict':'pass','reason':'Explicit native protocol fixture, not art-quality certification.'} for c in e['criteria']]
                warnings=[{'warning_id':w['id'],'verdict':'pass','reason':'Intentional whole-fixture translation in this protocol test.'} for w in e['warnings']]
                invalid=await b.call_tool('pixel_review_submit',{'review_id':e['review_id'],
                    'visual_checks':checks+[{'criterion_id':'invented','verdict':'pass','reason':'Extra id probe'}],
                    'warning_resolutions':warnings,'method':'frames_and_timing','summary':'Probe invalid ids',**tokens(s),'compact':True})
                assert invalid.isError and invalid.structuredContent['details']['unknown_ids']==['invented']
                assert invalid.structuredContent['details']['missing_ids']==[]
                s=data(await a.call_tool('pixel_review_submit',{'review_id':e['review_id'],'visual_checks':checks,
                    'warning_resolutions':warnings,'method':'frames_and_timing','summary':'Native fixture conclusions',**tokens(s),'compact':True}))
                assert s['review']['status']=='passed' and not s['review']['remaining_findings']
                assert data(await b.call_tool('pixel_export',{'path':'fixture.png'}))['delivery_status']=='reviewed_final'
                full=await a.call_tool('pixel_project',{'action':'save','path':'fixture.pixloom',**tokens(s)})
                s=data(full);small=await b.call_tool('pixel_project',{'action':'save',**tokens(s),'compact':True})
                receipt=data(small)
                full_bytes=sum(len(c.text.encode()) for c in full.content if c.type=='text')
                receipt_bytes=sum(len(c.text.encode()) for c in small.content if c.type=='text')
                assert receipt_bytes<full_bytes*.5
                assert Path(receipt['project_path']).is_file() and 'palette' in s and 'palette' not in receipt
                s=data(await a.call_tool('pixel_feedback',{'action':'create','shape':{'kind':'rect','rect':[1,1,3,3]},
                    'description':'Fixture corner needs inspection','frames':[0],**tokens(receipt),'compact':True}))
                issue=s['issue']['id']
                s=data(await a.call_tool('pixel_feedback',{'action':'ask','issue_id':issue,'text':'Which edge?',**tokens(s),'compact':True}))
                compact=data(await b.call_tool('pixel_feedback',{'action':'list','compact':True}))
                full_list=data(await a.call_tool('pixel_feedback',{'action':'list'}))
                assert compact['issues']==full_list['issues'] and 'issues' not in compact['feedback']
                assert compact['feedback']['needs_clarification_count']==1
                inspected=await a.call_tool('pixel_feedback',{'action':'inspect','issue_id':issue,'compact':True})
                assert not inspected.isError and any(c.type=='image' for c in inspected.content)
                assert data(await a.call_tool('pixel_history',{**tokens(s),'action':'undo','compact':True}))['can_redo']
                print(json.dumps({'ok':True,'clients':2,'save_full_json_bytes':full_bytes,'save_receipt_json_bytes':receipt_bytes,
                    'checks':['unknown nested and top-level arguments fail without mutation','merge/replace/null settings',
                        'effective policy receipts','stale guard unchanged','exact unknown review ids','shared verdict words',
                        'real final export gate retained','full legacy replies retained','feedback list appears once',
                        'questions and inspection images retained','compact undo']}))
        from pixel_workbench.cli import Client
        Client(home/'runtime/session.json').mutate('/shutdown',{'discard_changes':True})
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run())
