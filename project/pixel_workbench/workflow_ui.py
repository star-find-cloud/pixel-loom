"""Optional read-only workflow viewer. No permanent panels or artwork mutations."""
import tkinter as tk
from tkinter import ttk

from .creation_guidance import TOPICS, workflow_help
from .model import PixelError
from .workflow import ROUTES
from .ui import scrollable_widget


def show(editor):
    previous=getattr(editor,'workflow_window',None)
    if previous is not None and previous.winfo_exists():
        previous.lift();return previous
    window=tk.Toplevel(editor.root)
    editor.workflow_window=window
    window.title('AI 工作流与进度')
    window.geometry('850x650')
    window.transient(editor.root)
    summary_frame,summary=scrollable_widget(window,tk.Text,height=10,wrap='word',padx=12,pady=10)
    summary_frame.pack(fill='x')
    row=ttk.Frame(window,padding=8);row.pack(fill='x')
    ttk.Label(row,text='按需查看说明：').pack(side='left')
    choices={f'{title} · {key}':key for key,(_,title) in TOPICS.items()}
    selected=tk.StringVar(value=next(iter(choices)))
    combo=ttk.Combobox(row,textvariable=selected,values=list(choices),state='readonly',width=70)
    combo.pack(side='left',fill='x',expand=True)
    body=ttk.Frame(window);body.pack(fill='both',expand=True)
    guide=tk.Text(body,wrap='word',padx=12,pady=10)
    scrollbar=ttk.Scrollbar(body,command=guide.yview)
    guide.config(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right',fill='y');guide.pack(fill='both',expand=True)
    def replace(widget,value,keep_view=False):
        if widget.get('1.0','end-1c')==value:return
        top=widget.index('@0,0') if keep_view else '1.0'
        widget.config(state='normal');widget.delete('1.0','end');widget.insert('end',value);widget.config(state='disabled')
        widget.yview(top)
    def load_guide(event=None):replace(guide,workflow_help(choices[selected.get()])['guide'])
    combo.bind('<<ComboboxSelected>>',load_guide);load_guide()
    window.workflow_summary=summary
    def refresh():
        if not window.winfo_exists():return
        try:
            data=editor.service.tasks.status(editor.doc);context=data['context']
            lines=[editor.doc.name,'这些记录只说明 AI 的工作进度，不能代替看图检查。']
            if context is None:lines+=['当前没有 AI 工作记录。连接后从 pixel_onboard 开始即可；旧工程可以照常使用。']
            else:
                lines+=[f"{ROUTES[context['task']]['title']} · {context['stage']} · 记录 {data['task_revision']}",context['brief'],f"下一步：{context['next_action'] or '由 AI 根据任务继续'}"]
                for part in context['parts']:
                    lines.append(f"{part.get('name',part['layer'])}：{part['extraction']} / 遮挡处 {part['hidden']}"+('（需重新检查）' if not part['current'] else ''))
            replace(summary,'\n'.join(lines),keep_view=True)
        except PixelError as exc:replace(summary,f'工作记录暂时无法读取：{exc}\n原工程仍可照常打开、编辑和保存。',keep_view=True)
        window._workflow_job=window.after(1200,refresh)
    def destroyed(event):
        if event.widget is window:
            job=getattr(window,'_workflow_job',None)
            if job:window.after_cancel(job)
    window.bind('<Destroy>',destroyed);refresh()
    return window
