"""On-demand cleanup preview shared with the MCP service; never deletes on opening."""
from __future__ import annotations

import queue
from pathlib import Path
import threading
import tkinter as tk
from tkinter import messagebox

from .ui import BG, PANEL, FIELD, FG, MUTED, SMALL, place_dialog

REASONS={'Within retention age':'仍在保留期限内','Latest/retained version':'最新版本或最近保留的版本',
         'Pinned version':'已标记保留','Active review asset':'正在使用的检查预览',
         'Active document recovery':'当前作品的恢复稿','Unique/unsaved recovery':'独有或未保存的恢复稿',
         'Active or non-deleted project':'当前项目或尚未删除的项目','Project has pinned versions':'项目含标记保留的版本',
         'Project changed outside editor':'工程文件在应用外发生过修改','Project within retention age':'项目仍在保留期限内',
         'External project file is retained; only local records can be cleared':'外部工程文件保留，仅清理本机记录',
         'Unsafe history folder':'历史目录存在重定向，已跳过','Unsafe cache folder':'缓存目录存在重定向，已跳过',
         'Unsafe or unavailable path':'路径不可安全清理，已跳过','Unreadable recovery; retained for manual recovery':'无法读取的恢复稿，保留以便恢复'}


def size_text(value):
    for unit in ('B','KB','MB','GB'):
        if value<1024 or unit=='GB':return f'{value:.1f} {unit}'
        value/=1024


class StorageDialog:
    def __init__(self, editor, settings=None, on_cleanup=None):
        self.editor, self.fixed_settings, self.on_cleanup=editor,settings,on_cleanup
        self.plan=None
        self.queue=queue.Queue()
        self.job=None
        self.serial=0
        self.dialog=d=tk.Toplevel(editor.root)
        d.title('存储管理')
        d.configure(bg=PANEL)
        d.transient(editor.root)
        place_dialog(d,editor.root,900,650)
        d.minsize(730,540)
        editor.label(d,'存储管理',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',padx=18,pady=(16,5))
        editor.label(d,'先预览，再清理。当前作品、最新及标记保留的版本、未保存稿默认受保护。',MUTED,SMALL).pack(anchor='w',padx=18,pady=5)
        self.usage=editor.label(d,'正在统计本机占用…',MUTED,SMALL)
        self.usage.pack(anchor='w',padx=18,pady=8)
        options=tk.Frame(d,bg=PANEL)
        options.pack(fill='x',padx=18)
        self.cache=tk.BooleanVar(value=True)
        self.versions=tk.BooleanVar(value=False)
        self.recovery=tk.BooleanVar(value=False)
        self.keep=tk.StringVar(value='20')
        self.age=tk.StringVar(value='0')
        if settings is None:
            for text,var in [('无用检查缓存',self.cache),('当前项目旧版本',self.versions),('已保存的恢复副本',self.recovery)]:
                tk.Checkbutton(options,text=text,variable=var,bg=PANEL,fg=FG,selectcolor=FIELD,
                    activebackground=PANEL,font=SMALL,command=self.invalidate).pack(side='left')
            limits=tk.Frame(d,bg=PANEL)
            limits.pack(fill='x',padx=18,pady=5)
            editor.label(limits,'旧版本至少保留最近',MUTED,SMALL).pack(side='left')
            tk.Spinbox(limits,from_=1,to=10000,textvariable=self.keep,width=6,command=self.invalidate).pack(side='left',padx=5)
            editor.label(limits,'版；只清理',MUTED,SMALL).pack(side='left')
            tk.Spinbox(limits,from_=0,to=36500,textvariable=self.age,width=6,command=self.invalidate).pack(side='left',padx=5)
            editor.label(limits,'天以前的数据（0 为不限时间）',MUTED,SMALL).pack(side='left')
            self.keep.trace_add('write',lambda *_:self.invalidate())
            self.age.trace_add('write',lambda *_:self.invalidate())
        else:
            editor.label(options,'仅清理刚才所选的项目 / 版本，具体内容以下方预览为准。',MUTED,SMALL).pack(anchor='w')
        self.details=tk.Text(d,bg=BG,fg=FG,relief='flat',font=SMALL,height=14,wrap='word',padx=12,pady=12)
        self.details.pack(fill='both',expand=True,padx=18,pady=10)
        self.details.insert('end','打开此窗口不会删除任何内容。先点击“预览清理”。\n\n已删除项目的彻底清理：在“项目管理 → 已删除”中选择项目，再点击“彻底清理所选”。')
        self.details.config(state='disabled')
        footer=tk.Frame(d,bg=PANEL)
        footer.pack(fill='x',padx=18,pady=(0,16))
        self.preview_button=editor.button(footer,'预览清理',self.preview,True,font=SMALL)
        self.preview_button.pack(side='left')
        self.prev_button=editor.button(footer,'上一页',lambda:self.turn(-1),font=SMALL)
        self.prev_button.pack(side='left',padx=(8,2))
        self.next_button=editor.button(footer,'下一页',lambda:self.turn(1),font=SMALL)
        self.next_button.pack(side='left',padx=2)
        self.apply_button=editor.button(footer,'清理预览中的内容（不可撤销）',self.apply,font=SMALL)
        self.apply_button.pack(side='right')
        self.invalidate()
        d.bind('<Destroy>',self.cleanup,add='+')
        self.start(self.editor.service.storage.status,'status')

    def invalidate(self):
        self.plan=None
        if hasattr(self,'apply_button'):
            self.apply_button.config(state='disabled')
            self.prev_button.config(state='disabled')
            self.next_button.config(state='disabled')

    def start(self, function, kind):
        self.serial+=1
        serial=self.serial
        self.preview_button.config(state='disabled')
        self.apply_button.config(state='disabled')
        def worker():
            try:self.queue.put((serial,kind,function(),None))
            except (OSError,ValueError,KeyError) as exc:self.queue.put((serial,kind,None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        if self.job is None:self.job=self.dialog.after(40,self.poll)

    def poll(self):
        self.job=None
        try:
            while True:
                serial,kind,data,error=self.queue.get_nowait()
                if serial!=self.serial:continue
                self.preview_button.config(state='normal')
                if error:self.write(error)
                elif kind=='status':
                    names={'cache':'检查缓存','versions':'版本记录','recovery':'恢复副本','unsaved_drafts':'未保存草稿（保护）'}
                    self.usage.config(text='  ·  '.join(names[k]+' '+size_text(v['bytes']) for k,v in data['categories'].items()))
                else:self.render_plan(data)
                return
        except queue.Empty:self.job=self.dialog.after(40,self.poll)

    def write(self,text):
        self.details.config(state='normal')
        self.details.delete('1.0','end')
        self.details.insert('end',text)
        self.details.config(state='disabled')

    def settings(self):
        if self.fixed_settings is not None:return dict(self.fixed_settings)
        targets=[]
        if self.cache.get():targets.append('cache')
        if self.versions.get():targets.append('versions')
        if self.recovery.get():targets.append('recovery')
        settings={'targets':targets,'keep_latest':int(self.keep.get()),'older_than_days':int(self.age.get())}
        if 'versions' in targets:
            entry=self.editor.service.projects.by_path(self.editor.path) if self.editor.path else None
            if not entry:raise ValueError('先保存当前项目，再清理它的旧版本。')
            settings['project_ids']=[entry['id']]
        return settings

    def preview(self):
        self.editor.sync_service()
        try:settings=self.settings()
        except ValueError as exc:self.write(str(exc));return
        self.invalidate()
        self.write('正在生成清理预览…')
        self.start(lambda:self.editor.service.storage.plan(settings),'plan')

    def turn(self,delta):
        if not self.plan:return
        plan_id=self.plan['plan_id']
        page=max(0,self.plan['page']+delta)
        self.start(lambda:self.editor.service.storage.plan(plan_id=plan_id,page=page),'plan')

    def render_plan(self,data):
        self.plan=data
        lines=[f"将清理 {data['version_count']} 个旧版本、{data['file_count']} 个文件，预计释放 {size_text(data['reclaimable_bytes'])}；彻底移除 {data['deleted_project_count']} 条已删除项目记录。",
               f"已保护 / 跳过 {data['protected_count']} 项。第 {data['page']+1}/{data['pages']} 页。",'']
        names={'cache':'缓存','versions':'旧版本','recovery':'恢复副本','deleted_projects':'已删除项目'}
        lines += [f"{names[item['category']]} · {size_text(item['bytes'])} · {item.get('label') or Path(item['path']).name}" for item in data['items']]
        if data['protected']:
            lines+=['','保护项：']+[str(item.get('path') or item.get('project_id') or '')+' · '+REASONS.get(item['reason'],item['reason']) for item in data['protected']]
        self.write('\n'.join(lines))
        enabled=data['file_count']>0 or data['deleted_project_count']>0
        self.apply_button.config(state='normal' if enabled else 'disabled')
        self.prev_button.config(state='normal' if data['page']>0 else 'disabled')
        self.next_button.config(state='normal' if data['has_more'] else 'disabled')

    def apply(self):
        if not self.plan:return
        # Re-read the controls; typing in a field must never apply an older selection.
        try:current_settings=self.editor.service.storage.settings(self.settings())
        except (ValueError,KeyError) as exc:
            self.invalidate();self.write(str(exc));return
        if current_settings!=self.plan['settings']:
            self.invalidate();self.write('范围已改变，请重新预览清理。');return
        plan=self.plan
        self.apply_button.config(state='disabled')
        self.dialog.update_idletasks()
        try:
            result=self.editor.dispatch('POST','/storage',{},dict(action='apply',plan_id=plan['plan_id'],
                user_request='用户在存储管理中选择并执行预览范围的清理',
                expected_document_id=plan['expected_document_id'],expected_revision=plan['expected_revision']))[0]
            self.invalidate()
            self.write(f"已删除 {result['removed_files']} 个文件，释放 {size_text(result['freed_bytes'])}。\n失败 {result['failed_count']} 项。\n当前作品未改动。"+
                       '\n'.join('\n'+item['path']+'：'+item['error'] for item in result['failed']))
            if self.on_cleanup:self.on_cleanup()
            manager=getattr(self.editor,'project_manager',None)
            if manager and manager.dialog.winfo_exists():manager.refresh()
            self.start(self.editor.service.storage.status,'status')
            return result
        except (OSError,ValueError,KeyError) as exc:
            self.invalidate()
            self.write('清理未执行完毕：'+str(exc)+'\n请重新预览。')
            messagebox.showerror('清理未完成',str(exc),parent=self.dialog)

    def cleanup(self,event):
        if event.widget is self.dialog:
            self.serial+=1
            if self.job:self.dialog.after_cancel(self.job)
            self.job=None
