"""Real two-client MCP reference -> dry-run -> native redraw -> adjustment -> portable save."""
import asyncio
import base64
from contextlib import AsyncExitStack
import json
from pathlib import Path
import runpy
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


def data(result):
    assert not result.isError, result.structuredContent
    return result.structuredContent


def tokens(state):
    return {"expected_document_id": state["document_id"], "expected_revision": state["revision"]}


REDRAW = [
    {"op": "palette_set", "colors": ["#00000000", "#17283cff", "#e9bc61ff", "#ffe0b7ff", "#e5eef3ff", "#63c0bdff", "#a9c3d0ff"]},
    {"op": "polygon", "layer": "silhouette", "points": [[8, 8], [18, 4], [25, 9], [26, 19], [21, 24], [10, 22], [6, 17]], "color": 1},
    {"op": "polygon", "layer": "silhouette", "points": [[12, 21], [20, 22], [24, 35], [21, 38], [10, 37], [8, 31]], "color": 1},
    {"op": "polygon", "layer": "base-colors", "points": [[9, 9], [18, 5], [24, 10], [25, 18], [20, 23], [10, 21], [7, 16]], "color": 2},
    {"op": "polygon", "layer": "base-colors", "points": [[12, 12], [21, 11], [23, 15], [21, 21], [12, 20]], "color": 3},
    {"op": "polygon", "layer": "base-colors", "points": [[9, 12], [15, 7], [23, 11], [17, 12], [15, 15], [13, 12], [10, 16]], "color": 2},
    {"op": "polygon", "layer": "base-colors", "points": [[12, 24], [19, 23], [22, 33], [20, 36], [11, 35], [10, 31]], "color": 4},
    {"op": "polygon", "layer": "base-colors", "points": [[11, 24], [13, 24], [11, 34], [8, 37], [6, 35]], "color": 5},
    {"op": "rect", "layer": "base-colors", "x": 12, "y": 36, "width": 3, "height": 7, "color": 3},
    {"op": "rect", "layer": "base-colors", "x": 18, "y": 36, "width": 3, "height": 7, "color": 3},
    {"op": "rect", "layer": "details", "x": 14, "y": 16, "width": 1, "height": 2, "color": 1},
    {"op": "rect", "layer": "details", "x": 20, "y": 16, "width": 1, "height": 2, "color": 1},
    {"op": "rect", "layer": "details", "x": 14, "y": 23, "width": 5, "height": 2, "color": 5},
    {"op": "line", "layer": "details", "x1": 19, "y1": 27, "x2": 20, "y2": 33, "color": 6},
    {"op": "rect", "layer": "details", "x": 11, "y": 42, "width": 4, "height": 2, "color": 1},
    {"op": "rect", "layer": "details", "x": 18, "y": 42, "width": 4, "height": 2, "color": 1},
]


async def run(artifacts=None, server_executable=None):
    with tempfile.TemporaryDirectory(prefix="pixel-loom-reference-") as folder:
        root = Path(folder)
        home, workspace = root/"data", root/"workspace"
        workspace.mkdir()
        ordinary_image = runpy.run_path(str(Path(__file__).with_name("test_reference.py")))["ordinary_image"]
        source = workspace/"ordinary.png"
        ordinary_image(source)
        Image.new("RGB", (16, 16), "#63c0bd").save(workspace/"style.png")
        prefix = ["--mcp"] if server_executable else ["-m", "pixel_workbench", "--mcp"]
        params = StdioServerParameters(command=str(server_executable or sys.executable),
            args=[*prefix, "--headless", "--data-dir", str(home), "--workspace", str(workspace)], cwd=str(workspace))
        async with AsyncExitStack() as stack:
            sessions = []
            for _ in range(2):
                reader, writer = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(reader, writer))
                await session.initialize()
                sessions.append(session)
            first, second = sessions
            listed = await first.list_tools()
            assert {"pixel_reference", "pixel_reference_setup", "pixel_redraw_begin"} <= {t.name for t in listed.tools}
            onboard = data(await first.call_tool("pixel_onboard", {}))
            assert "reference_redraw" in onboard
            state = data(await first.call_tool("pixel_status", {}))
            ref = data(await first.call_tool("pixel_reference", {"view": "status"}))
            assert ref["style_reference"] is None and ref["style_reference_source"] is None
            loaded = await first.call_tool("pixel_reference_setup", {"action": "load", "path": "ordinary.png",
                "settings": {"width": 32, "height": 48, "colors": 12}, **tokens(state),
                "expected_reference_revision": ref["reference_revision"]})
            ref = data(loaded)
            assert len([c for c in loaded.content if c.type == "image"]) == 3
            assert ref["revision"] == state["revision"] and ref["document_id"] == state["document_id"]
            stale_ref = ref["reference_revision"]
            ref = data(await second.call_tool("pixel_reference_setup", {"action": "load", "role": "style", "path": "style.png",
                **tokens(state), "expected_reference_revision": stale_ref}))
            assert len(ref["image_roles"]) == 4
            assert ref["style_reference_source"] == "imported"
            stale = await first.call_tool("pixel_reference_setup", {"action": "configure", "settings": {"colors": 8},
                **tokens(state), "expected_reference_revision": stale_ref})
            assert stale.isError and stale.structuredContent["code"] == "REFERENCE_CONFLICT"
            state = data(await first.call_tool("pixel_edit", {"ops": [{"op": "pixel", "x": 1, "y": 1, "color": 1}], **tokens(state)}))
            protected = await first.call_tool("pixel_redraw_begin", {**tokens(state), "expected_reference_revision": ref["reference_revision"]})
            assert protected.isError and protected.structuredContent["code"] == "UNSAVED_CHANGES"
            state = data(await first.call_tool("pixel_project", {"action": "save", "path": "projects/original.pixloom"}))
            state = data(await first.call_tool("pixel_redraw_begin", {**tokens(state), "expected_reference_revision": ref["reference_revision"], "name": "Default automatic conversion"}))
            assert len(state["layers"]) == 1 and state["layers"][0]["id"] == "sampling-draft"
            assert not state["layers"][0]["locked"] and state["layers"][0]["visible"]
            state = data(await second.call_tool("pixel_project", {"action": "save", "path": "projects/draft.pixloom"}))
            ref = data(await first.call_tool("pixel_reference", {"view": "status"}))
            assert ref["style_reference_source"] == "project_embedded"
            cleared = data(await first.call_tool("pixel_reference_setup", {"action": "clear", "role": "style",
                **tokens(state), "expected_reference_revision": ref["reference_revision"]}))
            ref = data(await second.call_tool("pixel_reference", {"view": "status"}))
            assert ref["style_reference"] is None and ref["style_reference_source"] is None
            ref = data(await second.call_tool("pixel_reference_setup", {"action": "load", "role": "style", "path": "style.png",
                **tokens(cleared), "expected_reference_revision": ref["reference_revision"]}))
            state = data(await first.call_tool("pixel_project", {"action": "save"}))
            state = data(await first.call_tool("pixel_redraw_begin", {**tokens(state), "expected_reference_revision": ref["reference_revision"], "mode": "redraw", "name": "Reference redraw test"}))
            assert state["unsaved_changes"] and len(state["layers"]) == 4
            ref = data(await first.call_tool("pixel_reference", {"view": "status"}))
            before = state["revision"]
            dry = await first.call_tool("pixel_reference", {"proposed_ops": REDRAW, **tokens(state), "expected_reference_revision": ref["reference_revision"]})
            assert data(dry)["dry_run"] and "proposed_redraw" in data(dry)["image_roles"]
            assert data(await second.call_tool("pixel_status", {}))["revision"] == before
            state = data(await first.call_tool("pixel_edit", {"ops": REDRAW, **tokens(state), "label": "Native reference redraw"}))
            comparison = await second.call_tool("pixel_reference", {})
            assert data(comparison)["current_project_has_same_subject"]
            ref = data(comparison)
            adjusted = data(await second.call_tool("pixel_reference_setup", {"action": "configure", "settings": {"saturation": 0.6},
                **tokens(state), "expected_reference_revision": ref["reference_revision"]}))
            assert adjusted["revision"] > state["revision"]
            state = data(await first.call_tool("pixel_history", {"action": "undo", **tokens(adjusted)}))
            assert state["reference_workflow"]["settings"]["saturation"] == 1.0
            state = data(await first.call_tool("pixel_project", {"action": "save", "path": "projects/redraw.pixloom"}))
            exported = data(await first.call_tool("pixel_export", {"path": "exports/redraw.png", "draft": True}))
            assert exported["delivery_status"]=="unreviewed_draft"
            with Image.open(exported["path"]) as image:
                assert image.getpixel((0, 0))[3] == 0 and image.getbbox()
            source.unlink()
            data(await first.call_tool("pixel_project", {"action": "open", "path": "projects/original.pixloom"}))
            state = data(await first.call_tool("pixel_project", {"action": "open", "path": "projects/redraw.pixloom"}))
            restored = await first.call_tool("pixel_reference", {})
            assert len([c for c in restored.content if c.type == "image"]) == 4
            assert (await first.get_prompt("redraw_reference", {})).messages
            if artifacts:
                import shutil
                target = Path(artifacts)
                target.mkdir(parents=True, exist_ok=True)
                for role, content in zip(data(restored)["image_roles"], [c for c in restored.content if c.type == "image"]):
                    (target/(role+".png")).write_bytes(base64.b64decode(content.data))
                shutil.copy2(workspace/"projects/redraw.pixloom", target/"redraw.pixloom")
            print(json.dumps({"ok": True, "clients": 2, "tools": len(listed.tools), "checks": ["source/style image import",
                "typed settings", "reference conflict", "optional style/source/clear synchronized across clients", "original artwork preservation", "unsaved protection", "default editable automatic draft", "explicit layered redraw",
                "read-only proposed comparison", "native redraw", "editable setting undo", "transparent export", "portable embedded references", "redraw prompt"]}, indent=2))
        from pixel_workbench.cli import Client
        client = Client(home/"runtime/session.json")
        client.mutate("/shutdown")
        for _ in range(100):
            if not (home/"runtime/session.json").exists():
                break
            await asyncio.sleep(.05)
        assert not (home/"runtime/session.json").exists()
        from tests import cleanup_runtime
        await cleanup_runtime(root)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else None))
