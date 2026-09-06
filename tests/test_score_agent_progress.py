import importlib.util
from pathlib import Path


def worker_module():
    path = Path(__file__).resolve().parents[1] / 'server' / 'score_agent_worker.py'
    spec = importlib.util.spec_from_file_location('score_agent_progress_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_progress_guard_stops_repeated_noop_turns():
    guard = worker_module().ProgressGuard(stale_limit=3)
    assert guard.observe('a')['state'] == 'progress'
    assert guard.observe('a')['continue'] is True
    assert guard.observe('a')['continue'] is True
    stopped = guard.observe('a')
    assert stopped['continue'] is False
    assert stopped['state'] == 'stale'


def test_progress_guard_detects_artifact_oscillation():
    guard = worker_module().ProgressGuard()
    guard.observe('a')
    guard.observe('b')
    stopped = guard.observe('a')
    assert stopped['continue'] is False
    assert stopped['state'] == 'oscillation'


def test_work_fingerprint_changes_only_with_artifact_content(tmp_path):
    module = worker_module()
    first = module.work_fingerprint(tmp_path)
    (tmp_path / 'candidate.pdf').write_bytes(b'one')
    second = module.work_fingerprint(tmp_path)
    assert first != second
    (tmp_path / 'ignored.log').write_text('noise')
    assert module.work_fingerprint(tmp_path) == second
