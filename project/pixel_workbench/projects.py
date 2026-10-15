"""Persistent project shelf and non-destructive saved-version history."""
from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from .model import Document, PixelError, atomic_json


def path_key(path):
    return os.path.normcase(str(Path(path).resolve()))


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame_at(doc, time_ms):
    phase = max(0, int(time_ms)) % sum(doc.durations)
    for frame, duration in enumerate(doc.durations):
        if phase < duration:
            return frame
        phase -= duration
    return 0


class ProjectLibrary:
    def __init__(self, runtime, workspace):
        self.runtime, self.workspace = Path(runtime), Path(workspace)
        self.catalog = self.runtime / 'project-library.json'
        self.entries = []
        if self.catalog.exists():
            data = json.loads(self.catalog.read_text(encoding='utf-8'))
            if data.get('format') != 'pixel-loom/projects/v1' or not isinstance(data.get('projects'), list):
                raise PixelError('Invalid project library; keep its file for recovery')
            self.entries = data['projects']
            if any(not isinstance(entry,dict) or not re.fullmatch(r'[0-9a-f]{32}',str(entry.get('id','')))
                   or not isinstance(entry.get('path'),str) for entry in self.entries):
                raise PixelError('Invalid project library entry; keep its file for recovery')

    def persist(self):
        atomic_json(self.catalog, {'format': 'pixel-loom/projects/v1', 'projects': self.entries})

    def by_path(self, path):
        return next((entry for entry in self.entries if path_key(entry['path']) == path_key(path)), None)

    def get(self, project_id, include_deleted=False):
        entry = next((entry for entry in self.entries if entry['id'] == project_id), None)
        if entry is None:
            raise PixelError('Project not found. Read pixel_projects list.', code='PROJECT_NOT_FOUND')
        if entry.get('deleted_at') and not include_deleted:
            raise PixelError('Project is deleted from the shelf. Use pixel_projects undelete to restore it.',code='PROJECT_DELETED')
        return entry

    def register(self, path, doc=None, parent_id=None):
        path = Path(path).resolve()
        doc = doc or Document.open(path)
        entry = self.by_path(path)
        if entry is None:
            entry = {'id': uuid.uuid4().hex, 'number': len(self.entries) + 1, 'path': str(path),
                     'parent_id': parent_id, 'created_at': datetime.now(timezone.utc).isoformat()}
            self.entries.append(entry)
        entry.update(name=doc.name, document_id=doc.id, width=doc.width, height=doc.height,
                     frames=len(doc.durations), duration_ms=sum(doc.durations), disk_sha256=file_digest(path))
        entry.pop('deleted_at',None)  # Explicitly opening/adding its file restores the same project identity.
        self.persist()
        return entry

    def listing(self, active_path=None, deleted=False):
        active = path_key(active_path) if active_path else None
        return [{**entry, 'active': path_key(entry['path']) == active,
                 'available': Path(entry['path']).is_file()} for entry in self.entries
                if bool(entry.get('deleted_at'))==deleted]

    def set_deleted(self, project_ids, deleted=True):
        if not isinstance(project_ids,list) or not 1<=len(project_ids)<=256 or any(not isinstance(key,str) for key in project_ids):
            raise PixelError('Choose 1–256 project ids')
        selected=[self.get(key,include_deleted=not deleted) for key in dict.fromkeys(project_ids)]
        previous=deepcopy(self.entries)
        stamp=datetime.now(timezone.utc).isoformat()
        try:
            for entry in selected:
                if deleted:entry['deleted_at']=stamp
                else:entry.pop('deleted_at',None)
            self.persist()
        except (OSError,ValueError):
            self.entries=previous
            raise
        return selected

    def new_path(self, name):
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(name)).strip(' .')[:70] or 'project'
        if stem.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            stem = 'project-' + stem
        folder = self.workspace / 'projects'
        folder.mkdir(parents=True, exist_ok=True)
        while True:
            path = folder / f'{stem}-{uuid.uuid4().hex[:10]}.pixloom'
            if not path.exists():
                return path

    def history_folder(self, entry):
        return self.runtime / 'project-history' / entry['id']

    def versions(self, project_id):
        entry = self.get(project_id)
        folder = self.history_folder(entry)
        return [{'id': path.stem, 'path': str(path), 'saved_at': path.stem.split('-')[0],
                 'bytes': path.stat().st_size} for path in sorted(folder.glob('*.pixloom'), reverse=True)]

    def version_path(self, project_id, version_id):
        candidates = [item for item in self.versions(project_id) if item['id'] == version_id]
        if len(candidates) != 1:
            raise PixelError('Saved version not found', code='VERSION_NOT_FOUND')
        return Path(candidates[0]['path'])

    def backup(self, path, project_id=None):
        """Capture the existing file before any overwrite, deduplicated by its bytes."""
        path = Path(path)
        if not path.exists():
            return None
        entry = self.get(project_id) if project_id else self.by_path(path) or self.register(path)
        digest = file_digest(path)
        folder = self.history_folder(entry)
        folder.mkdir(parents=True, exist_ok=True)
        if any(folder.glob(f'*-{digest}.pixloom')):
            return None
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        target = folder / f'{stamp}-{digest}.pixloom'
        shutil.copy2(path, target)
        return target

    def check_external_change(self, path):
        entry = self.by_path(path)
        if entry and (not Path(path).is_file() or file_digest(path) != entry['disk_sha256']):
            raise PixelError('Project file changed outside the editor. Save to a new path or reopen it first.',
                             code='PROJECT_FILE_CHANGED')
