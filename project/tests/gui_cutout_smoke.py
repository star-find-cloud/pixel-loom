"""Real Tk controls: explicit entry, preview adjustment, protection, apply, undo and export."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-cutout-gui-') as folder:
        base=Path(folder)
        os.environ['PIXEL_LOOM_HOME']=str(base/'data')
        os.environ['PIXEL_LOOM_WORKSPACE']=str(base/'workspace')
        import tkinter as tk
        from PIL import Image
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        from tests.test_cutout import specimen
        source=base/'ordinary.png'
        specimen().save(source)
        root=tk.Tk()
        root.withdraw()
        editor=Editor(root)
        errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))

        def wait(milliseconds=230):
            root.after(milliseconds,root.quit)
            root.mainloop()

        def point(window,x,y):
            ox,oy,sx,sy,_,_=window.transforms['original']
            return SimpleNamespace(x=ox+(x+.5)*sx,y=oy+(y+.5)*sy)

        try:
            editor.replace_document(Document(32,32))
            editor.dispatch('POST','/reference/setup',{}, {'action':'load','path':str(source),'include_images':False,
                'expected_document_id':editor.doc.id,'expected_revision':editor.doc.revision,
                'expected_reference_revision':editor.service.references.revision})
            assert 'cutout' not in editor.service.references.context
            reference=editor.reference_dialog()
            root.update_idletasks()
            cutout=reference.cutout()
            wait()
            assert cutout.preview_id and 'cutout' not in editor.service.references.context
            cutout.tolerance.set(35)
            cutout.schedule()
            wait()
            assert cutout.ticket['settings']['tolerance']==35
            cutout.connected.set(False)
            cutout.schedule()
            wait()
            assert cutout.ticket['output'].getpixel((38,58))[3]==0
            cutout.set_mode('protect')
            cutout.pointer_down(point(cutout,33,51))
            cutout.pointer_move(point(cutout,46,68))
            cutout.pointer_up(point(cutout,46,68))
            wait()
            assert cutout.ticket['output'].getpixel((38,58))[3]==255
            assert 'cutout' not in editor.service.references.context
            assert cutout.action('apply')
            assert editor.service.references.context['cutout']['protect_regions']==[[33,51,14,18]]
            assert cutout.action('undo') and 'cutout' not in editor.service.references.context
            assert cutout.action('redo') and 'cutout' in editor.service.references.context
            export=base/'cutout.png'
            with patch('pixel_workbench.cutout_ui.filedialog.asksaveasfilename',return_value=str(export)):
                assert cutout.export()
            with Image.open(export) as image:
                assert image.getpixel((0,0))[3]==0 and image.getpixel((38,58))[3]==255
            cutout.tolerance.set(12)
            cutout.schedule()
            with patch('pixel_workbench.cutout_ui.filedialog.asksaveasfilename') as choose_file:
                assert not cutout.export()  # Also blocked during the debounce before a preview exists.
                choose_file.assert_not_called()
            wait()
            assert not cutout.export()  # Never exports a different, unapplied preview.
            expired=cutout.preview_id
            editor.service.cutouts.tickets[expired]['time']-=301
            assert not cutout.action('apply')
            wait()
            assert cutout.preview_id and cutout.preview_id != expired
            assert editor.service.references.context['cutout']['tolerance']==35
            assert cutout.action('reset') and 'cutout' not in editor.service.references.context
            # Pointer outside the image must not silently sample its edge.
            before=list(cutout.options['points'])
            cutout.set_mode('background')
            cutout.pointer_down(SimpleNamespace(x=-100,y=-100))
            assert cutout.options['points']==before
            cutout.dialog.destroy()
            reference.dialog.destroy()
            wait(50)
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['explicit entry only','read-only preview','slider adjustment',
                'drag protected region','apply','undo/redo','PNG export','unapplied export blocked','restore original',
                'outside click ignored','callback cleanup']},indent=2))
        finally:
            editor.service.closing=True
            editor.bridge.close()
            root.destroy()


if __name__=='__main__':
    main()
