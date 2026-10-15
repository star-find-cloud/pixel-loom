"""Startup guide and optional, local-only creator support panel."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageTk

from .paths import PACKAGE
from .ui import BG, PANEL, FIELD, FG, MUTED, ACCENT, GREEN, FONT, SMALL, place_dialog


@dataclass(frozen=True)
class SupportOption:
    amount_yuan: int
    image: Path


def support_options(folder=None):
    folder = Path(folder) if folder is not None else PACKAGE / "resources" / "support"
    data = json.loads((folder / "options.json").read_text(encoding="utf-8"))
    options, seen = [], set()
    for item in data["options"]:
        amount, name = item["amount_yuan"], item["image"]
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or amount in seen:
            raise ValueError("Invalid or repeated support amount")
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Support images must use local filenames")
        seen.add(amount)
        options.append(SupportOption(amount, folder / name))
    return tuple(sorted(options, key=lambda option: option.amount_yuan))


class WelcomeDialog:
    def __init__(self, editor):
        self.editor = editor
        self.dialog = d = tk.Toplevel(editor.root)
        d.title("欢迎使用 Pixel Loom · 使用说明")
        d.configure(bg=BG)
        d.transient(editor.root)
        d.resizable(False, False)
        place_dialog(d, editor.root, 740, 750)
        self.page = "guide"
        self.selected_amount = None
        self.payment_image_source = None
        self.photo = None
        self.amount_buttons = {}
        self.support_error = ""
        try:
            self.options = support_options()
        except (OSError, ValueError, KeyError, TypeError):
            self.options = ()
            self.support_error = "收款信息暂不可用，你可以直接进入软件。"

        header = tk.Frame(d, bg=PANEL, padx=28, pady=20)
        header.pack(fill="x")
        mark = tk.Canvas(header, width=42, height=42, bg=PANEL, highlightthickness=0)
        mark.pack(side="left", padx=(0, 14))
        for x, y, color in ((2, 2, ACCENT), (23, 2, GREEN), (2, 23, "#6982b8"), (23, 23, ACCENT)):
            mark.create_rectangle(x, y, x+15, y+15, fill=color, outline="")
        heading = tk.Frame(header, bg=PANEL)
        heading.pack(side="left")
        self.title = editor.label(heading, "欢迎使用像素织机", font=("Microsoft YaHei UI", 19, "bold"))
        self.title.pack(anchor="w")
        self.subtitle = editor.label(heading, "像素画、动画与 AI 协作，从这里开始", MUTED, SMALL)
        self.subtitle.pack(anchor="w", pady=(3, 0))

        footer = tk.Frame(d, bg=PANEL, padx=28, pady=18)
        footer.pack(side="bottom", fill="x")
        editor.label(footer, "打赏完全自愿，所有功能均可直接使用。", MUTED, SMALL).pack(anchor="w", pady=(0, 12))
        row = tk.Frame(footer, bg=PANEL)
        row.pack(fill="x")
        self.support_button = editor.button(row, "打赏 UP 喝杯奶茶", self.support, padx=20, pady=10)
        self.support_button.pack(side="left")
        self.enter_button = editor.button(row, "了解，进入", self.enter, True, padx=30, pady=10)
        self.enter_button.pack(side="right")

        self.content = tk.Frame(d, bg=BG, padx=28, pady=16)
        self.content.pack(fill="both", expand=True)
        self.guide_frame = tk.Frame(self.content, bg=BG)
        self.guide_frame.pack(fill="both", expand=True)
        items = [
            ("01", "从原图或画布开始", "导入参考图，调整尺寸和色数，生成可编辑的自动像素底稿；也可以新建画布手动画。"),
            ("02", "让 AI 操作同一份工程", "首次在“更多 → MCP 首次接入配置”连接客户端。AI 调用 pixel_onboard 后即可读图、绘画和编辑动画。"),
            ("03", "保留、修改，再交付", "新动作先复制为新项目，保留旧作品。用截图反馈问题；保存 .pixloom 工程，导出 PNG、精灵表或 GIF。"),
        ]
        for number, title, description in items:
            card = tk.Frame(self.guide_frame, bg=PANEL, padx=17, pady=15)
            card.pack(fill="x", pady=(0, 12))
            editor.label(card, number, GREEN, ("Consolas", 14, "bold")).pack(side="left", anchor="n", padx=(0, 15))
            text = tk.Frame(card, bg=PANEL)
            text.pack(fill="x", expand=True)
            editor.label(text, title, font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
            editor.label(text, description, MUTED, FONT, wraplength=555, justify="left").pack(anchor="w", pady=(6, 0))
        editor.label(self.guide_frame, "默认只做自动像素转换；明确提出重绘时，AI 才重新设计画面。", MUTED, SMALL,
                     wraplength=650, justify="left").pack(anchor="w", pady=4)

        self.support_frame = tk.Frame(self.content, bg=BG)
        amount_row = tk.Frame(self.support_frame, bg=BG)
        amount_row.pack(pady=(0, 10))
        for option in self.options:
            button = editor.button(amount_row, f"¥ {option.amount_yuan}", lambda value=option.amount_yuan: self.choose_amount(value),
                                   padx=23, pady=8)
            button.pack(side="left", padx=5)
            self.amount_buttons[option.amount_yuan] = button
        self.amount_label = editor.label(self.support_frame, "请选择一个金额", FG, ("Microsoft YaHei UI", 12, "bold"))
        self.amount_label.pack(pady=(0, 8))
        # A viewport shows the original white payment card. JPEG bytes are never
        # rewritten, the QR is never regenerated, and no payment request is sent.
        self.payment_canvas = tk.Canvas(self.support_frame, bg=FIELD, width=320, height=380,
                                        highlightthickness=0)
        self.payment_canvas.pack()
        self.payment_canvas.bind("<Configure>", lambda event: self.render_payment())
        self.support_status = editor.label(self.support_frame, "微信扫码支持 · 随时可直接进入软件", MUTED, SMALL)
        self.support_status.pack(pady=(8, 0))
        d.bind("<Return>", lambda event: self.enter())
        d.bind("<Escape>", lambda event: self.enter())
        d.protocol("WM_DELETE_WINDOW", self.enter)
        self.enter_button.focus_set()
        # No wait_window/mainloop here: the shared MCP service stays responsive.
        if editor.root.winfo_viewable():
            d.grab_set()

    def support(self):
        self.page = "support"
        self.guide_frame.pack_forget()
        self.support_frame.pack(fill="both", expand=True)
        self.title.config(text="请 UP 喝杯奶茶")
        self.subtitle.config(text="选择金额，显示对应的微信收款码")
        self.support_button.config(text="返回使用说明", command=self.guide)
        self.render_payment()

    def guide(self):
        self.page = "guide"
        self.support_frame.pack_forget()
        self.guide_frame.pack(fill="both", expand=True)
        self.title.config(text="欢迎使用像素织机")
        self.subtitle.config(text="像素画、动画与 AI 协作，从这里开始")
        self.support_button.config(text="打赏 UP 喝杯奶茶", command=self.support)

    def choose_amount(self, amount):
        option = next((option for option in self.options if option.amount_yuan == amount), None)
        self.selected_amount = option.amount_yuan if option else None
        self.payment_image_source = option.image if option else None
        for value, button in self.amount_buttons.items():
            button.config(bg=ACCENT if value == self.selected_amount else FIELD,
                          fg=BG if value == self.selected_amount else FG)
        self.amount_label.config(text=f"微信打赏 ¥{amount:.2f}" if option else "请选择一个金额")
        self.render_payment()

    def render_payment(self):
        if not self.dialog.winfo_exists() or self.page != "support":
            return
        canvas = self.payment_canvas
        canvas.delete("all")
        self.photo = None
        width, height = max(320, canvas.winfo_width()), max(1, canvas.winfo_height())
        if not self.payment_image_source:
            canvas.create_text(width//2, height//2, text=self.support_error or "选择上方金额\n显示对应的微信收款码",
                               fill=MUTED, font=FONT, justify="center", width=width-24)
            return
        try:
            with Image.open(self.payment_image_source) as original:
                image = original.convert("RGB")
            # Clip the green poster/header in the canvas, keeping the original
            # amount, QR code and recipient visible together in its white card.
            left, top, right, bottom = (.19*image.width, .185*image.height, .81*image.width, .74*image.height)
            scale = min(width/(right-left), height/(bottom-top))
            resized = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(resized)
            x = (width-(right-left)*scale)/2-left*scale
            y = (height-(bottom-top)*scale)/2-top*scale
            canvas.create_image(round(x), round(y), image=self.photo, anchor="nw")
        except (OSError, ValueError, Image.DecompressionBombError):
            self.payment_image_source = None
            canvas.create_text(width//2, height//2, text="收款图片暂不可用\n你可以直接进入软件", fill=MUTED,
                               font=FONT, justify="center", width=width-24)

    def enter(self):
        if self.dialog.winfo_exists():
            if self.dialog.grab_current() == self.dialog:
                self.dialog.grab_release()
            self.dialog.destroy()
        if getattr(self.editor, "welcome_window", None) is self:
            self.editor.welcome_window = None
