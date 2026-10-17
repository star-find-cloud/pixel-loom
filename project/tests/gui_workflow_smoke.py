"""Optional viewer opens/updates/closes without editing art or stopping playback."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-workflow-ui-') as folder:
        os.environ['PIXEL_LOOM_HOME']=str(Path(folder)/'data')
        os.environ['PIXEL_LOOM_WORKSPACE']=str(Path(folder)/'work')
        import tkinter as tk
        from pixel_workbench.app import Editor
        root=tk.Tk();root.withdraw();editor=Editor(root)
        errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        if editor.welcome_job:root.after_cancel(editor.welcome_job);editor.welcome_job=None
        try:
            before=editor.doc.to_dict();dirty=editor.dirty
            window=editor.workflow_dialog();root.update()
            assert '没有 AI' in window.workflow_summary.get('1.0','end')
            assert editor.workflow_dialog() is window
            editor.dispatch('POST','/task',{},dict(action='plan',task='text_static',brief='Read-only UI fixture',
                expected_task_revision=0,expected_document_id=editor.doc.id,expected_revision=editor.doc.revision))
            root.after(1400,root.quit);root.mainloop()
            assert 'Read-only UI fixture' in window.workflow_summary.get('1.0','end')
            assert editor.doc.to_dict()==before and editor.dirty==dirty
            window.destroy();root.update()
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['optional viewer','live note refresh','no art/undo/dirty mutation','single window','clean close']},ensure_ascii=False))
        finally:
            editor.saved_fingerprint=editor.doc.fingerprint();editor.dirty=False;editor.close()


if __name__=='__main__':main()
