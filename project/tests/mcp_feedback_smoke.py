"""Two real MCP clients exercise portable canvas feedback and repair evidence.

Resolution text is an explicit automated protocol fixture, not an artistic claim.
"""
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def data(response):
    assert not response.isError, response.structuredContent
    return response.structuredContent


def tokens(state):
    return {"expected_document_id": state["document_id"], "expected_revision": state["revision"]}


async def run(server_executable=None):
    with tempfile.TemporaryDirectory(prefix="pixel-loom-feedback-") as folder:
        root = Path(folder)
        work, home = root/"work", root/"data"
        work.mkdir()
        args = ["--mcp"] if server_executable else ["-m", "pixel_workbench", "--mcp"]
        params = StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*args, "--headless", "--data-dir", str(home), "--workspace", str(work)], cwd=str(work))
        async with AsyncExitStack() as stack:
            clients = []
            for _ in range(2):
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                clients.append(session)
            a, b = clients
            tools = await a.list_tools()
            screenshot_guide=data(await a.call_tool("pixel_help",{"topic":"feedback_images"}))
            assert screenshot_guide["format"]=="pixel-loom/feedback-image/v1"
            assert screenshot_guide["png_property"]=="pixel_loom_feedback"
            assert "PROBLEM FEEDBACK" in screenshot_guide["guide"]
            tool = next(t for t in tools.tools if t.name == "pixel_feedback")
            assert {"shape", "frames", "direct_user_quote", "inspection_id"} <= set(tool.inputSchema["properties"])
            state = data(await a.call_tool("pixel_project", {"action": "new", "width": 16, "height": 16, "name": "Canvas feedback fixture"}))
            state = data(await a.call_tool("pixel_edit", {"ops": [
                {"op": "rect", "x": 4, "y": 6, "width": 6, "height": 7, "color": 18},
                {"op": "frame_add", "copy_from": 0},
                {"op": "pixel", "frame": 1, "x": 10, "y": 9, "color": 7}], **tokens(state)}))
            malformed = await a.call_tool("pixel_feedback", {"action": "create", "shape": {"kind": "rect", "rect": [True, 0, 3, 3]},
                "frames": [0], "description": "Invalid MCP coordinates must not coerce bool to int", **tokens(state)})
            assert malformed.isError
            state = data(await a.call_tool("pixel_feedback", {"action": "create", "shape": {"kind": "lasso", "points": [[8, 7], [12, 7], [12, 12], [8, 12]]},
                "frames": [0, 1], "description": "Fixture user report: inspect detached white pixel in frame 1", **tokens(state)}))
            issue_id = state["issue"]["id"]
            assert state["feedback"]["pending_count"] == 1
            onboard = data(await b.call_tool("pixel_onboard", {}))
            assert onboard["current_document"]["feedback"]["pending_count"] == 1
            state = data(await b.call_tool("pixel_feedback", {"action": "start", "issue_id": issue_id, **tokens(state)}))
            original = data(await b.call_tool("pixel_feedback", {"action": "inspect", "issue_id": issue_id}))
            assert original["issue"]["frames"] == [0, 1]
            assert "frame:1:current_crop" in original["image_roles"]
            state = data(await b.call_tool("pixel_feedback", {"action": "ask", "issue_id": issue_id, "text": "Fixture question: do you mean the isolated white pixel?", **tokens(state)}))
            assert state["feedback"]["needs_clarification_count"] == 1
            refused = await a.call_tool("pixel_feedback", {"action": "resolve", "issue_id": issue_id,
                "inspection_id": original["inspection_id"], "text": "Not allowed before answer", **tokens(state)})
            assert refused.isError and refused.structuredContent["code"] == "FEEDBACK_NEEDS_REPLY"
            guessed = await a.call_tool("pixel_feedback", {"action": "reply", "issue_id": issue_id, "text": "invented answer", **tokens(state)})
            assert guessed.isError
            state = data(await a.call_tool("pixel_feedback", {"action": "reply", "issue_id": issue_id,
                "direct_user_quote": "Fixture actual-user quote: yes, remove that isolated white pixel.", **tokens(state)}))
            state = data(await b.call_tool("pixel_edit", {"ops": [{"op": "pixel", "frame": 1, "x": 10, "y": 9, "color": 0}], **tokens(state)}))
            stale = await b.call_tool("pixel_feedback", {"action": "resolve", "issue_id": issue_id,
                "inspection_id": original["inspection_id"], "text": "Not allowed with old evidence", **tokens(state)})
            assert stale.isError and stale.structuredContent["code"] == "FEEDBACK_INSPECTION_STALE"
            raw = await a.call_tool("pixel_feedback", {"action": "inspect", "issue_id": issue_id})
            fresh = data(raw)
            assert len([c for c in raw.content if c.type == "image"]) == 9
            assert fresh["differences"][1]["changed_pixels_in_shape"] == 1
            state = data(await b.call_tool("pixel_feedback", {"action": "resolve", "issue_id": issue_id,
                "inspection_id": fresh["inspection_id"], "text": "Protocol fixture: selected pixel erased; two current annotated frame images fetched.", **tokens(state)}))
            assert state["feedback"]["pending_count"] == 0
            state = data(await a.call_tool("pixel_feedback", {"action": "create", "shape": {"kind": "ellipse", "rect": [1, 1, 3, 3]},
                "frames": [1], "description": "Fixture obsolete issue for explicit user closure", **tokens(state)}))
            obsolete_id = state["issue"]["id"]
            refused = await b.call_tool("pixel_feedback", {"action": "dismiss", "issue_id": obsolete_id, "text": "AI would prefer to skip", **tokens(state)})
            assert refused.isError
            state = data(await b.call_tool("pixel_feedback", {"action": "dismiss", "issue_id": obsolete_id,
                "direct_user_quote": "Fixture actual-user quote: this old report is obsolete; close it.", **tokens(state)}))
            assert state["feedback"]["dismissed_count"] == 1 and state["issue"]["resolution"] is None
            state = data(await b.call_tool("pixel_project", {"action": "save", "path": "projects/feedback.pixloom"}))
            from pixel_workbench.model import Document
            saved = Document.open(work/"projects/feedback.pixloom")
            assert saved.feedback[0]["resolution"]["inspection_id"] == fresh["inspection_id"]
            assert saved.feedback[0]["questions"][0]["answer"].startswith("Fixture actual-user quote")
            print(json.dumps({"ok": True, "clients": 2, "tools": len(tools.tools), "checks": [
                "typed canvas shape", "pending issues in onboarding", "exact per-frame original/current images",
                "clarification blocks resolution", "real user quote required", "native pixel repair",
                "stale evidence refused", "current differences", "portable issue/question/snapshots",
                "user closure requires actual quote and is not AI repair"]}, indent=2))
        from pixel_workbench.cli import Client
        Client(home/"runtime/session.json").mutate("/shutdown", {"discard_changes": True})
        for _ in range(100):
            if not (home/"runtime/session.json").exists():
                break
            await asyncio.sleep(.05)
        assert not (home/"runtime/session.json").exists()
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None))
