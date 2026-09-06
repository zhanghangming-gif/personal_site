"""Atomic, reproducible job workspace for score compilation."""
import hashlib
import json
import os
import time

from score_contracts import new_manifest


DIRECTORIES = (
    'inspection', 'renders/preview-150', 'renders/analysis-400',
    'renders/regions', 'evidence', 'scores/source', 'scores/target',
    'layout/source', 'layout/target', 'candidates', 'review', 'logs',
)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporary, path)


class ScoreWorkspace:
    def __init__(self, job_dir):
        self.job_dir = os.path.abspath(job_dir)
        self.manifest_path = os.path.join(self.job_dir, 'manifest.json')

    def initialize(self, job_id, source_path, request, intent):
        os.makedirs(self.job_dir, exist_ok=True)
        for name in DIRECTORIES:
            os.makedirs(os.path.join(self.job_dir, *name.split('/')), exist_ok=True)
        manifest = new_manifest(job_id, file_sha256(source_path), request.get('name', 'score.pdf'), intent)
        atomic_json(self.manifest_path, manifest)
        return manifest

    def read(self):
        with open(self.manifest_path, encoding='utf-8') as stream:
            return json.load(stream)

    def write(self, manifest):
        manifest['updatedAt'] = time.time()
        atomic_json(self.manifest_path, manifest)
        return manifest

    def update_stage(self, stage, message, progress):
        if not os.path.isfile(self.manifest_path):
            return None
        manifest = self.read()
        entry = {'stage': stage, 'message': message, 'progress': int(progress), 'at': time.time()}
        manifest['pipeline'].update(entry)
        history = manifest['pipeline'].setdefault('history', [])
        if not history or history[-1].get('stage') != stage:
            history.append(entry)
        else:
            history[-1] = entry
        return self.write(manifest)

    def register_artifact(self, role, path, contract=None, metadata=None):
        if not os.path.isfile(path):
            return None
        manifest = self.read()
        relative = os.path.relpath(os.path.abspath(path), self.job_dir).replace('\\', '/')
        if relative.startswith('../') or relative == '..':
            raise ValueError('任务文件必须位于当前工作区')
        artifact = {
            'path': relative,
            'sha256': file_sha256(path),
            'size': os.path.getsize(path),
        }
        if metadata:
            artifact.update(metadata)
        manifest['artifacts'][role] = artifact
        if contract:
            if contract not in manifest['contracts']:
                raise ValueError('未知乐谱数据契约：%s' % contract)
            manifest['contracts'][contract] = role
        self.write(manifest)
        return artifact

    def record_patch(self, patch):
        manifest = self.read()
        value = dict(patch)
        value.setdefault('at', time.time())
        manifest.setdefault('patches', []).append(value)
        return self.write(manifest)

    def register_score_version(self, role, path, parent_version_id=None, metadata=None):
        if not os.path.isfile(path):
            return None
        manifest = self.read()
        relative = os.path.relpath(os.path.abspath(path), self.job_dir).replace('\\', '/')
        if relative.startswith('../') or relative == '..':
            raise ValueError('乐谱版本必须位于当前工作区')
        digest = file_sha256(path)
        version = {
            'versionId': 'score-' + digest[:16],
            'role': role,
            'artifact': relative,
            'sha256': digest,
            'parentVersionId': parent_version_id,
            'createdAt': time.time(),
        }
        if metadata:
            version.update(metadata)
        versions = manifest.setdefault('scoreVersions', [])
        existing = next((item for item in versions
                         if item.get('versionId') == version['versionId'] and item.get('role') == role), None)
        if existing:
            return existing
        versions.append(version)
        self.write(manifest)
        return version

    def record_runtime(self, engines=None, models=None, parameters=None):
        manifest = self.read()
        manifest.setdefault('engineVersions', {}).update(engines or {})
        manifest.setdefault('modelVersions', {}).update(models or {})
        manifest.setdefault('parameters', {}).update(parameters or {})
        return self.write(manifest)
