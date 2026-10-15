"""Isolated Tk + real stdio MCP exercise of the human canvas-feedback workflow.

The window stays withdrawn and all project/runtime paths are temporary. No
default user project, clipboard, running desktop or external AI is touched.
"""
import asyncio
from concurrent.futures import Future
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


class MCPWorker:
    """One persistent official MCP client; Tk remains on the main thread."""
    def __init__(self, home, work):
        self.home, self.work = home, work
        self.requests = queue.Queue()
        self.ready = Future()
        self.thread = threading.Thread(target=self.run, daemon=True, name="feedback-mcp-fixture")
        self.thread.start()

    def run(self):
        async def connect():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable, args=["-m", "pixel_workbench", "--mcp",
                "--data-dir", str(self.home), "--workspace", str(self.work)], cwd=str(self.work))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.ready.set_result(True)
                    while True:
                        request = await asyncio.to_thread(self.requests.get)
                        if request is None:
                            return
                        name, arguments, future = request
                        try:
                            future.set_result(await session.call_tool(name, arguments))
                        except Exception as exc:
                            future.set_exception(exc)
        try:
            asyncio.run(connect())
        except Exception as exc:
            if not self.ready.done():
                self.ready.set_exception(exc)
            else:
                self.requests.put(("WORKER_ERROR", exc, None))

    @staticmethod
    def wait(root, future, timeout=20):
        deadline = time.monotonic()+timeout
        while not future.done():
            root.update()
            if time.monotonic() > deadline:
                raise TimeoutError("Isolated MCP/Tk request did not finish")
            time.sleep(.005)
        return future.result()

    def call(self, root, name, **arguments):
        self.wait(root, self.ready)
        future = Future()
        self.requests.put((name, arguments, future))
        response = self.wait(root, future)
        assert not response.isError, response.structuredContent
        return response

    def close(self, root):
        self.requests.put(None)
        deadline = time.monotonic()+10
        while self.thread.is_alive() and time.monotonic() < deadline:
            root.update()
            self.thread.join(.01)
        assert not self.thread.is_alive(), "MCP fixture did not close"


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-gui-feedback-") as folder:
        destination = Path(folder)
        home, work = destination/"data", destination/"workspace"
        os.environ["PIXEL_LOOM_HOME"] = str(home)
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(work)
        import tkinter as tk
        from PIL import Image
        from pixel_workbench.app import Editor
        from pixel_workbench.feedback import summary
        from pixel_workbench.model import Document
        root = tk.Tk()
        # PanedWindow allocates its children on the first map. Lay it out
        # invisibly once, then keep the entire fixture withdrawn as before.
        root.attributes("-alpha", 0)
        callback_errors = []
        root.report_callback_exception = lambda *args: callback_errors.append(str(args[1]))
        editor = Editor(root)
        root.update_idletasks()
        root.withdraw()
        client = None
        try:
            root.update()
            assert editor.service.workspace == work.resolve()
            assert editor.service.runtime.is_relative_to(home.resolve())
            editor.replace_document(Document(32, 32, "GUI canvas feedback fixture"))
            base = editor.doc.active_layer
            ops = [{"op": "frame_set", "duration_ms": 120}]
            ops += [{"op": "frame_add", "copy_from": 0} for _ in range(7)]
            for frame in range(8):
                ops += [{"op": "rect", "layer": base, "frame": frame, "x": 8, "y": 8, "width": 9, "height": 16, "color": 18},
                        {"op": "pixel", "layer": base, "frame": frame, "x": 20, "y": 14, "color": 7}]
            ops += [{"op": "tag_set", "name": "idle", "start": 0, "end": 7}, {"op": "select", "frame": 0}]
            assert editor.apply(ops, "Eight-frame native artwork fixture")
            # Compatibility coverage for saved 0.6.0 reports, now an advanced history UI.
            from pixel_workbench.feedback_ui import LegacyFeedbackPanel
            panel = LegacyFeedbackPanel(editor,tk.Frame(root))
            editor.feedback_panel=panel

            def point(x, y):
                return SimpleNamespace(x=editor.origin[0]+(x+.5)*editor.zoom,
                                       y=editor.origin[1]+(y+.5)*editor.zoom)

            def drag(points):
                editor.pointer_down(point(*points[0]))
                for p in points[1:-1]:
                    editor.pointer_drag(point(*p))
                editor.pointer_up(point(*points[-1]))

            def all_pixels():
                return [editor.doc.composite(f).tobytes() for f in range(len(editor.doc.durations))]

            # A preview click or drag cannot accidentally paint.
            assert editor.workspace_mode == "preview"
            before = editor.doc.to_dict()
            drag([(20, 14), (21, 14)])
            assert editor.doc.to_dict() == before and editor.gesture is None
            assert editor.apply([{"op": "selection_set", "rect": [8, 8, 2, 2]}], "Existing selection fixture")
            editor.clipboard_image = Image.new("RGBA", (2, 2), "white")
            editor.clipboard_origin = (0, 0)
            before = editor.doc.to_dict()
            with patch.object(editor, "editing_text", return_value=False):
                editor.keypress(SimpleNamespace(widget=editor.canvas, state=0, keysym="Delete"))
                editor.cut_selection()
                editor.paste_selection()
            assert editor.doc.to_dict() == before, "Preview Delete/cut/paste must not alter old selection"
            assert editor.apply([{"op": "selection_set"}], "Clear existing selection fixture")

            # Human lasso is a transient overlay, then a metadata issue, never paint/undo.
            editor.set_workspace_mode("feedback")
            before_geometry = editor.doc.to_dict()
            for tool, kind in (("feedback_rect", "rect"), ("feedback_ellipse", "ellipse")):
                editor.choose_tool(tool)
                drag([(0, 0), (3, 3)])
                assert editor.feedback_draft["kind"] == kind
                assert editor.doc.to_dict() == before_geometry
                panel.clear_mark()
            editor.choose_tool("feedback_rect")
            panel.scope.set("当前帧")
            drag([(18, 12), (22, 16)])
            editor.select_frame(1)
            assert editor.feedback_draft is None, "Changing frame must clear a single-frame draft instead of reporting the wrong frame"
            for scope in ("当前动作", "全部帧"):
                panel.scope.set(scope)
                drag([(18, 12), (22, 16)])
                draft = deepcopy(editor.feedback_draft)
                editor.select_frame(0 if editor.doc.active_frame else 1)
                assert editor.feedback_draft == draft, "Multi-frame annotations keep their shared canvas coordinates"
                panel.clear_mark()
            editor.select_frame(0)
            editor.choose_tool("feedback_lasso")
            before_pixels = all_pixels()
            before_revision = editor.doc.revision
            before_history = len(editor.doc.undo_stack)
            drag([(18, 12), (22, 12), (22, 16), (18, 16), (18, 12)])
            assert editor.feedback_draft["kind"] == "lasso"
            assert editor.doc.revision == before_revision
            assert all_pixels() == before_pixels and len(editor.doc.undo_stack) == before_history
            assert editor.canvas.find_withtag("feedback")
            panel.scope.set("全部帧")
            panel.description.insert("1.0", "第1到8帧，右侧裙边有独立亮点，请逐帧看。")
            panel.submit()
            root.update()
            assert len(editor.doc.feedback) == 1
            issue_id = editor.doc.feedback[0]["id"]
            assert editor.doc.feedback[0]["frames"] == list(range(8))
            assert all_pixels() == before_pixels and len(editor.doc.undo_stack) == before_history
            original = deepcopy(editor.doc.feedback[0]["original"])

            # Real MCP reaches the SAME isolated GUI bridge and asks, without inventing a reply.
            client = MCPWorker(home, work)
            state = client.call(root, "pixel_status").structuredContent
            assert state["document_id"] == editor.doc.id
            client.call(root, "pixel_feedback", action="ask", issue_id=issue_id,
                        text="你指的是右裙边外面独立的白色亮点，还是裙边本身？",
                        expected_document_id=state["document_id"], expected_revision=state["revision"])
            assert panel.selected()["status"] == "needs_clarification"
            assert panel.reply_frame.winfo_manager() == "pack"
            panel.reply_text.insert("1.0", "是右边独立的白点，裙边本身保留。")
            panel.reply()
            state = client.call(root, "pixel_status").structuredContent
            assert state["feedback"]["issues"][0]["questions"][0]["answer"] == "是右边独立的白点，裙边本身保留。"
            assert editor.doc.feedback[0]["questions"][0]["answered_by"] == "手动"
            assert not panel.reply_text.get("1.0", "end").strip()

            # Manual canvas brush removes the defect in each frame. Undo restores paint only.
            editor.set_workspace_mode("manual")
            editor.choose_tool("eraser")
            for frame in range(8):
                editor.select_frame(frame)
                drag([(20, 14), (20, 14)])
                assert editor.doc.composite(frame).getpixel((20, 14))[3] == 0
                assert editor.doc.composite(frame).getpixel((12, 14))[3] == 255
            editor.undo()
            assert editor.doc.composite(7).getpixel((20, 14))[3] == 255
            assert editor.doc.feedback[0]["questions"][0]["answer"]
            editor.redo()
            assert editor.doc.composite(7).getpixel((20, 14))[3] == 0

            evidence = client.call(root, "pixel_feedback", action="inspect", issue_id=issue_id).structuredContent
            for page in range(1, evidence["page_count"]):
                client.call(root, "pixel_feedback", action="inspect", issue_id=issue_id,
                            inspection_id=evidence["inspection_id"], page=page)
            assert all(f"frame:{f}:current_crop" in evidence["image_roles"] for f in range(8))
            assert all(d["changed_pixels_in_shape"] == 1 for d in evidence["differences"])
            panel.manual_resolve()
            assert summary(editor.doc)["pending_count"] == 0
            assert editor.doc.feedback[0]["resolution"]["resolved_by"] == "手动"
            assert "不等同于 AI" in editor.doc.feedback[0]["resolution"]["explanation"]

            # A later real paint edit invalidates closure instead of silently retaining a pass.
            editor.select_frame(3)
            editor.choose_tool("pen")
            editor.select_color(7)
            drag([(20, 14), (20, 14)])
            assert summary(editor.doc)["issues"][0]["resolution_stale"]
            assert summary(editor.doc)["pending_count"] == 1
            assert "修改后待复查" in panel.queue.get(0)
            assert panel.manual_button.cget("state") == "normal"
            editor.choose_tool("eraser")
            drag([(20, 14), (20, 14)])
            panel.manual_resolve()
            assert summary(editor.doc)["pending_count"] == 0

            # Locate one-frame report and ensure marks follow the shown frame.
            editor.set_workspace_mode("feedback")
            editor.choose_tool("feedback_ellipse")
            drag([(4, 4), (7, 7)])
            panel.scope.set("当前帧")
            panel.description.insert("1.0", "单帧定位测试")
            panel.submit()
            second_id = panel.selected_id
            assert editor.doc.feedback[-1]["frames"] == [3]
            editor.select_frame(0)
            panel.locate()
            assert editor.doc.active_frame == 3 and editor.feedback_focus == second_id
            assert editor.canvas.find_withtag("feedback")
            editor.select_frame(0)
            assert not editor.canvas.find_withtag("feedback")
            editor.select_frame(3)
            editor.toggle_play()
            editor.play_tick()
            assert editor.play_frame != 3
            assert not editor.canvas.find_withtag("feedback"), "Frame-3 annotation must not overlay a different playback frame"
            editor.stop_play()

            # Changed canvas coordinates cannot be falsely resolved; user may close and re-mark.
            assert editor.apply([{"op": "canvas_resize", "width": 40, "height": 40}], "Intentional canvas change")
            panel.manual_resolve()
            assert summary(editor.doc)["issues"][-1]["status"] != "resolved"
            assert "Annotation" in panel.notice.cget("text") or "scope" in panel.notice.cget("text").lower()
            with patch("pixel_workbench.feedback_ui.simpledialog.askstring", return_value="画布尺寸已改，关闭旧单后重新标记。"):
                panel.dismiss()
            assert editor.doc.feedback[-1]["status"] == "dismissed"
            assert editor.doc.feedback[-1]["resolution"] is None
            assert editor.doc.feedback[0]["original"] == original

            project = work/"projects/canvas-feedback.pixloom"
            with patch("pixel_workbench.app.filedialog.asksaveasfilename", return_value=str(project)):
                assert editor.save()
            saved_pixels = all_pixels()
            with patch("pixel_workbench.app.filedialog.askopenfilename", return_value=str(project)):
                editor.open_dialog()
            assert all_pixels() == saved_pixels
            assert editor.doc.feedback[0]["original"] == original
            assert editor.doc.feedback[0]["questions"][0]["answer"] == "是右边独立的白点，裙边本身保留。"
            assert editor.doc.feedback[-1]["dismissal"]["reason"] == "画布尺寸已改，关闭旧单后重新标记。"
            assert not callback_errors, callback_errors
            assert root.state() == "withdrawn"
            print(json.dumps({"ok": True, "real_mcp_gui": True, "frames": 8, "checks": [
                "preview pointer/Delete/cut/paste cannot paint", "rect/ellipse/lasso overlays never change pixels or paint history", "eight-frame portable report",
                "real MCP asks same live GUI", "human reply persists", "manual brush repair and paint-only undo",
                "all annotated frame images", "manual resolution is not AI acceptance", "new pixels reopen stale resolution",
                "single-frame draft cleared on switch; multi-frame draft retained", "single-frame locate and playback marker visibility", "changed canvas refuses false resolution",
                "user closes obsolete issue", "mocked save/open preserves snapshots and answers", "withdrawn isolated window"]}))
        finally:
            if client:
                client.close(root)
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
