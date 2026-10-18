"""Desktop dispatch: proposals read-only; applying switches to a preserved project."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-art-gui-') as folder:
        path=Path(folder);os.environ['PIXEL_LOOM_HOME']=str(path/'data');os.environ['PIXEL_LOOM_WORKSPACE']=str(path/'workspace')
        import tkinter as tk
        from PIL import Image
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document, PixelError
        root=tk.Tk();root.withdraw();editor=Editor(root)
        try:
            editor.replace_document(Document(16,16));root.update()
            def call(endpoint,**values):
                values={'expected_document_id':editor.doc.id,'expected_revision':editor.doc.revision,**values}
                return editor.dispatch('POST',endpoint,{},values)[0]
            call('/task',action='plan',task='text_static',brief='GUI transport fixture',direction={'route':'native'},expected_task_revision=0)
            viewer=editor.workflow_dialog();root.update()
            assert '工具直接绘制' in viewer.workflow_summary.get('1.0','end')
            viewer.destroy();root.update()
            previous=(editor.doc.id,editor.doc.revision,editor.dirty,len(editor.doc.undo_stack))
            assert call('/art/board')['read_only']
            assert previous==(editor.doc.id,editor.doc.revision,editor.dirty,len(editor.doc.undo_stack))
            call('/task',action='update',direction={'route':'generated'},expected_task_revision=1)
            source=path/'image.png';Image.new('RGBA',(32,32),'#6a9fb8').save(source)
            assert not call('/generation',action='request')['image_generated']
            proposal=call('/generation',action='preview',path=str(source),settings={'width':16,'height':16,'colors':12})
            assert previous==(editor.doc.id,editor.doc.revision,editor.dirty,len(editor.doc.undo_stack))
            applied=call('/generation',action='apply',preview_id=proposal['preview_id']);root.update()
            assert editor.doc.id==applied['document_id'] and editor.path.exists()
            assert editor.doc.id!=previous[0] and editor.service.doc is editor.doc
            assert not editor.path_points and editor.selection_preview is None
            task_revision=editor.service.tasks.load(editor.doc)['revision']
            call('/task',action='update',direction={'route':'generated'},expected_task_revision=task_revision)
            proposal=call('/generation',action='preview',path=str(source),settings={'width':16,'height':16,'colors':12})
            with patch.object(editor.service,'save_project',side_effect=OSError('save disk fixture failure')):
                try:call('/generation',action='apply',preview_id=proposal['preview_id'])
                except PixelError as exc:assert exc.code=='GENERATION_APPLIED_NOT_SAVED'
                else:raise AssertionError('Expected an explicit post-apply save failure')
            assert editor.doc is editor.service.doc,'GUI must not overwrite the already-applied service document after failure'
            assert editor.doc.id!=applied['document_id'] and editor.path is None and editor.dirty
            call('/save',path='projects/recovered-after-failure.pixloom')
            assert editor.path.exists() and not editor.dirty
            print('GUI art direction: proposals read-only; apply switches editor to retained new project.')
        finally:
            editor.autosave();editor.bridge.close();root.destroy()


if __name__=='__main__':main()
