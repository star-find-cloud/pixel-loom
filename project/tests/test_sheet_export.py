"""Exchange format, legacy compatibility and multi-file failure regressions."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from pixel_workbench.model import Document,PixelError
from pixel_workbench.service import DocumentService
from pixel_workbench.sheet_export import export_paths,write_bundle


class SheetExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.doc=Document(8,8,'Exchange fixture')
        ops=[{'op':'pixel','x':1,'y':1,'color':7}]
        for i,ms in enumerate([70,110,230],1):
            ops += [{'op':'frame_add','blank':True,'duration_ms':ms}, {'op':'pixel','frame':i,'x':i+1,'y':1,'color':18}]
        ops += [{'op':'tag_set','name':'idle','start':0,'end':1},
                {'op':'tag_set','name':'run','start':2,'end':3,'direction':'reverse'}]
        self.doc.apply(ops)

    def export(self,fmt='native',name=None,**kw):
        path=self.root/(name or fmt+'.png');result=self.doc.export(path,'sheet',columns=2,sheet_format=fmt,**kw)
        return result,json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))

    def test_default_native_json_and_pixels_keep_the_legacy_contract(self):
        result,d=self.export()
        self.assertEqual(set(d),{'image','frames','tags','canvas'})
        self.assertEqual(d['canvas'],{'width':8,'height':8})
        self.assertEqual(d['frames'][2],{'index':2,'source_index':2,'x':0,'y':8,'width':8,'height':8,'duration_ms':110})
        self.assertEqual(d['tags'][1],{'name':'run','start':2,'end':3,'direction':'reverse'})
        self.assertNotIn('sheet_format',result)
        with Image.open(result['path']) as image:
            for f in range(4):self.assertEqual(image.crop(((f%2)*8,(f//2)*8,(f%2+1)*8,(f//2+1)*8)).tobytes(),self.doc.composite(f).tobytes())

    def test_hash_array_share_standard_fields_and_scaled_source_dimensions(self):
        _,h=self.export('aseprite_hash',scale=2)
        _,a=self.export('aseprite_array',scale=2)
        self.assertIsInstance(h['frames'],dict);self.assertIsInstance(a['frames'],list)
        self.assertEqual(h['meta']['scale'],'1');self.assertEqual(h['meta']['size'],{'w':32,'h':32})
        for i,frame in enumerate(a['frames']):
            self.assertEqual(frame['frame'],{'x':(i%2)*16,'y':(i//2)*16,'w':16,'h':16})
            self.assertEqual(frame['sourceSize'],{'w':16,'h':16})
            self.assertEqual(frame['spriteSourceSize'],{'x':0,'y':0,'w':16,'h':16})
            self.assertEqual(frame['duration'],self.doc.durations[i]);self.assertFalse(frame['rotated']);self.assertFalse(frame['trimmed'])
            other=list(h['frames'].values())[i]
            self.assertEqual(other,{k:v for k,v in frame.items() if k!='filename'})

    def test_tag_filter_rebases_indices_and_does_not_reverse_sheet_source_order(self):
        _,d=self.export('aseprite_array',tag='run')
        self.assertEqual([f['duration'] for f in d['frames']],[110,230])
        self.assertEqual(d['meta']['frameTags'],[{'name':'run','from':0,'to':1,'direction':'reverse'}])
        self.assertIn('_0002.png',d['frames'][0]['filename'])

    def test_aseprite_repeat_matches_official_string_field_for_one_shots(self):
        self.doc.apply([{'op':'quality_policy','data':{'tag_policies':{'run':{'loop':False}}}}])
        _,d=self.export('aseprite_hash')
        self.assertNotIn('repeat',d['meta']['frameTags'][0]);self.assertEqual(d['meta']['frameTags'][1]['repeat'],'1')

    def test_transparent_empty_source_frames_are_not_trimmed_or_dropped(self):
        self.doc.apply([{'op':'clear','frame':1}])
        _,d=self.export('aseprite_array')
        self.assertEqual(len(d['frames']),4);self.assertFalse(d['frames'][1]['trimmed'])
        with Image.open(self.root/'aseprite_array.png') as image:self.assertIsNone(image.crop((8,0,16,8)).getbbox())

    def test_godot_bundle_is_relative_and_retains_native_source_pixels(self):
        result,d=self.export('godot',name='中文 图集.png')
        text=Path(result['resource_path']).read_text(encoding='utf-8')
        self.assertIn('path="中文 图集.png"',text);self.assertNotIn(str(self.root),text)
        self.assertEqual(len(result['files']),3);self.assertEqual(d['meta']['image'],'中文 图集.png')
        self.assertIn('"name": &"run"',text)
        self.assertIn('"speed": 10.0',text)

    def test_unknown_or_non_sheet_options_do_not_create_outputs(self):
        for kind,fmt in [('sheet','made_up'),('png','aseprite_array'),('gif','godot')]:
            with self.assertRaises(PixelError):self.doc.export(self.root/'invalid.png',kind,sheet_format=fmt)
        self.assertFalse((self.root/'invalid.png').exists())
        self.assertFalse((self.root/'invalid.json').exists())

    def test_all_three_previous_files_restore_if_commit_fails(self):
        self.export('godot',name='bundle.png')
        files=export_paths(self.root/'bundle.png','sheet','godot');before={p:p.read_bytes() for p in files}
        self.doc.apply([{'op':'pixel','x':0,'y':0,'color':7}])
        real=os.replace;failed=False
        def interrupted(src,dest):
            nonlocal failed
            if Path(dest)==files[0] and not failed:
                failed=True;raise PermissionError('Simulated PNG commit failure')
            return real(src,dest)
        with patch('pixel_workbench.sheet_export.os.replace',side_effect=interrupted),self.assertRaises(PermissionError):
            self.export('godot',name='bundle.png')
        self.assertTrue(failed);self.assertEqual(before,{p:p.read_bytes() for p in files})
        self.assertFalse(list(self.root.glob('.pixel-loom-export-*')))

    def test_non_godot_format_cannot_leave_an_old_resource_pointing_at_replaced_png(self):
        self.export('godot',name='bundle.png');before=(self.root/'bundle.png').read_bytes()
        with self.assertRaises(PixelError) as e:self.export('native',name='bundle.png')
        self.assertEqual(e.exception.code,'EXPORT_SIDECAR_CONFLICT');self.assertEqual((self.root/'bundle.png').read_bytes(),before)

    def test_godot_sidecar_collision_is_checked_even_without_png_or_json(self):
        s=DocumentService(self.doc,workspace=self.root/'work',runtime=self.root/'data')
        s.workspace.mkdir(exist_ok=True);(s.workspace/'collision.tres').write_text('User resource',encoding='utf-8')
        with self.assertRaises(PixelError) as e:s.dispatch('POST','/export',payload={'path':'collision.png','kind':'sheet','sheet_format':'godot','draft':True,
            'expected_document_id':s.doc.id,'expected_revision':s.doc.revision})
        self.assertEqual(e.exception.code,'FILE_EXISTS');self.assertFalse((s.workspace/'collision.png').exists())
        self.assertEqual((s.workspace/'collision.tres').read_text(),'User resource')

    def test_new_formats_cannot_bypass_the_existing_review_gate(self):
        s=DocumentService(self.doc,workspace=self.root/'work',runtime=self.root/'data')
        for fmt in ['aseprite_hash','aseprite_array','godot']:
            with self.assertRaises(PixelError) as e:s.dispatch('POST','/export',payload={'path':fmt+'.png','kind':'sheet','sheet_format':fmt,
                'expected_document_id':s.doc.id,'expected_revision':s.doc.revision})
            self.assertEqual(e.exception.code,'REVIEW_REQUIRED')
            self.assertFalse((s.workspace/(fmt+'.png')).exists())

    def test_initial_staging_failure_keeps_previous_files_untouched(self):
        target=self.root/'x.png';target.write_bytes(b'original')
        with patch('pixel_workbench.sheet_export.Path.write_bytes',side_effect=PermissionError('Stage write failure')):
            with self.assertRaises(PermissionError):write_bundle({target:b'new'})
        self.assertEqual(target.read_bytes(),b'original');self.assertFalse(list(self.root.glob('.pixel-loom-export-*')))

    def test_recovery_backup_is_retained_if_original_file_cannot_be_restored(self):
        self.export('godot',name='recover.png')
        path=self.root/'recover.png';old_json=path.with_suffix('.json').read_bytes()
        real=os.replace;failed=False
        def interrupted(src,dest):
            nonlocal failed
            if Path(dest)==path and not failed:failed=True;raise PermissionError('Commit blocked')
            if failed and Path(dest)==path.with_suffix('.json'):raise PermissionError('Restore blocked')
            return real(src,dest)
        with patch('pixel_workbench.sheet_export.os.replace',side_effect=interrupted),self.assertRaises(PixelError) as e:
            self.export('godot',name='recover.png')
        self.assertEqual(e.exception.code,'EXPORT_RECOVERY_NEEDED')
        backup=Path(e.exception.details['backups'][0]['backup']);self.assertEqual(backup.read_bytes(),old_json)

    def test_failed_first_export_removes_only_its_incomplete_outputs(self):
        png=self.root/'new.png';real=os.replace
        def interrupted(src,dest):
            if Path(dest)==png:raise PermissionError('Commit blocked')
            return real(src,dest)
        with patch('pixel_workbench.sheet_export.os.replace',side_effect=interrupted),self.assertRaises(PermissionError):
            self.export('godot',name='new.png')
        self.assertFalse(any(p.exists() for p in export_paths(png,'sheet','godot')))
        self.assertFalse(list(self.root.glob('.pixel-loom-export-*')))

    def test_new_mcp_does_not_silently_export_native_from_an_older_backend(self):
        from pixel_workbench import mcp_server
        from unittest.mock import Mock
        client=Mock();client.request.return_value={'capabilities':{'features':['tag_review']}}
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            result=mcp_server.pixel_export(path='out.png',kind='sheet',sheet_format='godot')
        self.assertTrue(result.isError);self.assertEqual(result.structuredContent['code'],'BACKEND_UPGRADE_REQUIRED')
        client.mutate.assert_not_called()


if __name__=='__main__':unittest.main()
