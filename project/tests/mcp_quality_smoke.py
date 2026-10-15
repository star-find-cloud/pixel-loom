"""Real clients exercise evidence -> failed review -> repair -> recheck -> final export.

Verdicts are explicit protocol fixtures, not claims of a production AI aesthetic review.
"""
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


def data(response):
    assert not response.isError,response.structuredContent
    return response.structuredContent


def tokens(state):
    return {"expected_document_id":state["document_id"],"expected_revision":state["revision"]}


def assessment(evidence,bad=False):
    return {"review_id":evidence["review_id"],"method":"frames_and_timing",
            "summary":"Automated protocol fixture: rigid/uneven motion needs repair" if bad else "Automated protocol fixture: repaired trapezoid evidence",
            "visual_checks":[{"criterion_id":c["id"],"verdict":"fail" if bad and c["id"] in ("motion","timing") else "pass",
                "reason":"Fixture: unchanged cloth shape translates with long/short holds." if bad else "Fixture: native trapezoid changes at a fixed top edge with uniform timing; protocol assertion."} for c in evidence["criteria"]],
            "warning_resolutions":[{"warning_id":w["id"],"verdict":"needs_fix" if bad else "acceptable",
                "reason":"Fixture requires local deformation and uniform timing." if bad else "Intentional fixture warning."} for w in evidence["warnings"]]}


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix="pixel-loom-quality-") as folder:
        root=Path(folder);work=root/"workspace";home=root/"data";work.mkdir()
        args=["--mcp"] if server_executable else ["-m","pixel_workbench","--mcp"]
        params=StdioServerParameters(command=str(server_executable or sys.executable),args=[*args,"--headless","--data-dir",str(home),"--workspace",str(work)],cwd=str(work))
        async with AsyncExitStack() as stack:
            clients=[]
            for _ in range(2):
                read,write=await stack.enter_async_context(stdio_client(params))
                session=await stack.enter_async_context(ClientSession(read,write));await session.initialize();clients.append(session)
            a,b=clients
            tools=await a.list_tools()
            assert {"pixel_review_settings","pixel_review","pixel_review_submit"}<={t.name for t in tools.tools}
            state=data(await a.call_tool("pixel_project",{"action":"new","width":16,"height":16,"name":"Quality workflow fixture"}))
            ops=[{"op":"layer_add","id":"body","name":"body"},
                 {"op":"rect","layer":"body","x":6,"y":3,"width":4,"height":7,"color":18},
                 {"op":"rect","layer":"body","x":6,"y":13,"width":4,"height":1,"color":1},
                 {"op":"region_define","name":"feet","rect":[6,13,4,2]},
                 {"op":"layer_add","id":"cloth","name":"cloth"},
                 {"op":"rect","layer":"cloth","x":4,"y":7,"width":8,"height":6,"color":22},
                 {"op":"frame_set","frame":0,"duration_ms":600}]
            for i,duration in enumerate([400,400,700,60,80,60,900],1):
                ops += [{"op":"frame_add","after":i-1,"copy_from":0,"duration_ms":duration},
                        {"op":"translate","layer":"cloth","frame":i,"dx":1 if i%2 else 0,"dy":0}]
            ops += [{"op":"tag_set","name":"idle","start":0,"end":7}]
            state=data(await a.call_tool("pixel_edit",{"ops":ops,**tokens(state)}))
            state=data(await a.call_tool("pixel_review_settings",{"settings":{"expected_frames":8,"expected_width":16,"expected_height":16,
                    "fixed_regions":["feet"],"transparent_background":True,"brief":"Fixture: natural cloth with planted feet"},**tokens(state)}))
            blocked=await b.call_tool("pixel_export",{"path":"exports/premature.png"})
            assert blocked.isError and blocked.structuredContent["code"]=="REVIEW_REQUIRED"
            raw=await a.call_tool("pixel_review",{"tag":"idle"})
            evidence=data(raw)
            assert evidence["technical_passed"] and evidence["review_status"]=="visual_review_required"
            assert len([c for c in raw.content if c.type=="image"])>=3
            assert Path(evidence["playback_asset"]["path"]).exists()
            assert {"rigid_translation","uneven_timing"}<={w["id"] for w in evidence["warnings"]}
            state=data(await b.call_tool("pixel_review_submit",{**assessment(evidence,True),**tokens(state)}))
            assert state["review"]["status"]=="needs_changes"
            assert state["review"]["next_action"]=="edit_then_recheck"
            repaired=[]
            for i,edge in enumerate([0,1,2,1,0,-1,-2,-1]):
                repaired += [{"op":"clear","layer":"cloth","frame":i},
                    {"op":"polygon","layer":"cloth","frame":i,"points":[[6,7],[9,7],[12+edge,12],[3+edge,12]],"color":22},
                    {"op":"frame_set","frame":i,"duration_ms":200}]
            state=data(await a.call_tool("pixel_edit",{"ops":repaired,**tokens(state)}))
            stale=await b.call_tool("pixel_review_submit",{**assessment(evidence),**tokens(state)})
            assert stale.isError and stale.structuredContent["code"]=="REVIEW_STALE"
            second=data(await b.call_tool("pixel_review",{"tag":"idle","show_in_editor":False}))
            assert second["technical_passed"] and not second["warnings"]
            state=data(await a.call_tool("pixel_review_submit",{**assessment(second),**tokens(state)}))
            assert state["quality_review"]["status"]=="passed"
            state=data(await a.call_tool("pixel_project",{"action":"save","path":"projects/reviewed.pixloom"}))
            final=data(await b.call_tool("pixel_export",{"path":"exports/final.png"}))
            assert final["delivery_status"]=="reviewed_final" and final["review_id"]==second["review_id"]
            prompt=await a.get_prompt("finish_and_review",{})
            assert prompt.messages
            state=data(await a.call_tool("pixel_edit",{"ops":[{"op":"pixel","layer":"body","x":0,"y":0,"color":7}],**tokens(state)}))
            assert state["quality_review"]["status"]=="stale"
            blocked=await b.call_tool("pixel_export",{"path":"exports/stale.png"})
            assert blocked.isError and blocked.structuredContent["code"]=="REVIEW_REQUIRED"
            draft=data(await b.call_tool("pixel_export",{"path":"exports/draft.png","draft":True}))
            assert draft["delivery_status"]=="unreviewed_draft"
            print(json.dumps({"ok":True,"clients":2,"tools":len(tools.tools),"checks":["numeric pass still pending visual review",
                "actual frame/timing/seam images","playable evidence","rigid/uneven warnings","failed verdict blocks final",
                "native repair and new review","stale evidence rejected","passing report unlocks final","edits invalidate pass",
                "explicit draft label","finish-and-review prompt"]},indent=2))
        from pixel_workbench.cli import Client
        client=Client(home/"runtime/session.json");client.mutate("/shutdown",{"discard_changes":True})
        for _ in range(100):
            if not (home/"runtime/session.json").exists(): break
            await asyncio.sleep(.05)
        assert not (home/"runtime/session.json").exists()


if __name__=="__main__":
    asyncio.run(run())
