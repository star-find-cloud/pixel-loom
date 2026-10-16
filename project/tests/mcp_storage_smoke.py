"""Two real MCP clients preview/pin/clean isolated data, never the user's workspace."""
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.mcp_public_smoke import data


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-cleanup-mcp-') as folder:
        root=Path(folder)
        params=StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*(['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']),
                  '--headless','--data-dir',str(root/'data'),'--workspace',str(root/'work')])
        async with AsyncExitStack() as stack:
            sessions=[]
            for _ in range(2):
                reader,writer=await stack.enter_async_context(stdio_client(params))
                client=await stack.enter_async_context(ClientSession(reader,writer))
                init=await client.initialize()
                assert "pixel_help(topic='cleanup')" in init.instructions
                sessions.append(client)
            first,second=sessions
            tools={t.name:t for t in (await first.list_tools()).tools}
            assert tools['pixel_storage'].annotations.readOnlyHint
            assert tools['pixel_cleanup'].annotations.destructiveHint and tools['pixel_cleanup'].annotations.idempotentHint
            help_data=data(await first.call_tool('pixel_help',{'topic':'cleanup'}))
            assert len(help_data['examples'])>=5 and 'Ambiguous' in help_data['authorization']
            state=data(await first.call_tool('pixel_onboard',{}))['current_document']
            def tokens(s):return {'expected_document_id':s['document_id'],'expected_revision':s['revision']}
            state=data(await first.call_tool('pixel_projects',dict(action='new',name='Cleanup fixture',width=16,height=16,**tokens(state))))
            project_id=state['project_library']['active']['id']
            for color in (7,8,9):
                state=data(await second.call_tool('pixel_edit',dict(ops=[{'op':'pixel','x':3,'y':3,'color':color}],include_preview=False,**tokens(state))))
            before=dict(state)
            versions=data(await first.call_tool('pixel_projects',dict(action='versions',project_id=project_id,limit=2)))
            assert len(versions['versions'])==2 and versions['has_more'] and versions['total']==4
            older=data(await first.call_tool('pixel_projects',dict(action='versions',project_id=project_id,page=1,limit=2)))
            pinned=older['versions'][0]
            state=data(await first.call_tool('pixel_projects',dict(action='version_pin',project_id=project_id,version_id=pinned['id'],pinned=True,**tokens(state))))
            assert state['revision']==before['revision']
            settings={'targets':['versions'],'project_ids':[project_id],'keep_latest':1}
            plan=data(await first.call_tool('pixel_storage',dict(action='plan',settings=settings,limit=1)))
            assert plan['file_count']==4 and plan['protected_count']==2 and plan['has_more']
            page=data(await second.call_tool('pixel_storage',dict(action='plan',plan_id=plan['plan_id'],page=1,limit=1)))
            assert page['plan_id']==plan['plan_id'] and len(page['items'])==1
            result=data(await second.call_tool('pixel_cleanup',dict(plan_id=plan['plan_id'],user_request='当前项目只保留最新一版和标记保留的版本',**tokens(state))))
            assert result['ok'] and result['removed_files']==4 and result['freed_bytes']>0
            remain=data(await first.call_tool('pixel_projects',dict(action='versions',project_id=project_id)))
            assert remain['total']==2 and any(v['id']==pinned['id'] and v['pinned'] for v in remain['versions'])
            repeat=data(await first.call_tool('pixel_cleanup',dict(plan_id=plan['plan_id'],user_request='当前项目只保留最新一版和标记保留的版本',**tokens(state))))
            assert repeat['already_applied']
            after=data(await first.call_tool('pixel_status',{}))
            assert after['revision']==state['revision'] and after['document_id']==state['document_id']
            # Real expired review caches: four live tickets remain protected.
            for _ in range(5):data(await first.call_tool('pixel_review',{}))
            cache=data(await second.call_tool('pixel_storage',dict(action='plan')))
            assert cache['file_count']==1 and cache['protected_count']==4
            cleaned=data(await second.call_tool('pixel_cleanup',dict(plan_id=cache['plan_id'],user_request='只清理缓存，作品和历史不要动',**tokens(after))))
            assert cleaned['removed_files']==1
            pending=data(await first.call_tool('pixel_storage',dict(action='plan')))
            state=data(await second.call_tool('pixel_edit',dict(ops=[{'op':'pixel','x':4,'y':4,'color':7}],include_preview=False,**tokens(after))))
            rejected=await first.call_tool('pixel_cleanup',dict(plan_id=pending['plan_id'],user_request='只清理缓存',**tokens(state)))
            assert rejected.isError
            state=data(await first.call_tool('pixel_project',dict(action='save',**tokens(state))))
            print(json.dumps({'ok':True,'clients':2,'checks':['discover cleanup scope mappings','read-only and destructive annotations',
                'paged versions/plans','pin protection','preview before deletion','same-project art and revision intact',
                'shared cleanup receipt and safe retries','actual inactive review cache deletion','active review assets protected','stale plan rejected']}))
        from pixel_workbench.cli import Client
        session=root/'data/runtime/session.json'
        Client(session).mutate('/shutdown')
        for _ in range(100):
            if not session.exists():break
            await asyncio.sleep(.05)
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else None))
