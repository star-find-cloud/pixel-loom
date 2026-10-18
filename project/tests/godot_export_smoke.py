"""Optional real Godot 4 import/resource verification; no engine is bundled by this project."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from pixel_workbench.model import Document


def engine_run(executable,project,args,log):
    env=dict(os.environ)
    for key,name in [('APPDATA','appdata'),('LOCALAPPDATA','localdata')]:
        directory=Path(project)/'.test-user'/name;directory.mkdir(parents=True,exist_ok=True);env[key]=str(directory)
    result=subprocess.run([str(executable),'--headless','--path',str(project),*args],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90,env=env)
    output=result.stdout.decode('utf-8',errors='replace');Path(log).write_text(output,encoding='utf-8')
    if result.returncode or 'SCRIPT ERROR:' in output or '\nERROR:' in output:
        raise AssertionError(f'Godot validation failed ({result.returncode}): {output[-5000:]}')
    return output


SCRIPT='''extends SceneTree
func _initialize():
    var sf = load("res://assets/中文 图集.tres") as SpriteFrames
    if sf == null:
        printerr("SpriteFrames failed to load"); quit(1); return
    var orders = {"walk": [0,1,2,1], "strike": [4,3]}
    var times = [70.0,110.0,230.0,90.0,150.0]
    for name in orders:
        if sf.get_frame_count(name) != orders[name].size():
            printerr("Wrong frame count: ", name); quit(1); return
        if sf.get_animation_loop(name) != (name == "walk"):
            printerr("Wrong loop: ", name); quit(1); return
        for i in range(orders[name].size()):
            var source = orders[name][i]
            var tex = sf.get_frame_texture(name, i) as AtlasTexture
            var expected = Rect2((source % 3) * 16, (source / 3 as int) * 16, 16, 16)
            if tex == null or tex.region != expected:
                printerr("Wrong atlas rectangle: ", name, i); quit(1); return
            var ms = sf.get_frame_duration(name,i) / sf.get_animation_speed(name) * 1000.0
            if abs(ms-times[source]) > 0.0001:
                printerr("Duration loss: ", ms, times[source]); quit(1); return
            var pixels = tex.get_image()
            if pixels == null or pixels.get_size() != Vector2i(16,16) or pixels.get_pixel((source+1)*2,2).a != 1.0:
                printerr("Wrong texture pixels"); quit(1); return
    for format in ["aseprite_hash","aseprite_array"]:
        var data = JSON.parse_string(FileAccess.get_file_as_string("res://assets/"+format+".json"))
        var frames = data.frames.values() if data.frames is Dictionary else data.frames
        if frames.size() != 5 or data.meta.size.w != 48 or data.meta.size.h != 32:
            printerr("Wrong JSON container/size"); quit(1); return
        for i in range(frames.size()):
            if frames[i].duration != times[i] or frames[i].sourceSize.w != 16 or frames[i].frame.x != (i%3)*16:
                printerr("Wrong JSON frame: ",i); quit(1); return
    var first = sf.get_frame_texture("walk",0).get_image()
    if abs(first.get_pixel(0,0).a - 128.0/255.0) > 0.001:
        printerr("Partial alpha was lost"); quit(1); return
    var selected = load("res://assets/selected.tres") as SpriteFrames
    if selected == null or selected.get_animation_names().size() != 1 or selected.get_frame_count("strike") != 2:
        printerr("Wrong selected-tag resource"); quit(1); return
    if selected.get_frame_texture("strike",0).region != Rect2(16,0,16,16):
        printerr("Selected-tag source indices were not rebased"); quit(1); return
    print("PIXEL_LOOM_GODOT="+JSON.stringify({"ok":true,"animations":2,"json_formats":2,"relative_path":true,"durations":true,"reverse_pingpong":true,"loop":true,"pixels":true}))
    quit()
'''


def run(executable,artifacts=None):
    with tempfile.TemporaryDirectory(prefix='pixel-loom-godot-') as folder:
        root=Path(artifacts or folder).resolve();root.mkdir(parents=True,exist_ok=True)
        assets=root/'assets';assets.mkdir(exist_ok=True)
        (root/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Pixel Loom export verification"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
        doc=Document(8,8);ops=[{'op':'palette_add','colors':['#ff000080']}]
        for i,ms in enumerate([70,110,230,90,150]):
            if i:ops.append({'op':'frame_add','blank':True,'duration_ms':ms})
            else:ops.append({'op':'frame_set','frame':0,'duration_ms':ms})
            ops.append({'op':'pixel','frame':i,'x':i+1,'y':1,'color':7})
        ops.append({'op':'pixel','frame':0,'x':0,'y':0,'color':'#ff000080'})
        ops += [{'op':'tag_set','name':'walk','start':0,'end':2,'direction':'pingpong'},
                {'op':'tag_set','name':'strike','start':3,'end':4,'direction':'reverse'},
                {'op':'quality_policy','data':{'tag_policies':{'strike':{'loop':False}}}}]
        doc.apply(ops)
        for fmt,name in [('aseprite_hash','aseprite_hash.png'),('aseprite_array','aseprite_array.png'),('godot','中文 图集.png')]:
            doc.export(assets/name,'sheet',columns=3,scale=2,sheet_format=fmt)
        doc.export(assets/'selected.png','sheet',columns=3,scale=2,sheet_format='godot',tag='strike')
        (root/'check.gd').write_text(SCRIPT,encoding='utf-8')
        engine_run(executable,root,['--editor','--import','--quit'],root/'import.log')
        output=engine_run(executable,root,['--script','check.gd'],root/'check.log')
        data=json.loads(next(line.split('=',1)[1] for line in output.splitlines() if line.startswith('PIXEL_LOOM_GODOT=')))
        assert data['ok'];print(json.dumps(data));return data


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--godot',required=True,type=Path);p.add_argument('--artifacts',type=Path)
    args=p.parse_args();run(args.godot,args.artifacts)
