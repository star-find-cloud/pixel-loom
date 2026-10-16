"""Real MCP clients discover, preview, create, edit and compare independent VFX projects."""
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
    with tempfile.TemporaryDirectory(prefix="pixel-loom-effects-mcp-") as folder:
        root = Path(folder)
        args = ["--mcp"] if server_executable else ["-m", "pixel_workbench", "--mcp"]
        params = StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*args, "--headless", "--data-dir", str(root / "data"), "--workspace", str(root / "work")])
        async with AsyncExitStack() as stack:
            clients = []
            for _ in range(2):
                reader, writer = await stack.enter_async_context(stdio_client(params))
                client = await stack.enter_async_context(ClientSession(reader, writer))
                initialized = await client.initialize()
                assert "pixel_effect" in initialized.instructions
                clients.append(client)
            first, second = clients
            tools = {tool.name: tool for tool in (await first.list_tools()).tools}
            assert "strength" in json.dumps(tools["pixel_effect"].inputSchema)
            presets = data(await first.call_tool("pixel_effect", {}))
            assert set(presets["presets"]) == {"slash", "lightning", "magic", "fire", "burst"}
            state = data(await first.call_tool("pixel_status", {}))

            def tokens(state):
                return {"expected_document_id": state["document_id"], "expected_revision": state["revision"]}

            response = await first.call_tool("pixel_effect", {"action": "preview", "settings": {"size": 32, "frames": 8}})
            preview = data(response)
            assert any(block.type == "image" for block in response.content)
            assert Path(preview["preview_animation"]["path"]).exists()
            for preset in ("lightning", "magic"):
                evidence = data(await first.call_tool("pixel_effect", {"action": "preview", "settings": {"preset": preset, "size": 32, "frames": 8}}))
                assert evidence["effect"]["frames"] == 8 and evidence["settings"]["preset"] == preset
                assert Path(evidence["preview_animation"]["path"]).exists()
            after = data(await second.call_tool("pixel_status", {}))
            assert after["document_id"] == state["document_id"] and after["revision"] == state["revision"]
            fire = data(await second.call_tool("pixel_effect", {"action": "create", "settings": {"preset": "fire", "size": 32, "frames": 8}, **tokens(state)}))
            assert len(fire["layers"]) == 3 and len(fire["frames"]) == 8
            assert Path(fire["project_path"]).exists()
            old_bytes = Path(fire["project_path"]).read_bytes()
            stale = await first.call_tool("pixel_effect", {"action": "create", **tokens(state)})
            assert stale.isError
            slash = data(await first.call_tool("pixel_effect", {"action": "create", "settings": {"preset": "slash", "size": 32, "frames": 8}, **tokens(fire)}))
            assert slash["document_id"] != fire["document_id"]
            assert Path(fire["project_path"]).read_bytes() == old_bytes
            edited = data(await second.call_tool("pixel_edit", {"ops": [{"op": "pixel", "x": 0, "y": 0, "frame": 1, "color": 4}], **tokens(slash)}))
            assert edited["revision"] > slash["revision"]
            data(await first.call_tool("pixel_history", {"action": "undo", **tokens(edited)}))
            reused = data(await first.call_tool("pixel_effect", {"action": "preview", "include_images": False}))
            assert reused["settings"]["preset"] == "slash"
            print(json.dumps({"ok": True, "clients": 2, "checks": ["typed discovery", "actual all-frame evidence and GIF", "readonly preview", "editable saved VFX", "stale create rejected", "independent variants", "native pixel edit and shared undo", "portable recipe reuse"]}))
        from pixel_workbench.cli import Client
        session_path = root / "data/runtime/session.json"
        Client(session_path).mutate("/shutdown", {"discard_changes": True})
        for _ in range(100):
            if not session_path.exists():
                break
            await asyncio.sleep(.05)
        assert not session_path.exists()
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None))
