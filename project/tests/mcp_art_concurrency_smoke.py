"""Two real MCP clients: stale plans, user edits and duplicate generated-candidate apply."""
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests import cleanup_runtime
from tests.mcp_task_smoke import data, tokens


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-art-concurrency-') as folder:
        root=Path(folder);work=root/'work';work.mkdir()
        image=root/'source.png';Image.new('RGBA',(32,32),'#3498db').save(image)
        prefix=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*prefix,'--headless','--data-dir',str(root/'data'),'--workspace',str(work)],cwd=str(work))
        try:
            async with AsyncExitStack() as stack:
                clients=[]
                for _ in range(2):
                    reader,writer=await stack.enter_async_context(stdio_client(params))
                    client=await stack.enter_async_context(ClientSession(reader,writer));await client.initialize();clients.append(client)
                a,b=clients
                async def call(client,tool_name,**fields):return data(await client.call_tool(tool_name,fields))
                state=(await call(a,'pixel_onboard',task='text_static',compact=True))['current_document']
                state=await call(a,'pixel_projects',action='new',width=16,height=16,name='Concurrency fixture',compact=True,**tokens(state))
                task=await call(a,'pixel_task',action='plan',task='text_static',brief='One concurrency fixture',
                                direction={'route':'generated'},expected_task_revision=0,**tokens(state))
                async def preview(state):
                    return await call(a,'pixel_generation',action='preview',path=str(image),
                        settings={'width':16,'height':16,'colors':12},**tokens(state))
                proposed=await preview(state)
                await call(b,'pixel_task',action='update',next_action='Changed by another client',
                           expected_task_revision=task['task_revision'],**tokens(state))
                rejected=await a.call_tool('pixel_generation',{'action':'apply','preview_id':proposed['preview_id'],**tokens(state)})
                assert rejected.isError and rejected.structuredContent['code']=='GENERATION_PREVIEW_STALE'
                proposed=await preview(state)
                edited=await call(b,'pixel_edit',ops=[{'op':'pixel','x':1,'y':1,'color':18}],compact=True,**tokens(state))
                rejected=await a.call_tool('pixel_generation',{'action':'apply','preview_id':proposed['preview_id'],**tokens(state)})
                assert rejected.isError and rejected.structuredContent['code']=='REVISION_CONFLICT'
                state=await call(a,'pixel_status',compact=True)
                assert state['revision']==edited['revision'] and state['document_id']==edited['document_id']
                proposed=await preview(state)
                payload={'action':'apply','preview_id':proposed['preview_id'],**tokens(state)}
                first,second=[data(value) for value in await asyncio.gather(a.call_tool('pixel_generation',payload),b.call_tool('pixel_generation',payload))]
                assert first['document_id']==second['document_id']
                assert sum(bool(v.get('replayed')) for v in [first,second])==1
                assert (await call(a,'pixel_projects',compact=True))['total']==2
                current=await call(b,'pixel_status',compact=True)
                changed=await call(b,'pixel_edit',ops=[{'op':'pixel','x':0,'y':0,'color':0}],compact=True,**tokens(current))
                replay=await call(a,'pixel_generation',**payload)
                assert replay['replayed'] and replay['current_revision']==changed['revision']
                assert (await call(b,'pixel_status',compact=True))['revision']==changed['revision']
                report={'ok':True,'clients':2,'checks':['cross-client task change rejects stale candidate',
                    'user drawing rejects stale revision','simultaneous apply creates exactly one project',
                    'duplicate retry never reverts later edits'],'isolated':True}
                print(json.dumps(report,indent=2));return report
        finally:
            session=root/'data/runtime/session.json'
            if session.exists():
                from pixel_workbench.cli import Client
                Client(session).mutate('/shutdown',{'discard_changes':True})
            await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run())
