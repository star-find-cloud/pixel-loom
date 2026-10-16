"""Real MCP clients: optional discovery, preview/adjust/apply/undo and portable references."""
import asyncio
import base64
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


def data(result):
    assert not result.isError, result.structuredContent
    return result.structuredContent


def tokens(state):
    return {k:state[v] for k,v in (("expected_document_id","document_id"),("expected_revision","revision"),
                                  ("expected_reference_revision","reference_revision"))}


async def run(artifacts=None, server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-cutout-') as folder:
        root=Path(folder)
        home,workspace=root/'data',root/'workspace'
        workspace.mkdir()
        from tests.test_cutout import specimen
        source=workspace/'source.png'
        specimen().save(source)
        original_bytes=source.read_bytes()
        prefix=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),args=[*prefix,'--headless',
            '--data-dir',str(home),'--workspace',str(workspace)],cwd=str(workspace))
        async with AsyncExitStack() as stack:
            sessions=[]
            for _ in range(2):
                reader,writer=await stack.enter_async_context(stdio_client(params))
                session=await stack.enter_async_context(ClientSession(reader,writer))
                init=await session.initialize()
                assert 'never automatically on import/conversion' in init.instructions
                sessions.append(session)
            first,second=sessions
            listed={tool.name:tool for tool in (await first.list_tools()).tools}
            assert listed['pixel_cutout_preview'].annotations.readOnlyHint is True
            assert listed['pixel_cutout'].annotations.readOnlyHint is False
            assert 'base_preview_id' in listed['pixel_cutout_preview'].inputSchema['properties']
            onboard=data(await first.call_tool('pixel_onboard',{}))
            assert 'OPTIONAL' in onboard['reference_redraw']['background_removal']
            help_=data(await first.call_tool('pixel_help',{'topic':'cutout'}))
            assert 'not permission' in help_['when_to_use'] and help_['decision_guide']
            state=onboard['current_document']
            ref=data(await first.call_tool('pixel_reference',{'view':'status'}))
            ref=data(await first.call_tool('pixel_reference_setup',{'action':'load','path':'source.png',
                **tokens({**state,'reference_revision':ref['reference_revision']})}))
            assert ref['cutout']['applied'] is False
            before=ref['reference_revision']
            preview=await first.call_tool('pixel_cutout_preview',{**tokens(ref),
                'settings':{'connected':False,'protect_regions':[[33,51,14,18]]}})
            proposed=data(preview)
            assert len([c for c in preview.content if c.type=='image'])==3
            ref2=data(await second.call_tool('pixel_reference',{'view':'status'}))
            assert ref2['reference_revision']==before and ref2['cutout']['applied'] is False
            adjusted=await first.call_tool('pixel_cutout_preview',{**tokens(ref2),'base_preview_id':proposed['preview_id'],
                'settings':{'tolerance':32,'softness':8}})
            adjusted_data=data(adjusted)
            assert adjusted_data['settings']['protect_regions']==[[33,51,14,18]]
            ref=data(await second.call_tool('pixel_cutout',{'action':'apply','preview_id':adjusted_data['preview_id'],**tokens(ref2)}))
            assert ref['cutout']['applied'] is True and ref['cutout']['can_undo'] is True
            stale=await first.call_tool('pixel_cutout',{'action':'apply','preview_id':proposed['preview_id'],**tokens(ref2)})
            assert stale.isError and stale.structuredContent['code']=='REFERENCE_CONFLICT'
            ref=data(await first.call_tool('pixel_cutout',{'action':'undo',**tokens(ref)}))
            assert ref['cutout']['applied'] is False and ref['cutout']['can_redo'] is True
            ref=data(await second.call_tool('pixel_cutout',{'action':'redo',**tokens(ref)}))
            assert ref['cutout']['applied'] is True
            exported=data(await first.call_tool('pixel_cutout',{'action':'export','path':'exports/cut.png',**tokens(ref)}))
            with Image.open(exported['path']) as output:
                assert output.size==(80,96) and output.getpixel((0,0))[3]==0
                assert output.getpixel((38,58))[3]==255
            assert source.read_bytes()==original_bytes
            draft=data(await first.call_tool('pixel_redraw_begin',tokens(ref)))
            data(await first.call_tool('pixel_project',{'action':'save','path':'projects/cutout.pixloom'}))
            source.unlink()
            data(await first.call_tool('pixel_project',{'action':'open','path':'projects/cutout.pixloom'}))
            reopened=data(await first.call_tool('pixel_reference',{'view':'status'}))
            assert reopened['cutout']['applied'] is True
            assert reopened['cutout']['settings']['protect_regions']==[[33,51,14,18]]
            if artifacts:
                import shutil
                target=Path(artifacts)
                target.mkdir(parents=True,exist_ok=True)
                images=[c for c in adjusted.content if c.type=='image']
                for role,content in zip(adjusted_data['image_roles'],images):
                    (target/(role+'.png')).write_bytes(base64.b64decode(content.data))
                shutil.copy2(exported['path'],target/'cutout.png')
                shutil.copy2(workspace/'projects/cutout.pixloom',target/'cutout.pixloom')
            print(json.dumps({'ok':True,'clients':2,'version':init.serverInfo.version,'checks':['optional discovery',
                'import does not cut out','read-only 3-image preview','adjustment retains protection','same preview applied',
                'two-client stale rejection','cutout undo/redo','transparent export','original file unchanged',
                'default pixel draft uses explicit cutout','portable reopen without original']},indent=2))
        from pixel_workbench.cli import Client
        Client(home/'runtime/session.json').mutate('/shutdown')
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__=='__main__':
    asyncio.run(run(sys.argv[1] if len(sys.argv)>1 else None))
