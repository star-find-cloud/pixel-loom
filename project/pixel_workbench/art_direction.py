"""Bounded art direction and whole/detail evidence; no painting or aesthetic verdicts."""
from __future__ import annotations

import hashlib
import json
from typing import Literal
from typing_extensions import TypedDict

from PIL import Image, ImageDraw
from pydantic import StrictInt

from .model import PixelError, hexcolor, integer, rgba
from .reference import decoded_asset, encode_png
from .reference_ui_images import checker


class ArtRegion(TypedDict, total=False):
    id: str
    rect: list[StrictInt]
    goal: str
    layers: list[str]
    reference_role: Literal['subject', 'style']
    reference_rect: list[StrictInt]


class ArtDirection(TypedDict, total=False):
    route: Literal['native', 'generated']
    canvas: list[StrictInt]
    style_goals: list[str]
    lighting: str
    palette: list[str]
    detail_notes: str
    regions: list[ArtRegion]


def text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PixelError(f'{name} needs 1–{limit} characters')
    return value.strip()


def rect(value, size, name='rect'):
    if not isinstance(value, list) or len(value) != 4:
        raise PixelError(f'{name} must be [x,y,width,height]')
    x, y, w, h = [integer(v, name, 0, 1024) for v in value]
    if not w or not h or x+w > size[0] or y+h > size[1]:
        raise PixelError(f'{name} exceeds its image bounds')
    return [x, y, w, h]


def validate_direction(value, doc=None):
    if value == {}:
        return None
    if not isinstance(value, dict) or set(value)-set(ArtDirection.__annotations__):
        raise PixelError('Unknown art direction fields', details={'allowed_fields': list(ArtDirection.__annotations__)})
    if value.get('route') not in ('native', 'generated'):
        raise PixelError('Choose route=native or generated from the real human request')
    canvas = value.get('canvas', [doc.width, doc.height] if doc else None)
    if not isinstance(canvas, list) or len(canvas) != 2:
        raise PixelError('Art direction canvas needs [width,height]')
    canvas = [integer(v, 'canvas', 1, 512) for v in canvas]
    if doc and canvas != [doc.width, doc.height]:
        raise PixelError('Plan on the intended canvas; preserve the old work before resizing or creating a project.',
                         code='ART_CANVAS_CONFLICT')
    result = {'route': value['route'], 'canvas': canvas, 'style_goals': [], 'lighting': '',
              'palette': [], 'detail_notes': '', 'regions': []}
    goals = value.get('style_goals', [])
    if not isinstance(goals, list) or len(goals) > 8:
        raise PixelError('At most 8 style goals')
    result['style_goals'] = [text(v, 'style goal', 240) for v in goals]
    for key, limit in (('lighting', 240), ('detail_notes', 600)):
        if value.get(key):
            result[key] = text(value[key], key, limit)
        elif key in value and not isinstance(value[key], str):
            raise PixelError(key+' must be text')
    palette = value.get('palette', [])
    if not isinstance(palette, list) or len(palette) > 64:
        raise PixelError('Art direction palette needs at most 64 colors')
    result['palette'] = list(dict.fromkeys(hexcolor(rgba(v)) for v in palette))
    regions = value.get('regions', [])
    if not isinstance(regions, list) or len(regions) > 12:
        raise PixelError('Use at most 12 meaningful art regions')
    seen = set()
    for item in regions:
        if not isinstance(item, dict) or set(item)-set(ArtRegion.__annotations__):
            raise PixelError('Unknown art region fields')
        identity = text(item.get('id'), 'region id', 48)
        if identity in seen:
            raise PixelError('Art region ids must be unique')
        seen.add(identity)
        part = {'id': identity, 'rect': rect(item.get('rect'), canvas), 'goal': text(item.get('goal'), 'region goal', 240)}
        if 'layers' in item:
            layers = item['layers']
            if not isinstance(layers, list) or len(layers) > 16:
                raise PixelError('Region layers needs at most 16 stable ids')
            layers = [text(v, 'layer id', 120) for v in layers]
            part['layers'] = list(dict.fromkeys(doc.layer(v).id if doc else v for v in layers))
        if 'reference_role' in item or 'reference_rect' in item:
            if item.get('reference_role') not in ('subject', 'style'):
                raise PixelError('Reference crop needs reference_role=subject/style')
            part['reference_role'] = item['reference_role']
            part['reference_rect'] = rect(item.get('reference_rect'), [1024, 1024], 'reference_rect')
        result['regions'].append(part)
    return result


def summary(direction, doc):
    if not direction:
        return None
    return {'route': direction['route'], 'canvas': direction['canvas'], 'regions': len(direction['regions']),
            'canvas_current': direction['canvas'] == [doc.width, doc.height],
            'read_next': {'tool': 'pixel_help', 'arguments': {'topic': 'art_direction'}}}


def current_plan(service, route=None):
    notes = service.tasks.load(service.doc)
    context = notes['context']
    direction = context.get('direction') if context else None
    if not direction:
        raise PixelError('Record a concise pixel_task direction plan first.', code='ART_PLAN_REQUIRED',
                         recovery="Read pixel_help(topic='art_direction'); direction is optional for old workflows.")
    if direction['canvas'] != [service.doc.width, service.doc.height]:
        raise PixelError('Canvas changed; update the art direction plan before using its regions.', code='ART_CANVAS_CONFLICT')
    if route and direction['route'] != route:
        raise PixelError('This action needs the selected generated route; native drawing remains available.', code='ART_ROUTE_CONFLICT')
    return notes, context, direction


def _panel(image, title):
    image = image.convert('RGBA')
    # Integer enlargement only; large references are presentation thumbnails, never new source pixels.
    if max(image.size) <= 384:
        scale = min(8, max(1, 384//max(image.size)))
        view = image.resize((image.width*scale, image.height*scale), Image.Resampling.NEAREST)
    else:
        view = image.copy()
        view.thumbnail((384, 384), Image.Resampling.NEAREST)
    panel = Image.new('RGB', (404, 426), '#171d27')
    draw = ImageDraw.Draw(panel)
    draw.text((10, 8), title, fill='#e0e8ee')
    draw.text((10, 25), f'Source: {image.width} x {image.height}px', fill='#a8b6c5')
    panel.paste(checker(view).convert('RGB'), ((404-view.width)//2, 45+(376-view.height)//2))
    return panel


def board(service, payload):
    if service.view.get('gesture_active'):
        raise PixelError('Finish the active stroke before capturing art evidence.', code='EDITOR_BUSY')
    notes, context, direction = current_plan(service)
    doc = service.doc
    frame = integer(payload.get('frame', doc.active_frame), 'frame', 0, len(doc.durations)-1)
    region = None
    if payload.get('region_id'):
        region = next((v for v in direction['regions'] if v['id'] == payload['region_id']), None)
        if region is None:
            raise PixelError('Unknown art region', details={'allowed_ids': [v['id'] for v in direction['regions']]})
    region_rect = region['rect'] if region else [0, 0, doc.width, doc.height]
    x, y, w, h = region_rect
    full = doc.composite(frame)
    selected = full
    if region and region.get('layers'):
        # Do not silently return a composite for deleted/misspelled layers.
        layers = [doc.layer(v).id for v in region['layers']]
        selected = doc.preview(frame, 1, checker=False, layers=layers)
    focus = selected.crop((x, y, x+w, y+h))
    panels = [('WHOLE / current', full)]
    if focus.size != full.size or focus.tobytes() != full.tobytes():
        panels.append(('DETAIL / current', focus))
    refs = service.references.context
    chosen_role = region.get('reference_role') if region else None
    role = chosen_role or ('style' if refs.get('style') else 'subject')
    asset = refs.get(role)
    if chosen_role and not asset:
        raise PixelError('The planned reference is not loaded; load it or update this region.', code='REFERENCE_REQUIRED')
    if asset:
        reference = decoded_asset(asset['png'])
        panels.append((role.upper()+' / reference', reference))
        if region and region.get('reference_rect'):
            rx, ry, rw, rh = rect(region['reference_rect'], reference.size, 'reference_rect')
            panels.append(('DETAIL / reference', reference.crop((rx, ry, rx+rw, ry+rh))))
    scope = {'document_id': doc.id, 'revision': doc.revision, 'frame': frame, 'task_revision': notes['revision'],
             'reference_revision': service.references.revision, 'region_id': payload.get('region_id')}
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True).encode())
    for label, image in panels:
        digest.update(label.encode());digest.update(image.tobytes())
    key = digest.hexdigest()
    if key == payload.get('if_image_key'):
        return {'ok': True, **scope, 'image_key': key, 'unchanged': True, 'read_only': True}
    receipt = {'ok': True, **scope, 'image_key': key, 'unchanged': False,
               'route': direction['route'], 'native_size': [doc.width, doc.height], 'focus_rect': region_rect,
               'region_goal': region['goal'] if region else context['brief'],
               'image_roles': [p[0] for p in panels], 'read_only': True,
               'assessment': 'Compare actual images; this board is not a visual pass or a complete isolated-part receipt.'}
    picture = Image.new('RGB', (404*len(panels), 426), '#171d27')
    for i, (label, image) in enumerate(panels):
        picture.paste(_panel(image, label), (i*404, 0))
    receipt['images_png'] = [encode_png(picture)]
    colors = focus.getcolors(focus.width*focus.height) or []
    receipt['detail_statistics'] = {'opaque_or_partial_colors': sum(1 for _, c in colors if c[3]),
                                   'alpha_bounds': list(focus.getchannel('A').getbbox() or []),
                                   'dominant_colors': [hexcolor(c) for _, c in sorted(colors, reverse=True) if c[3]][:8]}
    return receipt
