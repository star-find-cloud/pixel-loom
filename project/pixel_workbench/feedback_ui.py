"""Human-first feedback dock and non-destructive canvas annotations."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import simpledialog

from .model import PixelError
from .ui import BG, PANEL, FIELD, EDGE, FG, MUTED, ACCENT, GREEN, SMALL

MARK = "#ffb887"
STATUS = {"open":"待 AI 查看", "working":"AI 处理中", "needs_clarification":"AI 想确认", "resolved":"已处理", "dismissed":"已关闭"}


def annotation_shape(tool, points):
    if not points:
        return None
    xs, ys = zip(*points)
    rect = [min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1]
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))
    if tool == "feedback_lasso" and len(set(points)) >= 3 and area:
        step = max(1, math.ceil(len(points)/500))
        sampled = points[::step]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        return {"kind":"lasso", "points":[list(p) for p in sampled]}
    return {"kind":"ellipse" if tool == "feedback_ellipse" else "rect", "rect":rect}


def shape_rect(shape):
    if shape.get("rect"):
        return shape["rect"]
    xs, ys = zip(*shape["points"])
    return [min(xs), min(ys), max(xs)-min(xs)+1, max(ys)-min(ys)+1]


def draw_annotations(editor):
    displayed_frame=editor.play_frame if editor.playing else editor.doc.active_frame
    shape = editor.feedback_draft
    label = "截图标记"
    issue = None
    if not shape and editor.feedback_focus:
        issue = next((i for i in getattr(editor.doc,"feedback",[]) if i["id"] == editor.feedback_focus),None)
        if issue and displayed_frame in issue["frames"]:
            shape, label = issue["shape"], "问题 " + issue["id"][:6]
    if shape and editor.feedback_draft and editor.feedback_panel.scope.get()=="当前帧" and displayed_frame!=getattr(editor,"feedback_draft_frame",editor.doc.active_frame):
        shape=None
    if editor.gesture and editor.gesture.get("annotation"):
        shape = annotation_shape(editor.gesture["tool"], editor.gesture["points"])
        label = "松开后截图并复制"
    if not shape or editor.workspace_mode != "feedback":
        return
    ox, oy = editor.origin
    z = editor.zoom
    x,y,w,h = shape_rect(shape)
    box = [ox+x*z,oy+y*z,ox+(x+w)*z,oy+(y+h)*z]
    options = dict(outline=MARK, width=2, dash=(6,3), tags="feedback")
    if shape["kind"] == "lasso":
        coords = [v for px,py in shape["points"] for v in (ox+(px+.5)*z,oy+(py+.5)*z)]
        if len(coords)>=6:
            editor.canvas.create_polygon(*coords, fill=MARK, stipple="gray12", **options)
    elif shape["kind"] == "ellipse":
        editor.canvas.create_oval(*box, **options)
    else:
        editor.canvas.create_rectangle(*box, **options)
    editor.canvas.create_text(box[0]+4,max(12,box[1]-10),text=label,fill=MARK,anchor="sw",font=SMALL,tags="feedback")


class LegacyFeedbackPanel:
    def __init__(self, editor, parent):
        self.editor = editor
        self.parent = parent
        self.selected_id = None
        self.signature = None
        self.issue_ids = []
        self.mode = None
        self.heading = editor.label(parent,"一起把成品改好",font=("Microsoft YaHei UI",13,"bold"))
        self.heading.pack(anchor="w",pady=(12,4))
        self.hint = editor.label(parent,"先看成品，再圈出需要修改的地方。",MUTED,SMALL,wraplength=252,justify="left")
        self.hint.pack(anchor="w",pady=(0,12))

        self.create_frame = tk.Frame(parent,bg=PANEL)
        self.create_frame.pack(fill="x")
        editor.label(self.create_frame,"想画什么？",fg=FG,font=SMALL).pack(anchor="w",pady=(0,5))
        self.brief = self.textbox(self.create_frame,3)
        self.brief.pack(fill="x")
        row=tk.Frame(self.create_frame,bg=PANEL)
        row.pack(fill="x",pady=7)
        editor.button(row,"导入参考图",editor.reference_dialog,pady=5,font=SMALL).pack(side="left")
        editor.button(row,"复制创作指令",self.copy_create,True,pady=5,font=SMALL).pack(side="right")
        editor.label(self.create_frame,"把指令交给已连接的 Codex / Claude。\nAI 和你编辑同一份工程。",MUTED,SMALL,justify="left").pack(anchor="w",pady=(2,10))

        self.form = tk.Frame(parent,bg=PANEL)
        self.mark_info = editor.label(self.form,"先在画布上圈选位置",MARK,SMALL,wraplength=252,justify="left")
        self.mark_info.pack(anchor="w",pady=(0,8))
        row=tk.Frame(self.form,bg=PANEL)
        row.pack(fill="x",pady=(0,7))
        editor.label(row,"问题出现于",MUTED,SMALL).pack(side="left")
        self.scope=tk.StringVar(value="当前帧")
        editor._option(row,self.scope,["当前帧","当前动作","全部帧"]).pack(side="right")
        self.description=self.textbox(self.form,4)
        self.description.pack(fill="x")
        editor.label(self.form,"写清问题会更快，例如“裙摆有残点”。\n也可以只圈选，让 AI 先问你。",MUTED,SMALL,justify="left",wraplength=252).pack(anchor="w",pady=6)
        row=tk.Frame(self.form,bg=PANEL)
        row.pack(fill="x",pady=(0,12))
        editor.button(row,"清除标记",self.clear_mark,pady=5,font=SMALL).pack(side="left")
        self.submit_button=editor.button(row,"提交问题",self.submit,True,pady=5,font=SMALL)
        self.submit_button.pack(side="right")

        self.notice=editor.label(parent,"",GREEN,SMALL,wraplength=252,justify="left")
        self.notice.pack(anchor="w",pady=(0,8))
        row=tk.Frame(parent,bg=PANEL)
        row.pack(fill="x",pady=(3,6))
        self.count=editor.label(row,"问题单",font=("Microsoft YaHei UI",10,"bold"))
        self.count.pack(side="left")
        editor.button(row,"圈一个问题",lambda:editor.set_workspace_mode("feedback"),pady=2,padx=5,font=SMALL).pack(side="right")
        self.queue=tk.Listbox(parent,bg=BG,fg=FG,selectbackground="#354b70",height=4,relief="flat",
                             exportselection=False,font=SMALL,activestyle="none")
        self.queue.pack(fill="x")
        self.queue.bind("<<ListboxSelect>>",self.select)
        self.detail=self.textbox(parent,6)
        self.detail.pack(fill="x",pady=(8,4))
        self.detail.config(state="disabled")
        self.actions=tk.Frame(parent,bg=PANEL)
        self.actions.pack(fill="x",pady=5)
        editor.button(self.actions,"定位标记",self.locate,pady=4,padx=7,font=SMALL).pack(side="left")
        editor.button(self.actions,"复制给 AI",self.copy_issue,pady=4,padx=7,font=SMALL).pack(side="right")
        self.reply_frame=tk.Frame(parent,bg=PANEL)
        editor.label(self.reply_frame,"回复 AI 的问题",MARK,SMALL).pack(anchor="w",pady=(8,5))
        self.reply_text=self.textbox(self.reply_frame,3)
        self.reply_text.pack(fill="x")
        editor.button(self.reply_frame,"提交回复",self.reply,True,pady=5,font=SMALL).pack(anchor="e",pady=6)
        self.manual_button=editor.button(parent,"我已手动检查并处理",self.manual_resolve,pady=5,font=SMALL)
        self.manual_button.pack(fill="x",pady=6)
        self.dismiss_button=editor.button(parent,"关闭这条问题",self.dismiss,pady=3,font=SMALL)
        self.dismiss_button.pack(anchor="e")
        self.footer=editor.label(parent,"问题单随工程保存。AI 通过 MCP 读取；\n复制指令到 AI 客户端可开始处理。",MUTED,SMALL,justify="left",wraplength=252)
        self.footer.pack(anchor="w",pady=(8,12))

    @staticmethod
    def textbox(parent,height):
        return tk.Text(parent,height=height,bg=FIELD,fg=FG,insertbackground=ACCENT,wrap="word",relief="flat",
                       highlightthickness=1,highlightbackground=EDGE,highlightcolor=ACCENT,font=SMALL,padx=9,pady=7,undo=True)

    def show_mode(self, mode):
        self.mode=mode
        self.create_frame.pack_forget()
        self.form.pack_forget()
        if mode=="feedback":
            self.form.pack(fill="x",before=self.notice)
            self.heading.config(text="圈出来，让 AI 仔细看")
            self.hint.config(text="标记只覆盖在画布上，原图不会被涂改。")
        else:
            self.create_frame.pack(fill="x",before=self.notice)
            self.heading.config(text="一起把成品改好")
            self.hint.config(text="先看成品，再圈出需要修改的地方。")
        self.update_mark()

    def update_mark(self):
        shape=self.editor.feedback_draft
        if shape:
            x,y,w,h=shape_rect(shape)
            frame=getattr(self.editor,"feedback_draft_frame",self.editor.doc.active_frame)+1
            self.mark_info.config(text=f"已标记第 {frame} 帧 · {w} × {h} 像素\n提交时会附上位置、相关帧和当前画面。")
        else:
            self.mark_info.config(text="拖动套圈、框选或椭圆来标记。\n没有标记时，提交整幅图的问题。")

    def selected(self):
        return next((i for i in getattr(self,"public_issues",[]) if i["id"]==self.selected_id),None)

    def refresh(self):
        if not hasattr(self.editor,"service"):
            return
        from .feedback import summary
        info=summary(self.editor.doc)
        issues=info["issues"]
        self.public_issues=issues
        signature=json_signature(issues)
        self.count.config(text=f"问题单 · {info['pending_count']} 待处理")
        if signature!=self.signature:
            self.signature=signature
            self.issue_ids=[i["id"] for i in issues]
            self.queue.delete(0,"end")
            for issue in issues:
                state=STATUS.get(issue["status"],issue["status"])
                if issue.get("resolution_stale"):
                    state="修改后待复查"
                text=issue["description"].replace("\n"," ")[:25]
                self.queue.insert("end",f"{state}  ·  {text}")
            for widget in (self.queue,self.actions,self.manual_button,self.dismiss_button):
                widget.pack_forget()
            if issues:
                self.detail.config(height=6)
                self.queue.pack(fill="x",before=self.detail)
                self.actions.pack(fill="x",pady=5,before=self.footer)
                self.manual_button.pack(fill="x",pady=6,before=self.footer)
                self.dismiss_button.pack(anchor="e",before=self.footer)
            else:
                self.detail.config(height=3)
            if self.selected_id not in self.issue_ids:
                self.selected_id=self.issue_ids[-1] if self.issue_ids else None
            if self.selected_id:
                self.queue.selection_set(self.issue_ids.index(self.selected_id))
            self.render_issue()
        if info.get("needs_clarification_count"):
            self.editor.workflow_hint.config(text=f"AI 有 {info['needs_clarification_count']} 个问题需要你确认",fg=MARK)
        self.update_mark()

    def select(self,event=None):
        picked=self.queue.curselection()
        if picked:
            self.selected_id=self.issue_ids[picked[0]]
            self.render_issue()

    def render_issue(self):
        issue=self.selected()
        self.detail.config(state="normal")
        self.detail.delete("1.0","end")
        self.reply_frame.pack_forget()
        if issue:
            frames="、".join(str(f+1) for f in issue["frames"][:12])
            if len(issue["frames"])>12:frames+="…"
            self.detail.insert("end",f"第 {frames} 帧\n{issue['description']}\n")
            for q in issue.get("questions",[]):
                self.detail.insert("end",f"\nAI：{q['question']}\n")
                if q.get("answer"):self.detail.insert("end",f"你：{q['answer']}\n")
            resolution=issue.get("resolution")
            if resolution:
                self.detail.insert("end","\n处理说明："+str(resolution.get("text",resolution.get("explanation","")))+"\n")
            if issue["status"]=="needs_clarification":
                self.reply_frame.pack(fill="x",before=self.manual_button)
                self.notice.config(text="AI 需要你补充说明。回复后，它能继续查看和修复。",fg=MARK)
            elif issue["status"]=="resolved":
                self.notice.config(text="这条问题已处理，可查看说明或继续标记新问题。",fg=GREEN)
            elif issue["status"]=="dismissed":
                self.notice.config(text="这条问题已关闭，原标注和问答仍会保留。",fg=MUTED)
            self.manual_button.config(state="disabled" if issue["status"] in ("resolved","dismissed") else "normal")
        else:
            self.detail.insert("end","还没有问题单。\n看到需要修改的地方，直接在画布上圈出来。")
            self.manual_button.config(state="disabled")
        self.detail.config(state="disabled")

    def call(self,action,**payload):
        e=self.editor
        e.stop_play()
        e.sync_service()
        data=e.service.feedback_action({"action":action,"source":"手动",**payload,
            "expected_document_id":e.doc.id,"expected_revision":e.doc.revision})
        if action not in ("list","inspect"):
            e.doc=e.service.doc
            e.changed("问题单已更新，随工程保存")
        return data

    def submit(self):
        e=self.editor
        try:
            if e.playing:
                frame=e.play_frame
                e.select_frame(frame)
            frames=[e.doc.active_frame]
            if self.scope.get()=="全部帧":frames=list(range(len(e.doc.durations)))
            elif self.scope.get()=="当前动作":
                tag=e.tag_var.get() if e.tag_var.get() in e.doc.tags else None
                frames=e.doc.frame_indices(tag)
            if len(frames)>64:
                raise PixelError("请分动作或帧段提交，每张问题单最多包含64帧。")
            shape=e.feedback_draft or {"kind":"rect","rect":[0,0,e.doc.width,e.doc.height]}
            text=self.description.get("1.0","end").strip()
            if not text:text="我标记了这个区域，但还没写具体问题。请先询问我希望修改什么，再动手修复。"
            d=self.call("create",shape=shape,frames=frames,description=text)
            self.selected_id=d["issue"]["id"]
            e.feedback_focus=self.selected_id
            e.feedback_draft=None
            self.description.delete("1.0","end")
            self.signature=None
            self.refresh()
            e.render()
            self.notice.config(text="已提交问题单。复制修复指令给已连接的 AI，它就能读取标记与画面。",fg=GREEN)
        except (ValueError,tk.TclError) as exc:
            self.notice.config(text=str(exc),fg=MARK)

    def locate(self):
        issue=self.selected()
        if not issue:return
        e=self.editor
        e.feedback_draft=None
        e.feedback_focus=issue["id"]
        e.set_workspace_mode("feedback")
        frame=next((f for f in issue["frames"] if f<len(e.doc.durations)),None)
        if frame is not None:e.select_frame(frame)
        e.render()

    def clear_mark(self):
        self.editor.feedback_draft=None
        self.editor.feedback_focus=None
        self.editor.render()
        self.update_mark()

    def copy(self,text,notice):
        self.editor.root.clipboard_clear()
        self.editor.root.clipboard_append(text)
        self.notice.config(text=notice,fg=GREEN)

    def copy_create(self):
        brief=self.brief.get("1.0","end").strip()
        if not brief:
            self.notice.config(text="先写下你想画的内容，或导入一张参考图。",fg=MARK)
            self.brief.focus_set()
            return
        self.copy("请通过 Pixel Loom MCP 制作下面的像素作品。先 pixel_onboard 读取当前工程，保留已有作品；"
            "使用原生图层和动画工具制作，让用户可以继续手动修改。完成后逐帧看图、修正并自检，保存工程。"
            "如果已有问题单先通过 pixel_feedback 读取；不清楚用户意思时先提问。\n\n用户需求："+brief,
            "已复制创作指令，粘贴到已连接的 AI 客户端即可开始。")

    def copy_issue(self):
        issue=self.selected()
        if not issue:return
        self.copy("请通过 Pixel Loom MCP 处理问题单 "+issue["id"]+"。先 pixel_onboard，再用 pixel_feedback(action='inspect', issue_id='"+
            issue["id"]+"') 查看全部相关帧的圈选位置、原始快照和当前区域。用户原话："+issue["description"]+
            "\n如果不清楚用户希望改什么，先 pixel_feedback(action='ask') 提出具体问题并等待用户回答，不要猜。"
            "明确后局部修复，重新 inspect 全部页，确认后 resolve 并说明修改；再逐帧自检和保存可编辑工程。",
            "已复制问题单指令。粘贴给已连接的 AI，它能直接定位对应区域。")

    def reply(self):
        issue=self.selected()
        if not issue:return
        text=self.reply_text.get("1.0","end").strip()
        if not text:
            self.notice.config(text="写下回复后再提交。",fg=MARK)
            return
        try:
            self.call("reply",issue_id=issue["id"],text=text)
            self.reply_text.delete("1.0","end")
            self.notice.config(text="回复已保存到问题单，AI 可以继续处理。",fg=GREEN)
        except ValueError as exc:self.notice.config(text=str(exc),fg=MARK)

    def manual_resolve(self):
        issue=self.selected()
        if not issue:return
        try:
            evidence=self.call("inspect",issue_id=issue["id"])
            for page in range(1,evidence.get("page_count",1)):
                self.call("inspect",issue_id=issue["id"],inspection_id=evidence["inspection_id"],page=page)
            self.call("resolve",issue_id=issue["id"],inspection_id=evidence["inspection_id"],
                      text="用户已手动查看并处理所圈区域；此标记不等同于 AI 成品验收。")
            self.notice.config(text="已记录为你手动处理。当前版本仍可随时保存和导出。",fg=GREEN)
        except ValueError as exc:self.notice.config(text=str(exc),fg=MARK)

    def dismiss(self):
        issue=self.selected()
        if not issue:return
        reason=simpledialog.askstring("关闭问题","说明关闭原因，例如：该帧已删除，准备重新圈选。",parent=self.editor.root)
        if reason:
            try:
                self.call("dismiss",issue_id=issue["id"],text=reason)
                self.notice.config(text="已保留记录并关闭这条问题。",fg=GREEN)
            except ValueError as exc:self.notice.config(text=str(exc),fg=MARK)


def json_signature(value):
    import json
    return json.dumps(value,ensure_ascii=False,sort_keys=True)


class FeedbackPanel:
    """Contextual screenshot toolbar; no permanent creation/AI sidebar."""
    def __init__(self, editor, parent):
        self.editor=editor
        self.parent=parent
        self.scope=tk.StringVar(value="当前帧")
        self.last_capture_path=None
        self.last_capture=None
        self.history_window=None
        self.capture_frame=tk.Frame(parent,bg=PANEL)
        self.capture_frame.pack(fill="x")
        self.capture_button=editor.button(self.capture_frame,"截图并复制",self.capture,True,pady=6,font=SMALL)
        self.capture_button.pack(side="left")
        editor.button(self.capture_frame,"清除标记",self.clear_mark,pady=6,font=SMALL).pack(side="left",padx=6)
        editor.button(self.capture_frame,"查看截图",self.show_last,pady=6,font=SMALL).pack(side="left")
        self.mark_info=editor.label(self.capture_frame,"",MARK,SMALL)
        self.mark_info.pack(side="left",padx=14)
        self.notice=editor.label(parent,"复制后到 AI 对话框按 Ctrl+V 粘贴，再说明要修改的内容。",MUTED,SMALL,justify="left")
        self.notice.pack(anchor="w",pady=(7,0))
        parent.bind("<Configure>",lambda event:self.notice.config(wraplength=max(300,event.width-24)))

    def show_mode(self,mode):
        if mode=="feedback":
            self.parent.pack(fill="x",before=self.editor.canvas_settings)
        else:
            self.parent.pack_forget()
        self.update_mark()

    def update_mark(self):
        frame=self.editor.play_frame if self.editor.playing else self.editor.doc.active_frame
        shape=self.editor.feedback_draft
        if shape:
            _,_,w,h=shape_rect(shape)
            self.mark_info.config(text=f"第 {frame+1} 帧 · 已标记 {w} × {h} px · 附局部放大")
        else:
            self.mark_info.config(text=f"第 {frame+1} 帧 · 整幅画布，可选圈出问题位置")

    def refresh(self):
        self.update_mark()

    def clear_mark(self):
        self.editor.feedback_draft=None
        self.editor.feedback_focus=None
        self.editor.render()
        self.update_mark()

    def capture(self):
        from .feedback_capture import capture_feedback
        from .image_clipboard import copy_image
        e=self.editor
        self.last_capture=self.last_capture_path=None
        frame=e.play_frame if e.playing else e.doc.active_frame
        e.stop_play()
        if frame!=e.doc.active_frame:e.select_frame(frame)
        shape=e.feedback_draft
        if not shape and e.feedback_focus:
            issue=next((i for i in getattr(e.doc,"feedback",[]) if i["id"]==e.feedback_focus and frame in i["frames"]),None)
            if issue:shape=issue["shape"]
        try:
            capture=capture_feedback(e.doc,frame,shape)
            target=capture.save(e.service.workspace/"feedback-captures")
            self.last_capture,self.last_capture_path=capture,target
            copied=copy_image(capture.image,capture.png_bytes(),e.root.winfo_id())
            if not copied.get("copied"):raise OSError("图片尚未复制；PNG 已保存。")
            self.notice.config(text="图片已复制。请到 AI 对话框按 Ctrl+V 粘贴，并说明希望修改的地方。",fg=GREEN)
            e.status_label.config(text="问题截图已复制 · 切换到 AI 对话框粘贴即可",fg=GREEN)
            self.update_mark()
            return target
        except (ValueError,OSError) as exc:
            self.notice.config(text=str(exc)+(" 可点“查看截图”，把保存的 PNG 发送给 AI。" if self.last_capture_path else ""),fg=MARK)
            e.status_label.config(text="截图复制未完成，请查看截图工具栏提示。",fg=MARK)
            return None

    def guide(self):
        from .feedback_capture import GUIDE_PATH
        return self.text_dialog("给 AI 的截图说明",GUIDE_PATH.read_text(encoding="utf-8"))

    def text_dialog(self,title,text):
        from .ui import place_dialog
        dialog=tk.Toplevel(self.editor.root)
        dialog.title(title)
        dialog.configure(bg=PANEL)
        dialog.transient(self.editor.root)
        place_dialog(dialog,self.editor.root,800,620)
        widget=LegacyFeedbackPanel.textbox(dialog,24)
        widget.pack(fill="both",expand=True,padx=16,pady=16)
        widget.insert("1.0",text)
        widget.config(state="disabled")
        return dialog

    def show_last(self):
        if not self.last_capture_path:
            self.notice.config(text="先点击“截图并复制”。",fg=MARK)
            return None
        from PIL import Image,ImageTk
        from .ui import place_dialog
        dialog=tk.Toplevel(self.editor.root)
        dialog.title("问题截图 · 可直接粘贴到 AI 对话框")
        dialog.configure(bg=PANEL)
        dialog.transient(self.editor.root)
        place_dialog(dialog,self.editor.root,900,760)
        image=Image.open(self.last_capture_path).convert("RGB")
        image.thumbnail((860,650),Image.Resampling.NEAREST)
        photo=ImageTk.PhotoImage(image)
        widget=tk.Label(dialog,image=photo,bg=BG)
        widget.image=photo
        widget.pack(fill="both",expand=True,padx=12,pady=12)
        self.editor.label(dialog,str(self.last_capture_path),MUTED,SMALL,wraplength=840).pack(padx=12,pady=(0,12))
        return dialog

    def history(self):
        from .ui import place_dialog
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift()
            return self.history_window
        dialog=tk.Toplevel(self.editor.root)
        self.history_window=dialog
        dialog.title("旧版问题记录 · 保留原标记与问答")
        dialog.configure(bg=PANEL)
        dialog.transient(self.editor.root)
        place_dialog(dialog,self.editor.root,420,760)
        panel=LegacyFeedbackPanel(self.editor,self.editor._scroll_panel(dialog))
        panel.heading.config(text="旧版问题记录")
        panel.hint.config(text="已有记录继续保留；新的反馈使用截图发送。")
        panel.create_frame.pack_forget()
        panel.refresh()
        dialog.panel=panel
        def poll():
            if dialog.winfo_exists():
                panel.refresh()
                dialog.after(900,poll)
        dialog.after(900,poll)
        return dialog
