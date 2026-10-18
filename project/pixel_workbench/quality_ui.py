"""Review evidence, real-duration playback and portable AI verdicts in the desktop."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from .model import PixelError
from .quality import effective_policy
from .ui import BG, PANEL, FIELD, FG, MUTED, ACCENT, GREEN, SMALL, place_dialog, scrollable_widget

LABELS = {"pending":"待 AI 看图复核","stale":"作品已修改 · 待复查","passed":"AI 自检通过",
          "needs_changes":"需要修改后复查","uncertain":"尚未确认合格","partial":"部分动作已通过"}


class QualityDialog:
    def __init__(self, editor, review_id=None):
        self.editor = editor
        self.doc_id = editor.doc.id
        self.dialog = d = tk.Toplevel(editor.root)
        d.title("成品自检 · 播放 / 证据 / AI 结论")
        d.configure(bg=BG)
        d.transient(editor.root)
        place_dialog(d,editor.root,1160,790)
        d.minsize(970,680)
        self.playing,self.player_job,self.poll_job=True,None,None
        self.index,self.speed,self.page=0,tk.StringVar(value="1× 原速"),0
        self.ticket,self.photos,self.sheets=None,{},[]
        header=tk.Frame(d,bg=PANEL,padx=18,pady=12)
        header.pack(fill="x")
        editor.label(header,"成品自检",font=("Microsoft YaHei UI",16,"bold")).pack(side="left")
        self.badge=editor.label(header,"",ACCENT,SMALL)
        self.badge.pack(side="left",padx=18)
        editor.button(header,"复制自动自检指令",self.copy_prompt).pack(side="right")
        editor.button(header,"重新检查",self.run,True).pack(side="right",padx=8)
        editor.button(header,"验收设置",self.toggle_settings).pack(side="right",padx=4)
        editor.button(header,"截图反馈",self.mark_frame).pack(side="right",padx=4)
        footer=tk.Frame(d,bg=PANEL,padx=18,pady=10)
        footer.pack(side="bottom",fill="x")
        self.message=editor.label(footer,"",MUTED,SMALL,justify="left",wraplength=1100)
        self.message.pack(anchor="w")
        body=tk.Frame(d,bg=BG,padx=12,pady=10)
        body.pack(fill="both",expand=True)
        side=tk.Frame(body,bg=PANEL,width=265)
        self.side_panel=side
        side.pack(side="left",fill="y",padx=(0,10))
        side.pack_propagate(False)
        controls=editor._scroll_panel(side)
        editor._section(controls,"验收要求","随工程保存")
        initial_tag=(editor.service.quality.tickets.get(review_id,{}).get('scope',{}).get('tag') if review_id else editor.tag_var.get())
        self.scope_choices={'整张图集 / 全局要求':None,**{'动作 · '+name:name for name in editor.doc.tags}}
        self.settings_scope=tk.StringVar(value='动作 · '+initial_tag if initial_tag in editor.doc.tags else '整张图集 / 全局要求')
        editor._option(controls,self.settings_scope,list(self.scope_choices),lambda _:self.load_policy()).pack(fill='x',pady=6)
        editor.label(controls,'动作继承全局要求；帧数按所选范围设置。',MUTED,SMALL,wraplength=225).pack(anchor='w')
        policy=effective_policy(editor.doc,self.scope_choices[self.settings_scope.get()])
        self.loaded_policy=editor.doc.quality_policy
        self.variables={key:tk.StringVar(value="" if policy[key] is None else policy[key]) for key in
                        ("expected_width","expected_height","expected_frames","max_colors","brief","max_rounds")}
        self.transparent=tk.BooleanVar(value=policy["transparent_background"] is True)
        self.uniform=tk.BooleanVar(value=policy["uniform_timing"])
        self.loop=tk.BooleanVar(value=policy["loop"])
        for text,key in [("任务要求","brief"),("目标宽度（可留空）","expected_width"),("目标高度（可留空）","expected_height"),
                         ("目标帧数（可留空）","expected_frames"),("最多不透明颜色（可留空）","max_colors"),("自动修正轮次","max_rounds")]:
            editor.label(controls,text,MUTED,SMALL).pack(anchor="w",pady=(7,3))
            editor._entry(controls,self.variables[key]).pack(fill="x",ipady=4)
        for text,var in [("需要透明背景",self.transparent),("帧时长保持一致",self.uniform),("检查循环衔接",self.loop)]:
            editor._check(controls,text,var).pack(anchor="w",pady=3)
        editor.label(controls,"固定部位（多选）",MUTED,SMALL).pack(anchor="w",pady=(9,4))
        self.region_names=list(editor.doc.regions)
        region_frame,self.regions=scrollable_widget(controls,tk.Listbox,horizontal=True,
            selectmode="multiple",exportselection=False,height=4,bg=BG,fg=FG,
            selectbackground="#354b70",relief="flat",font=SMALL)
        region_frame.pack(fill="x")
        for i,name in enumerate(self.region_names):
            self.regions.insert("end",name)
            if name in policy["fixed_regions"]:
                self.regions.selection_set(i)
        editor.label(controls,"放大检查部位（逗号分隔；留空自动）",MUTED,SMALL).pack(anchor="w",pady=(9,4))
        self.detail_regions=tk.StringVar(value=",".join(policy["detail_regions"]))
        editor._entry(controls,self.detail_regions).pack(fill="x",ipady=4)
        editor.label(controls,"额外视觉要求（每行一项）",MUTED,SMALL).pack(anchor="w",pady=(9,4))
        criteria_frame,self.criteria=scrollable_widget(controls,tk.Text,height=3,bg=BG,fg=FG,
            insertbackground=FG,relief="flat",wrap="word",font=SMALL)
        criteria_frame.pack(fill="x")
        self.criteria.insert("1.0","\n".join(policy["criteria"]))
        editor.button(controls,"保存要求并检查",self.save_settings,True,font=SMALL).pack(fill="x",pady=12)
        editor.label(controls,"程序检查通过后，AI 仍需看图复核。\n发现问题会修改并重新检查。\n作品修改后，旧结论自动失效。",MUTED,SMALL,
                     justify="left",wraplength=225).pack(anchor="w",pady=8)

        right=tk.Frame(body,bg=BG)
        self.right_panel=right
        right.pack(fill="both",expand=True)
        self.notebook=ttk.Notebook(right)
        self.notebook.pack(fill="both",expand=True)
        self.player_frame=tk.Frame(self.notebook,bg=BG)
        self.notebook.add(self.player_frame,text="动作播放")
        toolbar=tk.Frame(self.player_frame,bg=PANEL,padx=8,pady=6)
        toolbar.pack(fill="x")
        self.play_button=editor.button(toolbar,"暂停",self.toggle,pady=3)
        self.play_button.pack(side="left")
        editor.button(toolbar,"上一帧",lambda:self.step(-1),pady=3,font=SMALL).pack(side="left",padx=5)
        editor.button(toolbar,"下一帧",lambda:self.step(1),pady=3,font=SMALL).pack(side="left")
        editor._option(toolbar,self.speed,["1× 原速","0.5× 慢放","2× 快放"],lambda _:self.restart_tick()).pack(side="left",padx=8)
        self.player_info=editor.label(toolbar,"",MUTED,SMALL)
        self.player_info.pack(side="right")
        self.sequence_choice=tk.StringVar(value='')
        self.sequence_menu=editor._option(toolbar,self.sequence_choice,['当前动作'],lambda _:self.select_sequence())
        self.sequence_menu.pack(side='left',padx=4)
        self.player=tk.Label(self.player_frame,bg="#0c1018")
        self.player.pack(fill="both",expand=True)
        self.player.bind("<Configure>",lambda e:self.render_player())
        evidence=tk.Frame(self.notebook,bg=BG)
        self.notebook.add(evidence,text="逐帧与时序证据")
        nav=tk.Frame(evidence,bg=PANEL,padx=8,pady=6)
        nav.pack(fill="x")
        self.sheet_choice=tk.StringVar(value="")
        self.sheet_menu=editor._option(nav,self.sheet_choice,["帧对照"],lambda _:self.render_sheet())
        self.sheet_menu.pack(side="left")
        editor.button(nav,"上一页",lambda:self.change_page(-1),font=SMALL,pady=3).pack(side="left",padx=6)
        editor.button(nav,"下一页",lambda:self.change_page(1),font=SMALL,pady=3).pack(side="left")
        self.sheet_page=editor.label(nav,"",MUTED,SMALL)
        self.sheet_page.pack(side="right")
        self.sheet=tk.Label(evidence,bg=BG)
        self.sheet.pack(fill="both",expand=True)
        self.sheet.bind("<Configure>",lambda e:self.render_sheet())
        result=tk.Frame(self.notebook,bg=PANEL)
        self.notebook.add(result,text="程序检查与 AI 结论")
        self.report=tk.Text(result,bg=PANEL,fg=FG,relief="flat",wrap="word",padx=14,pady=12,font=SMALL)
        scroll=ttk.Scrollbar(result,command=self.report.yview)
        scroll.pack(side="right",fill="y")
        self.report.pack(fill="both",expand=True)
        self.report.config(yscrollcommand=scroll.set)
        d.bind("<Destroy>",self.cleanup,add="+")
        self.run(review_id)
        self.side_panel.pack_forget()
        self.poll_job=d.after(900,self.poll)

    def toggle_settings(self):
        if self.side_panel.winfo_manager():
            self.side_panel.pack_forget()
        else:
            self.side_panel.pack(side="left",fill="y",before=self.right_panel,padx=(0,10))

    def mark_frame(self):
        frame=self.play_indices[self.index%len(self.play_indices)] if self.ticket else self.editor.doc.active_frame
        self.dialog.destroy()
        self.editor.set_workspace_mode("feedback")
        if frame<len(self.editor.doc.durations):
            self.editor.select_frame(frame)
        self.editor.status_label.config(text="已回到当前帧 · 可标记位置，再截图并复制到 AI 对话框。",fg=GREEN)

    def run(self, review_id=None):
        try:
            if self.editor.doc.id!=self.doc_id:
                raise PixelError("工程已切换，请重新打开自检窗口")
            manager=self.editor.service.quality
            if review_id:
                requested=manager.ticket(review_id,self.editor.doc)['scope']['tag']
                self.settings_scope.set('动作 · '+requested if requested is not None else '整张图集 / 全局要求')
                self.load_policy()
            tag=self.scope_choices[self.settings_scope.get()]
            self.ticket=manager.ticket(review_id,self.editor.doc) if review_id else manager.start(self.editor.doc,tag)
            self.page,self.index=0,0
            self.sequence_labels={f"{i+1} · {s['tag'] or '未命名帧'}":i for i,s in enumerate(self.ticket['sequences'])}
            menu=self.sequence_menu['menu'];menu.delete(0,'end')
            for name in self.sequence_labels:menu.add_command(label=name,command=lambda v=name:(self.sequence_choice.set(v),self.select_sequence()))
            self.sequence_choice.set(next(iter(self.sequence_labels)))
            self.select_sequence()
            self.refresh_evidence()
            self.render_player()
            self.render_report()
            self.restart_tick()
        except (ValueError,OSError,KeyError) as exc:
            self.message.config(text=str(exc),fg="#f19493")

    def load_policy(self):
        policy=effective_policy(self.editor.doc,self.scope_choices[self.settings_scope.get()])
        self.loaded_policy=self.editor.doc.quality_policy
        for key,var in self.variables.items():var.set('' if policy[key] is None else policy[key])
        self.transparent.set(policy['transparent_background'] is True)
        self.uniform.set(policy['uniform_timing']);self.loop.set(policy['loop'])
        self.regions.selection_clear(0,'end')
        for i,name in enumerate(self.region_names):
            if name in policy['fixed_regions']:self.regions.selection_set(i)
        self.detail_regions.set(','.join(policy['detail_regions']))
        self.criteria.delete('1.0','end');self.criteria.insert('1.0','\n'.join(policy['criteria']))

    def select_sequence(self):
        seq=self.ticket['sequences'][self.sequence_labels[self.sequence_choice.get()]]
        self.play_indices=seq['playback_frames'];self.sequence_loop=seq['policy']['loop']
        self.index=0;self.render_player();self.restart_tick()

    def save_settings(self):
        try:
            if self.editor.doc.id!=self.doc_id or self.editor.doc.quality_policy!=self.loaded_policy:
                raise PixelError("工程或验收要求已变化，请重新打开窗口后调整")
            settings={key:(int(var.get()) if var.get().strip() else None) for key,var in self.variables.items() if key!="brief"}
            settings.update(brief=self.variables["brief"].get(),transparent_background=self.transparent.get(),
                            uniform_timing=self.uniform.get(),loop=self.loop.get(),
                            fixed_regions=[self.region_names[i] for i in self.regions.curselection()],
                            detail_regions=[v.strip() for v in self.detail_regions.get().replace("，",",").split(",") if v.strip()],
                            criteria=[line.strip() for line in self.criteria.get("1.0","end").splitlines() if line.strip()])
            self.editor.dispatch("POST","/review/settings",{}, {"settings":settings,'tag':self.scope_choices[self.settings_scope.get()],"source":"手动",
                "expected_document_id":self.editor.doc.id,"expected_revision":self.editor.doc.revision})
            self.loaded_policy=self.editor.doc.quality_policy
            self.run()
        except (ValueError,OSError,tk.TclError) as exc:
            self.message.config(text=str(exc),fg="#f19493")

    def refresh_evidence(self):
        data,self.sheets=self.editor.service.quality.evidence(self.ticket,self.page,mark_seen=False)
        self.sheet_labels={"frame_contact":"帧对照","two_loop_timing":"真实时序 · 两次循环",'one_shot_timing':'真实时序 · 单次播放',"loop_seam":"循环首尾","subject_reference":"原图参考","style_reference":"画风参考",
                           "character_pose":"角色基准造型", "character_front":"角色正面", "character_left":"角色左侧", "character_right":"角色右侧", "character_back":"角色背面"}
        choices=["部位放大 · "+role[7:] if role.startswith("detail:") else self.sheet_labels.get(role,role) for role in data["image_roles"]]
        menu=self.sheet_menu["menu"]
        menu.delete(0,"end")
        for choice in choices:
            menu.add_command(label=choice,command=lambda v=choice:(self.sheet_choice.set(v),self.render_sheet()))
        self.sheet_names=choices
        if self.sheet_choice.get() not in choices:
            self.sheet_choice.set(choices[0])
        self.sheet_page.config(text=f"{self.page+1} / {self.ticket['pages']}")
        self.render_sheet()

    def change_page(self, delta):
        if self.ticket:
            self.page=max(0,min(self.ticket["pages"]-1,self.page+delta))
            self.refresh_evidence()

    def render_sheet(self):
        if not self.sheets or self.sheet_choice.get() not in self.sheet_names:
            return
        image=self.sheets[self.sheet_names.index(self.sheet_choice.get())]
        self.display(self.sheet,image,"sheet")

    def display(self, widget, image, key):
        ratio=min(max(1,widget.winfo_width()-12)/image.width,max(1,widget.winfo_height()-12)/image.height,12)
        size=max(1,round(image.width*ratio)),max(1,round(image.height*ratio))
        self.photos[key]=ImageTk.PhotoImage(image.resize(size,Image.Resampling.NEAREST))
        widget.config(image=self.photos[key])

    def render_player(self):
        if not self.ticket:
            return
        frame=self.play_indices[self.index%len(self.play_indices)]
        doc=self.ticket["doc"]
        self.display(self.player,doc.preview(frame,scale=1),"player")
        self.player_info.config(text=f"第 {frame+1} 帧 · {doc.durations[frame]}ms · 快照播放")

    def restart_tick(self):
        if self.player_job:
            self.dialog.after_cancel(self.player_job)
            self.player_job=None
        if self.playing and self.ticket:
            frame=self.play_indices[self.index%len(self.play_indices)]
            speed={"1× 原速":1,"0.5× 慢放":.5,"2× 快放":2}[self.speed.get()]
            self.player_job=self.dialog.after(max(16,round(self.ticket["doc"].durations[frame]/speed)),self.tick)

    def tick(self):
        self.player_job=None
        if not self.sequence_loop and self.index==len(self.play_indices)-1:
            self.playing=False;self.play_button.config(text='播放');return
        self.index=(self.index+1)%len(self.play_indices)
        self.render_player()
        self.restart_tick()

    def toggle(self):
        self.playing=not self.playing
        if self.playing and not self.sequence_loop and self.index==len(self.play_indices)-1:self.index=0
        self.play_button.config(text="暂停" if self.playing else "播放")
        self.restart_tick()

    def step(self, delta):
        self.playing=False
        self.play_button.config(text="播放")
        self.index=(self.index+delta)%len(self.play_indices)
        self.render_player()
        self.restart_tick()

    def render_report(self):
        if not self.ticket:
            return
        manager=self.editor.service.quality
        stale=not manager.is_current(self.editor.doc,self.ticket) or self.editor.doc.id!=self.doc_id
        record=self.ticket["submitted"] or self.ticket.get("stored_record")
        scope=self.ticket["scope"]
        coverage=manager.coverage(self.editor.doc,scope['tag'],scope['layers']) if not stale else None
        blocked=[r for r in self.editor.doc.quality_reviews if coverage and r['review_id'] in coverage['blocked_review_ids']]
        status=('stale' if stale else 'needs_changes' if not self.ticket['analysis']['technical_passed'] else
                'passed' if coverage['passed'] else
                'needs_changes' if coverage['technical_failures'] or any(r['status']=='needs_changes' for r in blocked) else
                'uncertain' if blocked else 'partial' if coverage['review_ids'] else 'pending')
        self.badge.config(text=(scope["tag"]+" · " if scope["tag"] else "")+LABELS[status],fg=GREEN if status=="passed" else ACCENT)
        analysis=self.ticket["analysis"]
        lines=[f"检查范围：{scope['tag'] or '全部帧'} · {len(scope['frames'])} 帧 · {len(scope['layers'])} 图层",
               "程序检查（不代表视觉合格）",""]
        for check in analysis["technical_checks"]:
            details=check["details"]
            if "actual" in details:
                detail=f"实际 {details['actual']} / 要求 {details['required'] if details['required'] is not None else '未限定'}"
            elif "opaque_colors" in details:
                detail=f"实际 {details['opaque_colors']} 色 / 上限 {details['required_maximum'] if details['required_maximum'] is not None else '未限定'}"
            elif "durations_ms" in details:
                times=details["durations_ms"]
                detail=f"{times[0]}ms × {len(times)} 帧" if len(set(times))==1 else str(times[:16])+("…" if len(times)>16 else "")+" ms"
            elif "changed_frames" in details:
                detail="各帧保持一致" if not details["changed_frames"] else "发生变化的帧："+str([f+1 for f in details["changed_frames"]])
            elif "blank_frames" in details:
                detail="各帧均有可见画面" if not details["blank_frames"] else "空白帧："+str([f+1 for f in details["blank_frames"]])
            elif "has_transparent_pixels_in_every_frame" in details:
                detail="各帧含透明像素" if details["has_transparent_pixels_in_every_frame"] else "存在无透明像素的帧"
            else:
                detail="缺少指定命名区域" if "error" in details else str(details)
            lines.append(("✓ " if check["passed"] else "× ")+check["label"]+"  "+detail)
        if analysis["warnings"]:
            lines += ["","需要 AI 观察的风险"]+["• "+w["message"] for w in analysis["warnings"]]
        lines += ["","AI 视觉结论"]
        if record:
            if not self.ticket["submitted"]:
                lines.append("以下为当前内容已有的验收记录；本次新复查尚未提交。")
            lines += [LABELS[record["status"]],record["summary"],"查看方式："+("逐帧与时序图" if record["method"]=="frames_and_timing" else "实际播放与逐帧")]
            if record.get("round_budget_reached"):
                lines.append("已达到自动修正轮次；需要如实报告剩余问题，不能将未解决项标为通过。")
            labels={item["id"]:item["label"] for item in analysis["criteria"]}
            for item in record["visual_checks"]:
                verdict={"pass":"通过","fail":"未通过","uncertain":"未确认"}[item['verdict']]
                lines.append(f"{verdict} · {labels.get(item['criterion_id'],item['criterion_id'])}\n  {item['reason']}")
            if record["warning_resolutions"]:
                lines += ["","风险处理说明"]
                for item in record["warning_resolutions"]:
                    verdict={"acceptable":"接受并说明","needs_fix":"需要修正","uncertain":"未确认"}[item["verdict"]]
                    lines.append(verdict+" · "+item["reason"])
        else:
            if coverage and coverage['passed']:
                lines.append(f"当前范围由 {len(coverage['review_ids'])} 份有效通过记录共同覆盖；本次新复查尚未提交。")
            else:lines.append("尚未收到覆盖此范围的完整通过结论；程序项全部通过也不会自动标记合格。")
        if coverage and not coverage['passed']:
            lines.append('当前仍需复查的动作：'+('、'.join(coverage['missing_tags']) or '未命名帧 / 图集要求'))
        if stale:
            lines += ["","作品已变化：当前播放和检查结果来自旧快照，请重新检查。"]
        if self.editor.doc.quality_reviews:
            lines += ["","复查历史（最近 5 次）"]
            for item in self.editor.doc.quality_reviews[-5:]:
                current="当前范围有效" if manager.is_current(self.editor.doc,item) else "旧版本"
                lines.append(f"第 {item['round']} 轮 · {LABELS[item['status']]} · {current}\n{item['summary']}")
        self.report.config(state="normal")
        self.report.delete("1.0","end")
        self.report.insert("end","\n".join(lines))
        self.report.config(state="disabled")
        self.message.config(text="作品已修改，请重新检查。旧快照不会用于成品验收。" if stale else
            "AI 已完成视觉复核；合格结论仅适用于当前作品和已检查范围。" if status=="passed" else
            "向已连接 MCP 的 AI 发送自动自检指令。AI 会检查证据、修改问题并复查；未确认合格时保持待修改/待复核。",fg=GREEN if status=="passed" else MUTED)

    def copy_prompt(self):
        text=("请使用 Pixel Loom 完成当前作品并自动自检。先调用 pixel_onboard，读取验收要求。完成绘制后调用 pixel_review，"
              "查看所有页的实际画面、多帧对照、真实时序、循环首尾与参考图；可播放时也观看循环。发现贴片平移、断接、抖动、配色或节奏问题，"
              "用 pixel_edit 修正，再重新 pixel_review，直到符合要求。用 pixel_review_submit 逐项记录具体观察和真实查看方式。"
              "程序检查通过不等于视觉合格，不确定就如实记录。达到轮次预算仍有问题时报告剩余缺陷，不能为了交付改成通过。"
              "通过后保存 .pixloom，再成品导出；中间预览用 draft=true 并标为草稿。")
        self.editor.root.clipboard_clear()
        self.editor.root.clipboard_append(text)
        self.message.config(text="自动自检指令已复制；在已连接 MCP 的 AI 对话中发送即可。",fg=GREEN)

    def poll(self):
        self.poll_job=None
        self.render_report()
        self.poll_job=self.dialog.after(900,self.poll)

    def cleanup(self,event):
        if event.widget==self.dialog:
            for job in (self.player_job,self.poll_job):
                if job:
                    self.dialog.after_cancel(job)
            self.player_job=self.poll_job=None
