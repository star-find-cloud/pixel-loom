"""Optional support never gates editor use; needs Tk/display, uses isolated data."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-welcome-") as folder:
        os.environ["PIXEL_LOOM_HOME"] = str(Path(folder) / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(Path(folder) / "workspace")
        import tkinter as tk
        from unittest.mock import patch
        from pixel_workbench.app import Editor
        from pixel_workbench.welcome import SupportOption
        root = tk.Tk()
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        editor = Editor(root)
        try:
            root.update()
            root.deiconify()
            root.after(420, root.quit)
            root.mainloop()
            assert editor.welcome_window and editor.welcome_window.page == "guide"
            editor.welcome_window.enter_button.invoke()
            root.withdraw()
            fingerprint, revision, history = editor.doc.fingerprint(), editor.doc.revision, len(editor.doc.undo_stack)
            welcome = editor.show_welcome()
            root.update()
            assert welcome.page == "guide"
            assert welcome.selected_amount is None and welcome.payment_image_source is None
            assert editor.show_welcome() is welcome
            welcome.support_button.invoke()
            root.update()
            assert welcome.page == "support" and welcome.photo is None
            for amount in (5, 10, 15, 20, 5):
                welcome.amount_buttons[amount].invoke()
                root.update()
                assert welcome.selected_amount == amount
                assert welcome.payment_image_source.name == f"wechat-{amount:02d}.jpg"
                assert welcome.photo is not None and f"{amount:.2f}" in welcome.amount_label.cget("text")
            # MCP remains responsive while the welcome panel is displayed.
            current = editor.dispatch("GET", "/state", {}, {})[0]
            assert current["document_id"] == editor.doc.id
            welcome.support_button.invoke()
            root.update()
            assert welcome.page == "guide"
            welcome.enter_button.invoke()
            root.update()
            assert editor.welcome_window is None and root.winfo_exists()
            # No payment state, artwork change, history step or preference is required.
            assert editor.doc.fingerprint() == fingerprint and editor.doc.revision == revision
            assert len(editor.doc.undo_stack) == history
            welcome = editor.show_welcome()
            welcome.enter()  # Same path used by the window close / Escape bindings.
            assert root.winfo_exists() and editor.welcome_window is None
            # An unavailable receipt image still allows immediate entry.
            with patch("pixel_workbench.welcome.support_options", return_value=(SupportOption(5, Path(folder)/"missing.jpg"),)):
                welcome = editor.show_welcome()
            welcome.support()
            welcome.choose_amount(5)
            root.update()
            assert welcome.photo is None and welcome.payment_image_source is None
            welcome.enter_button.invoke()
            assert editor.welcome_window is None and not errors, errors
            print(json.dumps({"ok": True, "checks": ["automatic startup guide", "two optional startup actions", "5/10/15/20 correct poster switching",
                "back/enter/window close", "no artwork/history/payment gate", "shared service remains responsive",
                "missing QR does not prevent entry", "no Tk callback errors"]}))
        finally:
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.dirty = False
            editor.close()


if __name__ == "__main__":
    main()
