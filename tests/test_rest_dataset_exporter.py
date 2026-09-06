import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pymupdf as fitz
from PIL import Image


def exporter_module():
    path = Path(__file__).resolve().parents[1] / 'ml' / 'rest_detector' / 'export_review_queue.py'
    spec = importlib.util.spec_from_file_location('rest_dataset_exporter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_omr_candidate_sampling_is_bounded_and_provenance_safe(tmp_path):
    exporter = exporter_module()
    job = tmp_path / 'public-score'
    (job / 'omr').mkdir(parents=True)
    pdf = fitz.open(); pdf.new_page(width=300, height=200); pdf.save(str(job / 'input.pdf')); pdf.close()
    image = Image.new('1', (600, 400), 1)
    binary = io.BytesIO(); image.save(binary, format='PNG')
    xml = '''<sheet><rest shape="QUARTER_REST" id="1" grade="0.8"><bounds x="90" y="100" w="18" h="42"/></rest>
      <rest shape="QUARTER_REST" id="2" grade="0.7"><bounds x="190" y="100" w="18" h="42"/></rest>
      <rest shape="HALF_REST" id="3" grade="0.9"><bounds x="290" y="100" w="24" h="10"/></rest></sheet>'''
    with zipfile.ZipFile(str(job / 'omr' / 'input.omr'), 'w') as archive:
        archive.writestr('sheet#1/BINARY.png', binary.getvalue())
        archive.writestr('sheet#1/sheet#1.xml', xml)
    images = tmp_path / 'dataset' / 'images'; images.mkdir(parents=True)
    records = exporter.export_job(job, images, 800, {}, include_all_omr=True,
                                  maximum_omr_per_class=1)
    assert len(records) == 2
    assert {item['prelabel']['class'] for item in records} == {'quarter_rest', 'half_rest'}
    assert all(item['position'] == 'omr_candidate' for item in records)
    assert all(item['sourcePdfStored'] is False for item in records)
    assert all(Path(images / Path(item['image']).name).is_file() for item in records)


def test_existing_human_annotation_survives_candidate_refresh(tmp_path):
    exporter = exporter_module()
    sample = {'sampleId': 'abc', 'state': 'corrected',
              'annotation': {'targets': [{'class': 'quarter_rest', 'bboxXyxy': [1, 2, 3, 4], 'dots': 0}]},
              'annotator': 'site-admin', 'reviewedAt': '2026-09-06T00:00:00Z'}
    queue = tmp_path / 'queue.jsonl'
    queue.write_text(json.dumps(sample) + '\n', encoding='utf-8')
    loaded = exporter.existing_records(queue)
    assert loaded['abc']['state'] == 'corrected'
    assert loaded['abc']['annotation'] == sample['annotation']
