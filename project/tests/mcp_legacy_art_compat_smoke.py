"""Optional real released-MCP/current-backend compatibility matrix.

Pass a local released executable explicitly; the test never downloads a binary.
All images, notes and projects live in one isolated temporary test workspace.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests import cleanup_runtime
from tests.mcp_task_smoke import data, tokens
from pixel_workbench.cli import Client


async def run(legacy_exe):
    legacy_exe=Path(legacy_exe).resolve()
    if not legacy_exe.is_file():raise ValueError('Supply an existing released MCP executable')
    with tempfile.TemporaryDirectory(prefix='pixel-loom-legacy-art-compat-') as folder:
        root=Path(folder);work=root/'work';work.mkdir();session=root/'data/runtime/session.json'
        @asynccontextmanager
        async def connect(old=False):
            prefix=['--mcp'] if old else ['-m','pixel_workbench','--mcp']
            params=StdioServerParameters(command=str(legacy_exe if old else sys.executable),
                args=[*prefix,'--headless','--data-dir',str(root/'data'),'--workspace',str(work)],cwd=str(work))
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as client:
                    await client.initialize()
                    yield client
        async def call(client,tool_name,**fields):return data(await client.call_tool(tool_name,fields))
        async def shutdown(cleanup=True):
            if session.exists():Client(session).mutate('/shutdown',{'discard_changes':True})
            for _ in range(100):
                if not session.exists():break
                await asyncio.sleep(.03)
            if session.exists():raise RuntimeError('Test backend did not stop')
            if cleanup:await cleanup_runtime(root)
        try:
            # Updated MCP launches updated backend and creates ordinary legacy-compatible content.
            async with connect() as current:
                state=(await call(current,'pixel_onboard',task='text_static',compact=True))['current_document']
                state=await call(current,'pixel_projects',action='new',name='Compatibility fixture',width=16,height=16,compact=True,**tokens(state))
                state=await call(current,'pixel_edit',ops=[{'op':'rect','x':3,'y':4,'width':8,'height':9,'color':18}],compact=True,**tokens(state))
                task=await call(current,'pixel_task',action='plan',task='text_static',brief='Compatibility fixture',
                    direction={'route':'native','style_goals':['Keep fixture pixels']},expected_task_revision=0,**tokens(state))
                state=await call(current,'pixel_project',action='save',path='projects/current.pixloom',compact=True,**tokens(state))
                before=await call(current,'pixel_preview',scale=1)
                before_key=before['image_key']
            # Legacy MCP can still draw/save using the new backend and its shared note store.
            async with connect(old=True) as old:
                state=(await call(old,'pixel_onboard',task='text_static',compact=True))['current_document']
                assert 'art_direction' in state['capabilities']['features']
                assert (await call(old,'pixel_preview',scale=1))['image_key']==before_key
                await call(old,'pixel_task',action='update',next_action='Old client note update',expected_task_revision=task['task_revision'],**tokens(state))
                state=await call(old,'pixel_edit',ops=[{'op':'pixel','x':4,'y':5,'color':17}],compact=True,**tokens(state))
                state=await call(old,'pixel_project',action='save',path='projects/legacy-roundtrip.pixloom',compact=True,**tokens(state))
                reference_render=next(v.data for v in (await old.call_tool('pixel_preview',{'scale':1})).content if v.type=='image')
            async with connect() as current:
                notes=await call(current,'pixel_task')
                assert notes['context']['direction']['route']=='native'
                assert notes['context']['next_action']=='Old client note update'
            await shutdown(cleanup=False)
            # Released backend reopens the updated file with identical visible pixels and retained old operations.
            async with connect(old=True) as old:
                state=(await call(old,'pixel_onboard',compact=True))['current_document']
                old_features=state['capabilities']['features']
                assert 'generation_handoff_v2' not in old_features
                state=await call(old,'pixel_project',action='open',path='projects/legacy-roundtrip.pixloom',compact=True,**tokens(state))
                state=await call(old,'pixel_project',action='save',path='projects/old-backend.pixloom',compact=True,**tokens(state))
                assert next(v.data for v in (await old.call_tool('pixel_preview',{'scale':1})).content if v.type=='image')==reference_render
                before=(await call(old,'pixel_preview',scale=1))['image_key']
            # Updated MCP must reject only unavailable optional features, without breaking legacy drawing.
            async with connect() as current:
                state=(await call(current,'pixel_onboard',compact=True))['current_document']
                unsupported=[('pixel_generation',{})]
                if 'art_direction' not in old_features:
                    unsupported.extend([('pixel_art_board',{}),('pixel_task',{
                        'action':'update','direction':{'route':'native'},'expected_task_revision':0,**tokens(state)})])
                else:assert (await call(current,'pixel_art_board'))['read_only']
                for tool,args in unsupported:
                    rejected=await current.call_tool(tool,args)
                    assert rejected.isError and rejected.structuredContent['code']=='BACKEND_UPGRADE_REQUIRED'
                assert (await call(current,'pixel_preview',scale=1))['image_key']==before
                state=await call(current,'pixel_edit',ops=[{'op':'pixel','x':5,'y':5,'color':17}],compact=True,**tokens(state))
                await call(current,'pixel_project',action='save',compact=True,**tokens(state))
            report={'ok':True,'checks':['released MCP / updated backend drawing and notes',
                'updated file opened/saved by released backend','new optional fields survive old note updates',
                'updated MCP / released backend rejects unsupported coordination before mutation',
                'legacy drawing remains available in both directions'],'isolated':True}
            print(json.dumps(report,indent=2));return report
        finally:
            await shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--legacy-exe',required=True)
    args=parser.parse_args();asyncio.run(run(args.legacy_exe))
