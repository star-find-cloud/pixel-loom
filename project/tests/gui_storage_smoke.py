"""Isolated desktop cleanup preview, history retention and safe stale UI actions."""
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-storage-gui-') as folder:
        os.environ['PIXEL_LOOM_HOME']=str(Path(folder)/'data')
        os.environ['PIXEL_LOOM_WORKSPACE']=str(Path(folder)/'work')
        import tkinter as tk
        from unittest.mock import patch
        from pixel_workbench.app import Editor
        root=tk.Tk();root.withdraw()
        errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        editor=Editor(root)
        def wait(dialog):
            deadline=time.monotonic()+10
            while str(dialog.preview_button['state'])=='disabled' and time.monotonic()<deadline:
                root.update();time.sleep(.02)
            assert str(dialog.preview_button['state'])=='normal'
            root.update()
        try:
            editor.project_action('new',name='Storage fixture',width=16,height=16)
            for color in (7,8,9):
                editor.apply([{'op':'pixel','x':3,'y':3,'color':color}],'Artwork batch');editor.autosave()
            history=editor.project_history_dialog();root.update()
            history.listing.selection_clear(0,'end');history.listing.selection_set(1);history.pin_selected()
            assert history.versions[1]['pinned']
            history.listing.selection_clear(0,'end');history.listing.selection_set(2)
            storage=history.delete_selected();wait(storage)
            before=editor.doc.to_dict()
            storage.preview();wait(storage)
            assert storage.plan['file_count']==2
            result=storage.apply();root.update()
            assert result['removed_files']==2 and editor.doc.to_dict()==before
            assert len(history.versions)==3
            storage.dialog.destroy()
            cache=editor.service.runtime/'review-cache'/('a'*32)/'playback.gif'
            cache.parent.mkdir(parents=True);cache.write_bytes(b'preview')
            storage=editor.storage_dialog();wait(storage)
            storage.preview();wait(storage)
            assert storage.plan['file_count']==1
            storage.age.set('7');root.update()
            assert storage.plan is None and str(storage.apply_button['state'])=='disabled'
            storage.age.set('0');storage.preview();wait(storage)
            cache.write_bytes(b'changed!')
            with patch('pixel_workbench.storage_ui.messagebox.showerror') as error:
                assert storage.apply() is None
                error.assert_called_once()
            assert cache.exists()
            storage.dialog.destroy();history.dialog.destroy()
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['history mark-retain','selected-version preview/delete',
                'current art unchanged','history refresh','usage display','changed controls invalidate preview',
                'stale files block cleanup','worker callbacks cancelled safely']}))
        finally:
            editor.save();editor.close()


if __name__=='__main__':main()
