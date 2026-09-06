import json
import os
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))

from rest_annotation_admin import (  # noqa: E402
    build_training_archive, list_samples, sample_image_path, update_sample,
)


def seed_dataset(root):
    images = root / 'images'
    images.mkdir(parents=True)
    Image.new('RGB', (200, 100), 'white').save(str(images / 'sample.png'))
    record = {
        'schemaVersion': 1, 'sampleId': 'a' * 24, 'image': 'images/sample.png',
        'imageWidth': 200, 'imageHeight': 100, 'documentSha256': '1' * 64,
        'sourceJobId': 'private-job-id', 'sourcePdfStored': False,
        'gapId': 'rhythm-gap-p1-m8-v1-1', 'measureId': 'p1-m8', 'page': 1,
        'voice': '1', 'onset': '0/1', 'duration': '1/1', 'position': 'full',
        'imageSource': 'audiveris_binary', 'classificationStatus': 'strong',
        'prelabel': {'class': 'whole_rest', 'bboxXyxy': [80, 40, 120, 55],
                     'dots': 0, 'source': 'audiveris_internal_object'},
        'state': 'unreviewed', 'annotation': None, 'annotator': None, 'reviewedAt': None,
    }
    (root / 'queue.jsonl').write_text(json.dumps(record) + '\n', encoding='utf-8')
    return record


def test_public_queue_hides_job_and_file_paths(tmp_path):
    seed_dataset(tmp_path)
    data = list_samples(str(tmp_path), 'unreviewed', 0, 10)
    assert data['counts']['total'] == 1
    item = data['items'][0]
    assert 'sourceJobId' not in item and 'image' not in item and 'crop' not in item
    assert item['imageUrl'].endswith('/image')


def test_accept_requires_unchanged_omr_prelabel_and_revision(tmp_path):
    seed_dataset(tmp_path)
    item = list_samples(str(tmp_path))['items'][0]
    targets = [{'class': 'whole_rest', 'bboxXyxy': [80, 40, 120, 55], 'dots': 0}]
    saved = update_sample(str(tmp_path), item['sampleId'], {
        'revision': item['revision'], 'state': 'accepted', 'targets': targets, 'reason': '',
    })
    assert saved['state'] == 'accepted'
    with pytest.raises(ValueError, match='已被其他页面修改'):
        update_sample(str(tmp_path), item['sampleId'], {
            'revision': item['revision'], 'state': 'rejected', 'targets': [], 'reason': '',
        })
    with pytest.raises(ValueError, match='人工修正'):
        update_sample(str(tmp_path), item['sampleId'], {
            'revision': saved['revision'], 'state': 'accepted',
            'targets': [{'class': 'half_rest', 'bboxXyxy': [80, 40, 120, 55], 'dots': 0}],
            'reason': '',
        })


def test_corrected_box_is_bounded_and_skipped_needs_reason(tmp_path):
    seed_dataset(tmp_path)
    item = list_samples(str(tmp_path))['items'][0]
    with pytest.raises(ValueError, match='超出图片'):
        update_sample(str(tmp_path), item['sampleId'], {
            'revision': item['revision'], 'state': 'corrected',
            'targets': [{'class': 'quarter_rest', 'bboxXyxy': [-1, 2, 20, 30], 'dots': 0}],
            'reason': '',
        })
    with pytest.raises(ValueError, match='填写原因'):
        update_sample(str(tmp_path), item['sampleId'], {
            'revision': item['revision'], 'state': 'skipped', 'targets': [], 'reason': '',
        })


def test_coco_export_contains_only_reviewed_images_and_no_pdf(tmp_path):
    seed_dataset(tmp_path)
    item = list_samples(str(tmp_path))['items'][0]
    update_sample(str(tmp_path), item['sampleId'], {
        'revision': item['revision'], 'state': 'rejected', 'targets': [], 'reason': 'hard negative',
    })
    archive = build_training_archive(str(tmp_path))
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            assert not any(name.lower().endswith('.pdf') for name in names)
            assert 'dataset-manifest.json' in names
            split_file = next(name for name in names if name.startswith('annotations/') and
                              json.loads(bundle.read(name))['images'])
            payload = json.loads(bundle.read(split_file))
            assert len(payload['images']) == 1 and payload['annotations'] == []
            assert payload['images'][0]['document_sha256'] == '1' * 64
    finally:
        os.unlink(archive)


def test_image_path_cannot_escape_dataset(tmp_path):
    seed_dataset(tmp_path)
    outside = tmp_path.parent / 'outside.png'
    outside.write_bytes(b'private')
    record = json.loads((tmp_path / 'queue.jsonl').read_text())
    record['image'] = '../outside.png'
    (tmp_path / 'queue.jsonl').write_text(json.dumps(record) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='不存在'):
        sample_image_path(str(tmp_path), record['sampleId'])
