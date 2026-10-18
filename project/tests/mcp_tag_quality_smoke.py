"""Real two-client tag/atlas protocol regression; conclusions are explicit test fixtures."""
import asyncio
import base64
import io
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.mcp_quality_smoke import assessment,data,tokens


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-tag-quality-') as folder:
        root=Path(folder);home=root/'data';work=root/'work';work.mkdir()
        args=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),args=[*args,'--headless',
            '--data-dir',str(home),'--workspace',str(work)],cwd=str(work))
        async with stdio_client(params) as (ra,wa),stdio_client(params) as (rb,wb):
            async with ClientSession(ra,wa) as a,ClientSession(rb,wb) as b:
                await a.initialize();await b.initialize()
                s=data(await a.call_tool('pixel_project',{'action':'new','width':16,'height':16,'compact':True}))
                ops=[{'op':'rect','x':4,'y':5,'width':4,'height':7,'color':18}]
                for i in range(1,8):ops += [{'op':'frame_add','copy_from':0,'duration_ms':100},
                                          {'op':'pixel','frame':i,'x':i,'y':1,'color':7}]
                ops += [{'op':'tag_set','name':'idle','start':0,'end':3},
                        {'op':'tag_set','name':'run','start':4,'end':7}]
                s=data(await a.call_tool('pixel_edit',{'ops':ops,**tokens(s),'compact':True,'include_preview':False}))
                s=data(await a.call_tool('pixel_review_settings',{'settings':{'expected_frames':8,'expected_width':16},**tokens(s),'compact':True}))
                for tag in ['idle','run']:
                    s=data(await b.call_tool('pixel_review_settings',{'tag':tag,'settings':{'expected_frames':4,'loop':tag=='idle'},
                            **tokens(s),'compact':True}))
                    assert s['settings_scope']['tag']==tag and s['effective_policy']['expected_frames']==4
                ids=[]
                for tag in ['idle','run']:
                    raw=await a.call_tool('pixel_review',{'tag':tag,'show_in_editor':False});e=data(raw)
                    assert e['technical_passed']
                    for block in raw.content:
                        if block.type=='image':Image.open(io.BytesIO(base64.b64decode(block.data))).load()
                    assert ('loop_seam' in e['image_roles'])==(tag=='idle')
                    s=data(await b.call_tool('pixel_review_submit',{**assessment(e),**tokens(s),'compact':True}))
                    ids.append(e['review_id'])
                    if tag=='idle':
                        blocked=await a.call_tool('pixel_export',{'path':'early.png','kind':'sheet'})
                        assert blocked.isError and blocked.structuredContent['details']['missing_tags']==['run']
                        assert s['quality_review']['status']=='partial'
                final=data(await a.call_tool('pixel_export',{'path':'atlas.png','kind':'sheet','columns':4}))
                assert final['delivery_status']=='reviewed_final' and set(final['review_ids'])==set(ids)
                metadata=json.loads(Path(final['path']).with_suffix('.json').read_text())
                assert len(metadata['frames'])==8 and len(metadata['tags'])==2
                s=data(await b.call_tool('pixel_project',{'action':'save','path':'atlas.pixloom',**tokens(s),'compact':True}))
                path=s['project_path']
                s=data(await a.call_tool('pixel_project',{'action':'open','path':path,**tokens(s),'compact':True}))
                assert s['quality_review']['status']=='passed'
                idle=data(await a.call_tool('pixel_review',{'tag':'idle','show_in_editor':False}))
                run=data(await b.call_tool('pixel_review',{'tag':'run','show_in_editor':False}))
                s=data(await a.call_tool('pixel_edit',{'ops':[{'op':'pixel','frame':5,'x':15,'y':15,'color':7}],
                       **tokens(s),'compact':True,'include_preview':False}))
                data(await b.call_tool('pixel_export',{'path':'idle-still-valid.png','kind':'sheet','tag':'idle'}))
                blocked=await b.call_tool('pixel_export',{'path':'stale-atlas.png','kind':'sheet'})
                assert blocked.isError and blocked.structuredContent['details']['missing_tags']==['run']
                s=data(await b.call_tool('pixel_review_submit',{**assessment(idle),**tokens(s),'compact':True}))
                stale=await a.call_tool('pixel_review_submit',{**assessment(run),**tokens(s),'compact':True})
                assert stale.isError and stale.structuredContent['code']=='REVIEW_STALE'
                run=data(await a.call_tool('pixel_review',{'tag':'run','show_in_editor':False}))
                s=data(await a.call_tool('pixel_review_submit',{**assessment(run),**tokens(s),'compact':True}))
                data(await b.call_tool('pixel_export',{'path':'rechecked-atlas.png','kind':'sheet'}))
                whole=data(await b.call_tool('pixel_review',{'show_in_editor':False}))
                assert 'tag:idle:loop_seam' in whole['image_roles'] and 'tag:run:loop_seam' not in whole['image_roles']
                assert 'loop_seam' not in whole['image_roles'] and len(whole['playback_assets'])==2
                plan=data(await b.call_tool('pixel_storage',{'action':'plan'}))
                protected={p['path'] for p in plan['protected'] if 'path' in p}
                assert {p['path'] for p in whole['playback_assets']}.issubset(protected)
                print(json.dumps({'ok':True,'clients':2,'checks':['tag policies inherit global sizes but have own frame count',
                    'one-shot has no artificial seam','partial atlas lists missing action','independent passes unlock whole sheet',
                    'original JSON frame/tag format retained','save/reopen keeps both reviews','local edit preserves other action',
                    'old affected evidence rejected','new review repairs atlas coverage','whole review separates action timing']}))
        from pixel_workbench.cli import Client
        Client(home/'runtime/session.json').mutate('/shutdown',{'discard_changes':True})
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run())
