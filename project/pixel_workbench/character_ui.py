"""One on-demand window for reusable designs and visual motion troubleshooting."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from .model import Document, PixelError
from .motion import analyze_motion, evidence
from .quality import content_digest
from .reference import decoded_asset
from .ui import BG, PANEL, FIELD, FG, MUTED, FONT, SMALL, scrollable_widget

VIEW_LABELS = {"front": "正面", "left": "左侧", "right": "右侧", "back": "背面"}
KINDS = {"orphan_pixels": "独立小块", "fixed_region": "固定部位变化", "palette_drift": "颜色偏移",
         "baseline": "底边偏移", "empty_frame": "空白帧", "loop_jump": "循环衔接", "abrupt_change": "帧间突变"}


class CharacterDialog:
    def __init__(self, editor):
        self.editor = editor
        self.dialog = tk.Toplevel(editor.root, bg=BG)
        self.dialog.title("角色与动作 · Pixel Loom")
        left = max(0, min(editor.root.winfo_rootx() + (editor.root.winfo_width() - 860) // 2,
                          editor.root.winfo_screenwidth() - 880))
        top = max(0, min(editor.root.winfo_rooty() + (editor.root.winfo_height() - 700) // 2,
                         editor.root.winfo_screenheight() - 750))
        self.dialog.geometry(f"860x700+{left}+{top}")
        self.dialog.minsize(720, 600)
        self.dialog.transient(editor.root)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        self.dialog.bind("<Destroy>", self.destroyed, add="+")
        self.poll_job = None
        self.running = False
        self.report = None
        self.photos = []
        self.notice = tk.StringVar()
        top = tk.Frame(self.dialog, bg=BG, padx=16, pady=10)
        top.pack(fill="x")
        editor.label(top, "同一角色，保持造型，逐帧查错", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        editor.button(top, "刷新当前工程", self.reload, font=FONT).pack(side="right")
        self.tabs = ttk.Notebook(self.dialog)
        self.tabs.pack(fill="both", expand=True, padx=16)
        design = tk.Frame(self.tabs, bg=PANEL, padx=16, pady=12)
        motion = tk.Frame(self.tabs, bg=PANEL, padx=12, pady=12)
        self.tabs.add(design, text="  角色规范  ")
        self.tabs.add(motion, text="  动作检查  ")
        tk.Label(self.dialog, textvariable=self.notice, bg=BG, fg=MUTED, font=FONT,
                 anchor="w", wraplength=800, padx=16, pady=12).pack(fill="x")
        self.name, self.baseline = tk.StringVar(), tk.StringVar()
        row = tk.Frame(design, bg=PANEL)
        row.pack(fill="x")
        editor.label(row, "角色名").pack(side="left")
        tk.Entry(row, textvariable=self.name, bg=FIELD, fg=FG, insertbackground=FG, font=FONT).pack(side="left", fill="x", expand=True, padx=(8, 16))
        editor.label(row, "落地基准 Y").pack(side="left")
        tk.Entry(row, textvariable=self.baseline, width=5, bg=FIELD, fg=FG, font=FONT).pack(side="left", padx=8)
        editor.label(design, "造型说明（如脸部、配色、衣物特征；AI 会一起读取）", MUTED).pack(anchor="w", pady=(12, 4))
        self.notes = tk.Text(design, height=3, bg=FIELD, fg=FG, insertbackground=FG, font=FONT, wrap="word")
        self.notes.pack(fill="x")
        middle = tk.Frame(design, bg=PANEL)
        middle.pack(fill="both", expand=True, pady=12)
        self.pose_label = tk.Label(middle, bg=BG, fg=MUTED, text="尚未保存基准造型", width=25)
        self.pose_label.pack(side="left", fill="both", expand=True, padx=(0, 16))
        right = tk.Frame(middle, bg=PANEL)
        right.pack(side="left", fill="both", expand=True)
        editor.label(right, "固定部位（可选，最多 8 个）").pack(anchor="w")
        editor.label(right, "只保护此动作中应当不变的区域。", MUTED).pack(anchor="w", pady=(2, 4))
        parts_frame, self.parts = scrollable_widget(right, tk.Listbox, horizontal=True, height=4,
            selectmode="multiple", exportselection=False, bg=FIELD, fg=FG, selectbackground="#36517c", font=FONT)
        parts_frame.pack(fill="x")
        editor.button(right, "把画布选区设为固定部位…", self.add_region).pack(fill="x", pady=6)
        self.role = tk.StringVar(value="左侧")
        refrow = tk.Frame(right, bg=PANEL)
        refrow.pack(fill="x", pady=(10, 4))
        editor.label(refrow, "视角参考").pack(side="left")
        editor._option(refrow, self.role, list(VIEW_LABELS.values())).pack(side="right")
        self.ref_label = editor.label(right, "未提供参考", MUTED)
        self.ref_label.pack(anchor="w")
        self.role.trace_add("write", lambda *_: self.update_reference_label())
        controls = tk.Frame(right, bg=PANEL)
        controls.pack(fill="x", pady=5)
        for label, callback in (("导入…", self.import_reference), ("查看", self.show_reference), ("移除", self.remove_reference)):
            editor.button(controls, label, callback, padx=8).pack(side="left", padx=(0, 5))
        buttons = tk.Frame(design, bg=PANEL)
        buttons.pack(fill="x")
        self.save_button = editor.button(buttons, "保存当前造型", self.save_settings, True)
        self.save_button.pack(side="left")
        editor.button(buttons, "用当前帧更新造型", lambda: self.save_settings(recapture=True)).pack(side="left", padx=6)
        files = tk.Frame(design, bg=PANEL)
        files.pack(fill="x", pady=(10, 0))
        editor.button(files, "导入角色规范…", self.import_profile).pack(side="left")
        editor.button(files, "导出角色规范…", self.export_profile).pack(side="left", padx=6)
        editor.label(files, "随工程保存；更新可撤销。", MUTED).pack(side="right")
        options = tk.Frame(motion, bg=PANEL)
        options.pack(fill="x")
        self.mode = tk.StringVar(value="通用动作")
        editor._option(options, self.mode, ["通用动作", "待机 / 行走（落地）"]).pack(side="left")
        self.check_button = editor.button(options, "检查全部帧", self.run_check, True)
        self.check_button.pack(side="right")
        editor.label(motion, "只提供可疑线索。选一项查看前后帧，再决定是否修改。", MUTED).pack(anchor="w", pady=8)
        listing = tk.Frame(motion, bg=PANEL)
        listing.pack(fill="x")
        style = ttk.Style(self.dialog)
        style.configure("Motion.Treeview", background=BG, fieldbackground=BG, foreground=FG,
                        rowheight=28, font=SMALL, borderwidth=0)
        style.configure("Motion.Treeview.Heading", background=FIELD, foreground=FG, font=SMALL)
        style.map("Motion.Treeview", background=[("selected", "#354b70")], foreground=[("selected", FG)])
        self.tree = ttk.Treeview(listing, columns=("frame", "kind", "message"), show="headings", height=6,
                                 style="Motion.Treeview", selectmode="browse")
        for key, title, width in (("frame", "帧", 50), ("kind", "线索", 110), ("message", "观察提示", 560)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=key == "message")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.select_finding())
        self.detail = editor.label(motion, "检查完成后，这里显示前一帧 / 当前帧 / 后一帧。", MUTED)
        self.detail.pack(anchor="w", pady=6)
        self.evidence_label = tk.Label(motion, bg=BG, fg=MUTED, text="", height=1)
        self.evidence_label.pack(fill="both", expand=True)
        self.clean_button = editor.button(motion, "清理选中小块（可撤销）", self.clean_selected)
        self.clean_button.pack(anchor="e", pady=(8, 0))
        self.clean_button.config(state="disabled")
        self.reload()

    def destroyed(self, event):
        if event.widget == self.dialog and self.poll_job:
            self.editor.root.after_cancel(self.poll_job)
            self.poll_job = None

    def close(self):
        self.dialog.destroy()

    def current(self):
        return self.editor.doc.id == self.doc_id and content_digest(self.editor.doc) == self.digest

    def require_current(self):
        if not self.current():
            raise PixelError("工程已修改或切换，请先点击“刷新当前工程”再操作。")

    def reload(self):
        doc = self.editor.doc
        self.doc_id, self.digest = doc.id, content_digest(doc)
        self.profile = doc.character
        self.name.set(self.profile["name"] if self.profile else doc.name)
        self.baseline.set(str(self.profile["baseline_y"] if self.profile else (doc.composite().getbbox() or [0, 0, 0, doc.height])[3]))
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", self.profile["notes"] if self.profile else "")
        self.parts.delete(0, "end")
        fixed = {p["name"] for p in self.profile["fixed_parts"]} if self.profile else set()
        available = sorted(set(doc.regions) | fixed)
        for i, name in enumerate(available):
            self.parts.insert("end", name)
            if name in fixed:
                self.parts.selection_set(i)
        self.save_button.config(text="保存设置" if self.profile else "保存当前造型")
        self.pose_label.config(image="", text="尚未保存基准造型")
        if self.profile:
            image = decoded_asset(self.profile["pose"]["png"])
            scale = min(6, 220 / image.width, 260 / image.height)
            preview = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
            backing = Image.new("RGBA", preview.size, "#303a4d")
            backing.alpha_composite(preview)
            photo = ImageTk.PhotoImage(backing)
            self.pose_photo = photo
            self.pose_label.config(image=photo, text="")
        self.update_reference_label()
        self.notice.set("角色规范随工程携带；MCP 可直接读取基准造型、色板与各视角参考。")

    def update_reference_label(self):
        role = self.selected_role()
        item = (getattr(self, "profile", None) or {}).get("views", {}).get(role)
        self.ref_label.config(text=(item["name"][:34] if item else "此视角尚未提供参考"))

    def selected_role(self):
        return next(key for key, label in VIEW_LABELS.items() if label == self.role.get())

    def call(self, action, **kwargs):
        self.require_current()
        doc = self.editor.doc
        result, _ = self.editor.dispatch("POST", "/character", {}, {"action": action,
            "expected_document_id": doc.id, "expected_revision": doc.revision, "include_images": False,
            "source": "手动", **kwargs})
        self.reload()
        return result

    def attempt(self, callback):
        try:
            return callback()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            messagebox.showerror("角色与动作", str(exc), parent=self.dialog)
            return None

    def save_settings(self, recapture=False):
        def run():
            settings = {"name": self.name.get().strip(), "notes": self.notes.get("1.0", "end-1c"),
                        "baseline_y": int(self.baseline.get()), "fixed_regions": [self.parts.get(i) for i in self.parts.curselection()]}
            self.call("capture" if recapture or not self.profile else "configure", settings=settings)
            self.notice.set("角色规范已保存，可撤销。AI 修改动作时会读取这一份规范。")
        self.attempt(run)

    def add_region(self):
        def run():
            self.require_current()
            if not self.editor.doc.selection:
                raise PixelError("先在画布中用框选工具选中脸部等固定区域。")
            name = simpledialog.askstring("固定部位", "给这个部位取名（如：脸部）", parent=self.dialog)
            if not name:
                return
            if self.editor.apply([{"op": "region_define", "name": name, "rect": self.editor.doc.selection}], "定义固定部位"):
                self.reload()
                names = list(self.parts.get(0, "end"))
                self.parts.selection_set(names.index(name))
                self.notice.set("区域已选中，点击“保存设置”将它加入角色规范。")
        self.attempt(run)

    def import_reference(self):
        path = filedialog.askopenfilename(parent=self.dialog, title="导入视角参考", filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")])
        if path:
            self.attempt(lambda: self.call("reference_load", role=self.selected_role(), path=path))

    def remove_reference(self):
        self.attempt(lambda: self.call("reference_clear", role=self.selected_role()))

    def show_reference(self):
        def run():
            self.require_current()
            item = (self.profile or {}).get("views", {}).get(self.selected_role())
            if not item:
                raise PixelError("先导入此视角参考。")
            window = tk.Toplevel(self.dialog, bg=BG)
            window.title(VIEW_LABELS[self.selected_role()] + "参考 · " + item["name"])
            image = decoded_asset(item["png"]).copy()
            image.thumbnail((700, 600))
            photo = ImageTk.PhotoImage(image)
            label = tk.Label(window, image=photo, bg=BG)
            label.image = photo
            label.pack(padx=16, pady=16)
        self.attempt(run)

    def import_profile(self):
        path = filedialog.askopenfilename(parent=self.dialog, filetypes=[("角色规范", "*.pixelchar")])
        if path:
            self.attempt(lambda: self.call("load", path=path))

    def export_profile(self):
        path = filedialog.asksaveasfilename(parent=self.dialog, defaultextension=".pixelchar", filetypes=[("角色规范", "*.pixelchar")])
        if path:
            self.attempt(lambda: self.call("save", path=path, overwrite=True))

    def run_check(self):
        if self.running:
            return
        if self.editor.gesture:
            self.notice.set("请先完成画布上的笔画。")
            return
        clone = Document.from_dict(self.editor.doc.to_dict())
        digest = content_digest(clone)
        mode = "general" if self.mode.get() == "通用动作" else "grounded"
        self.running = True
        self.check_button.config(state="disabled", text="正在逐帧检查…")
        self.clean_button.config(state="disabled")
        channel = queue.Queue()

        def worker():
            try:
                channel.put((analyze_motion(clone, mode=mode), None))
            except Exception as exc:
                channel.put((None, str(exc)))

        def poll():
            self.poll_job = None
            try:
                report, error = channel.get_nowait()
            except queue.Empty:
                self.poll_job = self.editor.root.after(100, poll)
                return
            self.running = False
            self.check_button.config(state="normal", text="检查全部帧")
            if error:
                self.notice.set("检查失败：" + error)
                return
            self.report, self.report_doc, self.report_digest = report, clone, digest
            self.tree.delete(*self.tree.get_children())
            for i, finding in enumerate(report["findings"]):
                self.tree.insert("", "end", iid=str(i), values=(finding["frame"] + 1, KINDS[finding["kind"]], finding["message"]))
            self.notice.set(f'已检查 {report["scanned_frames"]} 帧，找到 {len(report["findings"])} 条待核对线索。' +
                            (f'另有 {report["omitted_findings"]} 条未列出，请分段检查。' if report["omitted_findings"] else "没有线索也仍需播放观察动作。"))
            if not self.report_current():
                self.notice.set("检查期间工程已修改，请重新检查。旧结果只供对照。")
            if report["findings"]:
                self.tree.selection_set("0")

        threading.Thread(target=worker, daemon=True).start()
        self.poll_job = self.editor.root.after(100, poll)

    def report_current(self):
        return self.report and self.editor.doc.id == self.report_doc.id and content_digest(self.editor.doc) == self.report_digest

    def selected_finding(self):
        selection = self.tree.selection()
        return self.report["findings"][int(selection[0])] if selection and self.report else None

    def select_finding(self):
        finding = self.selected_finding()
        self.clean_button.config(state="disabled")
        if not finding:
            return
        image = decoded_asset(evidence(self.report_doc, self.report["frames"], finding)).copy()
        image.thumbnail((780, 220), Image.Resampling.NEAREST)
        self.evidence_photo = ImageTk.PhotoImage(image)
        self.evidence_label.config(image=self.evidence_photo, text="", height=0)
        self.detail.config(text=f'第 {finding["frame"] + 1} 帧 · 区域 {finding["rect"]} · ' + finding["message"] +
                           " " + finding.get("repair_note", "请结合动画播放核对。"), wraplength=780)
        if self.report_current():
            self.editor.select_frame(finding["frame"])
            if finding.get("repair_ops"):
                self.clean_button.config(state="normal")
        else:
            self.notice.set("工程已修改或切换，请重新检查后再定位和清理。")

    def clean_selected(self):
        finding = self.selected_finding()
        if not self.report_current() or not finding or not finding.get("repair_ops"):
            self.clean_button.config(state="disabled")
            self.notice.set("结果已过期或此项不支持像素清理，请重新检查。")
            return
        if self.editor.apply(finding["repair_ops"], "清理选中独立小块"):
            self.clean_button.config(state="disabled")
            self.notice.set("已清理选中小块。Ctrl+Z 可完整撤销；请重新检查并播放观察。")
