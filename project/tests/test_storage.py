from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import uuid

from pixel_workbench.model import Document, PixelError, atomic_json
from pixel_workbench.service import DocumentService


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.service=DocumentService(Document(12,12,'Artwork'),runtime=self.root/'data',workspace=self.root/'work')
        self.service.save_project(self.service.projects.new_path('Artwork'))
        for color in (7,8,9):
            self.service.doc.apply([{'op':'pixel','x':2,'y':2,'color':color}],label=f'Edit {color}')
            self.service.autosave()
        self.entry=self.service.projects.by_path(self.service.path)

    def cache(self):
        path=self.service.runtime/'review-cache'/uuid.uuid4().hex/'playback.gif'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'cached preview')
        return path

    def versions(self):return self.service.projects.versions(self.entry['id'])

    def plan(self,**settings):return self.service.storage.plan(settings)

    def apply(self,plan):
        return self.service.storage.apply({'plan_id':plan['plan_id'],'user_request':'清理用户明确选中的范围',
            'expected_document_id':self.service.doc.id,'expected_revision':self.service.doc.revision})

    def test_cache_plan_is_read_only_and_apply_retry_never_deletes_new_files(self):
        cache=self.cache()
        stat=cache.stat()
        os.utime(cache,ns=(stat.st_atime_ns,stat.st_mtime_ns+60_000_000_000))
        before=self.service.doc.to_dict()
        files={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        plan=self.plan()
        self.assertEqual(plan['file_count'],1)
        self.assertEqual({p:p.read_bytes() for p in files},files)
        result=self.apply(plan)
        self.assertEqual(result['freed_bytes'],len(b'cached preview'))
        self.assertFalse(cache.exists())
        new=self.cache()
        self.assertTrue(self.apply(plan)['already_applied'])
        self.assertTrue(new.exists())
        self.assertEqual(self.service.doc.to_dict(),before)

    def test_active_review_protected_and_other_data_outside_allowlist_untouched(self):
        active=self.cache();old=self.cache()
        self.service.quality.tickets['active']={'asset':active}
        untouched=[]
        for name in ('session.json','reference-workspace.json','_internal/library.dll','review-cache/readme.txt'):
            path=self.service.runtime/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep')
            untouched.append(path)
        plan=self.plan()
        self.assertEqual(plan['file_count'],1)
        self.apply(plan)
        self.assertTrue(active.exists());self.assertFalse(old.exists())
        self.assertTrue(all(p.exists() for p in untouched))

    def test_empty_authorization_and_expired_plan_never_delete(self):
        path=self.cache();plan=self.plan()
        with self.assertRaises(PixelError):self.service.storage.apply({'plan_id':plan['plan_id']})
        self.service.storage.plans[plan['plan_id']]['expires']=0
        with self.assertRaises(PixelError):self.apply(plan)
        self.assertTrue(path.exists())

    def test_content_change_even_same_size_and_mtime_invalidates_before_any_delete(self):
        path=self.cache();plan=self.plan();stat=path.stat()
        path.write_bytes(b'changed asset!')
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaises(PixelError) as error:self.apply(plan)
        self.assertEqual(error.exception.code,'CLEANUP_PLAN_STALE')
        self.assertTrue(path.exists())

    def test_changed_document_and_drawing_gesture_block_cleanup(self):
        path=self.cache();plan=self.plan()
        self.service.doc.apply([{'op':'pixel','x':4,'y':4,'color':7}])
        with self.assertRaises(PixelError):self.apply(plan)
        self.assertTrue(path.exists())
        self.service.view['gesture_active']=True
        with self.assertRaises(PixelError):self.apply(self.plan())

    def test_latest_pinned_versions_survive_and_pin_change_invalidates_plan(self):
        versions=self.versions()
        chosen=versions[1]
        plan=self.plan(targets=['versions'],project_ids=[self.entry['id']],version_ids=[chosen['id']])
        self.service.projects.pin_version(self.entry['id'],chosen['id'],True)
        with self.assertRaises(PixelError):self.apply(plan)
        plan=self.plan(targets=['versions'],project_ids=[self.entry['id']],keep_latest=1)
        self.apply(plan)
        remaining=self.versions()
        self.assertEqual({v['id'] for v in remaining},{versions[0]['id'],chosen['id']})
        self.assertTrue(next(v for v in remaining if v['id']==chosen['id'])['pinned'])

    def test_exact_deletion_preserves_stable_old_numbers_and_current_project_file(self):
        import json
        versions=self.versions()
        # Existing 0.7.10 histories have no number field in their sidecars.
        for version in versions:
            path=Path(version['path']).with_suffix('.json')
            data=json.loads(path.read_text(encoding='utf-8'));data.pop('number',None);atomic_json(path,data)
        before=Path(self.service.path).read_bytes()
        selected=versions[1]
        plan=self.plan(targets=['versions'],project_ids=[self.entry['id']],version_ids=[selected['id']])
        self.apply(plan)
        self.assertEqual(Path(self.service.path).read_bytes(),before)
        self.assertEqual([v['number'] for v in self.versions()],[4,2,1])
        self.service.doc.apply([{'op':'pixel','x':3,'y':3,'color':7}]);self.service.autosave()
        self.assertEqual(self.versions()[0]['number'],5)

    def test_only_redundant_saved_recovery_copies_are_removed(self):
        self.service.save_project()
        saved_id=self.service.doc.id
        saved=self.service.runtime/'recovery'/f'{saved_id}.pixloom'
        self.service.projects_action({'action':'new','name':'Other','expected_document_id':saved_id,'expected_revision':self.service.doc.revision})
        unique=Document(12,12,'Unsaved')
        unique_path=self.service.runtime/'recovery'/f'{unique.id}.pixloom';unique.save(unique_path)
        self.service.autosave()
        active=self.service.runtime/'recovery'/f'{self.service.doc.id}.pixloom'
        plan=self.plan(targets=['recovery'])
        self.apply(plan)
        self.assertFalse(saved.exists());self.assertTrue(unique_path.exists());self.assertTrue(active.exists())

    def test_legacy_history_without_sidecar_leaves_no_orphan_after_cleanup(self):
        version=self.versions()[1]
        metadata=Path(version['path']).with_suffix('.json')
        metadata.unlink()
        plan=self.plan(targets=['versions'],project_ids=[self.entry['id']],version_ids=[version['id']])
        self.assertEqual(plan['file_count'],1)
        self.apply(plan)
        self.assertFalse(Path(version['path']).exists());self.assertFalse(metadata.exists())

    def test_deleted_project_purge_never_deletes_external_project(self):
        external=self.root/'external.pixloom';Document(12,12,'External').save(external)
        entry=self.service.projects.register(external)
        self.service.projects.set_deleted([entry['id']])
        plan=self.plan(targets=['deleted_projects'],deleted_project_ids=[entry['id']])
        result=self.apply(plan)
        self.assertEqual(result['purged_project_ids'],[entry['id']])
        self.assertTrue(external.exists());self.assertGreater(plan['protected_count'],0)

    def test_active_and_pinned_deleted_projects_are_protected(self):
        old=self.entry
        self.service.save_project()
        self.service.projects.pin_version(old['id'],self.versions()[1]['id'],True)
        self.service.projects.set_deleted([old['id']])
        plan=self.plan(targets=['deleted_projects'],deleted_project_ids=[old['id']])
        self.assertEqual(plan['file_count'],0)
        self.service.path=None
        plan=self.plan(targets=['deleted_projects'],deleted_project_ids=[old['id']])
        self.assertEqual(plan['deleted_project_count'],0)
        self.assertTrue(Path(old['path']).exists())

    def test_purge_managed_deleted_project_keeps_unrecognized_files(self):
        self.service.save_project();entry=self.entry
        self.service.projects.set_deleted([entry['id']]);self.service.path=None
        note=self.service.projects.history_folder(entry)/'user-notes.json';note.write_text('{}')
        result=self.apply(self.plan(targets=['deleted_projects'],deleted_project_ids=[entry['id']]))
        self.assertTrue(result['ok']);self.assertFalse(Path(entry['path']).exists())
        self.assertTrue(note.exists());self.assertFalse(self.service.projects.entries)
        restarted=DocumentService(workspace=self.service.workspace,runtime=self.service.runtime)
        path=restarted.projects.new_path('Next')
        Document(12,12,'Next').save(path)
        self.assertEqual(restarted.projects.register(path)['number'],2)

    def test_symlink_cache_and_history_redirects_never_delete_external_files(self):
        outside=self.root/'outside';outside.mkdir()
        victim=outside/'playback.gif';victim.write_bytes(b'keep')
        folder=self.service.runtime/'review-cache'/uuid.uuid4().hex;folder.parent.mkdir(parents=True)
        try:folder.symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Symlink creation not available')
        result=self.apply(self.plan())
        self.assertEqual(result['removed_files'],0)
        self.assertTrue(victim.exists())

    def test_paging_bounds_version_and_project_metadata(self):
        response=self.service.projects_action({'action':'versions','project_id':self.entry['id'],'page':0,'limit':2})
        self.assertEqual(len(response['versions']),2);self.assertTrue(response['has_more'])
        next_page=self.service.projects_action({'action':'versions','project_id':self.entry['id'],'page':1,'limit':2})
        self.assertFalse(next_page['has_more'])
        self.assertFalse(set(v['id'] for v in response['versions']) & set(v['id'] for v in next_page['versions']))
        with self.assertRaises(PixelError):self.service.storage.plan({'targets':['versions']})
        with self.assertRaises(PixelError):self.service.storage.plan({'path':'/arbitrary'})

    def test_partial_failure_reports_actual_results_and_is_not_replayed(self):
        first=self.cache();second=self.cache();plan=self.plan()
        original=Path.unlink
        def fail_one(path,*args,**kwargs):
            if path==first:raise PermissionError('busy')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_one):result=self.apply(plan)
        self.assertFalse(result['ok']);self.assertEqual(result['failed_count'],1)
        self.assertTrue(first.exists());self.assertFalse(second.exists())
        self.assertTrue(self.apply(plan)['already_applied']);self.assertTrue(first.exists())
