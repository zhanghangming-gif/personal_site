import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))

from score_rest_model import (  # noqa: E402
    merge_rest_model_evidence, run_rest_model, staff_geometry_consistency,
    visual_duration_matches, visual_rest_sequence,
)


def test_visual_duration_matching_respects_full_measure_and_written_value():
    assert visual_duration_matches('quarter_rest', {'gapDuration': '1'})
    assert not visual_duration_matches('half_rest', {'gapDuration': '1'})
    assert visual_duration_matches('whole_rest', {
        'gapDuration': '3', 'expectedMeasureDuration': '3', 'position': 'full_measure',
    })
    assert visual_duration_matches('quarter_rest', {'gapDuration': '3/2'}, dots=1)
    assert not visual_duration_matches('multi_measure_rest', {'gapDuration': '4'})


def test_staff_geometry_distinguishes_whole_and_half_rest_positions():
    geometry = {'lineYs': [10, 20, 30, 40, 50], 'spacing': 10}
    assert staff_geometry_consistency(
        {'class': 'whole_rest', 'bboxPdf': [1, 20, 9, 25]}, {'staffGeometry': geometry})
    assert staff_geometry_consistency(
        {'class': 'half_rest', 'bboxPdf': [1, 25, 9, 30]}, {'staffGeometry': geometry})
    assert not staff_geometry_consistency(
        {'class': 'half_rest', 'bboxPdf': [1, 15, 9, 20]}, {'staffGeometry': geometry})


def test_visual_sequence_can_fill_one_beat_with_two_eighth_rests():
    detections = [
        {'class': 'eighth_rest', 'score': 0.94, 'bboxPdf': [1, 1, 3, 5]},
        {'class': 'eighth_rest', 'score': 0.93, 'bboxPdf': [5, 1, 7, 5]},
        {'class': 'quarter_rest', 'score': 0.40, 'bboxPdf': [1, 1, 7, 5]},
    ]
    sequence = visual_rest_sequence(detections, {'gapDuration': '1'})
    assert [item['class'] for item in sequence] == ['eighth_rest', 'eighth_rest']


def test_merge_prefers_reviewable_sequence_over_noise_matching_gap_duration():
    report = {'engine': 'omr', 'classifications': [{
        'gapId': 'sequence', 'status': 'visual_confirmation_required',
        'suggestedNotation': None, 'autoRepairAllowed': False,
    }], 'summary': {}}
    model = {'engine': 'pytorch_fasterrcnn_cpu', 'modelVersion': 'v2',
             'processedGapCount': 1, 'results': [{
                 'gapId': 'sequence', 'gapDuration': '1', 'detections': [
                     {'class': 'eighth_rest', 'score': 0.69,
                      'bboxPdf': [1, 1, 3, 5]},
                     {'class': 'eighth_rest', 'score': 0.58,
                      'bboxPdf': [5, 1, 7, 5]},
                     {'class': 'quarter_rest', 'score': 0.06,
                      'bboxPdf': [5, 1, 7, 5]},
                 ],
             }]}
    merged = merge_rest_model_evidence(report, model)
    item = merged['classifications'][0]
    assert item['status'] == 'visual_rest_sequence_candidate'
    assert item['suggestedNotationSequence'] == ['eighth_rest', 'eighth_rest']
    assert item['visualModel']['durationMatchedDetections'] == 1
    assert item['visualModel']['reviewableDurationMatchedDetections'] == 0


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


def test_merge_uses_omr_dot_evidence_to_confirm_visual_shape():
    report = {'engine': 'omr', 'classifications': [{
        'gapId': 'dotted', 'status': 'weak_omr_candidate',
        'suggestedNotation': 'quarter_rest', 'suggestedDots': 1,
        'autoRepairAllowed': False,
    }], 'summary': {}}
    model = {'engine': 'pytorch_fasterrcnn_cpu', 'modelVersion': 'v2',
             'processedGapCount': 1, 'results': [{
                 'gapId': 'dotted', 'gapDuration': '3/2', 'detections': [
                     {'class': 'quarter_rest', 'score': 0.96, 'bboxPdf': [1, 2, 3, 4]}],
             }]}
    merged = merge_rest_model_evidence(report, model)
    assert merged['classifications'][0]['status'] == 'supported_by_omr_and_visual_model'
    assert merged['classifications'][0]['selectedVisualEvidence']['durationDotsUsed'] == 1


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
        'reviewRegion': {'page': 1, 'bbox': [10, 20, 30, 40],
                         'staffGeometry': {'lineYs': [21, 22, 23, 24, 25], 'spacing': 1}},
    }]}
    result = run_rest_model(str(job), str(pdf), rhythm, environ={
        'REST_MODEL_PYTHON': sys.executable,
        'REST_MODEL_WORKER': str(worker),
        'REST_MODEL_CHECKPOINT': str(checkpoint),
    })
    assert result['engine'] == 'fake' and result['processedGapCount'] == 1
    request = json.loads((job / 'review' / 'rest-model-request.json').read_text(encoding='utf-8'))
    assert request['gaps'][0]['bboxPdf'] == [10, 20, 30, 40]
    assert request['gaps'][0]['staffGeometry']['spacing'] == 1
    assert request['adaptiveDpi'] == 700
    assert request['threads'] == 1


def test_worker_bridge_persists_unavailable_audit(tmp_path):
    job = tmp_path / 'job'
    result = run_rest_model(str(job), str(tmp_path / 'missing.pdf'), {'gaps': []})
    saved = json.loads((job / 'review' / 'rest-model.json').read_text(encoding='utf-8'))
    assert result == saved
    assert saved['engine'] == 'unavailable'
    assert saved['reason'] == 'no_mapped_rhythm_gaps'
