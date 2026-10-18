"""Fresh native/generation MCP transport test; no artistic quality claim.
Optional real image is local-only and never added to the repo.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tests import cleanup_runtime
from tests.mcp_task_smoke import data, tokens


async def run(image_path=None, evidence_dir=None, server_executable=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-art-direction-') as folder:
        root=Path(folder);workspace=root/'workspace';workspace.mkdir()
        source=Path(image_path) if image_path else root/'fixture.png'
        if not image_path:Image.new('RGBA',(48,64),'#4a879cff').save(source)
        prefix=['--mcp'] if server_executable else ['-m','pixel_workbench','--mcp']
        params=StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*prefix,'--headless','--data-dir',str(root/'data'),'--workspace',str(workspace)],cwd=str(workspace))
        try:
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as client:
                    await client.initialize()
                    async def call(tool_name,**args):
                        response=await client.call_tool(tool_name,args);result=data(response)
                        if evidence_dir:
                            target=Path(evidence_dir);target.mkdir(parents=True,exist_ok=True)
                            for i,block in enumerate(response.content):
                                if block.type=='image':(target/f'{tool_name}-{result.get("preview_id",result.get("image_key","request"))}-{i}.png').write_bytes(base64.b64decode(block.data))
                        return result
                    onboard=await call('pixel_onboard',task='text_static',compact=True)
                    assert 'art_direction' in onboard['compatibility']['backend']['features']
                    help_call=onboard['creation_workflow']['optional_art_direction']
                    guide=await call(help_call['tool'],**help_call['arguments'])
                    assert 'host' in guide['guide'] and 'does NOT generate' in guide['guide']
                    assert {'pixel_art_board','pixel_generation'} <= {t.name for t in (await client.list_tools()).tools}
                    state=await call('pixel_projects',action='new',name='Native coordination fixture',width=32,height=32,
                                     compact=True,**tokens(onboard['current_document']))
                    state=await call('pixel_edit',ops=[{'op':'rect','x':8,'y':8,'width':16,'height':16,'color':18}],compact=True,**tokens(state))
                    task=await call('pixel_task',action='plan',task='text_static',brief='Protocol fixture only',
                        direction={'route':'native','style_goals':['Keep observed colors'],
                                   'regions':[{'id':'detail','rect':[8,8,16,16],'goal':'Inspect outline'}]},
                        expected_task_revision=0,**tokens(state))
                    board=await call('pixel_art_board',region_id='detail')
                    same=await call('pixel_art_board',region_id='detail',if_image_key=board['image_key'])
                    assert same['unchanged'] and board['native_size']==[32,32]
                    bad=await client.call_tool('pixel_task',{'action':'update','direction':{'route':'native','unknown':1},
                        'expected_task_revision':task['task_revision'],**tokens(state)})
                    assert bad.isError
                    task=await call('pixel_task',action='update',direction={'route':'generated','style_goals':['Preserve supplied source']},
                                    expected_task_revision=task['task_revision'],**tokens(state))
                    missing=await call('pixel_generation',action='request')
                    ready=await call('pixel_generation',action='request',generator_available=True)
                    assert missing['status']=='generator_unavailable' and ready['status']=='ready_for_host_generation'
                    assert not ready['image_generated'] and not ready['network_called']
                    size=[256,384] if image_path else [32,32]
                    proposal=await call('pixel_generation',action='preview',path=str(source),
                        settings={'width':size[0],'height':size[1],'colors':48,'fit':'contain'},**tokens(state))
                    original=proposal
                    proposal=await call('pixel_generation',action='preview',path=str(source),
                        settings={'width':size[0],'height':size[1],'colors':32,'fit':'contain'},
                        if_source_sha256=original['source_sha256'],**tokens(state))
                    assert proposal['source_image_omitted'] and proposal['image_roles']==['proposed_automatic_pixel_draft']
                    unchanged=await call('pixel_status',compact=True)
                    assert unchanged['document_id']==state['document_id'] and unchanged['revision']==state['revision']
                    applied=await call('pixel_generation',action='apply',preview_id=proposal['preview_id'],**tokens(state))
                    assert applied['native_size']==size and not applied['semantic_layers_ready'] and source.exists()
                    assert (await call('pixel_task'))['context']['task']=='image_static'
                    replay=await call('pixel_generation',action='apply',preview_id=proposal['preview_id'],**tokens(state))
                    assert replay['replayed'] and replay['document_id']==applied['document_id']
                    assert (await client.call_tool('pixel_export',{'path':'exports/unreviewed.png'})).isError
                    listing=await call('pixel_projects',compact=True)
                    assert listing['total']==2
                    report={'ok':True,'checks':['fresh discovery','optional guide through MCP','strict plan schema',
                        'whole/detail image','conditional image reuse','native drawing retained','honest missing generator',
                        'host handoff without network','read-only original/draft preview','conditional source reuse','preserved separate project',
                        'faithful image task','exact retry','final review still required'],
                        'source':'local supplied image' if image_path else 'protocol fixture','no_artistic_quality_claim':True}
                    if evidence_dir:(Path(evidence_dir)/'protocol-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                    print(json.dumps(report,indent=2));return report
        finally:
            session=root/'data/runtime/session.json'
            if session.exists():
                from pixel_workbench.cli import Client
                Client(session).mutate('/shutdown',{'discard_changes':True})
            await cleanup_runtime(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--image');parser.add_argument('--evidence-dir')
    args=parser.parse_args();asyncio.run(run(args.image,args.evidence_dir))
