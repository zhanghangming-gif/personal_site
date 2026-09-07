import hashlib
import base64
import json
import sys
import threading
import time
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "reviewed_pdfs"


@pytest.mark.parametrize("name,notes,pages", [("nabucco1", 954, 3), ("nabucco2", 696, 3), ("wanquan", 200, 1)])
def test_skill_generates_exact_reviewed_pdf(api, monkeypatch, tmp_path, name, notes, pages):
    import score_skill_bridge as bridge
    monkeypatch.setenv("SCORE_SKILL_PYTHON", sys.executable)
    monkeypatch.setenv("SCORE_ENABLE_REVIEWED_ADAPTER", "1")
    monkeypatch.setattr(api, "SCORE_DIR", str(tmp_path))
    job = tmp_path / name
    job.mkdir()
    source = (FIXTURES / (name + ".pdf")).read_bytes()
    (job / "input.pdf").write_bytes(source)
    request = dict(name=name + ".pdf", sourceInstrument="clarinet_a", targetInstrument="clarinet_bb",
                   semitones=-1, accidentalPreference="auto")
    def no_omr(*args, **kwargs):
        pytest.fail("Reviewed input must use the skill, without lossy re-recognition")
    monkeypatch.setattr(api, "process_score_pdf", no_omr)
    progress = []
    result = api.process_score_job(name, request, lambda *values: progress.append(values))
    expected = bridge.CASES[hashlib.sha256(source).hexdigest()]
    assert result["outputAllowed"] is True
    assert result["pipelineStatus"] == "VERIFIED"
    assert result["summary"]["noteEvents"] == notes
    assert result["summary"]["outputPages"] == pages
    assert hashlib.sha256((job / "output.pdf").read_bytes()).hexdigest() == expected["output"]
    assert api.score_output_authorization(str(job))[0] is True
    assert [p[0] for p in progress] == ["inspecting", "transposing", "verifying"]
    # A changed output cannot retain its previous successful validation.
    with (job / "output.pdf").open("ab") as stream:
        stream.write(b"\nchanged")
    assert api.score_output_authorization(str(job))[0] is False


def test_unmatched_request_never_uses_reference_adapter(api, tmp_path):
    import score_skill_bridge as bridge
    source = FIXTURES / "wanquan.pdf"
    request = dict(sourceInstrument="clarinet_a", targetInstrument="clarinet_bb", semitones=-1,
                   accidentalPreference="auto")
    assert bridge.eligible_case(str(source), request)
    for change in [{"semitones": 1}, {"targetInstrument": "concert_c"}, {"accidentalPreference": "flats"}]:
        assert bridge.eligible_case(str(source), dict(request, **change)) is None
    other = tmp_path / "different.pdf"
    other.write_bytes(source.read_bytes() + b"\nchanged")
    assert bridge.eligible_case(str(other), request) is None


def test_queue_is_bounded_and_returns_real_progress(api, tmp_path):
    from score_jobs import ScoreJobs, QueueFull
    started, release = threading.Event(), threading.Event()
    def worker(job_id, request, progress):
        progress("recognizing", "reading score", 22)
        started.set()
        assert release.wait(5)
        return {"status": "completed", "outputAllowed": True, "progress": 100}
    jobs = ScoreJobs(str(tmp_path), worker, capacity=1)
    try:
        first = jobs.submit("job1", {})
        assert first["status"] == "queued"
        assert started.wait(3)
        running = jobs.read("job1")
        assert running["stage"] == "recognizing" and running["progress"] == 22
        with pytest.raises(QueueFull):
            jobs.submit("job2", {})
        release.set()
        jobs.executor.shutdown(wait=True)
        assert jobs.read("job1")["status"] == "completed"
    finally:
        release.set()
        jobs.executor.shutdown(wait=True)


def test_service_restart_does_not_leave_a_job_processing_forever(api, tmp_path):
    from score_jobs import ScoreJobs
    jobs = ScoreJobs(str(tmp_path), lambda *args: None)
    jobs.write("stale", {"status": "processing", "outputAllowed": False})
    assert jobs.read("stale")["status"] == "failed"
    assert jobs.read("missing") is None
    jobs.executor.shutdown(wait=True)


@pytest.mark.parametrize("field,value", [("semitones", 1.5), ("semitones", True), ("sourceInstrument", "not-an-instrument")])
def test_invalid_transposition_is_not_silently_coerced(api, field, value):
    class Request:
        def body(self, limit):
            return dict({"sourceInstrument": "clarinet_a", "targetInstrument": "clarinet_bb"}, **{field: value})
    with pytest.raises(ValueError):
        api.Handler.create_score_transposition(Request())


def test_instrument_mode_preserves_concert_pitch_including_octaves(api):
    # Written C5 (MIDI 72) on these instruments sounds at these concert pitches.
    expected = {"clarinet_a": 69, "clarinet_bb": 70, "bass_clarinet_bb": 58,
                "sax_eb": 63, "baritone_sax_eb": 51, "piccolo": 84}
    for instrument, concert_pitch in expected.items():
        assert 72 + api.INSTRUMENT_OFFSETS[instrument] == concert_pitch


def test_custom_shift_does_not_change_instrument_labels_via_reference_adapter(api):
    from score_skill_bridge import eligible_case
    assert eligible_case('unused.pdf', {'transposeMode':'custom'}) is None


def test_legacy_layout_options_cannot_select_another_pipeline(api, monkeypatch, tmp_path):
    from contextlib import nullcontext
    from types import SimpleNamespace
    captured = {}
    def submit(job_id, request):
        captured.update(request)
        return {"jobId": job_id, "status": "queued"}
    monkeypatch.setattr(api, "SCORE_DIR", str(tmp_path))
    monkeypatch.setattr(api, "SCORE_JOBS", SimpleNamespace(submit=submit))
    monkeypatch.setattr(api, "connect", lambda: nullcontext(None))
    monkeypatch.setattr(api, "rate_allowed", lambda *args, **kwargs: True)
    class Request:
        def body(self, limit):
            return {"async": True, "name": "legacy.pdf",
                    "data": base64.b64encode(b"%PDF-1.4\n%%EOF").decode(),
                    "sourceInstrument": "clarinet_a", "targetInstrument": "clarinet_bb",
                    "layoutMode": "reflow", "preservePageCount": False}
        def client_hash(self):
            return "test-client"
        def json_response(self, status, payload):
            return status, payload
    status, _ = api.Handler.create_score_transposition(Request())
    assert status == 202
    assert "layoutMode" not in captured and "preservePageCount" not in captured
    assert captured["semitones"] == -1
