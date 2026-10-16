"""Isolated live Tk workflow, including asynchronous scan, stale guard and reversible cleanup."""
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-character-gui-") as folder:
        os.environ["PIXEL_LOOM_HOME"] = str(Path(folder) / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(Path(folder) / "work")
        import tkinter as tk
        from pixel_workbench.app import Editor
        from tests.test_character_motion import sprite
        root = tk.Tk()
        root.withdraw()
        editor = Editor(root)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        try:
            editor.replace_document(sprite())
            window = editor.character_dialog()
            root.update()
            assert editor.character_dialog() is window
            pose = editor.doc.character["pose"].copy()
            window.name.set("Hero GUI")
            window.save_settings()
            assert editor.doc.character["name"] == "Hero GUI"
            assert editor.doc.character["pose"] == pose
            editor.apply([{"op": "pixel", "frame": 1, "x": 23, "y": 24, "color": 7}], "orphan fixture")
            window.tabs.select(1)
            window.run_check()
            deadline = time.monotonic() + 20
            while window.running and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert not window.running and window.report
            finding_index = next(i for i, f in enumerate(window.report["findings"]) if f["kind"] == "orphan_pixels")
            window.tree.selection_set(str(finding_index))
            root.update()
            window.select_finding()
            assert editor.doc.active_frame == 1
            assert str(window.clean_button["state"]) == "normal"
            window.clean_selected()
            assert editor.doc.composite(1).getpixel((23, 24))[3] == 0
            editor.undo()
            assert editor.doc.composite(1).getpixel((23, 24))[3] == 255
            editor.apply([{"op": "pixel", "frame": 1, "x": 24, "y": 24, "color": 7}], "new edit")
            before = editor.doc.fingerprint()
            window.clean_selected()
            assert editor.doc.fingerprint() == before
            window.run_check()
            window.close()  # Closing during a worker must not call destroyed Tk widgets.
            for _ in range(10):
                root.update()
                time.sleep(0.02)
            assert window.poll_job is None and not errors, errors
            print(json.dumps({"ok": True, "checks": ["single on-demand dialog", "settings preserve pose", "background scan", "select jumps exact frame", "evidence displayed", "one undo repair", "stale repair blocked", "close during scan without Tk errors"]}))
        finally:
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
