import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))

from score_rest_model import (  # noqa: E402
    merge_rest_model_evidence, run_rest_model, visual_duration_matches,
)


def test_visual_duration_matching_respects_full_measure_and_written_value():
    assert visual_duration_matches('quarter_rest', {'gapDuration': '1'})
    assert not visual_duration_matches('half_rest', {'gapDuration': '1'})
    assert visual_duration_matches('whole_rest', {
        'gapDuration': '3', 'expectedMeasureDuration': '3', 'position': 'full_measure',
    })
    assert not visual_duration_matches('multi_measure_rest', {'gapDuration': '4'})


def test_merge_supports_agreement_and_blocks_class_conflict():
    report = {'engine': 'omr', 'classifications': [
        {'gapId': 'one', 'status': 'visual_confirmation_required',
         'suggestedNotation': None, 'autoRepairAllowed': False},
        {'gapId': 'two', 'status': 'supported_by_omr_object',
         'suggestedNotation': 'half_rest', 'autoRepairAllowed': False},
    ], 'summary': {}}
    model = {'engine': 'pytorch_fasterrcnn_cpu', 'modelVersion': 'v2',
             'modelSha256': 'a' * 64, 'processedGapCount': 2, 'results': [
                 {'gapId': 'one', 'gapDuration': '1', 'detections': [
                     {'class': 'quarter_rest', 'score': 0.96, 'bboxPdf': [1, 2, 3, 4]}]},
                 {'gapId': 'two', 'gapDuration': '1', 'detections': [
                     {'class': 'quarter_rest', 'score': 0.97, 'bboxPdf': [5, 6, 7, 8]}]},
             ]}
    merged = merge_rest_model_evidence(report, model)
    assert merged['classifications'][0]['status'] == 'supported_by_visual_model'
    assert merged['classifications'][0]['suggestedNotation'] == 'quarter_rest'
    assert merged['classifications'][1]['status'] == 'conflicting_visual_evidence'
    assert merged['classifications'][1]['suggestedNotation'] == 'half_rest'
    assert not any(item['autoRepairAllowed'] for item in merged['classifications'])
    assert merged['summary']['visualSupportedCount'] == 1
    assert merged['summary']['visualConflictCount'] == 1


def test_worker_bridge_uses_files_and_returns_json(tmp_path):
    job = tmp_path / 'job'
    pdf = tmp_path / 'input.pdf'
    checkpoint = tmp_path / 'model.pt'
    worker = tmp_path / 'fake_worker.py'
    pdf.write_bytes(b'%PDF fake')
    checkpoint.write_bytes(b'model')
    worker.write_text(
        'import json,sys\n'
        'request=json.load(open(sys.argv[1], encoding="utf-8"))\n'
        'result={"engine":"fake","modelVersion":"test","processedGapCount":len(request["gaps"]),"results":[]}\n'
        'json.dump(result,open(sys.argv[2],"w",encoding="utf-8"))\n', encoding='utf-8')
    rhythm = {'gaps': [{
        'id': 'g1', 'duration': '1', 'position': 'trailing',
        'expectedMeasureDuration': '4', 'location': {'page': 1},
        'reviewRegion': {'page': 1, 'bbox': [10, 20, 30, 40]},
    }]}
    result = run_rest_model(str(job), str(pdf), rhythm, environ={
        'REST_MODEL_PYTHON': sys.executable,
        'REST_MODEL_WORKER': str(worker),
        'REST_MODEL_CHECKPOINT': str(checkpoint),
    })
    assert result['engine'] == 'fake' and result['processedGapCount'] == 1
    request = json.loads((job / 'review' / 'rest-model-request.json').read_text(encoding='utf-8'))
    assert request['gaps'][0]['bboxPdf'] == [10, 20, 30, 40]
    assert request['threads'] == 1


def test_worker_bridge_persists_unavailable_audit(tmp_path):
    job = tmp_path / 'job'
    result = run_rest_model(str(job), str(tmp_path / 'missing.pdf'), {'gaps': []})
    saved = json.loads((job / 'review' / 'rest-model.json').read_text(encoding='utf-8'))
    assert result == saved
    assert saved['engine'] == 'unavailable'
    assert saved['reason'] == 'no_mapped_rhythm_gaps'
