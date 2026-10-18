"""Widget/handler smoke test in an isolated, withdrawn Tk window. Requires Tk/display."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-gui-") as folder:
        os.environ["PIXEL_LOOM_HOME"] = str(Path(folder) / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(Path(folder) / "workspace")
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.guidance import STARTER
        from pixel_workbench.model import Document
        from unittest.mock import patch
        from types import SimpleNamespace
        root = tk.Tk()
        root.withdraw()
        editor = Editor(root)
        callback_errors = []
        root.report_callback_exception = lambda *args: callback_errors.append(str(args[1]))
        try:
            root.update()
            editor.replace_document(Document(32, 32))
            editor.symmetry_var.set("四向对称")
            editor.stroke_size.set(2)
            editor.gesture = {"points": [(3, 4), (6, 8)], "tool": "pen", "revision": editor.doc.revision,
                              "layer": editor.doc.active_layer, "frame": 0}
            before_gesture = editor.doc.fingerprint()
            editor.update_gesture()
            expected_preview = editor.override[1].copy()
            assert editor.doc.fingerprint() == before_gesture
            editor.pointer_up(SimpleNamespace(x=editor.origin[0]+6*editor.zoom,
                                              y=editor.origin[1]+8*editor.zoom))
            assert editor.doc.layer().cels[0].tobytes() == expected_preview.tobytes()
            editor.undo()
            editor.symmetry_var.set("关闭对称")
            editor.stroke_size.set(1)
            assert editor.apply(STARTER, "native drawing")
            editor.choose_tool("polygon")
            editor.path_points = [(2, 2), (4, 2), (3, 5)]
            path_revision = editor.doc.revision
            editor.finish_path()
            assert not editor.path_points and editor.doc.revision == path_revision+1
            editor.apply([{"op": "selection_set", "rect": [1, 1, 5, 5]}], "select")
            editor.copy_selection()
            assert editor.clipboard_image.size == (5, 5)
            editor.paste_selection()
            editor.rotate_selection()
            editor.apply([{"op": "selection_set"}, {"op": "frame_add"},
                          {"op": "tag_set", "name": "idle", "start": 0, "end": 1}], "animate")
            editor.tag_var.set("idle")
            preview_fingerprint = editor.doc.fingerprint()
            preview_revision = editor.doc.revision
            preview_history = len(editor.doc.undo_stack)
            editor.set_playback_speed("0.5×")
            assert editor.playback_delay(150) == 300
            editor.toggle_play()
            slow_job = editor.playback_job
            editor.set_playback_speed("2×")
            assert editor.playback_job != slow_job and editor.playback_delay(150) == 75
            assert slow_job not in root.tk.splitlist(root.tk.call("after", "info"))
            assert editor.service.view["playback_rate"] == 2
            editor.set_playback_speed("nan×")
            assert editor.playback_rate == 2 and editor.playback_speed.get() == "2×"
            assert editor.doc.fingerprint() == preview_fingerprint
            assert editor.doc.revision == preview_revision and len(editor.doc.undo_stack) == preview_history
            editor.play_tick()
            editor.stop_play()
            assert not editor.playing
            editor.set_playback_speed("1×")
            before = editor.doc.fingerprint()
            history = len(editor.doc.undo_stack)
            workflow = editor.automation_dialog("float")
            assert workflow.ops and workflow.proposed
            root.update()
            assert editor.doc.fingerprint() == before and len(editor.doc.undo_stack) == history
            workflow.preview_mode.set("动画预览")
            workflow.switch_preview()
            root.update()
            assert workflow.animation_job
            assert workflow.commit()
            assert len(editor.doc.undo_stack) == history+1
            assert len(editor.doc.durations) == 10
            editor.undo()
            assert editor.doc.fingerprint() == before
            stale = editor.automation_dialog("duration")
            editor.apply([{"op": "rename", "name": "newer artwork"}], "another writer")
            with patch("pixel_workbench.ui.messagebox.showinfo") as conflict:
                assert not stale.commit()
                conflict.assert_called_once()
            stale.dialog.destroy()
            for kind in ("duration", "duplicate", "outline", "travel"):
                planned = editor.automation_dialog(kind)
                root.update()
                assert planned.ops and planned.proposed
                planned.dialog.destroy()
            for callback in (editor.new_dialog, editor.resize_dialog, editor.export_dialog,
                             editor.overview_dialog, editor.command_palette):
                snapshot = editor.doc.fingerprint()
                callback()
                root.update()
                assert editor.doc.fingerprint() == snapshot
                for child in root.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        child.destroy()
            editor.apply([{"op": "palette_add", "colors": [f"#{value:02x}{value:02x}{value:02x}ff" for value in range(252)]}], "full palette")
            assert len(editor.palette_buttons) == len(editor.doc.palette) == 256
            editor.help_dialog()
            editor.connection_dialog()
            root.update()
            connection=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='MCP · Pixel Loom')
            def connection_widgets(parent):
                for widget in parent.winfo_children():yield widget;yield from connection_widgets(widget)
            connection_text=next(w for w in connection_widgets(connection) if isinstance(w,tk.Text)).get('1.0','end')
            assert '--data-dir' in connection_text and '--workspace' in connection_text
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
            import runpy
            ordinary_image = runpy.run_path(str(Path(__file__).with_name("test_reference.py")))["ordinary_image"]
            source = Path(folder) / "ordinary.png"
            ordinary_image(source)
            reference = editor.reference_dialog()
            root.update()
            original = editor.doc.fingerprint()
            with patch("pixel_workbench.reference_ui.filedialog.askopenfilename", return_value=str(source)):
                reference.load("subject")
            root.update()
            assert editor.doc.fingerprint() == original
            reference.variables["width"].set("32")
            reference.variables["height"].set("48")
            reference.variables["colors"].set("12")
            assert reference.flush()
            assert editor.service.references.context["settings"]["width"] == 32
            assert "subject" in reference.photos and "draft" in reference.photos
            assert str(reference.style_view_button.cget("state")) == "disabled"
            assert "不自带" in reference.style_label.cget("text")
            with patch("pixel_workbench.reference_ui.filedialog.askopenfilename", return_value=str(source)):
                reference.load("style")
            root.update()
            assert str(reference.style_clear_button.cget("state")) == "normal"
            assert reference.style_import_button.cget("text") == "替换风格图"
            reference.show_style()
            root.update()
            assert reference.style_window and reference.style_window.winfo_exists()
            assert reference.clear_style()
            root.update()
            assert reference.style_window is None
            assert editor.service.references.context["subject"] and editor.service.references.context["style"] is None
            assert editor.doc.fingerprint() == original
            assert str(reference.style_clear_button.cget("state")) == "disabled"
            with patch.object(root, "clipboard_clear"), patch.object(root, "clipboard_append") as copied:
                reference.copy_prompt()
                assert "pixel_reference" in copied.call_args.args[0]
                assert "mode='draft'" in copied.call_args.args[0]
            editor.path = Path(folder) / "workspace/projects/before-redraw.pixloom"
            assert editor.save()
            assert reference.begin()
            root.update()
            assert editor.doc.reference and editor.dirty and editor.doc.width == 32
            from pixel_workbench.reference import make_draft
            assert len(editor.doc.layers) == 1 and not editor.doc.layer().locked
            assert editor.doc.composite().tobytes() == make_draft(editor.doc.reference)[0].tobytes()
            fingerprint = editor.doc.fingerprint()
            editor.show_reference.set(True)
            editor.render()
            assert editor.doc.fingerprint() == fingerprint
            reference.variables["brightness"].set("1.2")
            assert reference.flush()
            assert editor.doc.reference["settings"]["brightness"] == 1.2
            editor.undo()
            assert editor.service.references.context["settings"]["brightness"] == 1.0
            reference.dialog.destroy()
            assert editor.apply([{"op":"pixel","x":4,"y":6,"color":1}],"quality fixture pixel")
            before_review=editor.doc.fingerprint()
            quality=editor.quality_dialog()
            root.update()
            assert quality.ticket and quality.player_job
            assert editor.doc.fingerprint()==before_review
            first_index=quality.index
            if quality.player_job:
                quality.dialog.after_cancel(quality.player_job)
                quality.player_job=None
            quality.tick()
            assert quality.index==(first_index+1)%len(quality.play_indices)
            quality.step(1)
            assert not quality.playing
            evidence=editor.service.review_evidence({"review_id":quality.ticket["id"]})
            submitted=editor.dispatch("POST","/review/submit",{}, {"review_id":evidence["review_id"],
                "visual_checks":[{"criterion_id":c["id"],"verdict":"pass","reason":"GUI protocol fixture assertion"} for c in evidence["criteria"]],
                "warning_resolutions":[{"warning_id":w["id"],"verdict":"acceptable","reason":"Intentional GUI fixture"} for w in evidence["warnings"]],
                "method":"frames_and_timing","summary":"GUI fixture review","expected_revision":editor.doc.revision,"expected_document_id":editor.doc.id})[0]
            assert submitted["review"]["status"]=="passed"
            quality.render_report()
            assert "通过" in quality.badge.cget("text")
            quality.dialog.destroy()
            quality=editor.quality_dialog()
            root.update()
            assert "通过" in quality.badge.cget("text")
            editor.apply([{"op":"pixel","x":0,"y":0,"color":7}],"changed after review")
            quality.render_report()
            assert "修改" in quality.badge.cget("text")
            quality.dialog.destroy()
            editor.sync_service()
            expected = {"expected_revision": editor.doc.revision, "expected_document_id": editor.doc.id,
                        "ops": [{"op": "pixel", "x": 0, "y": 0, "color": 1}], "include_preview": False}
            before = editor.doc.revision
            result = editor.dispatch("POST", "/validate", {}, expected)[0]
            assert result["dry_run"] and editor.doc.revision == before
            assert not callback_errors, callback_errors
            print(json.dumps({"ok": True, "native_widgets": True, "checks": ["polygon handler", "selection copy/paste/rotation",
                "tag playback", "all 256 palette entries reachable", "help/recovery dialog", "portable MCP config dialog", "shared-service dry run",
                "read-only workflow previews", "animated preview", "one-undo workflow commit", "stale preview protection",
                "all five workflows", "new/resize/export/overview/command dialogs", "reference import/settings/new project",
                "reference overlay does not alter pixels", "bound reference setting undo", "AI prompt copy",
                "quality evidence/player/report UI", "quality changes become stale", "no Tk callback errors"]}))
        finally:
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
