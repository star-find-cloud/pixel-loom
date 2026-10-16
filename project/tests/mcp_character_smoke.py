"""Two real MCP clients: preserve approved pose, fork, inspect evidence, repair, undo."""
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
    with tempfile.TemporaryDirectory(prefix="pixel-loom-character-mcp-") as folder:
        root = Path(folder)
        args = ["--mcp"] if server_executable else ["-m", "pixel_workbench", "--mcp"]
        params = StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*args, "--headless", "--data-dir", str(root / "data"), "--workspace", str(root / "work")])
        async with AsyncExitStack() as stack:
            sessions = []
            for _ in range(2):
                reader, writer = await stack.enter_async_context(stdio_client(params))
                client = await stack.enter_async_context(ClientSession(reader, writer))
                init = await client.initialize()
                assert "pixel_character" in init.instructions and "pixel_motion_check" in init.instructions
                sessions.append(client)
            first, second = sessions
            tools = {t.name: t for t in (await first.list_tools()).tools}
            assert tools["pixel_motion_check"].annotations.readOnlyHint
            assert "fixed_regions" in json.dumps(tools["pixel_character"].inputSchema)
            state = data(await first.call_tool("pixel_status", {}))

            def tokens(state):
                return {"expected_document_id": state["document_id"], "expected_revision": state["revision"]}

            state = data(await first.call_tool("pixel_projects", {"action": "new", "name": "Approved idle", "width": 32, "height": 32, **tokens(state)}))
            state = data(await first.call_tool("pixel_edit", {"ops": [
                {"op": "rect", "x": 10, "y": 5, "width": 10, "height": 22, "color": 7},
                {"op": "region_define", "name": "face", "rect": [12, 6, 6, 5]}], **tokens(state)}))
            response = await first.call_tool("pixel_character", {"action": "capture", "settings": {"name": "Hero", "fixed_regions": ["face"]}, **tokens(state)})
            spec = data(response)
            assert spec["character"]["configured"] and any(b.type == "image" for b in response.content)
            source_id = spec["document_id"]
            state = data(await second.call_tool("pixel_projects", {"action": "fork", "name": "Walk test", **tokens(spec)}))
            assert state["document_id"] != source_id and state["character"]["name"] == "Hero"
            state = data(await second.call_tool("pixel_edit", {"ops": [
                {"op": "frame_add", "copy_from": 0}, {"op": "frame_add", "copy_from": 0},
                *[{"op": "pixel", "frame": frame, "x": x, "y": 24, "color": 7} for frame in (1, 2) for x in (23, 26, 29)]], **tokens(state)}))
            response = await first.call_tool("pixel_motion_check", {})
            report = data(response)
            assert report["scanned_frames"] == 3 and report["pages"] > 1
            assert any(b.type == "image" for b in response.content)
            for page in range(1, report["pages"]):
                more = data(await second.call_tool("pixel_motion_check", {"report_id": report["report_id"], "page": page}))
                assert more["page"] == page
            finding = next(f for f in report["findings"] if f["kind"] == "orphan_pixels")
            ops = finding["repair_ops"]
            dry = data(await first.call_tool("pixel_validate", {"ops": ops, **tokens(state)}))
            assert dry["dry_run"]
            changed = data(await first.call_tool("pixel_edit", {"ops": ops, **tokens(state)}))
            assert (await second.call_tool("pixel_motion_check", {"report_id": report["report_id"]})).isError
            undo = data(await second.call_tool("pixel_history", {"action": "undo", **tokens(changed)}))
            new_report = data(await first.call_tool("pixel_motion_check", {}))
            assert new_report["counts"]["orphan_pixels"] == report["counts"]["orphan_pixels"]
            exported = data(await first.call_tool("pixel_character", {"action": "save", "path": str(root / "hero.pixelchar"), "include_images": False}))
            assert Path(exported["path"]).exists()
            review = data(await first.call_tool("pixel_review", {}))
            assert "character_pose" in review["image_roles"]
            assert "character_consistency" in [c["id"] for c in review["criteria"]]
            stale = await first.call_tool("pixel_character", {"action": "configure", "settings": {"name": "stale"}, **tokens(state)})
            assert stale.isError and undo["document_id"] == state["document_id"]
            print(json.dumps({"ok": True, "clients": 2, "checks": ["typed discovery", "approved pose image", "fork inherits spec", "all paged evidence", "exact dry-run and repair", "stale report rejected", "shared undo", "portable export", "visual acceptance criterion", "stale writes rejected"]}))
        from pixel_workbench.cli import Client
        session_path = root / "data" / "runtime" / "session.json"
        Client(session_path).mutate("/shutdown", {"discard_changes": True})
        for _ in range(100):
            if not session_path.exists():
                break
            await asyncio.sleep(0.05)
        assert not session_path.exists()
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None))
