"""Isolated real-MCP task notes, compact evidence and history metadata regression.

The geometric fixture checks protocol invariants, not artistic quality.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pixel_workbench import __version__
from tests import cleanup_runtime


def data(response):
    value=response.structuredContent or json.loads(response.content[0].text)
    assert not response.isError,value
    return value


def tokens(state):
    return {'expected_document_id':state['document_id'],'expected_revision':state['revision']}


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-task-') as folder:
        root=Path(folder);workspace=root/'workspace';workspace.mkdir()
        prefix=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*prefix,'--headless','--data-dir',str(root/'data'),'--workspace',str(workspace)],cwd=str(workspace))
        try:
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as client:
                    assert (await client.initialize()).serverInfo.version==__version__
                    async def call(tool_name,**arguments):return data(await client.call_tool(tool_name,arguments))
                    onboard=await call('pixel_onboard',task='text_static',compact=True)
                    assert onboard['compatibility']['status']=='matched'
                    assert onboard['read_next']['arguments']['topic']=='text_workflow'
                    state=await call('pixel_projects',action='new',width=16,height=16,name='Task protocol fixture',
                                     compact=True,**tokens(onboard['current_document']))
                    state=await call('pixel_edit',ops=[{'op':'rect','x':4,'y':4,'width':7,'height':7,'color':18}],
                                     compact=True,**tokens(state))
                    layer=state['layers'][0]['id']
                    task=await call('pixel_task',action='plan',task='text_static',brief='Static protocol fixture',
                                    expected_task_revision=0,**tokens(state))
                    parts=[{'layer':layer,'extraction':'clean','hidden':'unfilled'}]
                    rejected=await client.call_tool('pixel_task',{'action':'update','parts':parts,
                        'expected_task_revision':task['task_revision'],**tokens(state)})
                    assert rejected.isError and rejected.structuredContent['code']=='PART_PREVIEW_REQUIRED'
                    preview=await call('pixel_preview',layers=[layer])
                    cached=await client.call_tool('pixel_preview',{'layers':[layer],'if_image_key':preview['image_key']})
                    assert data(cached)['unchanged'] and not any(c.type=='image' for c in cached.content)
                    task=await call('pixel_task',action='update',parts=parts,
                                    expected_task_revision=task['task_revision'],**tokens(state))
                    unchanged=await call('pixel_status',compact=True,if_revision=state['revision'],document_id=state['document_id'])
                    assert unchanged['unchanged'] and unchanged['workflow_context']['task_revision']==task['task_revision']
                    proposal=await call('pixel_validate',ops=[{'op':'pixel','x':4,'y':4,'color':17}],compact=True,**tokens(state))
                    assert proposal['base_revision']==state['revision'] and proposal['proposed_state']['frame_count']==1
                    assert 'changes' in proposal
                    state=await call('pixel_edit',ops=[{'op':'pixel','x':4,'y':4,'color':17}],compact=True,**tokens(state))
                    assert not (await call('pixel_task'))['context']['parts'][0]['current']
                    state=await call('pixel_history',action='undo',**tokens(state))
                    assert (await call('pixel_task'))['context']['parts'][0]['current']
                    state=await call('pixel_project',action='save',path='projects/task.pixloom',**tokens(state))
                    project_id=state['project_library']['active']['id']
                    versions=await call('pixel_projects',action='versions',project_id=project_id,compact=True)
                    comparison=await call('pixel_projects',action='version_preview',project_id=project_id,
                        version_id=versions['versions'][0]['id'],compact=True)
                    assert [v['role'] for v in comparison['items']]==['selected_version','current']
                    assert all('durations' in v for v in comparison['items'])
                    missing=await client.call_tool('pixel_projects',{'action':'versions','compact':True})
                    assert missing.isError and 'project_library.active.id' in missing.structuredContent['recovery']
                    before=await call('pixel_status',compact=True)
                    await call('pixel_task',action='clear',expected_task_revision=task['task_revision'],**tokens(before))
                    after=await call('pixel_status',compact=True)
                    assert after['revision']==before['revision'] and after['can_undo']==before['can_undo']
                    assert after['workflow_context']['context'] is None
                    result={'ok':True,'version':__version__,'checks':['compact task discovery','part evidence required',
                        'unchanged PNG omitted','conditional notes refresh','compact proposal metadata','stale part checks',
                        'undo restores matching checks','compact comparison roles/durations','missing project ID recovery',
                        'notes clear without artwork/history mutation']}
                    print(json.dumps(result,indent=2));return result
        finally:
            session=root/'data/runtime/session.json'
            if session.exists():
                from pixel_workbench.cli import Client
                Client(session).mutate('/shutdown',{'discard_changes':True})
            await cleanup_runtime(root)


if __name__=='__main__':asyncio.run(run())
