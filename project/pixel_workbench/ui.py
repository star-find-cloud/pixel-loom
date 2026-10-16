"""Native desktop presentation: tool icons, compact panels and discoverable workflows."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .model import Document, PixelError
from .paths import WORKSPACE
from .workflows import animation_plan
from .quality import pending_feedback
from .messages import user_error

BG = "#11141b"
PANEL = "#1a1f2b"
FIELD = "#252d3d"
EDGE = "#303a4d"
FG = "#e8edf7"
MUTED = "#97a6bf"
ACCENT = "#94b8ff"
GREEN = "#7edcc3"
FONT = ("Microsoft YaHei UI", 10)
SMALL = ("Microsoft YaHei UI", 9)
TOOL_INFO = {
    "pen": ("铅笔", "B", "拖动绘画；右键取色。支持对称绘画。"),
    "eraser": ("橡皮", "E", "擦除当前图层；选区内擦除。"),
    "fill": ("填充", "G", "单击填充相连的同色区域。"),
    "picker": ("取色", "I", "从可见画面读取颜色，自动加入调色板。"),
    "line": ("直线", "L", "拖出起点与终点，松开提交。"),
    "rect": ("矩形", "R", "拖出矩形；可切换实心或空心。"),
    "ellipse": ("椭圆", "O", "拖出椭圆；可切换实心或空心。"),
    "polygon": ("多边形", "P", "逐点单击；Enter / 右键完成，Esc 取消。"),
    "bezier": ("曲线", "Q", "放置 3 或 4 个控制点；Enter 完成。"),
    "select": ("选区", "S", "拖出矩形；Ctrl+C / X / V 复制、剪切、粘贴。"),
    "move": ("移动", "M", "拖动当前图层；有选区时只移动选中部分。"),
    "feedback_lasso": ("套圈", "A", "可选：标记位置后截图并复制，原图不会改变。"),
    "feedback_rect": ("框选", "", "可选：在截图上标出需要 AI 仔细观察的区域。"),
    "feedback_ellipse": ("椭圆", "", "可选：圈出位置，再截图粘贴到 AI 对话框。"),
}


def place_dialog(dialog, parent, width, height):
    width = min(width, parent.winfo_screenwidth()-60)
    height = min(height, parent.winfo_screenheight()-85)
    x = max(0, min(parent.winfo_screenwidth()-width-20, parent.winfo_rootx()+(parent.winfo_width()-width)//2))
    y = max(0, min(parent.winfo_screenheight()-height-60, parent.winfo_rooty()+(parent.winfo_height()-height)//2))
    dialog.geometry(f"{width}x{height}+{x}+{y}")


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.job, self.window = widget, text, None, None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, event=None):
        self.hide()
        self.job = self.widget.after(500, self.show)

    def show(self):
        self.job = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.geometry(f"+{self.widget.winfo_rootx()+12}+{self.widget.winfo_rooty()+self.widget.winfo_height()+5}")
        tk.Label(self.window, text=self.text, bg="#354157", fg=FG, padx=10, pady=7, font=SMALL).pack()

    def hide(self, event=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window:
            self.window.destroy()
            self.window = None


def tool_icon(name):
    image = Image.new("RGBA", (24, 24))
    d = ImageDraw.Draw(image)
    ink = FG
    if name.startswith("feedback_"):
        if name == "feedback_rect":
            d.rectangle((3,4,21,19),outline="#ffb887",width=2)
        else:
            d.ellipse((3,4,21,18),outline="#ffb887",width=2)
            if name == "feedback_lasso":
                d.line((7,17,5,21,10,22,12,19),fill="#ffb887",width=2)
    elif name == "pen":
        d.polygon([(5, 17), (7, 12), (17, 2), (21, 6), (11, 16)], outline=ink, width=2)
        d.line((5, 17, 10, 16), fill=ink, width=2)
    elif name == "eraser":
        d.polygon([(4, 14), (13, 4), (21, 11), (12, 21), (9, 21)], outline=ink, width=2)
        d.line((8, 10, 16, 17), fill=ink, width=2)
    elif name in ("rect", "select"):
        if name == "select":
            for n in (4, 10, 16):
                d.line((n, 4, n + 3, 4), fill=ink, width=2)
                d.line((n, 20, n + 3, 20), fill=ink, width=2)
                d.line((4, n, 4, n + 3), fill=ink, width=2)
                d.line((20, n, 20, n + 3), fill=ink, width=2)
        else:
            d.rectangle((4, 5, 20, 19), outline=ink, width=2)
    elif name == "ellipse":
        d.ellipse((3, 5, 21, 19), outline=ink, width=2)
    elif name == "line":
        d.line((4, 20, 20, 4), fill=ink, width=2)
        for x, y in [(4, 20), (20, 4)]:
            d.rectangle((x-2, y-2, x+2, y+2), fill=ink)
    elif name == "polygon":
        d.polygon([(4, 18), (8, 4), (20, 9), (17, 20)], outline=ink, width=2)
    elif name == "bezier":
        d.arc((3, 3, 20, 22), 190, 345, fill=ink, width=2)
        d.line((4, 16, 9, 4, 20, 16), fill=MUTED)
        for x, y in [(4, 16), (9, 4), (20, 16)]:
            d.rectangle((x-1, y-1, x+1, y+1), fill=ink)
    elif name == "picker":
        d.line((6, 18, 17, 7), fill=ink, width=4)
        d.line((13, 4, 21, 12), fill=ink, width=2)
        d.line((4, 21, 7, 18), fill=ink, width=2)
    elif name == "fill":
        d.polygon([(4, 11), (12, 3), (20, 11), (12, 19)], outline=ink, width=2)
        d.line((4, 11, 20, 11), fill=ink, width=2)
        d.ellipse((19, 16, 22, 21), fill=ACCENT)
    else:
        d.line((3, 12, 21, 12), fill=ink, width=2)
        d.line((12, 3, 12, 21), fill=ink, width=2)
        for points in [[(3, 12), (7, 8), (7, 16)], [(21, 12), (17, 8), (17, 16)],
                       [(12, 3), (8, 7), (16, 7)], [(12, 21), (8, 17), (16, 17)]]:
            d.polygon(points, fill=ink)
    return ImageTk.PhotoImage(image)


def contact_preview(doc, frames, columns=4):
    """Bounded UI thumbnails with one-based frame labels, independent of canvas size."""
    columns = min(columns, len(frames))
    sheet = Image.new("RGBA", (columns*136, ((len(frames)+columns-1)//columns)*130), BG)
    draw = ImageDraw.Draw(sheet)
    for n, frame in enumerate(frames):
        im = doc.preview(frame, scale=1)
        ratio = min(124/im.width, 96/im.height)
        im = im.resize((max(1, int(im.width*ratio)), max(1, int(im.height*ratio))), Image.Resampling.NEAREST)
        x, y = (n%columns)*136, (n//columns)*130
        draw.rectangle((x+2, y+2, x+132, y+126), fill=FIELD)
        sheet.paste(im, (x+(136-im.width)//2, y+8+(96-im.height)//2))
        draw.text((x+9, y+109), f"{frame+1:02d}  {doc.durations[frame]}ms", fill=FG)
    return sheet


class DesktopUI:
    def _check(self, parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command, bg=parent.cget("bg"),
                              fg=MUTED, selectcolor=FIELD, activebackground=PANEL, activeforeground=FG,
                              bd=0, padx=3, cursor="hand2", font=SMALL)

    def _entry(self, parent, variable, width=7):
        return tk.Entry(parent, textvariable=variable, width=width, bg=BG, fg=FG, insertbackground=ACCENT,
                        relief="flat", highlightthickness=1, highlightbackground=EDGE, highlightcolor=ACCENT)

    def _option(self, parent, variable, choices, command=None):
        widget = tk.OptionMenu(parent, variable, *choices, command=command)
        widget.config(bg=FIELD, fg=FG, activebackground=EDGE, activeforeground=FG, highlightthickness=0,
                      relief="flat", bd=0, font=SMALL)
        widget["menu"].config(bg=FIELD, fg=FG, activebackground=EDGE, activeforeground=FG, font=SMALL)
        return widget

    def _section(self, parent, title, subtitle=None):
        frame = tk.Frame(parent, bg=PANEL)
        frame.pack(fill="x", pady=(14, 6))
        self.label(frame, title, font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        if subtitle:
            self.label(frame, subtitle, MUTED, ("Segoe UI", 8)).pack(side="right")
        return frame

    def _scroll_panel(self, parent):
        canvas = tk.Canvas(parent, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.config(yscrollcommand=scroll.set)
        frame = tk.Frame(canvas, bg=PANEL, padx=14, pady=2)
        window = canvas.create_window(0, 0, window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        # Local bindings: scrolling this dock must never change the canvas zoom.
        def bind_scroll(widget):
            widget.bind("<MouseWheel>", lambda e: (canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"), "break")[-1], add="+")
            for child in widget.winfo_children():
                bind_scroll(child)
        self.root.after_idle(lambda: bind_scroll(frame) if frame.winfo_exists() else None)
        frame.bind("<Map>", lambda e: bind_scroll(frame), add="+")
        return frame

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=PANEL, borderwidth=0, tabmargins=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 9), font=SMALL)
        style.map("TNotebook.Tab", background=[("selected", FIELD)], foreground=[("selected", ACCENT)])
        style.configure("Vertical.TScrollbar", background=EDGE, troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED)
        style.configure("Horizontal.TScrollbar", background=EDGE, troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED)
        self.symmetry_var = tk.StringVar(value="关闭对称")
        self.duration_var = tk.IntVar(value=100)
        self.opacity_var = tk.IntVar(value=255)
        self.zoom_var = tk.StringVar(value="100%")
        self._palette_signature = None
        self._frame_signature = None
        self.frame_buttons = []
        top = tk.Frame(self.root, bg=PANEL, padx=16, pady=6)
        top.pack(fill="x")
        logo = tk.Canvas(top, width=30, height=30, bg=PANEL, highlightthickness=0)
        logo.pack(side="left", padx=(0, 10))
        for x, y, color in [(0, 0, ACCENT), (14, 0, GREEN), (0, 14, "#718aba"), (14, 14, ACCENT)]:
            logo.create_rectangle(x+2, y+2, x+12, y+12, fill=color, outline="")
        self.label(top, "PIXEL LOOM", font=("Segoe UI", 15, "bold")).pack(side="left")
        self.label(top, f"  {__version__}   /   像素织机", MUTED, SMALL).pack(side="left", padx=(0, 18))
        file_button=tk.Menubutton(top,text="文件 ▾",bg=PANEL,fg=FG,activebackground=FIELD,
                                  activeforeground=FG,relief="flat",font=SMALL,padx=8,pady=6)
        file_menu=tk.Menu(file_button,tearoff=False,bg=FIELD,fg=FG)
        for text,callback in [("新建工程",self.new_dialog),("打开工程 / PNG",self.open_dialog),
                              ("导入普通图片",self.reference_dialog),("保存工程  Ctrl+S",self.save),
                              ("另存为",self.save_as),("导出图片 / 动画",self.export_dialog)]:
            file_menu.add_command(label=text,command=callback)
        file_button.config(menu=file_menu)
        file_button.pack(side="left",padx=(0,8))
        for text, callback, accent in [("导出", self.export_dialog, True), ("保存", self.save, False),
                                      ("导入参考", self.reference_dialog, False)]:
            self.button(top, text, callback, accent, pady=6).pack(side="right", padx=3)
        more=tk.Menubutton(top,text="更多 ▾",bg=FIELD,fg=FG,activebackground=EDGE,activeforeground=FG,
                           relief="flat",font=SMALL,padx=10,pady=6)
        more_menu=tk.Menu(more,tearoff=False,bg=FIELD,fg=FG)
        for text,callback in [("检查成品",self.quality_dialog),("动画总览",self.overview_dialog),
                              ("检查更新",self.show_updates),
                              ("使用说明与支持作者",self.show_welcome),
                              ("MCP 首次接入配置",self.connection_dialog),("协作记录",self.activity_dialog),
                              ("旧版问题记录",lambda:self.feedback_panel.history()),
                              ("给 AI 的截图说明",lambda:self.feedback_panel.guide()),
                              ("搜索全部命令  Ctrl+K",self.command_palette),
                              ("使用指南与恢复",self.help_dialog)]:
            more_menu.add_command(label=text,command=callback)
        more.config(menu=more_menu)
        more.pack(side="right",padx=5)
        workflow=tk.Frame(self.root,bg=BG,padx=16,pady=4)
        self.workflow_bar = workflow
        workflow.pack(fill="x")
        self.mode_buttons={}
        for mode,title in [("preview","1  预览成品"),("feedback","2  截图反馈"),("manual","3  手动修改")]:
            b=self.button(workflow,title,lambda m=mode:self.set_workspace_mode(m),font=SMALL,pady=5,padx=12)
            b.pack(side="left",padx=(0,6))
            self.mode_buttons[mode]=b
        self.workflow_hint=self.label(workflow,"看成品、截图发给 AI，也能自己动手改。",MUTED,SMALL)
        self.workflow_hint.pack(side="left",padx=12)

        shelf=tk.Frame(self.root,bg=BG,padx=16,pady=1)
        self.project_shelf = shelf
        shelf.pack(fill="x")
        shelf_menu=tk.Menubutton(workflow,text='项目 ▾',bg=FIELD,fg=FG,font=SMALL,relief='flat',padx=10,pady=5)
        self.project_menu=tk.Menu(shelf_menu,tearoff=False,bg=FIELD,fg=FG)
        shelf_menu.config(menu=self.project_menu)
        shelf_menu.pack(side='right')
        self.project_tabs_canvas=tk.Canvas(shelf,bg=BG,height=30,highlightthickness=0)
        self.project_tabs_canvas.pack(side="left",fill="x",expand=True)
        self.project_tabs=tk.Frame(self.project_tabs_canvas,bg=BG)
        self.project_tabs_canvas.create_window((0,0),window=self.project_tabs,anchor="nw")
        self.project_tabs_canvas.bind('<MouseWheel>',lambda e:self.project_tabs_canvas.xview_scroll(-1 if e.delta>0 else 1,'units'))
        self.project_tabs_signature=None

        # Pack the footer and timeline first: the canvas gets the remaining height.
        footer = tk.Frame(self.root, bg=BG, padx=16, pady=4)
        footer.pack(side="bottom", fill="x")
        self.status_label = self.label(footer, "就绪 · 所有绘画操作均可撤销", MUTED, SMALL)
        self.status_label.pack(side="left")
        self.coordinates_label = self.label(footer, "", MUTED, ("Consolas", 9))
        self.coordinates_label.pack(side="right")
        self.main_panes = tk.PanedWindow(self.root, orient="vertical", bg=EDGE, bd=0,
                                         sashwidth=6, sashrelief="flat", opaqueresize=True)
        self.main_panes.pack(fill="both", expand=True, padx=10, pady=(4, 0))
        timeline = tk.Frame(self.main_panes, bg=PANEL, padx=12, pady=6)
        self.timeline = timeline
        row = tk.Frame(timeline, bg=PANEL)
        row.pack(fill="x")
        self.label(row, "动画时间轴", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=(0, 14))
        self.play_button = self.button(row, "▶ 播放", self.toggle_play, True, pady=4)
        self.play_button.pack(side="left", padx=3)
        self.button(row, "■ 停止", self.stop_animation, pady=4, padx=8).pack(side="left", padx=3)
        self.label(row, "速度", MUTED, SMALL).pack(side="left", padx=(8, 2))
        self.speed_menu = self._option(row, self.playback_speed,
                                      ["0.25×", "0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×", "3×", "4×"],
                                      command=self.set_playback_speed)
        self.speed_menu.pack(side="left", padx=(0, 7))
        for text, callback in [("+ 帧", lambda: self.apply([{"op": "frame_add"}], "复制动画帧")),
                               ("动画设置", self.tags_dialog), ("逐帧总览", self.overview_dialog)]:
            self.button(row, text, callback, pady=4, padx=8).pack(side="left", padx=3)
        self.tag_menu = self._option(row, self.tag_var, ["全部帧"])
        self.tag_menu.pack(side="left", padx=6)
        self.frame_info = self.label(row, "", MUTED, SMALL)
        self.frame_info.pack(side="right")
        self.frame_canvas = tk.Canvas(timeline, bg=PANEL, height=84, highlightthickness=0)
        self.frame_canvas.pack(fill="both", expand=True, pady=(5, 0))
        scroll = ttk.Scrollbar(timeline, orient="horizontal", command=self.frame_canvas.xview)
        scroll.pack(fill="x")
        self.frame_canvas.config(xscrollcommand=scroll.set)
        self.frames_widget = tk.Frame(self.frame_canvas, bg=PANEL)
        self.frame_canvas.create_window((0, 0), window=self.frames_widget, anchor="nw")
        self.frame_canvas.bind("<MouseWheel>", lambda e: self.frame_canvas.xview_scroll(-1 if e.delta > 0 else 1, "units"))

        workspace = tk.Frame(self.main_panes, bg=BG)
        self.workspace=workspace
        self.main_panes.add(workspace, minsize=200, stretch="always")
        self.main_panes.add(timeline, minsize=105, height=self.layout_size("timeline_height", 145, 105, 350), stretch="never")
        self.main_panes.bind("<ButtonRelease-1>", self.save_ui_layout)
        rail = tk.Frame(workspace, bg=PANEL, padx=7, pady=10)
        self.tool_rail=rail
        rail.pack(side="left", fill="y", padx=(0, 8))
        self.rail_title=self.label(rail, "绘画工具", MUTED, SMALL)
        self.rail_title.pack(pady=(0, 9))
        grid = tk.Frame(rail, bg=PANEL)
        grid.pack()
        self.tool_buttons, self.tool_icons = {}, {}
        for index, (tool, (name, key, hint)) in enumerate(TOOL_INFO.items()):
            icon = tool_icon(tool)
            self.tool_icons[tool] = icon
            button = self.button(grid, f"{name} {key}", lambda t=tool: self.choose_tool(t),
                                 image=icon, compound="top", width=53, height=48, padx=3, pady=3, font=("Microsoft YaHei UI", 8))
            button.grid(row=index//2, column=index%2, padx=2, pady=3)
            Tooltip(button, f"{name}  [{key}]\n{hint}")
            self.tool_buttons[tool] = button
        self.tool_more=tk.Menubutton(rail,text="更多 ▾",bg=FIELD,fg=FG,activebackground=EDGE,
                                    activeforeground=FG,font=SMALL,relief="flat",pady=7)
        tool_menu=tk.Menu(self.tool_more,tearoff=False,bg=FIELD,fg=FG)
        for name in ("line","rect","ellipse","polygon","bezier"):
            title,key,_=TOOL_INFO[name]
            tool_menu.add_command(label=f"{title}  {key}",command=lambda t=name:self.choose_tool(t))
        tool_menu.add_separator()
        for text,callback in [("水平翻转",self.flip_selection),("旋转90°",self.rotate_selection),
                              ("描边预览",lambda:self.automation_dialog("outline"))]:
            tool_menu.add_command(label=text,command=callback)
        self.tool_more.config(menu=tool_menu)
        self.tool_more.pack(fill="x",pady=6)
        self.button(rail, "使用指南", self.help_dialog, font=SMALL).pack(side="bottom", fill="x", pady=(10, 0))

        self.editor_panes = tk.PanedWindow(workspace, orient="horizontal", bg=EDGE, bd=0,
                                           sashwidth=6, sashrelief="flat", opaqueresize=True)
        self.editor_panes.pack(side="left", fill="both", expand=True)
        self.editor_panes.bind("<ButtonRelease-1>", self.save_ui_layout)
        dock = tk.Frame(self.editor_panes, bg=PANEL, width=310)
        self.editor_dock=dock
        dock.pack_propagate(False)
        preview = tk.Frame(dock, bg=PANEL, padx=14, pady=10)
        self.navigator_panel=preview
        preview.pack(fill="x")
        self.label(preview, "导航预览", font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w")
        self.preview_widget = tk.Label(preview, bg=BG, height=0, cursor="hand2")
        self.preview_widget.pack(fill="x", pady=(8, 5))
        self.preview_widget.bind("<Button-1>", lambda e: self.fit())
        Tooltip(self.preview_widget, "单击适应窗口；动画播放时同步预览")
        self.preview_info = self.label(preview, "", MUTED, SMALL)
        self.preview_info.pack(anchor="w")
        notebook = ttk.Notebook(dock)
        self.control_notebook=notebook
        notebook.pack(fill="both", expand=True)
        panels = []
        for title in ("图层颜色", "工具"):
            frame = tk.Frame(notebook, bg=PANEL)
            notebook.add(frame, text=title)
            panels.append(self._scroll_panel(frame))
        props, automate = panels
        self.manual_tab=notebook.tabs()[0]
        self._section(props, "调色板", "PALETTE")
        self.palette_frame = tk.Frame(props, bg=PANEL)
        self.palette_frame.pack(fill="x")
        self.color_label = self.label(props, "", MUTED, ("Consolas", 8))
        self.color_label.pack(anchor="w", pady=7)
        self.palette_constraint = tk.BooleanVar(value=True)
        self._check(props, "仅使用调色板颜色", self.palette_constraint,
                    lambda: self.apply([{"op": "palette_lock", "enabled": self.palette_constraint.get()}], "设置颜色约束")).pack(anchor="w")
        self.button(props, "+ 添加颜色", self.add_color, font=SMALL, pady=4).pack(anchor="w")
        self._section(props, "图层", "上层在前 / 右键更多")
        self.layers_widget = tk.Listbox(props, bg=BG, fg=FG, selectbackground="#354b70", selectforeground=FG,
                                       relief="flat", borderwidth=0, height=5, activestyle="none", exportselection=False,
                                       font=SMALL, selectborderwidth=0)
        self.layers_widget.pack(fill="x")
        self.layers_widget.bind("<<ListboxSelect>>", self.layer_selected)
        self.layers_widget.bind("<Double-Button-1>", self.rename_layer)
        self.layers_widget.bind("<Button-3>", self.layer_menu)
        row = tk.Frame(props, bg=PANEL)
        row.pack(fill="x", pady=6)
        for text, cb in [("+", self.add_layer), ("显隐", self.toggle_layer), ("锁定", self.lock_layer),
                         ("↑", lambda: self.reorder_layer(1)), ("↓", lambda: self.reorder_layer(-1))]:
            self.button(row, text, cb, padx=7, pady=3, font=SMALL).pack(side="left", padx=(0, 3))
        row = tk.Frame(props, bg=PANEL)
        row.pack(fill="x", pady=3)
        self.label(row, "不透明度", MUTED, SMALL).pack(side="left")
        self._entry(row, self.opacity_var, 4).pack(side="left", padx=8)
        self.button(row, "应用", self.apply_opacity, pady=2, font=SMALL).pack(side="left")
        self._section(props, "当前帧", "TIMING")
        row = tk.Frame(props, bg=PANEL)
        row.pack(fill="x")
        self._entry(row, self.duration_var, 6).pack(side="left")
        self.label(row, " ms", MUTED, SMALL).pack(side="left")
        self.button(row, "应用时长", self.apply_duration, pady=3, font=SMALL).pack(side="right")
        self.timing_hint = self.label(props, "", MUTED, SMALL)
        self.timing_hint.pack(anchor="w", pady=7)

        self._section(automate, "原生自动化", "预览 → 应用 → 可撤销")
        self.quality_label=self.label(automate,"自检：待检查与 AI 看图复核",ACCENT,SMALL,wraplength=270,justify="left")
        self.quality_label.pack(anchor="w",pady=(0,5))
        self.button(automate,"成品自检 · 观看并复查",self.quality_dialog,font=SMALL).pack(fill="x",pady=(0,8))
        self.button(automate, "图片 → 像素底稿", self.reference_dialog, True, font=SMALL).pack(fill="x", pady=(0, 10))
        self.label(automate, "将重复操作变成可调参数的流程。\n应用前查看结果，一次撤销恢复。", MUTED, SMALL, justify="left").pack(anchor="w", pady=(0, 8))
        for kind, title, hint in [("float", "起伏循环", "复制当前帧，让当前图层周期移动"),
                                  ("travel", "往返位移", "设置终点偏移，自动生成往返动作"),
                                  ("duration", "批量帧时长", "统一指定范围的动画节奏"),
                                  ("duplicate", "复制帧范围", "保留全部图层与原始时长"),
                                  ("outline", "批量像素描边", "当前图层 · 当前颜色 · 指定帧范围")]:
            card = tk.Frame(automate, bg=FIELD, padx=10, pady=8)
            card.pack(fill="x", pady=4)
            self.button(card, title + "  →", lambda k=kind: self.automation_dialog(k), padx=0, pady=0,
                        font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
            self.label(card, hint, MUTED, ("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(5, 0))
        self.button(automate, "动画接触表 / 多帧总览", self.overview_dialog, font=SMALL).pack(fill="x", pady=12)
        center = tk.Frame(self.editor_panes, bg=PANEL)
        self.center_panel=center
        self.editor_panes.add(center, minsize=220, stretch="always")
        tabs = tk.Frame(center, bg=PANEL, padx=12, pady=4)
        tabs.pack(fill="x")
        self.project_label = self.label(tabs, "", font=("Microsoft YaHei UI", 10, "bold"))
        self.project_label.pack(side="left")
        self.tab_label = self.label(tabs, "", MUTED, SMALL)
        self.tab_label.pack(side="right")
        settings = tk.Frame(center, bg=FIELD, padx=8, pady=5)
        self.canvas_settings=settings
        settings.pack(fill="x")
        from .feedback_ui import FeedbackPanel
        self.feedback_toolbar=tk.Frame(center,bg=PANEL,padx=12,pady=8)
        self.feedback_panel=FeedbackPanel(self,self.feedback_toolbar)
        edit_controls=tk.Frame(settings,bg=FIELD)
        self.edit_controls=edit_controls
        edit_controls.pack(side="left")
        self.canvas_mode_label=self.label(settings,"成品预览",MUTED,SMALL)
        self.undo_button = self.button(edit_controls, "↶", self.undo, padx=8, pady=2)
        self.undo_button.pack(side="left")
        self.redo_button = self.button(edit_controls, "↷", self.redo, padx=8, pady=2)
        self.redo_button.pack(side="left", padx=(3, 8))
        Tooltip(self.undo_button, "撤销  Ctrl+Z")
        Tooltip(self.redo_button, "重做  Ctrl+Y")
        self.tool_name_label = self.label(edit_controls, "铅笔", ACCENT, SMALL)
        self.tool_name_label.pack(side="left", padx=(0, 8))
        tk.Spinbox(edit_controls, from_=1, to=16, width=3, textvariable=self.stroke_size, bg=BG, fg=FG,
                   buttonbackground=FIELD, relief="flat", insertbackground=FG).pack(side="left")
        self._check(edit_controls, "实心", self.filled).pack(side="left", padx=5)
        self._option(edit_controls, self.symmetry_var, ["关闭对称", "左右对称", "上下对称", "四向对称"], lambda _: self.render()).pack(side="left")
        self.button(settings, "适应 F", self.fit, pady=3, padx=7, font=SMALL).pack(side="right")
        self.button(settings, "−", lambda: self.change_zoom(-1), pady=3, padx=7).pack(side="right", padx=2)
        self.zoom_label = self.label(settings, "100%", MUTED, ("Consolas", 9))
        self.zoom_label.pack(side="right", padx=4)
        self.button(settings, "+", lambda: self.change_zoom(1), pady=3, padx=7).pack(side="right", padx=2)
        view_button = tk.Menubutton(settings, text="视图 ▾", bg=FIELD, fg=FG, activebackground=EDGE,
                                    activeforeground=FG, relief="flat", font=SMALL, padx=7, pady=3)
        view_menu = tk.Menu(view_button, tearoff=False, bg=FIELD, fg=FG)
        for text, var in [("像素网格", self.show_grid), ("洋葱皮", self.onion), ("部位标记", self.show_regions), ("参考叠加", self.show_reference)]:
            view_menu.add_checkbutton(label=text, variable=var, command=self.render)
        view_menu.add_separator()
        view_menu.add_command(label="调整画布…", command=self.resize_dialog)
        view_button.config(menu=view_menu)
        view_button.pack(side="right", padx=(0, 5))
        self.canvas = tk.Canvas(center, bg="#0d1017", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        for event, handler in [("<Configure>", lambda e: self.render()), ("<Button-1>", self.pointer_down),
                               ("<B1-Motion>", self.pointer_drag), ("<ButtonRelease-1>", self.pointer_up),
                               ("<Motion>", self.pointer_hover), ("<Leave>", lambda e: self.canvas.delete("cursor")),
                               ("<Button-3>", lambda e: self.finish_path() if self.path_points else self.pick(e)),
                               ("<Double-Button-1>", lambda e: self.finish_path() if self.tool == "polygon" else None),
                               ("<MouseWheel>", self.wheel), ("<Button-2>", self.pan_start), ("<B2-Motion>", self.pan_move),
                               ("<Button-4>", lambda e: self.change_zoom(1)), ("<Button-5>", lambda e: self.change_zoom(-1))]:
            self.canvas.bind(event, handler)
        self.tool_hint = self.label(center, "", MUTED, ("Microsoft YaHei UI", 8), anchor="w", padx=12, pady=3)
        self.tool_hint.pack(fill="x")
        self.choose_tool("pen")

    def symmetry_mode(self):
        return {"左右对称": "x", "上下对称": "y", "四向对称": "xy"}.get(self.symmetry_var.get(), "off")

    def refresh_projects(self):
        if not hasattr(self,'service'):return
        entries=self.service.projects.listing(self.path)
        signature=tuple((item['id'],item['name'],item['active'],item['available']) for item in entries)
        if self.project_tabs_signature==signature:return
        self.project_tabs_signature=signature
        for child in self.project_tabs.winfo_children():child.destroy()
        self.project_menu.delete(0,'end')
        for title, callback in [("＋ 新项目", self.new_dialog), ("复制为新项目", self.fork_project_dialog),
                                ("历史版本", self.project_history_dialog), ("并排对照", self.compare_projects_dialog)]:
            self.project_menu.add_command(label=title, command=callback)
        self.project_menu.add_separator()
        self.project_menu.add_command(label='项目管理 · 添加 / 删除 / 恢复',command=self.manage_projects_dialog)
        self.project_menu.add_command(label='添加已有项目…',command=self.add_existing_projects)
        self.project_menu.add_command(label='已删除的项目',command=lambda:self.manage_projects_dialog(deleted=True))
        self.project_menu.add_separator()
        for entry in entries:
            title=f"{entry['number']} · {entry['name']}"
            self.project_menu.add_command(label=title,command=lambda key=entry['id']:self.project_action('switch',project_id=key),
                                          state='normal' if entry['available'] else 'disabled')
            button=self.button(self.project_tabs,title[:25],lambda key=entry['id']:self.project_action('switch',project_id=key),
                               entry['active'],pady=5,font=SMALL)
            button.pack(side='left',padx=(0,5))
            button.bind('<Button-3>',lambda event,key=entry['id']:self.project_context_menu(event,key))
            if not entry['available']:button.config(state='disabled')
            Tooltip(button,title+'\n'+entry['path']+'\n右键可删除项目；工程与历史可恢复。')
        if entries:
            if not self.project_shelf.winfo_manager():
                self.project_shelf.pack(fill="x", after=self.workflow_bar)
        else:
            self.project_shelf.pack_forget()
        self.project_tabs.update_idletasks()
        self.project_tabs_canvas.config(scrollregion=self.project_tabs_canvas.bbox('all'))

    def manage_projects_dialog(self,deleted=False):
        from .project_ui import ProjectManagerDialog
        existing=getattr(self,'project_manager',None)
        if existing and existing.dialog.winfo_exists():
            existing.select_tab(deleted)
            existing.refresh()
            existing.dialog.lift()
            return existing
        self.project_manager=ProjectManagerDialog(self,deleted)
        return self.project_manager

    def add_existing_projects(self):
        manager=getattr(self,'project_manager',None)
        parent=manager.dialog if manager and manager.dialog.winfo_exists() else self.root
        paths=filedialog.askopenfilenames(parent=parent,
                    title='添加已有项目 · 可多选',filetypes=[('Pixel Loom 工程','*.pixloom')])
        added=0
        for path in paths:
            if self.project_action('register',path=path):added+=1
        manager=getattr(self,'project_manager',None)
        if manager and manager.dialog.winfo_exists():manager.refresh()
        if added:self.status_label.config(text=f'已添加 {added} 个工程 · 当前作品保持打开',fg=GREEN)
        return added

    def delete_projects(self,project_ids):
        try:
            entries=[self.service.projects.get(key) for key in project_ids]
        except ValueError as exc:
            messagebox.showerror('项目已变化',str(exc),parent=self.root)
            return None
        names='\n'.join(f"{entry['number']} · {entry['name']}" for entry in entries[:5])
        if len(entries)>5:names+=f'\n… 共 {len(entries)} 个项目'
        if not messagebox.askyesno('删除项目',f'删除所选项目？\n\n{names}\n\n将从项目栏移除，工程文件与历史版本保留，可在“已删除”中恢复。',parent=self.root):
            return None
        return self.project_action('remove',project_ids=project_ids)

    def project_context_menu(self,event,project_id):
        menu=tk.Menu(self.root,tearoff=False,bg=FIELD,fg=FG)
        menu.add_command(label='切换到此项目',command=lambda:self.project_action('switch',project_id=project_id))
        menu.add_command(label='添加已有项目…',command=self.add_existing_projects)
        menu.add_command(label='项目管理…',command=self.manage_projects_dialog)
        menu.add_separator()
        menu.add_command(label='删除此项目（可恢复）',command=lambda:self.delete_projects([project_id]))
        menu.tk_popup(event.x_root,event.y_root)

    def project_action(self,action,**fields):
        self.stop_play()
        self.sync_service()
        try:
            result=self.dispatch('POST','/projects',{},dict(action=action,expected_document_id=self.doc.id,
                                  expected_revision=self.doc.revision,source='手动',**fields))[0]
            messages={'remove':'项目已删除 · 文件和历史保留，可从“管理项目 → 已删除”恢复。',
                      'undelete':'项目已恢复 · 原编号、工程文件和历史版本保留。',
                      'register':'已有工程已加入项目栏。'}
            self.status_label.config(text=messages.get(action,'项目已保留 · 可从项目栏切换；新动作请复制为新项目。'),fg=GREEN)
            manager=getattr(self,'project_manager',None)
            if manager and manager.dialog.winfo_exists():manager.refresh()
            return result
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('项目操作未完成',user_error(exc),parent=self.root)
            return None

    def fork_project_dialog(self):
        from tkinter import simpledialog
        name=simpledialog.askstring('复制为新项目','新项目名称（例如：角色 · 向左行走）：',
                                   initialvalue=self.doc.name+' · 新动作',parent=self.root)
        if name and name.strip():return self.project_action('fork',name=name.strip())

    def project_history_dialog(self):
        from .project_ui import HistoryDialog
        self.sync_service()
        try:
            entry=self.service.checkpoint_current()
            if entry is None:
                messagebox.showinfo('历史版本','当前没有已保存项目。先新建、添加或保存一个工程。',parent=self.root)
                return None
        except (OSError,ValueError) as exc:
            messagebox.showerror('历史版本',str(exc),parent=self.root)
            return None
        self.path=self.service.path
        self.saved_fingerprint=self.service.saved_fingerprint
        self.dirty=self.service.dirty
        self.refresh()
        return HistoryDialog(self)

    def compare_projects_dialog(self,project_ids=None):
        from .project_ui import ComparisonDialog
        self.sync_service()
        return ComparisonDialog(self,project_ids)

    def reference_dialog(self):
        from .reference_ui import ReferenceDialog
        existing = getattr(self, "reference_window", None)
        if existing and existing.dialog.winfo_exists():
            existing.dialog.lift()
            return existing
        self.reference_window = ReferenceDialog(self)
        return self.reference_window

    def quality_dialog(self,review_id=None):
        from .quality_ui import QualityDialog
        self.stop_play()
        existing=getattr(self,"quality_window",None)
        if existing and existing.dialog.winfo_exists():
            if existing.doc_id==self.doc.id and existing.loaded_policy==self.doc.quality_policy and existing.region_names==list(self.doc.regions):
                existing.dialog.lift()
                existing.run(review_id)
                return existing
            existing.dialog.destroy()
        self.sync_service()
        self.quality_window=QualityDialog(self,review_id)
        return self.quality_window

    def apply_duration(self):
        try:
            self.apply([{"op": "frame_set", "duration_ms": self.duration_var.get()}], "修改帧时长")
        except tk.TclError:
            self.status_label.config(text="帧时长请输入 16–60000 的整数", fg="#f19493")

    def apply_opacity(self):
        try:
            self.apply([{"op": "layer_set", "opacity": self.opacity_var.get()}], "修改图层不透明度")
        except tk.TclError:
            self.status_label.config(text="不透明度请输入 0–255 的整数", fg="#f19493")

    def new_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("新建像素工程")
        place_dialog(dialog, self.root, 660, 510)
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        body = tk.Frame(dialog, bg=PANEL, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        self.label(body, "从一张画布开始", font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        self.label(body, "选择常用尺寸，或设置自己的整数像素画布。", MUTED, SMALL).pack(anchor="w", pady=(5, 18))
        name, width, height = tk.StringVar(value="未命名作品"), tk.IntVar(value=48), tk.IntVar(value=48)
        presets = tk.Frame(body, bg=PANEL)
        presets.pack(fill="x")
        for i, (title, w, h) in enumerate([("图标 / 16×16", 16, 16), ("角色 / 32×48", 32, 48), ("精灵 / 64×64", 64, 64),
                                           ("瓦片素材 / 32×32", 32, 32), ("场景 / 320×180", 320, 180), ("场景 / 480×270", 480, 270)]):
            self.button(presets, title, lambda x=w, y=h: (width.set(x), height.set(y)), font=SMALL,
                        width=19, pady=10).grid(row=i//3, column=i%3, padx=(0, 7), pady=4)
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x", pady=16)
        for title, var, size in [("名称", name, 22), ("宽", width, 5), ("高", height, 5)]:
            self.label(row, title, MUTED, SMALL).pack(side="left", padx=(0, 5))
            self._entry(row, var, size).pack(side="left", padx=(0, 12), ipady=5)
        visual = tk.Canvas(body, bg=BG, height=120, highlightthickness=0)
        visual.pack(fill="x")
        hint = self.label(body, "", MUTED, SMALL)
        hint.pack(anchor="w", pady=8)
        def update(*_):
            visual.delete("all")
            try:
                w, h = width.get(), height.get()
                Document(w, h)
                ratio = min(440/w, 80/h)
                x, y = (590-w*ratio)/2, (120-h*ratio)/2
                visual.create_rectangle(x, y, x+w*ratio, y+h*ratio, fill=FIELD, outline=ACCENT)
                visual.create_text(295, 60, text=f"{w} × {h} px", fill=FG, font=FONT)
                hint.config(text="透明底色 · 初始 1 图层 / 1 帧 · 可由人和 AI 继续编辑", fg=MUTED)
            except (ValueError, tk.TclError):
                hint.config(text="宽高请输入 1–512 的整数", fg="#f19493")
        for variable in (width, height):
            variable.trace_add("write", update)
        def create():
            try:
                doc = Document(width.get(), height.get(), name.get().strip() or "未命名作品")
                if self.project_action('new',width=doc.width,height=doc.height,name=doc.name):
                    dialog.destroy()
            except (ValueError, tk.TclError) as exc:
                hint.config(text=str(exc), fg="#f19493")
        self.button(body, "创建工程", create, True).pack(side="right", pady=(5, 0))
        update()

    def resize_dialog(self):
        self.stop_play()
        dialog = tk.Toplevel(self.root)
        dialog.title("调整画布 · 预览")
        place_dialog(dialog, self.root, 720, 540)
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        base_id, revision = self.doc.id, self.doc.revision
        source = Document.from_dict(self.doc.to_dict())
        width, height = tk.IntVar(value=source.width), tk.IntVar(value=source.height)
        mode, anchor = tk.StringVar(value="扩展 / 裁剪"), tk.StringVar(value="居中")
        frame = tk.Frame(dialog, bg=PANEL, padx=22, pady=18)
        frame.pack(fill="both", expand=True)
        self.label(frame, "调整画布", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        self.label(frame, "作用于全部图层和帧。应用前可检查裁切或最近邻缩放的结果。", MUTED, SMALL).pack(anchor="w", pady=8)
        row = tk.Frame(frame, bg=PANEL)
        row.pack(fill="x", pady=10)
        for text, var in [("宽", width), ("高", height)]:
            self.label(row, text, MUTED, SMALL).pack(side="left", padx=(0, 5))
            self._entry(row, var, 5).pack(side="left", padx=(0, 12), ipady=5)
        self._option(row, mode, ["扩展 / 裁剪", "最近邻缩放"]).pack(side="left", padx=4)
        self._option(row, anchor, ["左上角", "居中", "底部居中"]).pack(side="left", padx=4)
        preview = tk.Label(frame, bg=BG)
        preview.pack(fill="both", expand=True)
        hint = self.label(frame, "", MUTED, SMALL)
        hint.pack(anchor="w", pady=10)
        plan, photo, job = [None], [None], [None]
        def update():
            job[0] = None
            plan[0] = None
            try:
                op = {"op": "sprite_scale" if mode.get() == "最近邻缩放" else "canvas_resize", "width": width.get(), "height": height.get()}
                if op["op"] == "canvas_resize":
                    op["anchor"] = {"左上角": "top_left", "居中": "center", "底部居中": "bottom_center"}[anchor.get()]
                proposed = Document.from_dict(source.to_dict())
                proposed.apply([op])
                im = proposed.preview(scale=1)
                ratio = min(620/im.width, 270/im.height, 12)
                photo[0] = ImageTk.PhotoImage(im.resize((max(1, int(im.width*ratio)), max(1, int(im.height*ratio))), Image.Resampling.NEAREST))
                preview.config(image=photo[0], text="")
                hint.config(text=f"{source.width} × {source.height}  →  {proposed.width} × {proposed.height} px  ·  {len(source.layers)} 图层 / {len(source.durations)} 帧", fg=MUTED)
                plan[0] = [op]
            except (ValueError, tk.TclError) as exc:
                preview.config(image="", text=str(exc), fg="#f19493", wraplength=600)
                hint.config(text="请检查尺寸或工程总像素限制", fg="#f19493")
        def schedule(*_):
            plan[0] = None
            if job[0]:
                dialog.after_cancel(job[0])
            job[0] = dialog.after(220, update)
        def commit():
            if self.doc.id != base_id or self.doc.revision != revision:
                messagebox.showinfo("工程已发生变化", "请重新打开画布预览，以当前工程为基础调整。", parent=dialog)
                return
            if plan[0] and not self.gesture and not self.path_points and self.apply(plan[0], "调整画布"):
                dialog.destroy()
        self.button(frame, "应用调整", commit, True).pack(anchor="e")
        for variable in (width, height, mode, anchor):
            variable.trace_add("write", schedule)
        def cleanup(e):
            if e.widget == dialog and job[0]:
                dialog.after_cancel(job[0])
                job[0] = None
        dialog.bind("<Destroy>", cleanup, add="+")
        dialog.update_idletasks()
        update()

    def export_dialog(self):
        self.stop_play()
        dialog = tk.Toplevel(self.root)
        dialog.title("导出游戏素材")
        place_dialog(dialog, self.root, 790, 610)
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        # Export the document shown when the window opened, even if AI edits later.
        source = Document.from_dict(self.doc.to_dict())
        source_key = (self.doc.id, self.doc.revision)
        draft_export=tk.BooleanVar(value=self.service.quality.matching_record(source) is None or
                                   self.service.quality.matching_record(source).get("status")!="passed" or
                                   bool(pending_feedback(source)))
        body = tk.Frame(dialog, bg=PANEL, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        self.label(body, "导出游戏素材", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        snapshot_row = tk.Frame(body, bg=PANEL)
        snapshot_row.pack(fill="x", pady=(5, 9))
        snapshot_label = self.label(snapshot_row, "", MUTED, SMALL)
        snapshot_label.pack(side="left")
        refresh_button = self.button(snapshot_row, "刷新为当前工程", lambda: refresh_snapshot(), font=SMALL, pady=3)
        refresh_button.pack(side="right")
        kind = tk.StringVar(value="精灵表 + JSON")
        scale = tk.IntVar(value=1)
        columns = tk.IntVar(value=min(8, len(source.durations)))
        initial_tag = self.tag_var.get() if self.tag_var.get() in source.tags else "全部帧"
        tag = tk.StringVar(value=initial_tag)
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x", pady=8)
        self._option(row, kind, ["透明 PNG", "精灵表 + JSON", "动画 GIF"]).pack(side="left")
        tag_choice = self._option(row, tag, ["全部帧", *source.tags])
        tag_choice.pack(side="left", padx=8)
        for title, var in [("倍数", scale), ("每行列数", columns)]:
            self.label(row, title, MUTED, SMALL).pack(side="left", padx=(8, 4))
            self._entry(row, var, 4).pack(side="left", ipady=5)
        self.label(body, "PNG 导出当前帧；动画按所选动作导出。精灵表附带帧坐标、时长和动作标签。", MUTED, SMALL).pack(anchor="w", pady=7)
        self._check(body,"直接导出当前版本（不标记为 AI 验收）",draft_export).pack(anchor="w",pady=3)
        preview = tk.Label(body, bg=BG)
        preview.pack(fill="both", expand=True)
        hint = self.label(body, "", MUTED, SMALL, justify="left")
        hint.pack(anchor="w", pady=12)
        job, poll_job, photo, valid = [None], [None], [None], [False]
        def update():
            job[0], valid[0] = None, False
            try:
                k = {"透明 PNG": "png", "精灵表 + JSON": "sheet", "动画 GIF": "gif"}[kind.get()]
                s, c = scale.get(), columns.get()
                if not 1 <= s <= 16 or not 1 <= c <= 256:
                    raise PixelError("导出倍数 1–16，每行列数 1–256")
                indexes = source.frame_indices(tag.get() if tag.get() in source.tags else None, playback=k == "gif")
                if k == "png":
                    indexes = [source.active_frame]
                w = source.width*s*(c if k == "sheet" else 1)
                h = source.height*s*((len(indexes)+c-1)//c if k == "sheet" else 1)
                if source.width*source.height*len(indexes)*s*s > 16_777_216 or w*h > 16_777_216:
                    raise PixelError("输出超过 16M 像素；请降低倍数或缩小动作范围")
                if k == "sheet":
                    # Match the selected column layout; huge sheets use a bounded first-row preview.
                    shown = indexes[:min(32, max(c, 1)*4)]
                    im = contact_preview(source, shown, columns=min(c, len(shown)))
                elif k == "png":
                    im = source.preview(source.active_frame, scale=1)
                else:
                    im = contact_preview(source, indexes[:12], columns=4)
                ratio = min(max(1, preview.winfo_width()-10)/im.width, max(1, preview.winfo_height()-10)/im.height, 8)
                photo[0] = ImageTk.PhotoImage(im.resize((max(1, int(im.width*ratio)), max(1, int(im.height*ratio))), Image.Resampling.NEAREST))
                preview.config(image=photo[0], text="")
                hint.config(text=f"输出：{w} × {h} px  ·  {len(indexes)} 帧  ·  {s}× 最近邻\n" + ("布局预览含帧号；实际 PNG 精灵表保留透明背景且不含帧号。" if k == "sheet" else "GIF 预览前 12 帧，采用二值透明和 10ms 时长精度。" if k == "gif" else "保留 RGBA 透明通道。"), fg=MUTED)
                valid[0] = True
            except (ValueError, tk.TclError) as exc:
                hint.config(text=user_error(exc), fg="#f19493")
                preview.config(image="", text="请调整导出参数", fg=MUTED)
            export_button.config(state="normal" if valid[0] else "disabled")
        def schedule(*_):
            valid[0] = False
            export_button.config(state="disabled")
            if job[0]:
                dialog.after_cancel(job[0])
            job[0] = dialog.after(180, update)
        def export():
            if not valid[0]:
                return
            k = {"透明 PNG": "png", "精灵表 + JSON": "sheet", "动画 GIF": "gif"}[kind.get()]
            chosen_tag=tag.get() if tag.get() in source.tags else None
            if not draft_export.get():
                try:
                    self.service.quality.require_pass(source,chosen_tag,frame=source.active_frame if k=="png" else None)
                except ValueError:
                    messagebox.showinfo("仍有待复查内容","可让 AI 先处理问题并复查，或选择“直接导出当前版本”。",parent=dialog)
                    return
            extension = ".gif" if k == "gif" else ".png"
            path = filedialog.asksaveasfilename(parent=dialog, initialdir=WORKSPACE / "exports", initialfile=source.name + ("-当前版" if draft_export.get() else "") + ("-sheet" if k == "sheet" else "") + extension,
                                                defaultextension=extension, filetypes=[(k.upper(), "*"+extension)])
            if not path:
                return
            if k == "sheet" and Path(path).with_suffix(".json").exists():
                if not messagebox.askyesno("覆盖精灵表元数据", "对应的 JSON 已存在，是否同时覆盖？", parent=dialog):
                    return
            try:
                source.export(path, k, scale=scale.get(), columns=columns.get(), tag=tag.get() if tag.get() in source.tags else None)
                self.status_label.config(text=("已导出当前版本 · " if draft_export.get() else "已导出已验收成品 · ") + path, fg=GREEN)
                dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror("导出失败", user_error(exc), parent=dialog)
        export_button = self.button(body, "选择位置并导出", export, True)
        export_button.pack(anchor="e")
        def snapshot_status():
            stale = (self.doc.id, self.doc.revision) != source_key
            snapshot_label.config(text=("工程已更新 · 当前仍导出旧快照" if stale else "当前工程快照") +
                                  f" · {source.name} · r{source.revision}", fg="#ffb887" if stale else MUTED)
            refresh_button.config(state="normal" if stale else "disabled")
        def refresh_snapshot():
            nonlocal source, source_key
            source = Document.from_dict(self.doc.to_dict())
            source_key = (self.doc.id, self.doc.revision)
            menu = tag_choice["menu"]
            menu.delete(0, "end")
            for name in ["全部帧", *source.tags]:
                menu.add_command(label=name, command=tk._setit(tag, name))
            if tag.get() not in source.tags:
                tag.set("全部帧")
            record = self.service.quality.matching_record(source)
            if not record or record.get("status") != "passed" or pending_feedback(source):
                draft_export.set(True)
            if job[0]:
                dialog.after_cancel(job[0])
                job[0] = None
            update()
            snapshot_status()
        def poll():
            poll_job[0] = None
            snapshot_status()
            poll_job[0] = dialog.after(600, poll)
        for var in (kind, tag, scale, columns):
            var.trace_add("write", schedule)
        preview.bind("<Configure>", lambda e: schedule())
        def cleanup(e):
            if e.widget == dialog:
                for pending in (job, poll_job):
                    if pending[0]:
                        dialog.after_cancel(pending[0])
                        pending[0] = None
        dialog.bind("<Destroy>", cleanup, add="+")
        dialog.update_idletasks()
        update()
        poll()
        return dialog

    def automation_dialog(self, kind="float"):
        self.stop_play()
        return AutomationDialog(self, kind)

    def overview_dialog(self):
        self.stop_play()
        source = Document.from_dict(self.doc.to_dict())
        dialog = tk.Toplevel(self.root)
        dialog.title("动画总览 · 单击任意帧跳转")
        place_dialog(dialog, self.root, 820, 610)
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        selected = self.tag_var.get() if self.tag_var.get() in self.doc.tags else None
        indices = source.frame_indices(selected)
        self.label(dialog, f"{selected or '全部动画'}   ·   {len(indices)} 帧   ·   {sum(source.durations[i] for i in indices)/1000:.2f} 秒",
                   font=("Microsoft YaHei UI", 12, "bold"), padx=16, pady=14).pack(anchor="w")
        self.label(dialog, "每页最多 48 帧；点击缩略图返回编辑。", MUTED, SMALL, padx=16).pack(anchor="w")
        controls = tk.Frame(dialog, bg=PANEL, padx=16, pady=10)
        controls.pack(side="bottom", fill="x")
        content = tk.Frame(dialog, bg=PANEL)
        content.pack(fill="both", expand=True)
        body = self._scroll_panel(content)
        page = [0]
        def show(delta=0):
            page[0] = max(0, min((len(indices)-1)//48, page[0]+delta))
            for child in body.winfo_children():
                child.destroy()
            dialog.photos = []
            for n, frame in enumerate(indices[page[0]*48:(page[0]+1)*48]):
                im = source.preview(frame, scale=1)
                ratio = min(90/im.width, 70/im.height)
                photo = ImageTk.PhotoImage(im.resize((max(1, int(im.width*ratio)), max(1, int(im.height*ratio))), Image.Resampling.NEAREST))
                dialog.photos.append(photo)
                def choose(f=frame):
                    if self.doc.id == source.id and self.doc.revision == source.revision:
                        self.select_frame(f)
                    else:
                        messagebox.showinfo("工程已发生变化", "请重新打开总览，查看最新动画帧。", parent=dialog)
                    dialog.destroy()
                self.button(body, f"{frame+1:02d}   {source.durations[frame]}ms", choose, image=photo, compound="top",
                            width=108, height=96, font=("Segoe UI", 9)).grid(row=n//6, column=n%6, padx=4, pady=4)
            page_label.config(text=f"{page[0]+1} / {(len(indices)-1)//48+1}")
        self.button(controls, "上一页", lambda: show(-1)).pack(side="left")
        self.button(controls, "下一页", lambda: show(1)).pack(side="left", padx=6)
        page_label = self.label(controls, "", MUTED)
        page_label.pack(side="right")
        show()

    def command_palette(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("命令中心 · 搜索工具和操作")
        place_dialog(dialog, self.root, 560, 510)
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        self.label(dialog, "想做什么？", font=("Microsoft YaHei UI", 14, "bold"), padx=18, pady=14).pack(anchor="w")
        query = tk.StringVar()
        entry = self._entry(dialog, query)
        entry.pack(fill="x", padx=18, ipady=7)
        listing = tk.Listbox(dialog, bg=BG, fg=FG, selectbackground="#354b70", relief="flat", activestyle="none", font=FONT)
        listing.pack(fill="both", expand=True, padx=18, pady=12)
        commands = [(f"{name}   [{key}]", lambda t=tool: self.choose_tool(t)) for tool, (name, key, _) in TOOL_INFO.items()]
        commands += [("适应画布  [F]", self.fit), ("另存为  [Ctrl Shift S]", self.save_as), ("新建工程", self.new_dialog),
                     ("检查更新 · 新版本与下载", self.show_updates),
                     ("成品自检 · 证据 / 循环播放 / AI结论",self.quality_dialog),
                     ("图片转像素 · 参考图 / MCP 重绘", self.reference_dialog),
                     ("导出素材", self.export_dialog), ("调整画布", self.resize_dialog), ("多帧总览", self.overview_dialog),
                     ("自动化 · 起伏循环", lambda: self.automation_dialog("float")),
                     ("自动化 · 往返位移", lambda: self.automation_dialog("travel")),
                     ("自动化 · 批量帧时长", lambda: self.automation_dialog("duration")),
                     ("自动化 · 复制帧范围", lambda: self.automation_dialog("duplicate")),
                     ("自动化 · 批量描边", lambda: self.automation_dialog("outline")),
                     ("连接 AI / MCP", self.connection_dialog), ("使用指南与恢复", self.help_dialog)]
        filtered = []
        def update(*_):
            filtered[:] = [(name, cb) for name, cb in commands if query.get().lower() in name.lower()]
            listing.delete(0, "end")
            for name, _ in filtered:
                listing.insert("end", name)
            if filtered:
                listing.selection_set(0)
        def run(event=None):
            chosen = listing.curselection()
            if chosen:
                callback = filtered[chosen[0]][1]
                dialog.destroy()
                callback()
        query.trace_add("write", update)
        listing.bind("<Double-Button-1>", run)
        dialog.bind("<Return>", run)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        def arrow(event):
            if filtered:
                index = listing.curselection()[0] if listing.curselection() else 0
                index = max(0, min(len(filtered)-1, index + (1 if event.keysym == "Down" else -1)))
                listing.selection_clear(0, "end")
                listing.selection_set(index)
                listing.see(index)
            return "break"
        entry.bind("<Down>", arrow)
        entry.bind("<Up>", arrow)
        update()
        entry.focus_set()


class AutomationDialog:
    """A planned edit is bound to the exact document/revision shown in its preview."""
    LABELS = {"float": "起伏循环", "travel": "往返位移", "duration": "批量帧时长",
              "duplicate": "复制帧范围", "outline": "批量像素描边"}

    def __init__(self, editor, kind):
        self.editor, self.kind = editor, kind
        self.dialog = d = tk.Toplevel(editor.root)
        d.title("自动化工作台 · " + self.LABELS[kind])
        place_dialog(d, editor.root, 880, 660)
        d.minsize(780, 560)
        d.configure(bg=BG)
        d.transient(editor.root)
        self.job, self.ops, self.proposed = None, None, None
        self.animation_job, self.animation_index = None, 0
        self.base_id, self.base_revision = editor.doc.id, editor.doc.revision
        self.color = editor.color_index
        # Stable snapshot: another AI edit invalidates Apply instead of silently changing the plan.
        self.base = Document.from_dict(editor.doc.to_dict())
        head = tk.Frame(d, bg=PANEL, padx=20, pady=14)
        head.pack(fill="x")
        editor.label(head, self.LABELS[kind], font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        editor.label(head, "调整参数实时预览，应用后作为一次编辑记录。", MUTED, SMALL).pack(anchor="w", pady=(5, 0))
        footer = tk.Frame(d, bg=PANEL, padx=18, pady=12)
        footer.pack(side="bottom", fill="x")
        self.apply_button = editor.button(footer, "应用到工程", self.commit, True)
        self.apply_button.pack(side="right")
        editor.button(footer, "取消", d.destroy).pack(side="right", padx=8)
        self.summary = editor.label(footer, "", MUTED, SMALL, justify="left")
        self.summary.pack(side="left")
        body = tk.Frame(d, bg=BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        controls_outer = tk.Frame(body, bg=PANEL, width=235)
        controls_outer.pack(side="left", fill="y", padx=(0, 14))
        controls_outer.pack_propagate(False)
        controls = editor._scroll_panel(controls_outer)
        self.variables = {
            "first": tk.IntVar(value=editor.doc.active_frame+1), "last": tk.IntVar(value=editor.doc.active_frame+1),
            "count": tk.IntVar(value=8), "dx": tk.IntVar(value=0), "dy": tk.IntVar(value=2 if kind == "float" else 8),
            "duration": tk.IntVar(value=editor.doc.durations[editor.doc.active_frame]), "name": tk.StringVar(value=self.unique_tag("float" if kind == "float" else "travel"))}
        editor.label(controls, "参数", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        fields = [("新增帧数", "count"), ("X 偏移 / px", "dx"), ("Y 偏移 / px", "dy"), ("每帧 / ms", "duration"), ("动作名称", "name")] if kind in ("float", "travel") else [("起始帧", "first"), ("结束帧", "last")]
        if kind == "duration":
            fields.append(("每帧 / ms", "duration"))
        for label, key in fields:
            editor.label(controls, label, MUTED, SMALL).pack(anchor="w", pady=(5, 3))
            editor._entry(controls, self.variables[key]).pack(fill="x", ipady=4)
        target = f"当前图层：{editor.doc.layer().name}\n" if kind in ("float", "travel", "outline") else "全部图层\n"
        target += "只修改选区内像素" if editor.doc.selection and kind in ("float", "travel", "outline") else ""
        if kind in ("float", "travel"):
            target += "\n追加新帧；原始帧保留。\n超出画布的像素会被裁切。"
        if kind == "outline":
            target += "\n描边颜色：" + editor.doc.palette[editor.color_index]
        editor.label(controls, target, MUTED, ("Microsoft YaHei UI", 8), justify="left", wraplength=195).pack(anchor="w", pady=16)
        visual = tk.Frame(body, bg=BG)
        visual.pack(fill="both", expand=True)
        toolbar = tk.Frame(visual, bg=BG)
        toolbar.pack(fill="x", pady=(0, 10))
        self.preview_mode = tk.StringVar(value="帧总览")
        editor._option(toolbar, self.preview_mode, ["帧总览", "动画预览"], lambda _: self.switch_preview()).pack(side="left")
        self.play_label = editor.label(toolbar, "", MUTED, SMALL)
        self.play_label.pack(side="right")
        self.preview = tk.Label(visual, bg=BG, anchor="center")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda e: self.draw_preview())
        for variable in self.variables.values():
            variable.trace_add("write", self.schedule)
        d.bind("<Escape>", lambda e: d.destroy())
        d.bind("<Destroy>", self.cleanup, add="+")
        d.update_idletasks()
        self.rebuild()

    def unique_tag(self, prefix):
        value, index = prefix, 2
        while value in self.editor.doc.tags:
            value, index = f"{prefix}-{index}", index+1
        return value

    def cleanup(self, event):
        if event.widget == self.dialog:
            for job in (self.job, self.animation_job):
                if job:
                    self.dialog.after_cancel(job)
            self.job = self.animation_job = None

    def schedule(self, *_):
        self.ops = None
        self.apply_button.config(state="disabled")
        if self.job:
            self.dialog.after_cancel(self.job)
        self.job = self.dialog.after(220, self.rebuild)

    def rebuild(self):
        self.job = None
        if self.animation_job:
            self.dialog.after_cancel(self.animation_job)
            self.animation_job = None
        try:
            values = {key: variable.get() for key, variable in self.variables.items()}
            values["first"] -= 1
            values["last"] -= 1
            self.ops = animation_plan(self.base, self.kind, color=self.color, **values)
            self.proposed = Document.from_dict(self.base.to_dict())
            self.proposed.apply(self.ops, label=self.LABELS[self.kind], source="手动")
            if self.kind in ("float", "travel"):
                self.preview_frames = list(range(len(self.base.durations), len(self.proposed.durations)))
            elif self.kind == "duplicate":
                self.preview_frames = list(range(values["last"]+1, values["last"]+2+values["last"]-values["first"]))
            else:
                self.preview_frames = list(range(values["first"], values["last"]+1))
            self.animation_index = 0
            total = sum(self.proposed.durations[i] for i in self.preview_frames)/1000
            self.summary.config(text=f"{len(self.preview_frames)} 帧 · {total:.2f} 秒 · 应用后可一次撤销\n总览前 16 帧；动画预览按真实时长播放。", fg=MUTED)
            self.apply_button.config(state="normal")
            self.switch_preview()
        except (PixelError, ValueError, tk.TclError) as exc:
            self.ops = None
            self.proposed = None
            self.preview.config(image="", text=str(exc), fg="#f19493", wraplength=440, font=FONT)
            self.summary.config(text="参数无效，请调整后查看预览。", fg="#f19493")
            self.apply_button.config(state="disabled")

    def draw_preview(self):
        if self.proposed is None:
            return
        if self.preview_mode.get() == "动画预览":
            frame = self.play_indices[self.animation_index % len(self.play_indices)]
            im = self.proposed.preview(frame, scale=1)
            self.play_label.config(text=f"第 {frame+1} 帧 · {self.proposed.durations[frame]}ms")
        else:
            im = contact_preview(self.proposed, self.preview_frames[:16])
            self.play_label.config(text="只读预览")
        width, height = max(1, self.preview.winfo_width()-8), max(1, self.preview.winfo_height()-8)
        ratio = min(width/im.width, height/im.height, 6)
        im = im.resize((max(1, int(im.width*ratio)), max(1, int(im.height*ratio))), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(im)
        self.preview.config(image=self.photo, text="")

    def switch_preview(self):
        if self.animation_job:
            self.dialog.after_cancel(self.animation_job)
            self.animation_job = None
        if not self.proposed:
            return
        self.play_indices = list(self.preview_frames)
        if self.kind == "travel" and len(self.play_indices) > 2:
            self.play_indices += self.play_indices[-2:0:-1]
        self.animation_index = 0
        self.draw_preview()
        if self.preview_mode.get() == "动画预览":
            self.animation_job = self.dialog.after(self.proposed.durations[self.play_indices[0]], self.tick)

    def tick(self):
        self.animation_job = None
        if not self.proposed or self.preview_mode.get() != "动画预览":
            return
        self.animation_index = (self.animation_index+1) % len(self.play_indices)
        self.draw_preview()
        self.animation_job = self.dialog.after(self.proposed.durations[self.play_indices[self.animation_index]], self.tick)

    def commit(self):
        if not self.ops:
            return False
        editor = self.editor
        if editor.doc.id != self.base_id or editor.doc.revision != self.base_revision:
            messagebox.showinfo("工程已发生变化", "你或 AI 已修改工程。请关闭此预览，重新打开自动化流程。", parent=self.dialog)
            return False
        if editor.gesture or editor.path_points:
            messagebox.showinfo("请先完成绘画", "完成当前笔画或路径后再应用。", parent=self.dialog)
            return False
        if editor.apply(self.ops, self.LABELS[self.kind]):
            if self.kind in ("float", "travel") and self.variables["name"].get().strip():
                editor.choose_tag(self.variables["name"].get().strip())
            self.dialog.destroy()
            return True
        return False
