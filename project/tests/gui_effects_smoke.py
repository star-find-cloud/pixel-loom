"""Live isolated effect controls, asynchronous playback, preservation and cleanup."""
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-effects-gui-") as folder:
        os.environ["PIXEL_LOOM_HOME"] = str(Path(folder) / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(Path(folder) / "work")
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        root = tk.Tk()
        root.withdraw()
        editor = Editor(root)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))

        def wait_for(window):
            deadline = time.monotonic() + 20
            while window.ready_sequence != window.sequence and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            assert window.proposed and window.ready_sequence == window.sequence, window.notice.get()

        try:
            doc = Document(24, 24, "Keep this drawing")
            doc.apply([{"op": "pixel", "x": 2, "y": 3, "color": 7}])
            editor.replace_document(doc)
            before = doc.composite().tobytes()
            window = editor.effects_dialog()
            assert editor.effects_dialog() is window
            wait_for(window)
            self_loop = [window.proposed.composite(f).tobytes() for f in range(len(window.proposed.durations))]
            window.vary()
            wait_for(window)
            assert [window.proposed.composite(f).tobytes() for f in range(len(window.proposed.durations))] != self_loop
            window.kind.set("弧形斩击")
            window.frames.set("8")
            window.size.set("32")
            wait_for(window)
            assert window.config["preset"] == "slash" and window.config["frames"] == 8
            window.overview.set(True)
            window.switch_view()
            assert window.tick_job is None and window.photo
            assert editor.doc.id == doc.id and editor.doc.composite().tobytes() == before
            old_review = editor.quality_dialog()
            assert window.commit()
            assert not old_review.dialog.winfo_exists()
            assert editor.doc.id != doc.id and editor.doc.effect_recipe["settings"]["preset"] == "slash"
            retained = next(p for p in editor.service.projects.listing() if p["document_id"] == doc.id)
            assert Document.open(retained["path"]).composite().tobytes() == before
            reopened = editor.effects_dialog()
            assert reopened.kind.get() == "弧形斩击" and reopened.frames.get() == "8"
            assert reopened.duration.get() == editor.doc.durations[0]
            reopened.size.set("128")
            reopened.frames.set("32")
            reopened.kind.set("爆炸火花")
            reopened.build()
            reopened.close()
            for _ in range(10):
                root.update()
                time.sleep(.02)
            assert not errors, errors
            assert reopened.poll_job is None and reopened.tick_job is None
            print(json.dumps({"ok": True, "checks": ["single visual entry", "background preview", "seed variation", "preset and frame controls", "all-frame overview", "source art intact", "independent saved project", "recipe restored", "safe close during build"]}))
        finally:
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
