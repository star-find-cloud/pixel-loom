"""Compact native workspace: reachable controls, dedicated panels and responsive canvas."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-layout-") as folder:
        os.environ["PIXEL_LOOM_HOME"] = str(Path(folder)/"data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(Path(folder)/"work")
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        root=tk.Tk();root.withdraw();editor=Editor(root)
        root.after_cancel(editor.welcome_job);editor.welcome_job=None
        editor.updates.preferences["check_on_startup"]=False
        errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        try:
            editor.replace_document(Document(32,32,"Layout fixture"))
            editor.apply([{"op":"layer_add","id":f"layer-{i}","name":f"Layer {i}"} for i in range(63)]+
                [{"op":"frame_add","blank":True} for _ in range(47)]+
                [{"op":"palette_set","colors":[f"#{i:02x}1020ff" for i in range(256)]}],"large workspace")
            editor.set_workspace_mode("manual")
            root.deiconify()
            for width,height in ((1160,760),(1460,980),(1160,800)):
                root.geometry(f"{width}x{height}+20+20")
                root.after(150,root.quit);root.mainloop();root.update()
                assert len(editor.control_notebook.tabs())==3
                assert [editor.control_notebook.tab(t,"text") for t in editor.control_notebook.tabs()]==["图层","调色","操作"]
                assert editor.layers_widget.winfo_height()>150
                assert not editor.palette_frame.winfo_viewable()
                assert editor.layers_widget.vertical_scrollbar.winfo_ismapped()
                editor.layers_widget.yview_moveto(1)
                assert editor.layers_widget.bbox(63) is not None
                for button in editor.mode_buttons.values():
                    assert button.winfo_ismapped() and button.winfo_width()>=button.winfo_reqwidth()
                    assert button.winfo_rootx()+button.winfo_width()<=editor.header.winfo_rootx()+editor.header.winfo_width()
                assert editor.frame_info.winfo_width()>=editor.frame_info.winfo_reqwidth()
                assert editor.timing_hint.winfo_width()>=editor.timing_hint.winfo_reqwidth()
                assert editor.canvas.winfo_height()>300
            before=editor.doc.to_dict()
            editor.control_notebook.select(editor.palette_page);root.update()
            assert editor.palette_frame.winfo_viewable() and not editor.layers_widget.winfo_viewable()
            editor.set_workspace_mode("preview");root.update()
            preview_width=editor.canvas.winfo_width()
            assert len(editor.editor_panes.panes())==1 and not editor.tool_rail.winfo_ismapped()
            assert not editor.canvas_settings.winfo_ismapped()
            editor.set_workspace_mode("manual");root.update()
            assert editor.control_notebook.select()==editor.palette_page
            assert editor.canvas.winfo_width()<preview_width and editor.canvas_settings.winfo_ismapped()
            editor.set_workspace_mode("feedback");root.update()
            assert editor.feedback_toolbar.winfo_ismapped() and not editor.editor_dock.winfo_ismapped()
            assert not editor.canvas_settings.winfo_ismapped()
            editor.set_workspace_mode("manual");root.update()
            assert not editor.feedback_toolbar.winfo_ismapped()
            assert editor.doc.to_dict()==before,"Switching layouts changed artwork or history"
            editor.duration_var.set(140);editor.apply_duration()
            assert editor.doc.durations[editor.doc.active_frame]==140
            editor.undo();assert editor.doc.durations[editor.doc.active_frame]==160
            editor.opacity_var.set(128);editor.apply_opacity()
            assert editor.doc.layer().opacity==128
            editor.undo();assert editor.doc.layer().opacity==255
            assert not errors,errors
            print(json.dumps({"ok":True,"checks":["compact header controls fit small and large windows",
                "dedicated layers/colors/operations pages","64 layers visible by scroll without palette obstruction",
                "256 palette remains independent","48-frame timeline controls fit",
                "canvas remains usable at 1160x760","preview and feedback hide editing panels",
                "return to drawing remembers palette tab","mode switches preserve all artwork/history",
                "relocated duration and opacity edits remain undoable","no Tk callback errors"]}))
        finally:
            editor.saved_fingerprint=editor.doc.fingerprint();editor.dirty=False;editor.close()


if __name__=="__main__":main()
