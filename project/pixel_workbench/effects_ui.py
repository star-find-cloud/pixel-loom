"""Small visual VFX creator: adjust, play, generate an independent editable project."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import colorchooser, messagebox

from PIL import Image, ImageTk

from .effects import DEFAULTS, PRESETS, make_effect
from .ui import BG, PANEL, FIELD, FG, MUTED, FONT, SMALL


class EffectsDialog:
    def __init__(self, editor):
        self.editor = editor
        self.dialog = tk.Toplevel(editor.root, bg=BG)
        self.dialog.title("像素特效 · Pixel Loom")
        x = max(0, editor.root.winfo_rootx() + (editor.root.winfo_width() - 860) // 2)
        y = max(0, min(editor.root.winfo_rooty() + 60, editor.root.winfo_screenheight() - 710))
        self.dialog.geometry(f"860x650+{x}+{y}")
        self.dialog.minsize(760, 640)
        self.dialog.transient(editor.root)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        self.dialog.bind("<Destroy>", self.destroyed, add="+")
        self.job = self.tick_job = self.poll_job = None
        self.closed = self.building = self.pending = False
        self.sequence, self.ready_sequence = 0, -1
        self.proposed = self.config = None
        self.index, self.seed = 0, 0
        base = dict((editor.doc.effect_recipe or {}).get("settings", DEFAULTS))
        self.seed = base["seed"]
        self.kind = tk.StringVar(value=PRESETS[base["preset"]]["label"])
        self.size = tk.StringVar(value=str(base["size"]))
        self.frames = tk.StringVar(value=str(base["frames"]))
        self.duration = tk.IntVar(value=base["duration_ms"])
        self.strength = tk.IntVar(value=base["strength"])
        self.color = base["color"]
        self.overview = tk.BooleanVar(value=False)
        self.paused = False
        self.notice = tk.StringVar(value="正在准备像素预览…")
        header = tk.Frame(self.dialog, bg=BG, padx=18, pady=14)
        header.pack(fill="x")
        editor.label(header, "像素特效", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        editor.label(header, "调好效果，生成可逐帧修改的独立项目。", MUTED).pack(anchor="w", pady=(4, 0))
        content = tk.Frame(self.dialog, bg=BG)
        content.pack(fill="both", expand=True, padx=18)
        controls = tk.Frame(content, bg=PANEL, padx=14, pady=14, width=225)
        controls.pack(side="left", fill="y", padx=(0, 12))
        controls.pack_propagate(False)
        for title, variable, choices in (("特效类型", self.kind, [p["label"] for p in PRESETS.values()]),
                                          ("画布尺寸", self.size, ["32", "48", "64", "96", "128"]),
                                          ("动画帧数", self.frames, ["8", "12", "16", "24", "32"])):
            editor.label(controls, title, MUTED, SMALL).pack(anchor="w", pady=(5, 3))
            editor._option(controls, variable, choices).pack(fill="x")
        editor.label(controls, "主色", MUTED, SMALL).pack(anchor="w", pady=(12, 4))
        self.color_button = editor.button(controls, "选择颜色…", self.choose_color)
        self.color_button.pack(fill="x")
        self.update_color_button()
        for label, variable, low, high in (("强度", self.strength, 1, 100), ("帧间隔 · 越小越快", self.duration, 30, 500)):
            editor.label(controls, label, MUTED, SMALL).pack(anchor="w", pady=(12, 1))
            tk.Scale(controls, from_=low, to=high, variable=variable, orient="horizontal", bg=PANEL, fg=FG,
                     highlightthickness=0, troughcolor=FIELD, activebackground=FIELD, font=SMALL).pack(fill="x")
        editor.button(controls, "换一种变化", self.vary).pack(fill="x", pady=(12, 0))
        right = tk.Frame(content, bg=PANEL)
        right.pack(side="left", fill="both", expand=True)
        self.preview = tk.Label(right, bg=BG, fg=MUTED, text="正在生成预览…")
        self.preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.preview.bind("<Configure>", lambda _: self.draw_preview())
        row = tk.Frame(right, bg=PANEL, padx=10, pady=8)
        row.pack(fill="x")
        self.pause_button = editor.button(row, "暂停", self.toggle_play, padx=10, pady=4)
        self.pause_button.pack(side="left")
        tk.Checkbutton(row, text="全部帧总览", variable=self.overview, command=self.switch_view,
                       bg=PANEL, fg=FG, selectcolor=FIELD, activebackground=PANEL, activeforeground=FG,
                       font=SMALL).pack(side="left", padx=8)
        self.frame_label = editor.label(row, "", MUTED, SMALL)
        self.frame_label.pack(side="right")
        footer = tk.Frame(self.dialog, bg=BG, padx=18, pady=12)
        footer.pack(fill="x")
        self.create_button = editor.button(footer, "生成新项目", self.commit, True)
        self.create_button.pack(side="right", padx=(12, 0))
        tk.Label(footer, textvariable=self.notice, bg=BG, fg=MUTED, font=SMALL,
                 anchor="w", justify="left", wraplength=570).pack(side="left", fill="x", expand=True)
        for variable in (self.size, self.frames, self.strength, self.duration):
            variable.trace_add("write", lambda *_: self.schedule())
        self.kind.trace_add("write", lambda *_: self.change_preset())
        self.schedule()

    def destroyed(self, event):
        if event.widget == self.dialog:
            self.closed = True
            for name in ("job", "tick_job", "poll_job"):
                job = getattr(self, name)
                if job:
                    self.editor.root.after_cancel(job)
                    setattr(self, name, None)

    def close(self):
        self.dialog.destroy()

    def preset(self):
        return next(key for key, value in PRESETS.items() if value["label"] == self.kind.get())

    def values(self):
        return {"preset": self.preset(), "size": int(self.size.get()), "frames": int(self.frames.get()),
                "duration_ms": self.duration.get(), "strength": self.strength.get(),
                "color": self.color, "seed": self.seed}

    def update_color_button(self):
        color = self.color[:7]
        brightness = sum(int(color[i:i + 2], 16) * weight for i, weight in ((1, .299), (3, .587), (5, .114)))
        self.color_button.config(text=color.upper() + "  改色…", bg=color, fg="#11141b" if brightness > 140 else FG)

    def choose_color(self):
        _, color = colorchooser.askcolor(self.color[:7], parent=self.dialog, title="选择特效主色")
        if color:
            self.color = color
            self.update_color_button()
            self.schedule()

    def change_preset(self):
        self.color = PRESETS[self.preset()]["color"]
        self.frames.set(str(PRESETS[self.preset()]["frames"]))
        self.duration.set(PRESETS[self.preset()]["duration_ms"])
        self.update_color_button()
        self.schedule()

    def vary(self):
        self.seed = (self.seed + 1) % 1000000
        self.schedule()

    def schedule(self):
        self.sequence += 1
        self.create_button.config(state="disabled")
        if self.job:
            self.editor.root.after_cancel(self.job)
        self.job = self.editor.root.after(180, self.build)

    def build(self):
        self.job = None
        if self.closed:
            return
        if self.building:
            self.pending = True
            return
        try:
            values = self.values()
        except (ValueError, tk.TclError, ZeroDivisionError):
            self.notice.set("请使用有效的尺寸、帧数和速度。")
            return
        self.building = True
        self.notice.set("正在更新预览…")
        sequence, channel = self.sequence, queue.Queue()

        def worker():
            try:
                channel.put((*make_effect(values), None))
            except Exception as exc:
                channel.put((None, None, str(exc)))

        def poll():
            self.poll_job = None
            try:
                doc, config, error = channel.get_nowait()
            except queue.Empty:
                self.poll_job = self.editor.root.after(50, poll)
                return
            self.building = False
            if sequence == self.sequence:
                if error:
                    self.notice.set("预览失败：" + error)
                else:
                    self.proposed, self.config, self.ready_sequence = doc, config, sequence
                    self.index = 0
                    self.create_button.config(state="normal")
                    self.notice.set(PRESETS[config["preset"]]["description"] + "\n生成后可手动改色、改图层和每一帧。")
                    self.switch_view()
            if self.pending or sequence != self.sequence:
                self.pending = False
                if self.job:
                    self.editor.root.after_cancel(self.job)
                    self.job = None
                self.build()

        threading.Thread(target=worker, daemon=True).start()
        self.poll_job = self.editor.root.after(50, poll)

    def draw_preview(self):
        if not self.proposed or self.closed:
            return
        if self.overview.get():
            image = self.proposed.contact_sheet(columns=4, scale=1)
            self.frame_label.config(text=f"全部 {len(self.proposed.durations)} 帧")
        else:
            image = self.proposed.preview(self.index, scale=1)
            self.frame_label.config(text=f"{self.index + 1:02d} / {len(self.proposed.durations):02d} 帧 · {self.proposed.durations[self.index]}ms")
        factor = min(max(1, self.preview.winfo_width() - 16) / image.width,
                     max(1, self.preview.winfo_height() - 16) / image.height, 7)
        image = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(image)
        self.preview.config(image=self.photo, text="")

    def switch_view(self):
        if self.tick_job:
            self.editor.root.after_cancel(self.tick_job)
            self.tick_job = None
        self.draw_preview()
        if self.proposed and not self.paused and not self.overview.get():
            self.tick_job = self.editor.root.after(self.proposed.durations[self.index], self.tick)

    def tick(self):
        self.tick_job = None
        self.index = (self.index + 1) % len(self.proposed.durations)
        self.switch_view()

    def toggle_play(self):
        self.paused = not self.paused
        self.pause_button.config(text="播放" if self.paused else "暂停")
        self.switch_view()

    def commit(self):
        if self.proposed is None or self.ready_sequence != self.sequence:
            return False
        editor = self.editor
        if editor.gesture or editor.path_points:
            messagebox.showinfo("请先完成绘画", "完成当前笔画或路径后再生成新项目。", parent=self.dialog)
            return False
        try:
            editor.dispatch("POST", "/effects", {}, {"action": "create", "settings": self.config,
                "include_images": False, "expected_document_id": editor.doc.id,
                "expected_revision": editor.doc.revision})
            self.close()
            return True
        except (ValueError, OSError, RuntimeError) as exc:
            messagebox.showerror("像素特效", str(exc), parent=self.dialog)
            return False
