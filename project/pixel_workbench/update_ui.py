"""Nonblocking desktop release notifications; downloads open only on a user click."""
from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
import webbrowser

from . import __version__
from .model import atomic_json
from .paths import RUNTIME
from .ui import BG, PANEL, FG, MUTED, ACCENT, GREEN, SMALL, place_dialog
from .updates import CHECK_INTERVAL, RELEASES_URL, Version, fetch_latest, valid_download_url


class UpdateController:
    def __init__(self, editor, fetcher=fetch_latest, current_version=__version__, clock=time.time):
        self.editor, self.root = editor, editor.root
        self.fetcher, self.current_version, self.clock = fetcher, current_version, clock
        self.current = Version.parse(current_version)
        self.settings_path = RUNTIME / "update-preferences.json"
        self.preferences = {"check_on_startup": True, "include_prereleases": self.current.core[0] == 0,
                            "last_checked": 0}
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("check_on_startup", "include_prereleases"):
                    if type(data.get(key)) is bool:
                        self.preferences[key] = data[key]
                stamp = data.get("last_checked", 0)
                if type(stamp) in (float, int) and 0 <= stamp <= self.clock():
                    self.preferences["last_checked"] = stamp
        except (OSError, ValueError):
            pass
        self.dialog = self.banner = None
        self.release = None
        self.error = None
        self.checked = self.busy = self.closed = False
        self.results = queue.SimpleQueue()
        self.poll_job = None
        self.startup_job = self.root.after(1500, self.startup)
        self.map_binding = self.root.bind("<Map>", self.on_map, add="+")
        self.dismissed_tag = None
        self.worker = None

    def on_map(self, event):
        if event.widget is self.root and not self.closed and self.startup_job is None and not self.busy:
            self.startup_job = self.root.after(1500, self.startup)

    def startup(self):
        self.startup_job = None
        due = self.clock() - self.preferences["last_checked"] >= CHECK_INTERVAL
        if not self.closed and self.root.winfo_viewable() and self.preferences["check_on_startup"] and due:
            self.check()

    def save_preferences(self):
        try:
            atomic_json(self.settings_path, self.preferences)
        except OSError:
            return False
        return True

    def configure(self, key, value):
        if key not in ("check_on_startup", "include_prereleases") or type(value) is not bool:
            raise ValueError("Invalid update preference")
        changed = self.preferences[key] != value
        self.preferences[key] = value
        if changed and key == "include_prereleases":
            self.preferences["last_checked"] = 0
        saved = self.save_preferences()
        if changed and key == "include_prereleases":
            self.dismiss_banner()
            self.check()
        return saved

    def show_dialog(self, check=True):
        if self.closed:
            return None
        if self.dialog is None or not self.dialog.dialog.winfo_exists():
            self.dialog = UpdateDialog(self)
        else:
            self.dialog.dialog.lift()
        self.dialog.render()
        if check:
            self.check()
        return self.dialog

    def check(self):
        if self.closed or self.busy:
            return False
        self.busy, self.error = True, None
        include = self.preferences["include_prereleases"]
        if self.dialog and self.dialog.dialog.winfo_exists():
            self.dialog.render()

        def work():
            try:
                self.results.put((include, self.fetcher(include), None))
            except Exception as exc:
                # Only a bounded, public metadata request runs here. Never touch Tk from this thread.
                from .updates import UpdateError
                message = str(exc) if isinstance(exc, UpdateError) else "检查更新暂时失败，请稍后重试，或打开发版页面。"
                self.results.put((include, None, message))

        self.worker = threading.Thread(target=work, name="pixel-loom-update-check", daemon=True)
        self.worker.start()
        self.poll_job = self.root.after(80, self.poll)
        return True

    def poll(self):
        self.poll_job = None
        if self.closed:
            return
        try:
            include, release, error = self.results.get_nowait()
        except queue.Empty:
            self.poll_job = self.root.after(80, self.poll)
            return
        self.busy = False
        if include != self.preferences["include_prereleases"]:
            self.check()
            return
        self.release, self.error, self.checked = release, error, True
        if not error:
            self.preferences["last_checked"] = self.clock()
            self.save_preferences()
        if self.dialog and self.dialog.dialog.winfo_exists():
            self.dialog.render()
        if self.has_update and self.preferences["check_on_startup"]:
            self.show_banner()
        else:
            self.dismiss_banner()

    @property
    def has_update(self):
        return not self.error and self.release is not None and self.release.version > self.current

    def show_banner(self):
        if self.release.tag == self.dismissed_tag:
            return
        if self.banner is None:
            self.banner = tk.Frame(self.root, bg=PANEL, padx=12, pady=5)
            self.banner_label = self.editor.label(self.banner, "", ACCENT, SMALL)
            self.banner_label.pack(side="left")
            self.editor.button(self.banner, "查看并下载", lambda: self.show_dialog(check=False), True,
                               font=SMALL, pady=3).pack(side="right", padx=4)
            self.editor.button(self.banner, "稍后", self.snooze, font=SMALL, pady=3).pack(side="right")
        suffix = "（测试版）" if self.release.prerelease else ""
        self.banner_label.config(text=f"发现新版本 {self.release.number}{suffix}，可查看更新内容并下载。")
        self.banner.pack(fill="x", after=self.editor.workflow_bar, padx=10, pady=2)

    def dismiss_banner(self):
        if self.banner is not None:
            self.banner.pack_forget()

    def snooze(self):
        self.dismissed_tag = self.release.tag if self.release else None
        self.dismiss_banner()

    def close(self):
        self.closed = True
        for name in ("startup_job", "poll_job"):
            job = getattr(self, name)
            if job:
                self.root.after_cancel(job)
            setattr(self, name, None)
        if self.map_binding:
            self.root.unbind("<Map>", self.map_binding)
            self.map_binding = None
        if self.dialog and self.dialog.dialog.winfo_exists():
            self.dialog.dialog.destroy()
        if self.banner is not None:
            self.banner.destroy()
            self.banner = None


class UpdateDialog:
    def __init__(self, controller):
        self.controller = controller
        editor = controller.editor
        self.dialog = dialog = tk.Toplevel(controller.root)
        dialog.title("检查更新 · Pixel Loom")
        dialog.configure(bg=PANEL)
        dialog.transient(controller.root)
        place_dialog(dialog, controller.root, 720, 570)
        body = tk.Frame(dialog, bg=PANEL, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        editor.label(body, "检查更新", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        editor.label(body, f"当前版本：{controller.current_version}", MUTED, SMALL).pack(anchor="w", pady=(5, 12))
        self.status = editor.label(body, "准备检查更新", ACCENT, SMALL, wraplength=660, justify="left")
        self.status.pack(anchor="w", pady=(0, 9))
        self.notes = tk.Text(body, bg=BG, fg=FG, relief="flat", wrap="word", height=10,
                             font=SMALL, padx=12, pady=10, state="disabled")
        self.notes.pack(fill="both", expand=True)
        self.automatic = tk.BooleanVar(value=controller.preferences["check_on_startup"])
        self.previews = tk.BooleanVar(value=controller.preferences["include_prereleases"])
        editor._check(body, "启动时检查更新（成功检查后 24 小时内不重复）", self.automatic,
                      lambda: self.change_preference("check_on_startup", self.automatic.get())).pack(anchor="w", pady=(10, 0))
        editor._check(body, "包含公开测试版", self.previews,
                      lambda: self.change_preference("include_prereleases", self.previews.get())).pack(anchor="w")
        editor.label(body, "仅向 GitHub 请求公开版本信息，不上传作品、参考图或客户端配置。\n下载会在浏览器中打开；请保存作品后按发布说明更新。",
                     MUTED, SMALL, justify="left").pack(anchor="w", pady=9)
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self.check_button = editor.button(row, "重新检查", controller.check, font=SMALL)
        self.check_button.pack(side="left")
        editor.button(row, "打开发版页面", self.open_release, font=SMALL).pack(side="left", padx=7)
        self.download_button = editor.button(row, "下载 Windows 便携版", self.open_download, True, font=SMALL)
        self.download_button.pack(side="right")
        dialog.bind("<Escape>", lambda event: dialog.destroy())

    def change_preference(self, key, value):
        if not self.controller.configure(key, value):
            self.status.config(text="更新偏好暂时无法保存，下次启动可能恢复默认设置。", fg="#ffb887")

    def render(self):
        controller = self.controller
        release = controller.release
        self.check_button.config(state="disabled" if controller.busy else "normal")
        downloadable = controller.has_update and release.download_url and valid_download_url(release.download_url, release.tag)
        self.download_button.config(state="normal" if downloadable and not controller.busy else "disabled")
        if controller.busy:
            text, color = "正在后台检查版本，可以继续编辑作品……", ACCENT
        elif controller.error:
            text, color = controller.error, "#ffb887"
        elif not controller.checked:
            text, color = "准备检查更新", MUTED
        elif release is None:
            text, color = "暂未找到此渠道的发布版本，可打开发版页面查看。", MUTED
        elif controller.has_update:
            suffix = "（公开测试版）" if release.prerelease else ""
            size = f" · {release.download_bytes/1024/1024:.1f} MB" if release.download_bytes else ""
            text, color = f"发现新版本：{release.number}{suffix}{size}", GREEN
            if not downloadable:
                text += "\nWindows 便携包暂未提供，请查看发布页。"
        elif release.version == controller.current:
            text, color = "当前已是最新发布版本。", GREEN
        else:
            text, color = f"当前版本高于已发布版本 {release.number}，无需更新。", MUTED
        self.status.config(text=text, fg=color)
        notes = release.notes if release else ""
        self.notes.config(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", notes or "版本说明将在检查成功后显示，也可以直接打开发版页面。")
        self.notes.config(state="disabled")

    def open_release(self):
        release = self.controller.release
        self.open_url(release.page_url if release else RELEASES_URL)

    def open_download(self):
        release = self.controller.release
        if self.controller.has_update and release.download_url and valid_download_url(release.download_url, release.tag):
            self.open_url(release.download_url)

    def open_url(self, url):
        try:
            opened = webbrowser.open(url, new=2)
        except (OSError, webbrowser.Error):
            opened = False
        if not opened:
            self.status.config(text="无法打开浏览器，请手动访问发布页：\n" + RELEASES_URL, fg="#ffb887")
