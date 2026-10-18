"""Provider-neutral host-generation handoff and reviewed local draft candidates.

No HTTP client, credentials, subprocess or model implementation lives here.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import re
import time
import uuid

from .art_direction import current_plan
from .model import PixelError
from .reference import DEFAULTS, decoded_asset, encode_png, read_asset_bytes, load_asset_bytes, new_redraw_document, validate_context, validate_settings
from .reference_ui_images import checker


def check_generation_settings(value):
    if not isinstance(value,dict) or not {'width','height','colors'} <= value.keys():
        raise PixelError('Preview requires explicit width, height and colors.',
                         details={'required_fields':['width','height','colors']})
    # Run before MCP coercion too; validate the real crop against its source later.
    validate_settings(value,{'size':[1024,1024]})
    return value


class GenerationManager:
    def __init__(self):
        self.tickets = OrderedDict()

    def prune(self):
        now = time.monotonic()
        for key, value in list(self.tickets.items()):
            if now-value['created'] > 300:
                del self.tickets[key]
        while len(self.tickets) > 2:
            self.tickets.popitem(last=False)

    def action(self, service, payload):
        action = payload.get('action', 'request')
        if action not in ('request', 'preview', 'apply'):
            raise PixelError('Unknown generation action')
        common={'action','expected_document_id','expected_revision'}
        allowed=common | {'request':{'generator_available'},'preview':{'path','settings','name','if_source_sha256'},'apply':{'preview_id'}}[action]
        unused=set(payload)-allowed
        if action!='request' and payload.get('generator_available',False) is False:unused.discard('generator_available')
        if unused:
            raise PixelError('Arguments do not belong to this generation action.',code='GENERATION_ARGUMENT_CONFLICT',
                             details={'action':action,'allowed_fields':sorted(allowed),'unused_fields':sorted(unused)})
        self.prune()
        if action == 'apply':
            return self.apply(service, payload)
        if action == 'request':
            return self.request(service, payload)
        return self.preview(service, payload)

    def request(self, service, payload):
        if 'expected_document_id' in payload or 'expected_revision' in payload:service.guard(payload)
        notes, context, direction = current_plan(service, 'generated')
        available = payload.get('generator_available', False)
        if not isinstance(available, bool):
            raise PixelError('generator_available must be boolean')
        lines = ['Create ONE static artwork from this recorded design; reconcile it with the current human request.',
                 'Brief: '+context['brief'], f'Target pixel canvas: {service.doc.width} x {service.doc.height}.',
                 'Preserve requested objects, viewpoint, proportions, palette relationships and detail density.',
                 'Do not replace careful shapes with repeated identical marks or random texture.',
                 'Do not add accessories, animation, hidden-area completion or background removal unless the human requested them.']
        if direction['style_goals']:
            lines.append('Style goals: '+'; '.join(direction['style_goals']))
        if direction['lighting']:
            lines.append('Lighting: '+direction['lighting'])
        if direction['palette']:
            lines.append('Planned colors: '+', '.join(direction['palette']))
        if direction['detail_notes']:
            lines.append('Detail decisions: '+direction['detail_notes'])
        if direction['regions']:
            lines.append('Composition/detail regions (target pixels): '+'; '.join(
                f"{r['id']} {r['rect']}: {r['goal']}" for r in direction['regions']))
        references, images, roles = [], [], []
        for role in ('subject', 'style'):
            asset = service.references.context.get(role)
            if asset:
                references.append({'role': role, 'name': asset['name'], 'id': asset['id'], 'size': asset['size']})
                images.append(asset['png']);roles.append(role+'_reference')
        return {'ok': True, 'document_id': service.doc.id, 'revision': service.doc.revision,
                'task_revision': notes['revision'], 'execution': 'host_generator_required',
                'generator_available_reported_by_caller': available,
                'status': 'ready_for_host_generation' if available else 'generator_unavailable',
                'image_generated': False, 'network_called': False, 'prompt': '\n'.join(lines),
                'references': references, 'image_roles': roles, 'images_png': images,
                'next_action': 'Use the host generator, inspect its actual output, then preview(path, settings).'
                if available else 'This client has not supplied a generator. Use an external generator/imported image, or choose native; never claim generation happened.'}

    def preview(self, service, payload):
        service.guard(payload)
        notes, context, direction = current_plan(service, 'generated')
        settings=check_generation_settings(payload.get('settings'))
        known_source = payload.get('if_source_sha256')
        if known_source is not None:
            if not isinstance(known_source, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', known_source):
                raise PixelError('if_source_sha256 needs the SHA256 of an original image already viewed.')
            known_source = known_source.lower()
        if not isinstance(payload.get('path'), str) or not payload['path']:
            raise PixelError('Supply the real local image returned by a generator or explicitly imported by the human.')
        source = service.resolve(payload['path'])
        if not source.is_file() or source.stat().st_size > 50_000_000:
            raise PixelError('Generated image must be a local file of at most 50 MB')
        raw = read_asset_bytes(source)
        source_hash = hashlib.sha256(raw).hexdigest()
        asset = load_asset_bytes(raw,source.name)
        # Detect concurrent source replacement during decode as well as at apply.
        if hashlib.sha256(read_asset_bytes(source)).hexdigest() != source_hash:
            raise PixelError('Source changed during preview; retry the new source.', code='GENERATION_SOURCE_CHANGED')
        reference = validate_context({'subject': asset, 'style': deepcopy(service.references.context.get('style')),
                                      'settings': {**DEFAULTS, 'width': service.doc.width, 'height': service.doc.height,
                                                   'style': 'scene', **settings}})
        suffix=' · 生成底稿'
        name = payload.get('name')
        if name is None:name=service.doc.name[:120-len(suffix)]+suffix
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise PixelError('Candidate name needs 1–120 characters')
        candidate = new_redraw_document(reference, name=name.strip(), mode='draft')
        ticket_id = uuid.uuid4().hex
        ticket = {'created': time.monotonic(), 'base_id': service.doc.id, 'base_revision': service.doc.revision,
                  'task_revision': notes['revision'], 'reference_revision': service.references.revision,
                  'source': source, 'source_hash': source_hash, 'candidate': candidate,
                  'reference_subject_id':(service.references.context.get('subject') or {}).get('id'),
                  'direction': deepcopy(direction), 'brief': context['brief'], 'applied': None}
        self.tickets[ticket_id] = ticket
        self.prune()
        source_unchanged = known_source == source_hash
        draft = candidate.composite(0)
        scale = max(1, min(8, 512//max(draft.size)))
        images, roles = [], []
        if not source_unchanged:
            images.append(encode_png(checker(decoded_asset(asset['png']))))
            roles.append('generated_original_reference')
        images.append(encode_png(checker(draft.resize((draft.width*scale, draft.height*scale), resample=0))))
        roles.append('proposed_automatic_pixel_draft')
        return {'ok': True, 'dry_run': True, 'preview_id': ticket_id, 'expires_in_seconds': 300,
                'document_id': service.doc.id, 'revision': service.doc.revision,
                'task_revision': notes['revision'], 'source_size': asset['original_size'],
                'stored_reference_size': asset['size'], 'candidate_size': list(draft.size),
                'first_frame_only':asset['first_frame_only'],
                'conversion_settings': reference['settings'], 'source_sha256': source_hash,
                'source_image_omitted': source_unchanged, 'image_roles': roles, 'images_png': images,
                'next_action': 'VIEW the new draft against the original already viewed. Adjust or apply this exact preview_id as a separate project.'
                if source_unchanged else 'VIEW both images. Adjust settings with a new preview, or apply this exact preview_id as a separate project.',
                'limitations': 'Sampled draft, not semantic layers, artistic approval, automatic cutout or animation. Large source references follow the existing 1024px storage limit.'}

    def apply(self, service, payload):
        key = payload.get('preview_id')
        ticket = self.tickets.get(key) if isinstance(key, str) else None
        if ticket is None:
            raise PixelError('Generated preview is missing/expired; preview the actual file again.', code='GENERATION_PREVIEW_EXPIRED')
        # Exact retry returns a receipt, never imports a duplicate project.
        if ticket['applied'] is not None:
            if payload.get('expected_document_id') != ticket['base_id'] or payload.get('expected_revision') != ticket['base_revision']:
                raise PixelError('A retry must refer to the original viewed candidate and tokens.', code='DOCUMENT_CONFLICT')
            receipt={**deepcopy(ticket['applied']), 'replayed': True,
                     'current_document_id': service.doc.id, 'current_revision': service.doc.revision}
            if not receipt['ok']:
                raise PixelError('This candidate was already applied but still needs recovery/save.',
                                 code=receipt['code'],details=receipt,recovery=receipt['recovery'])
            return receipt
        service.guard(payload)
        notes, _, _ = current_plan(service, 'generated')
        if (service.doc.id, service.doc.revision, notes['revision'], service.references.revision) != (
                ticket['base_id'], ticket['base_revision'], ticket['task_revision'], ticket['reference_revision']):
            raise PixelError('Artwork, art plan or references changed after preview; inspect a new candidate.', code='GENERATION_PREVIEW_STALE')
        source = ticket['source']
        if not source.is_file() or source.stat().st_size > 50_000_000 or hashlib.sha256(read_asset_bytes(source)).hexdigest() != ticket['source_hash']:
            raise PixelError('The source image changed/disappeared after preview.', code='GENERATION_SOURCE_CHANGED')
        candidate = ticket['candidate']
        target = service.projects.new_path(candidate.name)
        direction = deepcopy(ticket['direction'])
        direction['canvas'] = [candidate.width, candidate.height]
        reset_regions = [candidate.width, candidate.height] != ticket['direction']['canvas']
        source_changed=ticket['reference_subject_id'] != candidate.reference['subject']['id']
        reference_regions=[r['id'] for r in direction['regions'] if source_changed and r.get('reference_role')=='subject']
        if reset_regions:direction['regions'] = []
        else:
            for region in direction['regions']:
                region.pop('layers', None)
                if source_changed and region.get('reference_role')=='subject':
                    region.pop('reference_role',None);region.pop('reference_rect',None)
        task_plan={'action': 'plan', 'task': 'image_static', 'brief': ticket['brief'],
                   'expected_task_revision': 0, 'direction': direction, 'stage': 'separate',
                   'parts': [{'layer': candidate.layers[0].id, 'frame': 0, 'extraction': 'pending', 'hidden': 'not_requested',
                              'note': 'Generated image sampled into a faithful draft; visible-object layers still need inspection/separation.'}],
                   'next_action': 'Inspect and separate visible objects; preserve the faithful converted draft. Existing review/export gate still applies.'}
        # Existing versions are checkpointed using the same project/GUI model path.
        outgoing = service.checkpoint_current()
        try:
            service.replace(candidate)
            service.saved_fingerprint = ''
            service.tasks.update(candidate, task_plan,
                                 service.part_receipts, service.quality)
            service.save_project(target, parent_id=outgoing['id'] if outgoing else None)
        except (OSError, ValueError) as error:
            if service.doc is not candidate:
                raise  # Replacement failed before the live document changed.
            service.saved_fingerprint = ''  # A new unsaved document must not look saved after a partial switch.
            reference_sync_pending=service.references.context != candidate.reference
            try:task_pending=service.tasks.load(candidate)['context'] is None
            except PixelError:task_pending=True
            recovery_path=None
            try:
                emergency=service.runtime/'recovery'/(candidate.id+'.pixloom')
                candidate.save(emergency);recovery_path=str(emergency)
            except (OSError,ValueError):pass  # Full-disk failures must not hide the original outcome.
            recovery='Read current state after storage recovers. '
            if reference_sync_pending:recovery+='Restore its reference with pixel_reference_setup(action=use_project). '
            if task_pending:recovery+='Use task_recovery with fresh document tokens to restore the faithful-draft task. '
            recovery+='Save this applied project. '
            recovery+='Do not reapply the candidate.'
            receipt = {'ok': False, 'code': 'GENERATION_APPLIED_NOT_SAVED', 'applied': True,
                       'document_id': candidate.id, 'revision': candidate.revision, 'project_path': str(service.path) if service.path else None,
                       'reference_sync_pending':reference_sync_pending,'task_plan_pending':task_pending,
                       'recovery_path':recovery_path,'recovery':recovery}
            if task_pending:receipt['task_recovery']=deepcopy(task_plan)
            ticket['applied'] = receipt
            ticket.pop('candidate',None)  # Retry needs a receipt, not a retained live document/undo stack.
            raise PixelError('Candidate applied but local task/save failed: '+str(error), code=receipt['code'], details=receipt,
                             recovery=receipt['recovery']) from error
        receipt = {'ok': True, 'applied': True, 'document_id': candidate.id, 'revision': candidate.revision,
                   'project_path': str(service.path), 'native_size': [candidate.width, candidate.height],
                   'outgoing_project_id': outgoing['id'] if outgoing else None, 'source_preserved': True,
                   'history_preserved': True, 'semantic_layers_ready': False, 'regions_need_replanning': reset_regions,
                   'reference_regions_need_replanning':reference_regions,
                   'delivery_status': 'unreviewed_automatic_pixel_draft',
                   'next_action': 'Inspect editable draft, separate actual visible objects, then use existing review/save/export. Local touch-ups require the human edit scope.'}
        ticket['applied'] = deepcopy(receipt)
        ticket.pop('candidate',None)
        return receipt
