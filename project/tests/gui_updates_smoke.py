"""Isolated Tk update checks, thread lifecycle, notification and browser-link tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import Mock, patch


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-loom-updates-gui-") as folder:
        base = Path(folder)
        os.environ["PIXEL_LOOM_HOME"] = str(base / "data")
        os.environ["PIXEL_LOOM_WORKSPACE"] = str(base / "workspace")
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.update_ui import UpdateController
        from pixel_workbench.updates import UpdateError, expected_download_url, select_release
        from tests.test_updates import release_data

        root = tk.Tk()
        root.withdraw()
        editor = Editor(root)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        editor.updates.close()
        latest = select_release([release_data("v0.7.8", preview=True, body="# New editor\nUpdated tools")])
        current = select_release([release_data("v0.7.7")])
        entered, release_worker = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        observed_threads = []

        def slow_fetch(include):
            observed_threads.append(threading.get_ident())
            entered.set()
            if not release_worker.wait(4):
                raise TimeoutError("fixture timed out")
            return latest

        def pump_until(predicate):
            end = time.monotonic() + 5
            while not predicate() and time.monotonic() < end:
                root.update()
                time.sleep(.01)
            assert predicate(), "Update fixture did not finish"
            root.update()

        controller = UpdateController(editor, fetcher=slow_fetch, current_version="0.7.7", clock=lambda: 1_000_000)
        editor.updates = controller
        try:
            before = editor.doc.to_dict()
            with patch("pixel_workbench.update_ui.webbrowser.open") as browser:
                dialog = editor.show_updates()
                pump_until(entered.is_set)
                assert controller.busy and dialog.check_button.cget("state") == "disabled"
                responsive = []
                root.after(1, lambda: responsive.append(True))
                pump_until(lambda: bool(responsive))
                assert len(observed_threads) == 1 and observed_threads[0] != main_thread
                assert controller.check() is False, "Concurrent checks must coalesce"
                assert not browser.called
                release_worker.set()
                pump_until(lambda: not controller.busy)
                assert "发现新版本" in dialog.status.cget("text")
                assert "测试版" in dialog.status.cget("text")
                assert dialog.download_button.cget("state") == "normal"
                assert controller.banner is not None and controller.banner.winfo_manager() == "pack"
                assert editor.doc.to_dict() == before
                dialog.download_button.invoke()
                browser.assert_called_once_with(expected_download_url("v0.7.8"), new=2)
                dialog.open_release()
                assert browser.call_args.args[0] == latest.page_url

                controller.fetcher = lambda include: latest if include else current
                dialog.previews.set(False)
                dialog.change_preference("include_prereleases", False)
                pump_until(lambda: not controller.busy)
                assert "最新发布版本" in dialog.status.cget("text")
                assert dialog.download_button.cget("state") == "disabled"
                assert not controller.banner.winfo_manager()
                dialog.automatic.set(False)
                dialog.change_preference("check_on_startup", False)
                saved = json.loads(controller.settings_path.read_text(encoding="utf-8"))
                assert saved == {"check_on_startup": False, "include_prereleases": False, "last_checked": 1_000_000}

                def offline(include):
                    raise UpdateError("无法连接更新服务，请打开发版页面。")
                controller.fetcher = offline
                stamp = controller.preferences["last_checked"]
                controller.check()
                pump_until(lambda: not controller.busy)
                assert "无法连接" in dialog.status.cget("text")
                assert dialog.check_button.cget("state") == "normal"
                assert dialog.download_button.cget("state") == "disabled"
                assert controller.preferences["last_checked"] == stamp
                dialog.open_release()
                assert browser.call_args.args[0].endswith("/pixel-loom/releases")
                browser.return_value = False
                dialog.open_release()
                assert "无法打开浏览器" in dialog.status.cget("text")
                browser.return_value = True

                controller.fetcher = lambda include: select_release([release_data("v0.7.8", asset=False)])
                controller.check()
                pump_until(lambda: not controller.busy)
                assert "便携包暂未提供" in dialog.status.cget("text")
                assert dialog.download_button.cget("state") == "disabled"
                dialog.open_release()
                assert browser.call_args.args[0].endswith("/releases/tag/v0.7.8")

                fetch = Mock(return_value=latest)
                controller.fetcher = fetch
                with patch.object(root, "winfo_viewable", return_value=True):
                    controller.startup()
                    assert not fetch.called, "Disabled automatic checks must not access the network"
                    controller.configure("check_on_startup", True)
                    controller.startup()
                    assert not fetch.called, "Successful checks must be cached for 24 hours"
                    controller.preferences["last_checked"] = 0
                    controller.startup()
                pump_until(lambda: not controller.busy)
                assert fetch.call_count == 1
                controller.snooze()
                assert not controller.banner.winfo_manager()
                assert editor.doc.to_dict() == before and not editor.dirty

                controller.close()
                restored = UpdateController(editor, fetcher=fetch, current_version="0.7.7", clock=lambda: 1_000_000)
                editor.updates = restored
                assert restored.preferences["include_prereleases"] is False
                assert restored.preferences["last_checked"] == 1_000_000
                assert restored.preferences["check_on_startup"] is True
                restored.close()
                restored.settings_path.write_text(json.dumps({"last_checked": 10**400,
                    "include_prereleases": None, "check_on_startup": "false"}), encoding="utf-8")
                invalid_settings = UpdateController(editor, fetcher=fetch, current_version="0.7.7")
                assert invalid_settings.preferences == {"check_on_startup": True, "include_prereleases": True, "last_checked": 0}
                invalid_settings.close()

                waiting, finish = threading.Event(), threading.Event()
                def waiting_fetch(include):
                    waiting.set()
                    finish.wait(3)
                    return latest
                closing = UpdateController(editor, fetcher=waiting_fetch, current_version="0.7.7")
                editor.updates = closing
                closing.check()
                pump_until(waiting.is_set)
                closing.close()
                finish.set()
                closing.worker.join(3)
                root.update()
                assert closing.poll_job is None and closing.startup_job is None and closing.map_binding is None
                assert closing.banner is None and not closing.worker.is_alive()
                assert not errors, errors
            assert not list((base / "workspace/exports").glob("*.zip"))
            print(json.dumps({"ok": True, "checks": ["manual update entry", "network runs off Tk thread",
                "editing stays responsive", "checks coalesce", "new-version banner and preview badge",
                "trusted download and release-page links on explicit clicks", "no document/history mutation",
                "stable/preview channels", "persisted preferences", "offline fallback and retry",
                "missing Windows package fallback", "opt-out and daily cache", "snooze",
                "safe shutdown during network request", "no Tk callback errors"]}))
        finally:
            release_worker.set()
            editor.dirty = False
            editor.saved_fingerprint = editor.doc.fingerprint()
            editor.close()


if __name__ == "__main__":
    main()
