"""Two actual MCP clients verify exchange formats retain coverage, pixels and overwrite guards."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from tests.mcp_quality_smoke import assessment,data,tokens


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-export-mcp-') as folder:
        root=Path(folder);home=root/'data';work=root/'work';work.mkdir()
        args=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),args=[*args,'--headless',
            '--data-dir',str(home),'--workspace',str(work)],cwd=str(work))
        async with stdio_client(params) as (ra,wa),stdio_client(params) as (rb,wb):
            async with ClientSession(ra,wa) as a,ClientSession(rb,wb) as b:
                init=await a.initialize();await b.initialize()
                assert "pixel_help(topic='export')" in init.instructions
                help=data(await b.call_tool('pixel_help',{'topic':'export'}));assert 'aseprite_array' in help['guide'] and 'Godot 4' in help['guide']
                s=data(await a.call_tool('pixel_project',{'action':'new','width':8,'height':8,'compact':True}))
                ops=[{'op':'pixel','x':1,'y':1,'color':7}]
                for i,ms in enumerate([70,110,230],1):
                    ops += [{'op':'frame_add','blank':True,'duration_ms':ms},{'op':'pixel','frame':i,'x':i+1,'y':1,'color':18}]
                ops += [{'op':'tag_set','name':'idle','start':0,'end':1}, {'op':'tag_set','name':'run','start':2,'end':3,'direction':'reverse'}]
                s=data(await a.call_tool('pixel_edit',{'ops':ops,**tokens(s),'compact':True,'include_preview':False}))
                for fmt in ['aseprite_hash','aseprite_array','godot']:
                    r=await b.call_tool('pixel_export',{'path':fmt+'-early.png','kind':'sheet','sheet_format':fmt})
                    assert r.isError and r.structuredContent['code']=='REVIEW_REQUIRED'
                    assert not (work/(fmt+'-early.png')).exists()
                for tag in ['idle','run']:
                    e=data(await a.call_tool('pixel_review',{'tag':tag,'show_in_editor':False}))
                    s=data(await b.call_tool('pixel_review_submit',{**assessment(e),**tokens(s),'compact':True}))
                observed=s['revision'];ids=None
                for fmt in ['native','aseprite_hash','aseprite_array','godot']:
                    r=data(await a.call_tool('pixel_export',{'path':fmt+'.png','kind':'sheet','sheet_format':fmt,'columns':2}))
                    assert r['delivery_status']=='reviewed_final' and len(r['review_ids'])==2
                    if ids is None:ids=set(r['review_ids'])
                    assert set(r['review_ids'])==ids
                    doc=json.loads((work/(fmt+'.json')).read_text(encoding='utf-8'))
                    if fmt=='native':assert doc['frames'][2]['duration_ms']==110 and len(doc['tags'])==2
                    else:
                        assert doc['meta']['image']==fmt+'.png'
                        frames=list(doc['frames'].values()) if isinstance(doc['frames'],dict) else doc['frames']
                        assert [f['duration'] for f in frames]==[160,70,110,230]
                        assert doc['meta']['frameTags'][1]['direction']=='reverse'
                    if fmt=='godot':assert Path(r['resource_path']).exists() and len(r['files'])==3
                native=Image.open(work/'native.png').convert('RGBA')
                for fmt in ['aseprite_hash','aseprite_array','godot']:
                    with Image.open(work/(fmt+'.png')) as image:assert image.convert('RGBA').tobytes()==native.tobytes()
                blocked=await b.call_tool('pixel_export',{'path':'godot.png','kind':'sheet','sheet_format':'aseprite_hash','overwrite':True})
                assert blocked.isError and blocked.structuredContent['code']=='EXPORT_SIDECAR_CONFLICT'
                blocked=await b.call_tool('pixel_export',{'path':'godot.png','kind':'sheet','sheet_format':'godot'})
                assert blocked.isError and blocked.structuredContent['code']=='FILE_EXISTS'
                data(await a.call_tool('pixel_export',{'path':'godot.png','kind':'sheet','sheet_format':'godot','overwrite':True}))
                bad=await b.call_tool('pixel_export',{'path':'invalid.png','kind':'png','sheet_format':'aseprite_array'})
                assert bad.isError and not (work/'invalid.png').exists()
                status=data(await a.call_tool('pixel_status',{'compact':True}));assert status['revision']==observed
                data(await b.call_tool('pixel_export',{'path':'run.png','kind':'sheet','sheet_format':'aseprite_array','tag':'run'}))
                one=json.loads((work/'run.json').read_text());assert one['meta']['frameTags'][0]['from']==0 and len(one['frames'])==2
                cli=subprocess.run([sys.executable,'-m','pixel_workbench.cli','--session',str(home/'runtime/session.json'),
                    'export',str(work/'cli-run.png'),'--kind','sheet','--sheet-format','aseprite_array','--tag','run'],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
                assert cli.returncode==0,cli.stderr
                assert isinstance(json.loads((work/'cli-run.json').read_text())['frames'],list)
                print(json.dumps({'ok':True,'clients':2,'checks':['MCP-bundled export guide','old native output retained',
                    'Aseprite hash and array fields','Godot relative resource bundle','same pixels across four formats',
                    'same combined review ids reused','unreviewed art blocked in every new format','safe bundle overwrite',
                    'stale Godot sidecar prevented','invalid PNG options rejected','tag export rebased','CLI format/tag accepted','no document mutation']}))
        from pixel_workbench.cli import Client
        Client(home/'runtime/session.json').mutate('/shutdown',{'discard_changes':True})
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run())
