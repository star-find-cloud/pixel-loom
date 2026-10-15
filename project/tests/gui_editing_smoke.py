"""Regression coverage for editing, viewport, layout and export snapshots.

All documents, preferences and exports belong to an isolated temporary runtime.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-editing-") as folder:
        base = Path(folder)
        os.environ["PIXEL_LOOM_HOME"] = str(base / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(base / "workspace")
        import tkinter as tk
        from PIL import Image
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document

        root = tk.Tk()
        root.withdraw()
        editor = Editor(root)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        root.update()

        def fresh(width=16, height=16):
            editor.replace_document(Document(width, height))
            editor.set_workspace_mode("manual")
            editor.symmetry_var.set("关闭对称")

        def wait_callbacks(milliseconds):
            root.after(milliseconds, root.quit)
            root.mainloop()

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        def button(dialog, text):
            return next(widget for widget in descendants(dialog)
                        if isinstance(widget, tk.Button) and widget.cget("text") == text)

        try:
            fresh()
            editor.apply([{"op": "frame_add", "blank": True}, {"op": "select", "frame": 0}], "frames")
            editor.apply([{"op": "pixel", "x": 1, "y": 1, "color": 7}], "paint")
            editor.undo()
            with patch.object(Document, "to_dict", side_effect=AssertionError("browsing serialized artwork")):
                editor.select_frame(1)
            assert editor.doc.redo_stack
            editor.redo()
            assert editor.doc.composite(0).getpixel((1, 1))[3] == 255
            thumbnails = list(editor.thumb_images)
            editor.apply([{"op": "pixel", "frame": 1, "x": 2, "y": 2, "color": 7}], "changed frame")
            assert editor.thumb_images[0] is thumbnails[0]
            assert editor.thumb_images[1] is not thumbnails[1]

            fresh(8, 8)
            editor.apply([{"op": "palette_set", "colors": ["#ff0000ff"]},
                          {"op": "pixel", "x": 1, "y": 1, "color": 0}], "custom palette")
            editor.choose_tool("eraser")
            event = SimpleNamespace(x=editor.origin[0]+1.5*editor.zoom, y=editor.origin[1]+1.5*editor.zoom)
            editor.pointer_down(event)
            editor.pointer_up(event)
            assert editor.doc.composite().getpixel((1, 1))[3] == 0

            image = Image.new("RGBA", (16, 16))
            image.putdata([(x*16, y*16, 128, 255) for y in range(16) for x in range(16)])
            source = base / "full-color.png"
            image.save(source)
            editor.replace_document(editor.service.import_png(source))
            editor.apply([{"op": "selection_set", "rect": [0, 0, 16, 16]}], "select")
            editor.copy_selection()
            editor.apply([{"op": "clear"}], "clear")
            editor.paste_selection()
            assert not editor.doc.strict_palette
            assert editor.doc.composite().tobytes() == image.tobytes()

            fresh(8, 8)
            editor.dispatch("POST", "/reference/setup", {}, {
                "action": "load", "path": str(source), "include_images": False,
                "expected_document_id": editor.doc.id, "expected_revision": editor.doc.revision,
                "expected_reference_revision": editor.service.references.revision})
            editor.apply([{"op": "pixel", "x": 1, "y": 1, "color": 7}], "dirty")
            reference = editor.reference_dialog()
            root.update_idletasks()
            original_id = editor.doc.id
            with patch("pixel_workbench.app.messagebox.askyesnocancel", return_value=None):
                assert reference.begin() is False
            assert editor.doc.id == original_id
            with patch("pixel_workbench.app.messagebox.askyesnocancel", return_value=False):
                assert reference.begin() is True
            assert editor.doc.id != original_id and editor.doc.reference
            reference.dialog.destroy()
            root.update_idletasks()

            fresh()
            editor.apply([{"op": "frame_add"}, {"op": "frame_add"}, {"op": "select", "frame": 0}], "animation")
            editor.toggle_play()
            editor.play_tick()
            viewed_frame = editor.play_frame
            editor.toggle_play()
            assert not editor.playing and editor.doc.active_frame == viewed_frame
            editor.toggle_play()
            assert editor.play_frame == viewed_frame
            editor.stop_animation()
            assert not editor.playing and editor.doc.active_frame == 0

            fresh(512, 512)
            with patch.object(editor.canvas, "winfo_width", return_value=640), \
                 patch.object(editor.canvas, "winfo_height", return_value=300), \
                 patch.object(editor, "render"):
                editor.fit()
                assert 0 < editor.zoom < 1 and 512*editor.zoom <= 300
                editor.change_zoom(-1)
                assert editor.zoom == .5
                editor.change_zoom(-1)
                assert editor.zoom == .25
                editor.change_zoom(1)
                assert editor.zoom == .5

            with patch.object(editor.editor_dock, "winfo_width", return_value=380), \
                 patch.object(editor.timeline, "winfo_height", return_value=164):
                editor.save_ui_layout()
            preferences = json.loads((base / "data/runtime/ui-layout.json").read_text(encoding="utf-8"))
            assert preferences["dock_width"] == 380 and preferences["timeline_height"] == 164
            editor.set_workspace_mode("preview")
            assert len(editor.editor_panes.panes()) == 1
            editor.set_workspace_mode("manual")
            assert len(editor.editor_panes.panes()) == 2
            assert len(editor.main_panes.panes()) == 2

            fresh()
            export = editor.export_dialog()
            root.update()
            refresh = button(export, "刷新为当前工程")
            assert refresh.cget("state") == "disabled"
            editor.apply([{"op": "pixel", "x": 3, "y": 3, "color": 7}], "new pixels")
            wait_callbacks(650)
            assert refresh.cget("state") == "normal"
            assert any(isinstance(widget, tk.Label) and "工程已更新" in widget.cget("text")
                       for widget in descendants(export))
            refresh.invoke()
            assert refresh.cget("state") == "disabled"
            entries = [widget for widget in descendants(export) if isinstance(widget, tk.Entry)]
            scale_variable = entries[0].cget("textvariable")
            root.setvar(scale_variable, 0)
            wait_callbacks(220)
            export_button = button(export, "选择位置并导出")
            assert export_button.cget("state") == "disabled"
            root.setvar(scale_variable, 1)
            wait_callbacks(220)
            assert export_button.cget("state") == "normal"
            output = base / "fresh-sheet.png"
            with patch("pixel_workbench.ui.filedialog.asksaveasfilename", return_value=str(output)):
                export_button.invoke()
            with Image.open(output) as actual:
                assert actual.convert("RGBA").tobytes() == editor.doc.composite().tobytes()
            root.update()
            assert not errors, errors
            print(json.dumps({"ok": True, "checks": ["browsing preserves redo without pixel serialization",
                "only changed thumbnail refreshed", "transparent eraser with opaque-only palette",
                "256-color PNG paste fidelity", "cancel/discard conversion semantics", "pause/resume/stop",
                "512px canvas fit and fractional zoom", "resizable panes and persisted layout",
                "stale export snapshot refresh", "invalid export disabled", "fresh snapshot export pixels",
                "no Tk callback errors"]}))
        finally:
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
