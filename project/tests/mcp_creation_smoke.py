"""Fresh MCP clients discover bundled methods, create clean cels, repair and review.

All artwork is an isolated abstract protocol fixture. Automated pixel assertions
and fixture verdicts do not claim an AI model understood art or judged beauty.
"""
import asyncio
import base64
from contextlib import AsyncExitStack
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pixel_workbench import __version__


def data(result):
    if result.isError:
        raise AssertionError(result.content)
    return result.structuredContent or json.loads(next(c.text for c in result.content if c.type == "text"))


def tokens(state):
    return {"expected_document_id": state["document_id"], "expected_revision": state["revision"]}


def picture(result):
    return Image.open(BytesIO(base64.b64decode(next(c.data for c in result.content if c.type == "image")))).convert("RGBA")


def fixture_verdict(review, passed):
    return {
        "review_id": review["review_id"],
        "visual_checks": [{
            "criterion_id": item["id"], "verdict": "pass" if passed else "fail",
            "reason": ("Automated abstract fixture: rendered pixel assertions match fixed/moving geometry; no production aesthetic claim."
                       if passed else "Automated abstract fixture: unexpected motion-layer pixel at (15,15) remains in frame 2.")
        } for item in review["criteria"]],
        "warning_resolutions": [{
            "warning_id": item["id"], "verdict": "acceptable",
            "reason": "Intentional abstract protocol fixture movement, verified from rendered pixels; not an artistic verdict."
        } for item in review["warnings"]],
        "method": "frames_and_timing",
        "summary": "Automated protocol fixture verification, not a model/art quality assessment",
    }


async def run(server_executable=None, artifacts=None):
    with tempfile.TemporaryDirectory(prefix="pixel-loom-creation-") as folder:
        root = Path(folder)
        home, workspace = root / "data", root / "workspace"
        workspace.mkdir()
        prefix = ["--mcp"] if server_executable else ["-m", "pixel_workbench", "--mcp"]
        params = StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*prefix, "--headless", "--data-dir", str(home), "--workspace", str(workspace)], cwd=str(workspace))
        try:
            async with AsyncExitStack() as stack:
                async def connect():
                    reader, writer = await stack.enter_async_context(stdio_client(params))
                    client = await stack.enter_async_context(ClientSession(reader, writer))
                    initialized = await client.initialize()
                    assert initialized.serverInfo.version == __version__
                    assert "pixel_help(topic='workflow')" in initialized.instructions
                    assert "decomposition_workflow" in initialized.instructions
                    return client

                first = await connect()
                tools = await first.list_tools()
                names = {item.name for item in tools.tools}
                assert "pixel_effect" not in names
                guide = data(await first.call_tool("pixel_onboard", {}))
                entry = guide["creation_workflow"]
                request = entry["read_next"]
                learned = data(await first.call_tool(request["tool"], request["arguments"]))
                assert learned["topic"] == "workflow" and "image_static" in learned["guide"]
                for request in entry["details"]:
                    detail = data(await first.call_tool(request["tool"], request["arguments"]))
                    assert detail["guide"]
                resources = await first.list_resources()
                assert entry["resource"] in {str(item.uri) for item in resources.resources}
                full = json.loads((await first.read_resource(entry["resource"])).contents[0].text)
                from pixel_workbench.creation_guidance import TOPICS
                assert set(full) == set(TOPICS)
                assert entry['single_image_animation']['read_next']['arguments']['topic'] == 'decomposition_workflow'
                for name, arguments in [("draw_sprite", {"brief": "abstract fixture"}),
                                        ("animate_sprite", {"action": "abstract fixture"}),
                                        ("finish_and_review", {})]:
                    assert (await first.get_prompt(name, arguments)).messages
                before = guide["current_document"]
                # Guide requests are read-only and require no local README.
                unchanged = data(await first.call_tool("pixel_status", {}))
                assert unchanged["document_id"] == before["document_id"] and unchanged["revision"] == before["revision"]
                state = data(await first.call_tool("pixel_projects", {
                    "action": "new", "name": "Workflow protocol fixture", "width": 16, "height": 16, **tokens(unchanged)}))
                base = state["layers"][0]["id"]
                state = data(await first.call_tool("pixel_review_settings", {
                    "settings": {"expected_width": 16, "expected_height": 16, "expected_frames": 4,
                                 "transparent_background": True, "uniform_timing": True,
                                 "fixed_regions": ["fixed"], "detail_regions": ["moving"],
                                 "brief": "Abstract fixed/moving fixture, never shipped as a content preset"},
                    **tokens(state)}))
                ops = [
                    {"op": "rect", "layer": base, "frame": 0, "x": 2, "y": 2, "width": 4, "height": 4, "color": 3},
                    {"op": "layer_add", "id": "motion", "name": "moving"},
                    {"op": "region_define", "name": "fixed", "rect": [2, 2, 4, 4]},
                    {"op": "region_define", "name": "moving", "rect": [7, 8, 9, 8]},
                    {"op": "frame_set", "frame": 0, "duration_ms": 80},
                ]
                for f in range(1, 4):
                    ops.append({"op": "frame_add", "after": f-1, "copy_from": 0, "duration_ms": 80})
                # Only now draw motion; copied moving cels were empty.
                for f, x in enumerate([8, 10, 12, 10]):
                    ops.append({"op": "rect", "layer": "motion", "frame": f,
                                "x": x, "y": 9, "width": 2, "height": 2, "color": 7})
                ops.append({"op": "pixel", "layer": "motion", "frame": 2, "x": 15, "y": 15, "color": 7})
                for operation in ["rect", "frame_add", "clear"]:
                    assert data(await first.call_tool("pixel_help", {"operation": operation}))["schema"]
                dry = await first.call_tool("pixel_validate", {"ops": ops, **tokens(state)})
                assert data(dry)["dry_run"]
                assert data(await first.call_tool("pixel_status", {}))["revision"] == state["revision"]
                state = data(await first.call_tool("pixel_edit", {"ops": ops, "include_preview": False,
                            "label": "Protocol fixture with deliberate residual pixel", **tokens(state)}))
                for f, x in enumerate([8, 10, 12, 10]):
                    image = picture(await first.call_tool("pixel_preview", {"frame": f, "scale": 1, "checker": False}))
                    assert image.getpixel((2, 2))[3] == 255
                    assert image.getpixel((x, 9))[3] == 255
                    if f:
                        assert image.getpixel((8, 9))[3] == 0  # no inherited frame-0 motion
                    assert (image.getpixel((15, 15))[3] == 255) == (f == 2)
                before_isolation = data(await first.call_tool('pixel_status', {}))
                isolated_result = await first.call_tool('pixel_preview', {'frame':0,'scale':1,'checker':False,'layers':['motion']})
                isolated = picture(isolated_result)
                assert isolated.getpixel((2,2))[3] == 0 and isolated.getpixel((8,9))[3] == 255
                assert data(isolated_result)['layers'] == ['motion']
                after_isolation = data(await first.call_tool('pixel_status', {}))
                for key in ['document_id','revision','layers','active_layer','active_frame','can_undo','can_redo','unsaved_changes']:
                    assert before_isolation[key] == after_isolation[key], key
                premature = await first.call_tool("pixel_export", {"path": "exports/premature.png"})
                assert premature.isError and premature.structuredContent["code"] == "REVIEW_REQUIRED"
                diagnostic = data(await first.call_tool("pixel_motion_check", {}))
                for page in range(1, diagnostic["pages"]):
                    data(await first.call_tool("pixel_motion_check", {"report_id": diagnostic["report_id"], "page": page}))
                evidence_raw = await first.call_tool("pixel_review", {"show_in_editor": False})
                evidence = data(evidence_raw)
                assert picture(evidence_raw).width > 0
                for page in range(1, evidence["pages"]):
                    data(await first.call_tool("pixel_review", {"review_id": evidence["review_id"], "page": page, "show_in_editor": False}))
                state = data(await first.call_tool("pixel_review_submit", {**fixture_verdict(evidence, False), **tokens(state)}))
                assert state["review"]["status"] == "needs_changes"
                state = data(await first.call_tool("pixel_edit", {"ops": [
                    {"op": "clear", "layer": "motion", "frame": 2},
                    {"op": "rect", "layer": "motion", "frame": 2, "x": 12, "y": 9, "width": 2, "height": 2, "color": 7},
                ], "label": "Repair only the fixture moving cel", **tokens(state)}))
                stale = await first.call_tool("pixel_review_submit", {**fixture_verdict(evidence, True), **tokens(state)})
                assert stale.isError and stale.structuredContent["code"] == "REVIEW_STALE"
                assert picture(await first.call_tool("pixel_preview", {"frame": 2, "scale": 1, "checker": False})).getpixel((15, 15))[3] == 0
                data(await first.call_tool("pixel_motion_check", {}))
                repaired = data(await first.call_tool("pixel_review", {"show_in_editor": False}))
                state = data(await first.call_tool("pixel_review_submit", {**fixture_verdict(repaired, True), **tokens(state)}))
                assert state["review"]["status"] == "passed"
                state = data(await first.call_tool("pixel_project", {
                    "action": "save", "path": "projects/workflow.pixloom", **tokens(state)}))
                for kind, filename in [("png", "workflow.png"), ("gif", "workflow.gif"), ("sheet", "workflow-sheet.png")]:
                    exported = data(await first.call_tool("pixel_export", {"path": "exports/" + filename, "kind": kind}))
                    assert exported["delivery_status"] == "reviewed_final" and Path(exported["path"]).is_file()
                # A second fresh standard MCP session also discovers guidance, without local files.
                second = await connect()
                second_entry = data(await second.call_tool("pixel_onboard", {}))["creation_workflow"]["read_next"]
                assert data(await second.call_tool(second_entry["tool"], second_entry["arguments"]))["guide"]
                assert data(await second.call_tool("pixel_status", {}))["document_id"] == state["document_id"]
                if artifacts:
                    import shutil
                    destination = Path(artifacts)
                    destination.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(workspace / "exports", destination, dirs_exist_ok=True)
                summary = {"ok": True, "version": __version__, "fresh_clients": 2, "guidance_topics": len(full),
                           "scope": "Protocol/discovery fixture, not an external AI model benchmark",
                           "checks": ["initialize discovery", "onboard-directed help", "bundled resource without local docs",
                                      "existing prompts", "read-only help", "native clean-frame drawing", "dry-run",
                                      "actual PNG decoding", "all motion pages", "review gate", "failed verdict",
                                      "bounded repair", "stale evidence rejected", "fresh review", "save and final exports",
                                      "second fresh session"]}
                print(json.dumps(summary, indent=2))
                return summary
        finally:
            session_file = home / "runtime" / "session.json"
            if session_file.exists():
                from pixel_workbench.cli import Client
                Client(session_file).mutate("/shutdown", {"discard_changes": True})
            from tests import cleanup_runtime
            await cleanup_runtime(root)


if __name__ == "__main__":
    asyncio.run(run())
