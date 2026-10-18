"""Native scoped settings/player regression, with explicit protocol-fixture verdicts."""
import json
import os
from pathlib import Path
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix='pixel-loom-gui-tag-') as folder:
        os.environ['PIXEL_LOOM_HOME']=str(Path(folder)/'data')
        os.environ['PIXEL_LOOM_WORKSPACE']=str(Path(folder)/'work')
        import tkinter as tk
        from pixel_workbench.app import Editor
        from pixel_workbench.model import Document
        from pixel_workbench.quality import effective_policy
        root=tk.Tk();root.withdraw();editor=Editor(root)
        root.after_cancel(editor.welcome_job);editor.welcome_job=None
        editor.updates.preferences['check_on_startup']=False
        errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        try:
            editor.replace_document(Document(16,16,'Tagged GUI fixture'))
            ops=[{'op':'rect','x':4,'y':5,'width':4,'height':7,'color':18}]
            for i in range(1,8):ops += [{'op':'frame_add','copy_from':0}, {'op':'pixel','frame':i,'x':i,'y':1,'color':7}]
            ops += [{'op':'tag_set','name':'idle','start':0,'end':3},{'op':'tag_set','name':'run','start':4,'end':7}]
            assert editor.apply(ops,'Tagged fixture')
            editor.dispatch('POST','/review/settings',{}, {'settings':{'expected_frames':8},
                'expected_document_id':editor.doc.id,'expected_revision':editor.doc.revision})
            editor.tag_var.set('全部帧');q=editor.quality_dialog();root.update()
            assert len(q.sequence_labels)==2
            q.settings_scope.set('动作 · run');q.load_policy()
            assert q.variables['expected_frames'].get()==''
            q.variables['expected_frames'].set('4');q.loop.set(False);q.save_settings();root.update()
            assert effective_policy(editor.doc)['expected_frames']==8
            assert effective_policy(editor.doc,'run')['expected_frames']==4
            assert not effective_policy(editor.doc,'run')['loop']
            assert q.ticket['scope']['tag']=='run' and not q.sequence_loop
            if q.player_job:q.dialog.after_cancel(q.player_job);q.player_job=None
            q.playing=True;q.index=len(q.play_indices)-1;q.tick();assert not q.playing
            e=editor.service.review_evidence({'review_id':q.ticket['id']})
            editor.dispatch('POST','/review/submit',{}, {'review_id':e['review_id'],
                'visual_checks':[{'criterion_id':c['id'],'verdict':'pass','reason':'GUI protocol fixture'} for c in e['criteria']],
                'warning_resolutions':[{'warning_id':w['id'],'verdict':'acceptable','reason':'Intentional GUI fixture'} for w in e['warnings']],
                'method':'frames_and_timing','summary':'GUI fixture',
                'expected_document_id':editor.doc.id,'expected_revision':editor.doc.revision})
            q.render_report();assert '通过' in q.badge.cget('text')
            editor.apply([{'op':'pixel','frame':0,'x':15,'y':15,'color':7}],'Other action edit')
            q.render_report();assert '通过' in q.badge.cget('text')
            idle=editor.service.review_evidence({'tag':'idle'})
            editor.quality_dialog(idle['review_id']);root.update()
            assert q.settings_scope.get()=='动作 · idle' and q.ticket['scope']['tag']=='idle'
            assert q.loop.get()
            editor.dispatch('POST','/review/submit',{}, {'review_id':idle['review_id'],
                'visual_checks':[{'criterion_id':c['id'],'verdict':'pass','reason':'GUI independent-action fixture'} for c in idle['criteria']],
                'warning_resolutions':[{'warning_id':w['id'],'verdict':'acceptable','reason':'Intentional GUI fixture'} for w in idle['warnings']],
                'method':'frames_and_timing','summary':'Idle GUI fixture',
                'expected_document_id':editor.doc.id,'expected_revision':editor.doc.revision})
            q.dialog.destroy()
            editor.tag_var.set('全部帧');q=editor.quality_dialog();root.update()
            q.render_report();assert '通过' in q.badge.cget('text')
            assert q.ticket['stored_coverage']['passed']
            choices=list(q.sequence_labels);q.sequence_choice.set(choices[1]);q.select_sequence()
            assert q.play_indices==[4,5,6,7] and not q.sequence_loop
            q.dialog.destroy()
            assert not errors,errors
            print(json.dumps({'ok':True,'checks':['tag/global settings share original optional dialog',
                'global frame count preserved','tag one-shot policy saved','one-shot player stops',
                'unrelated action edit preserves visible approval','MCP ticket synchronizes settings scope',
                'full-review player selects independent action','no Tk callback errors']}))
        finally:
            editor.saved_fingerprint=editor.doc.fingerprint();editor.dirty=False;editor.close()


if __name__=='__main__':main()
