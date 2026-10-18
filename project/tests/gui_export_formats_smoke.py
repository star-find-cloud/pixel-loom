"""Exercise actual optional format controls, output bundles and collision prompts."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-gui-export-') as folder:
        root_path=Path(folder)
        os.environ['PIXEL_LOOM_HOME']=str(root_path/'data');os.environ['PIXEL_LOOM_WORKSPACE']=str(root_path/'work')
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        root=tk.Tk();root.withdraw();editor=Editor(root)
        root.after_cancel(editor.welcome_job);editor.welcome_job=None;editor.updates.preferences['check_on_startup']=False
        errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        def widgets(parent):
            for child in parent.winfo_children():yield child;yield from widgets(child)
        def option(dialog,first):
            for w in widgets(dialog):
                if isinstance(w,tk.OptionMenu) and w['menu'].entrycget(0,'label')==first:return w
            raise AssertionError(first)
        def flush():root.after(260,root.quit);root.mainloop();root.update()
        try:
            editor.replace_document(Document(8,8,'GUI format fixture'))
            editor.apply([{'op':'pixel','x':1,'y':1,'color':7},{'op':'frame_add','copy_from':0},
                          {'op':'pixel','frame':1,'x':2,'y':2,'color':18},
                          {'op':'tag_set','name':'idle','start':0,'end':1}],'Export fixture')
            before=editor.doc.to_dict()
            d=editor.export_dialog();root.update()
            formats=option(d,'原生 JSON');kind=option(d,'透明 PNG')
            assert formats['menu'].index('end')==3
            formats['menu'].invoke(3);flush()
            assert formats.master.winfo_manager()
            kind['menu'].invoke(0);flush();assert not formats.master.winfo_manager()
            kind['menu'].invoke(1);flush();assert formats.master.winfo_manager()
            target=root_path/'actor.png'
            button=next(w for w in widgets(d) if isinstance(w,tk.Button) and w.cget('text')=='选择位置并导出')
            with patch('pixel_workbench.ui.filedialog.asksaveasfilename',return_value=str(target)):
                button.invoke();root.update()
            assert target.exists() and target.with_suffix('.tres').exists()
            data=json.loads(target.with_suffix('.json').read_text(encoding='utf-8'))
            assert isinstance(data['frames'],dict) and data['meta']['image']=='actor.png'
            original={p:p.read_bytes() for p in [target,target.with_suffix('.json'),target.with_suffix('.tres')]}
            d=editor.export_dialog();root.update();formats=option(d,'原生 JSON')
            button=next(w for w in widgets(d) if isinstance(w,tk.Button) and w.cget('text')=='选择位置并导出')
            with patch('pixel_workbench.ui.filedialog.asksaveasfilename',return_value=str(target)),\
                 patch('pixel_workbench.ui.messagebox.askyesno',return_value=True),\
                 patch('pixel_workbench.ui.messagebox.showerror') as error:
                button.invoke();root.update();error.assert_called_once()
            assert original=={p:p.read_bytes() for p in original}
            d.destroy();assert editor.doc.to_dict()==before
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['native remains default','four formats in original export dialog',
                'format controls hide for PNG and return for sheet','Godot outputs real PNG/JSON/TRES',
                'stale sidecar conflict explained without changing files','opening/exporting preserves art/history',
                'no Tk callback errors']}))
        finally:
            editor.saved_fingerprint=editor.doc.fingerprint();editor.dirty=False;editor.close()


if __name__=='__main__':main()
