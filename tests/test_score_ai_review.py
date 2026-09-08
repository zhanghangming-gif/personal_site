import importlib.util
import json
import sys
from pathlib import Path


def worker():
    path = Path(__file__).resolve().parents[1] / 'server' / 'score_ai_review_worker.py'
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('score_ai_review_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_risky_locations_prioritize_structured_gaps_and_deduplicate(tmp_path):
    report = {'verification': {
        'omr': {'multirestRepair': {'unresolvedGaps': [
            {'page': 2, 'system': 3, 'reason': 'gap'}]}},
        'issues': [
            {'phase': 'render', 'message': 'same', 'location': {'page': 2, 'system': 3}},
            {'phase': 'source', 'code': 'missing_rhythm_duration', 'message': 'next',
             'location': {'page': 2, 'system': 4},
             'pdfRegion': {'bbox': [10, 20, 30, 40]}},
        ],
    }}
    (tmp_path / 'pipeline-report.json').write_text(json.dumps(report), encoding='utf-8')
    rows = worker().risky_locations(tmp_path)
    assert [(row['page'], row['system']) for row in rows] == [(2, 3), (2, 4)]
    assert rows[0]['kind'] == 'structure_gap'
    assert rows[1]['kind'] == 'source_rhythm_gap'
    assert rows[1]['sourceBboxHint'] == [10, 20, 30, 40]


def test_visual_reviewer_has_no_authority_to_approve_output():
    assert '不能批准候选 PDF' in worker().SYSTEM or '不声明整份乐谱正确' in worker().SYSTEM


def test_visual_reviewer_accepts_fenced_json_but_rejects_empty_output():
    module = worker()
    value = module.parse_model_json('```json\n{"summary":"ok","regions":[]}\n```')
    assert value['summary'] == 'ok'
    try:
        module.parse_model_json('')
        assert False, 'empty output must fail'
    except ValueError:
        pass
