"""Screenshot-first GUI flow; clipboard writes are mocked to preserve the user's clipboard."""
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-capture-') as folder:
        os.environ['PIXEL_LOOM_HOME']=str(Path(folder)/'data')
        os.environ['PIXEL_LOOM_WORKSPACE']=str(Path(folder)/'work')
        import tkinter as tk
        from PIL import Image
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        from pixel_workbench.feedback_capture import PNG_KEY
        root=tk.Tk()
        root.withdraw()
        editor=Editor(root)
        errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        try:
            root.update()
            editor.replace_document(Document(32,40))
            editor.apply([{'op':'rect','x':9,'y':7,'width':12,'height':20,'color':7},
                          {'op':'frame_add','copy_from':0}], 'Capture fixture')
            panel=editor.feedback_panel
            self_doc=editor.doc.to_dict()
            self_history=len(editor.doc.undo_stack)
            assert not hasattr(panel,'description') and not hasattr(panel,'submit_button')
            assert not hasattr(panel,'brief')
            assert [editor.control_notebook.tab(tab,'text') for tab in editor.control_notebook.tabs()]==['图层','调色','操作']
            assert editor.workspace_mode=='preview'
            assert not editor.editor_dock.winfo_manager() and not editor.tool_rail.winfo_manager()
            assert not editor.feedback_toolbar.winfo_manager()
            assert editor.bridge.session_path.exists() and editor.bridge.thread.is_alive()
            editor.set_workspace_mode('manual')
            assert editor.editor_dock.winfo_manager()=='panedwindow' and editor.tool_rail.winfo_manager()=='pack'
            assert not editor.feedback_toolbar.winfo_manager()
            editor.control_notebook.select(1)
            editor.set_workspace_mode('preview')
            assert not editor.editor_dock.winfo_manager() and not editor.tool_rail.winfo_manager()
            assert editor.doc.to_dict()==self_doc
            activity=editor.activity_dialog()
            assert editor.activity_dialog() is activity
            assert 'Capture fixture' in editor.events_widget.get('1.0','end')
            activity.destroy()
            editor.refresh_events()
            activity=editor.activity_dialog()
            assert 'Capture fixture' in editor.events_widget.get('1.0','end')
            activity.destroy()
            editor.set_workspace_mode('feedback')
            assert not editor.editor_dock.winfo_manager()
            assert editor.feedback_toolbar.winfo_manager()=='pack'
            editor.choose_tool('feedback_ellipse')
            def point(x,y):
                return SimpleNamespace(x=editor.origin[0]+(x+.5)*editor.zoom,y=editor.origin[1]+(y+.5)*editor.zoom)
            editor.pointer_down(point(12,12))
            editor.pointer_up(point(22,26))
            assert editor.feedback_draft['kind']=='ellipse'
            assert editor.doc.to_dict()==self_doc
            with patch('pixel_workbench.image_clipboard.copy_image',return_value={'copied':True,'formats':['CF_DIB','PNG']}) as copied:
                path=panel.capture()
                assert path.is_file() and copied.call_count==1
                image,png,owner=copied.call_args.args
                assert owner==root.winfo_id() and image.mode=='RGB'
                metadata=json.loads(Image.open(io.BytesIO(png)).info[PNG_KEY])
                assert metadata['annotation']['kind']=='ellipse'
                assert metadata['rect']==[12,12,11,15]
                assert 'Ctrl+V' in panel.notice.cget('text')
            assert editor.doc.to_dict()==self_doc and len(editor.doc.undo_stack)==self_history
            assert not editor.doc.feedback
            guide=panel.guide()
            guide.withdraw()
            root.update()
            guide.destroy()
            preview=panel.show_last()
            preview.withdraw()
            root.update()
            preview.destroy()
            panel.clear_mark()
            editor.toggle_play()
            editor.play_tick()
            shown=editor.play_frame
            with patch('pixel_workbench.image_clipboard.copy_image',return_value={'copied':True}):
                assert panel.capture()
            assert not editor.playing and panel.last_capture.metadata['frame']==shown
            before=editor.doc.fingerprint()
            with patch('pixel_workbench.image_clipboard.copy_image',side_effect=OSError('Clipboard busy')):
                assert panel.capture() is None
            assert panel.last_capture_path.is_file()
            assert 'Clipboard busy' in panel.notice.cget('text')
            assert editor.doc.fingerprint()==before
            editor.set_workspace_mode('preview')
            assert not editor.feedback_toolbar.winfo_manager() and not editor.editor_dock.winfo_manager()
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['full-width preview without sidebars','manual-only layer/tool dock',
                'contextual screenshot toolbar','local service starts without activation','advanced activity dialog survives reopening',
                'no problem or creation form','ellipse overlay changes no pixels',
                'one-click PNG+image clipboard payload','visible paste reminder','metadata remains in saved PNG',
                'no ticket/project/history mutation','guide and screenshot preview','captures actual playback frame',
                'copy failure retains local PNG','clipboard is mocked in test']}))
        finally:
            editor.saved_fingerprint=editor.doc.fingerprint()
            editor.dirty=False
            editor.close()


if __name__=='__main__':main()
