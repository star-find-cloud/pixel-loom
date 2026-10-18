"""Portable sheet metadata and engine resources; no pixel generation or script execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from . import __version__
from .model import PixelError

SHEET_FORMATS = ('native','aseprite_hash','aseprite_array','godot')
FORMAT_LABELS = {'原生 JSON':'native','Aseprite JSON · Hash':'aseprite_hash',
                 'Aseprite JSON · Array':'aseprite_array','Godot 4 · SpriteFrames':'godot'}


def export_paths(path, kind='sheet', sheet_format='native'):
    if kind not in ('png','sheet','gif') or sheet_format not in SHEET_FORMATS:
        raise PixelError('Unknown export kind or sheet_format',details={'kinds':['png','sheet','gif'],'sheet_formats':list(SHEET_FORMATS)})
    if kind!='sheet' and sheet_format!='native':
        raise PixelError('sheet_format applies only to kind=sheet; PNG/GIF use native.',details={'sheet_formats':list(SHEET_FORMATS)})
    path=Path(path)
    return [path,*([path.with_suffix('.json')] if kind=='sheet' else []),
            *([path.with_suffix('.tres')] if kind=='sheet' and sheet_format=='godot' else [])]


def check_sidecars(path, kind, sheet_format):
    if kind=='sheet' and sheet_format!='godot' and Path(path).with_suffix('.tres').exists():
        raise PixelError('A Godot resource with this basename already exists. Choose a new basename or export the matching Godot bundle.',
            code='EXPORT_SIDECAR_CONFLICT',recovery='Do not leave an older .tres referencing a replaced atlas; use another filename or the Godot format.')


def aseprite_data(doc, path, metadata, exported_tags, size, array=False, tag=None):
    """Mirror Aseprite's untrimmed JSON_HASH/JSON_ARRAY fields, in exported source order."""
    from .quality import effective_policy
    frames=[]
    for item in metadata:
        w,h=item['width'],item['height']
        frames.append({'filename':f'{Path(path).stem}_{item["source_index"]:04d}.png',
            'frame':{'x':item['x'],'y':item['y'],'w':w,'h':h},'rotated':False,'trimmed':False,
            'spriteSourceSize':{'x':0,'y':0,'w':w,'h':h},'sourceSize':{'w':w,'h':h},'duration':item['duration_ms']})
    tags=[]
    for item in exported_tags:
        if tag is not None and item['name']!=tag:continue
        entry={'name':item['name'],'from':item['start'],'to':item['end'],'direction':item['direction']}
        # Aseprite's exporter writes repeat as a string, and omits unlimited repetition.
        if not effective_policy(doc,item['name'])['loop']:entry['repeat']='1'
        tags.append(entry)
    return {'frames':frames if array else {f['filename']:{k:v for k,v in f.items() if k!='filename'} for f in frames},
        'meta':{'app':'https://github.com/yangsir2077/pixel-loom','version':__version__,
                'image':Path(path).name,'format':'RGBA8888','size':{'w':size[0],'h':size[1]},'scale':'1','frameTags':tags}}


def godot_resource(doc, path, metadata, tag=None):
    """Godot 4 text resource. Relative PNG reference survives moving the whole bundle."""
    from .quality import effective_policy
    quoted=lambda value:json.dumps(value,ensure_ascii=False)
    mapping={item['source_index']:item['index'] for item in metadata}
    animations=[]
    if tag is not None:
        animations=[(tag,doc.frame_indices(tag,playback=True),effective_policy(doc,tag)['loop'])]
    elif doc.tags:
        animations=[(name,doc.frame_indices(name,playback=True),effective_policy(doc,name)['loop']) for name in doc.tags]
        covered={f for name in doc.tags for f in doc.frame_indices(name)}
        used=set(doc.tags)
        for frame in mapping:
            if frame not in covered:
                name=f'unnamed_{frame}'
                while name in used:name+='_'  # Never collide with a user-authored action name.
                used.add(name);animations.append((name,[frame],False))
    else:animations=[('default',list(mapping),effective_policy(doc)['loop'])]
    lines=[f'[gd_resource type="SpriteFrames" load_steps={len(metadata)+2} format=3]',
           '; Exported by Pixel Loom. Keep the PNG beside this resource.',
           f'[ext_resource type="Texture2D" path={quoted(Path(path).name)} id="1_atlas"]','']
    for item in metadata:
        lines += [f'[sub_resource type="AtlasTexture" id="AtlasTexture_{item["index"]}"]',
                  'atlas = ExtResource("1_atlas")',
                  f'region = Rect2({item["x"]}, {item["y"]}, {item["width"]}, {item["height"]})','']
    parts=[]
    for name,order,loop in animations:
        entries=[f'{{"duration": {doc.durations[f]/100.0}, "texture": SubResource("AtlasTexture_{mapping[f]}")}}' for f in order]
        parts.append('{"frames": ['+',\n'.join(entries)+'], "loop": '+str(loop).lower()+
                     ', "name": &'+quoted(name)+', "speed": 10.0}')
    lines += ['[resource]','animations = ['+',\n'.join(parts)+']','']
    return '\n'.join(lines)


def write_bundle(outputs):
    """Stage every file before replacing anything; restore previous outputs on commit failure."""
    staged={};backups={};installed=[];temporary=set();retain=set()
    def allocate(parent):
        fd,name=tempfile.mkstemp(prefix='.pixel-loom-export-',dir=parent);os.close(fd)
        path=Path(name);temporary.add(path);return path
    try:
        for target,data in outputs.items():
            target=Path(target)
            if target.exists() and not target.is_file():raise PixelError(f'Export target is not a file: {target}')
            target.parent.mkdir(parents=True,exist_ok=True)
            stage=allocate(target.parent);stage.write_bytes(data);staged[target]=stage
        for target in staged:
            if target.exists():
                backup=allocate(target.parent);os.replace(target,backup);backups[target]=backup
        for target,stage in staged.items():
            os.replace(stage,target);installed.append(target)
    except (OSError,ValueError):
        failures=[]
        for target in installed:
            if target not in backups:
                try:target.unlink(missing_ok=True)
                except OSError:failures.append({'target':str(target),'error':'Could not remove incomplete new output'})
        for target,backup in backups.items():
            try:os.replace(backup,target)
            except OSError:
                retain.add(backup);failures.append({'target':str(target),'backup':str(backup)})
        if failures:
            raise PixelError('Export failed and some outputs need recovery; previous files are retained where restoration failed.',
                code='EXPORT_RECOVERY_NEEDED',details={'backups':failures})
        raise
    finally:
        for path in temporary-retain:
            try:path.unlink(missing_ok=True)
            except OSError:pass  # Never hide the original error or remove a retained recovery copy.
