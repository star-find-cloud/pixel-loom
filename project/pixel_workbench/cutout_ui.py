"""A small non-destructive background-removal dialog using the shared service."""
from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk

from .cutout import DEFAULTS
from .messages import user_error
from .reference import decoded_asset
from .reference_ui_images import checker
from .ui import BG, PANEL, FIELD, FG, MUTED, ACCENT, GREEN, SMALL, place_dialog


class CutoutDialog:
    def __init__(self, editor, parent=None):
        self.editor = editor
        self.dialog = d = tk.Toplevel(parent or editor.root)
        d.title("去背景 · 原图始终保留")
        d.configure(bg=BG)
        d.transient(parent or editor.root)
        place_dialog(d, editor.root, 1060, 730)
        d.minsize(860, 620)
        self.job = self.poll_job = None
        self.photos, self.transforms = {}, {}
        self.preview_id = None
        self.drag = None
        self.mode = "background"
        context = editor.service.references.context
        self.asset_id = context["subject"]["id"]
        self.options = deepcopy(context.get("cutout") or DEFAULTS)
        self.tolerance = tk.IntVar(value=self.options["tolerance"])
        self.soft = tk.BooleanVar(value=bool(self.options["softness"]))
        self.connected = tk.BooleanVar(value=self.options["connected"])
        self.show_mask = tk.BooleanVar(value=False)
        header = tk.Frame(d, bg=PANEL, padx=18, pady=12)
        header.pack(fill="x")
        editor.label(header, "去背景", font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        editor.label(header, "先看效果，再应用到参考图", MUTED, SMALL).pack(side="left", padx=16)
        footer = tk.Frame(d, bg=PANEL, padx=14, pady=12)
        footer.pack(side="bottom", fill="x")
        self.apply_button = editor.button(footer, "应用去背景", lambda: self.action("apply"), True)
        self.apply_button.pack(side="right")
        self.export_button = editor.button(footer, "导出 PNG", self.export)
        self.export_button.pack(side="right", padx=8)
        editor.button(footer, "关闭", d.destroy).pack(side="right")
        self.undo_button = editor.button(footer, "撤销抠图", lambda: self.action("undo"))
        self.undo_button.pack(side="left")
        self.redo_button = editor.button(footer, "重做", lambda: self.action("redo"))
        self.redo_button.pack(side="left", padx=6)
        editor.button(footer, "恢复原图", lambda: self.action("reset")).pack(side="left", padx=4)
        self.status = editor.label(d, "", MUTED, SMALL, wraplength=1000, justify="left", anchor="w")
        self.status.pack(side="bottom", fill="x", padx=18, pady=8)
        self.status.bind("<Configure>", lambda event: self.status.config(wraplength=max(100,event.width)))
        body = tk.Frame(d, bg=BG, padx=14, pady=12)
        body.pack(fill="both", expand=True)
        controls = tk.Frame(body, bg=PANEL, padx=12, pady=12, width=220)
        controls.pack(side="left", fill="y", padx=(0, 12))
        controls.pack_propagate(False)
        editor.label(controls, "① 调整去除强度", FG, SMALL).pack(anchor="w")
        tk.Scale(controls, from_=0, to=120, resolution=1, orient="horizontal", variable=self.tolerance,
                 bg=PANEL, fg=FG, troughcolor=FIELD, activebackground=ACCENT, bd=0,
                 highlightthickness=0, font=SMALL, command=lambda _: self.schedule()).pack(fill="x", pady=5)
        editor.label(controls, "数值越大，去除的相近颜色越多", MUTED, SMALL, wraplength=190, justify="left").pack(anchor="w")
        for text, var in (("只去相连背景", self.connected), ("柔和边缘", self.soft)):
            tk.Checkbutton(controls, text=text, variable=var, command=self.schedule,
                           bg=PANEL, fg=FG, selectcolor=FIELD, activebackground=PANEL,
                           activeforeground=FG, highlightthickness=0).pack(anchor="w", pady=5)
        editor.label(controls, "② 必要时点选 / 保护", FG, SMALL).pack(anchor="w", pady=(18, 7))
        self.pick_button = editor.button(controls, "点背景 · 可添加多个点", lambda: self.set_mode("background"), True, font=SMALL)
        self.pick_button.pack(fill="x", pady=3)
        self.protect_button = editor.button(controls, "框住要保护的部位", lambda: self.set_mode("protect"), font=SMALL)
        self.protect_button.pack(fill="x", pady=3)
        editor.button(controls, "重新自动取背景", self.auto, font=SMALL).pack(fill="x", pady=(12, 3))
        editor.button(controls, "清除保护", self.clear_protection, font=SMALL).pack(fill="x", pady=3)
        editor.label(controls, "在左图点击背景；封闭空隙可另点一下。\n保护模式：在左图拖框。\n绿框内的像素不会被去除。", MUTED, SMALL,
                     justify="left", wraplength=190).pack(anchor="w", pady=12)
        tk.Checkbutton(controls, text="查看去除蒙版", variable=self.show_mask, command=self.draw,
                       bg=PANEL, fg=MUTED, selectcolor=FIELD, activebackground=PANEL, highlightthickness=0).pack(anchor="w")
        editor.label(controls, "适合纯色 / 简单背景。\n复杂场景、相近衣色、头发与玻璃可能需要保护或精修。", MUTED, SMALL,
                     justify="left", wraplength=190).pack(anchor="w", pady=14)
        previews = tk.Frame(body, bg=BG)
        previews.pack(fill="both", expand=True)
        previews.rowconfigure(0, weight=1)
        self.canvases = {}
        for col, (key, title) in enumerate((("original", "原图 · 点击背景 / 拖框保护"), ("result", "去背景预览 · 棋盘代表透明"))):
            previews.columnconfigure(col, weight=1, uniform="preview")
            panel = tk.Frame(previews, bg=PANEL, padx=7, pady=9)
            panel.grid(row=0, column=col, sticky="nsew", padx=(0, 8 if col == 0 else 0))
            editor.label(panel, title, FG, SMALL).pack(anchor="w", pady=(0, 8))
            canvas = tk.Canvas(panel, bg="#0c1018", highlightthickness=0,
                               cursor="crosshair" if key == "original" else "arrow")
            canvas.pack(fill="both", expand=True)
            canvas.bind("<Configure>", lambda event: self.draw())
            self.canvases[key] = canvas
        source = self.canvases["original"]
        source.bind("<Button-1>", self.pointer_down)
        source.bind("<B1-Motion>", self.pointer_move)
        source.bind("<ButtonRelease-1>", self.pointer_up)
        d.bind("<Escape>", lambda event: d.destroy())
        d.bind("<Control-z>", lambda event: self.action("undo"))
        d.bind("<Control-y>", lambda event: self.action("redo"))
        d.bind("<Destroy>", self.cleanup, add="+")
        self.ticket = None
        self.observed = self.tokens()
        self.refresh_buttons()
        self.schedule()
        self.poll_job = d.after(700, self.poll)
        d.grab_set()

    def tokens(self):
        service = self.editor.service
        return service.doc.id, service.doc.revision, service.references.revision

    def payload(self, **fields):
        return {"expected_document_id": self.observed[0], "expected_revision": self.observed[1],
                "expected_reference_revision": self.observed[2], "source": "手动", "include_images": False, **fields}

    def settings(self):
        self.options.update(tolerance=self.tolerance.get(), connected=self.connected.get(),
                            softness=(self.options["softness"] or 10) if self.soft.get() else 0)
        return deepcopy(self.options)

    def schedule(self, *_):
        self.preview_id = None
        self.apply_button.config(state="disabled")
        if self.job:
            self.dialog.after_cancel(self.job)
        self.job = self.dialog.after(180, self.preview)

    def preview(self):
        if self.job:
            self.dialog.after_cancel(self.job)
        self.job = None
        asset = self.editor.service.references.context["subject"]
        if not asset or asset["id"] != self.asset_id:
            self.status.config(text="原图已更换，请关闭后重新打开去背景。", fg=ACCENT)
            return False
        self.observed = self.tokens()
        try:
            result = self.editor.dispatch("POST", "/reference/cutout/preview", {}, self.payload(settings=self.settings()))[0]
            self.preview_id = result["preview_id"]
            self.ticket = self.editor.service.cutouts.tickets[self.preview_id]
            stats = result["statistics"]
            warning = " ".join(stats["warnings"])
            self.status.config(text=f"已预览 · 影响 {stats['affected_fraction']:.1%} 的可见像素 · 原图始终保留。 " + warning,
                               fg=ACCENT if warning else MUTED)
            self.apply_button.config(state="normal")
            self.refresh_buttons()
            self.draw()
            return True
        except (OSError, ValueError, KeyError) as exc:
            self.status.config(text=user_error(exc), fg="#f19493")
            if getattr(exc, "code", None) in ("CUTOUT_PREVIEW_REQUIRED", "CUTOUT_PREVIEW_STALE", "REFERENCE_CONFLICT", "REVISION_CONFLICT"):
                self.schedule()
            return False

    def refresh_buttons(self):
        context = self.editor.service.references.context
        state = self.editor.service.cutouts.status(self.editor.doc.id, context)
        self.undo_button.config(state="normal" if state["can_undo"] else "disabled")
        self.redo_button.config(state="normal" if state["can_redo"] else "disabled")
        self.export_button.config(state="normal" if state["applied"] else "disabled")

    def action(self, action, **fields):
        if action == "apply" and (self.preview_id is None or self.tokens() != self.observed):
            self.preview()
            self.status.config(text="预览已更新，请查看后再次点击应用。", fg=ACCENT)
            return False
        try:
            self.editor.dispatch("POST", "/reference/cutout", {}, self.payload(action=action, preview_id=self.preview_id, **fields))
            if action != "export":
                self.options = deepcopy(self.editor.service.references.context.get("cutout") or DEFAULTS)
                self.tolerance.set(self.options["tolerance"])
                self.soft.set(bool(self.options["softness"]))
                self.connected.set(self.options["connected"])
                self.preview()
            self.status.config(text={"apply": "已应用到参考图，可继续生成像素底稿；现有画布不变。", "undo": "已撤销抠图调整。",
                                    "redo": "已重做抠图调整。", "reset": "已恢复原图背景。", "export": "透明 PNG 已导出。"}[action], fg=GREEN)
            self.refresh_buttons()
            return True
        except (OSError, ValueError, KeyError) as exc:
            self.status.config(text=user_error(exc), fg="#f19493")
            if getattr(exc, "code", None) in ("CUTOUT_PREVIEW_REQUIRED", "CUTOUT_PREVIEW_STALE", "REFERENCE_CONFLICT", "REVISION_CONFLICT"):
                self.schedule()
            return False

    def export(self):
        # Export only the applied result: never silently export an unapplied preview.
        context = self.editor.service.references.context
        if self.job or self.preview_id is None or self.tokens() != self.observed or self.settings() != context.get("cutout"):
            self.status.config(text="当前预览尚未应用，请先应用，再导出这个效果。", fg=ACCENT)
            return False
        path = filedialog.asksaveasfilename(parent=self.dialog, title="导出去背景 PNG", defaultextension=".png",
                                          initialfile="去背景.png", filetypes=[("透明 PNG", "*.png")])
        return self.action("export", path=path, overwrite=True) if path else False

    def set_mode(self, mode):
        self.mode = mode
        self.pick_button.config(bg=ACCENT if mode == "background" else FIELD)
        self.protect_button.config(bg=ACCENT if mode == "protect" else FIELD)

    def auto(self):
        self.options["points"] = []
        self.options["background_color"] = None
        self.schedule()

    def clear_protection(self):
        self.options["protect_regions"] = []
        self.options["keep_polygons"] = []
        self.schedule()

    def point(self, event, clamp=False):
        transform = self.transforms.get("original")
        if not transform:
            return None
        x, y, sx, sy, width, height = transform
        px, py = int((event.x-x)/sx), int((event.y-y)/sy)
        if clamp:
            return [max(0, min(width-1, px)), max(0, min(height-1, py))]
        return [px, py] if x <= event.x < x+width*sx and y <= event.y < y+height*sy else None

    def pointer_down(self, event):
        point = self.point(event)
        if point is None:
            return
        if self.mode == "background":
            if len(self.options["points"]) >= 16:
                self.status.config(text="最多16个背景点，可点“重新自动取背景”清空。", fg=ACCENT)
                return
            self.options["points"].append(point)
            self.schedule()
        else:
            self.drag = point

    def pointer_move(self, event):
        if self.drag is None:
            return
        last = self.point(event, True)
        x, y, sx, sy, _, _ = self.transforms["original"]
        canvas = self.canvases["original"]
        canvas.delete("drag")
        canvas.create_rectangle(x+self.drag[0]*sx, y+self.drag[1]*sy,
                                x+(last[0]+1)*sx, y+(last[1]+1)*sy, outline=GREEN, width=2, tags="drag")

    def pointer_up(self, event):
        if self.drag is None:
            return
        last, first = self.point(event, True), self.drag
        self.drag = None
        if len(self.options["protect_regions"]) < 32:
            self.options["protect_regions"].append([min(first[0],last[0]), min(first[1],last[1]),
                                                    abs(last[0]-first[0])+1, abs(last[1]-first[1])+1])
            self.schedule()
        else:
            self.status.config(text="最多32个保护框，可先清除保护再重新设置。", fg=ACCENT)

    def draw(self):
        asset = self.editor.service.references.context["subject"]
        if not asset or asset["id"] != self.asset_id:
            return
        original = decoded_asset(asset["png"])
        result = self.ticket["mask"].convert("RGBA") if self.ticket and self.show_mask.get() else (
            self.ticket["output"] if self.ticket else original)
        for key, image in (("original", original), ("result", result)):
            canvas = self.canvases[key]
            canvas.delete("all")
            scale = min(max(1,canvas.winfo_width()-14)/image.width, max(1,canvas.winfo_height()-14)/image.height, 4)
            size = (max(1, round(image.width*scale)), max(1, round(image.height*scale)))
            shown = checker(image).resize(size, Image.Resampling.NEAREST)
            self.photos[key] = ImageTk.PhotoImage(shown)
            x, y = (canvas.winfo_width()-size[0])//2, (canvas.winfo_height()-size[1])//2
            canvas.create_image(x, y, image=self.photos[key], anchor="nw")
            self.transforms[key] = (x,y,size[0]/image.width,size[1]/image.height,image.width,image.height)
            if key == "original":
                sx, sy = size[0]/image.width, size[1]/image.height
                for px, py in self.options["points"]:
                    cx, cy = x+(px+.5)*sx, y+(py+.5)*sy
                    canvas.create_oval(cx-4,cy-4,cx+4,cy+4,outline=ACCENT,width=2)
                for px,py,w,h in self.options["protect_regions"]:
                    canvas.create_rectangle(x+px*sx,y+py*sy,x+(px+w)*sx,y+(py+h)*sy,outline=GREEN,width=2)
                for polygon in self.options["keep_polygons"]:
                    canvas.create_polygon(*[v for px,py in polygon for v in (x+px*sx,y+py*sy)],fill="",outline=GREEN,width=2)

    def poll(self):
        self.poll_job = None
        if self.tokens() != self.observed:
            self.schedule()
            self.refresh_buttons()
        self.poll_job = self.dialog.after(700, self.poll)

    def cleanup(self, event):
        if event.widget == self.dialog:
            for job in (self.job, self.poll_job):
                if job:
                    self.dialog.after_cancel(job)
            self.job = self.poll_job = None
