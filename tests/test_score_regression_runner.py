import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import score_regression_runner as runner
import score_benchmark as benchmark


def test_human_readable_verification_summary_does_not_crash_metrics_collection(
        monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "unseen.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")

    def fake_process(_source, workspace, *_args, **_kwargs):
        output = Path(workspace, "output.pdf")
        output.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return str(output), {}, {"summary": "发现待复核项目。"}

    def fake_preserve(workspace, _source, output):
        preserved = Path(workspace, "header-preserved.pdf")
        preserved.write_bytes(Path(output).read_bytes())
        return str(preserved), {"preservedPages": 1}

    def fake_report(_workspace):
        return {
            "pipeline": {
                "overallStatus": "NEEDS_REVIEW",
                "stage": "structure_repair",
            },
            "verification": {
                "summary": "发现待复核项目。",
                "output": {"measures": 180, "noteEvents": 178},
                "rhythmGapDetection": {"gapCount": 3, "overflowCount": 1},
            },
        }

    monkeypatch.setattr(runner, "process_score_pdf", fake_process)
    monkeypatch.setattr(runner, "preflight_pdf", lambda source, _workspace: (source, {}))
    monkeypatch.setattr(runner, "inspect_score_pdf", lambda *_args: {
        "scoreProfile": {"documentType": "vector"},
    })
    monkeypatch.setattr(runner, "inspect_rendered_score_pdf", lambda *_args: {})
    monkeypatch.setattr(runner, "preserve_score_headers", fake_preserve)
    monkeypatch.setattr(runner, "write_pipeline_report", lambda *_args: None)
    monkeypatch.setattr(runner, "read_pipeline_report", fake_report)

    result = runner.run(str(input_dir), str(output_dir))

    row = result["results"][0]
    assert row["status"] == "NEEDS_REVIEW"
    assert row["outputAvailable"] is True
    assert row["reviewMetrics"] == {
        "rhythmGaps": 3,
        "rhythmOverflows": 1,
        "measureCount": 180,
        "noteEvents": 178,
    }
    persisted = json.loads((output_dir / "regression-report.json").read_text("utf-8"))
    assert persisted["counts"] == {"NEEDS_REVIEW": 1}


def test_manifest_is_hash_bound_and_excluded_from_training(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    pdf = source / "score.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schemaVersion": 1,
        "benchmarkId": "blind-v1",
        "trainingPolicy": "exclude_all_cases",
        "cases": [{
            "caseId": "case-01", "source": "score.pdf",
            "sha256": benchmark.file_sha256(str(pdf)),
            "tags": ["scan"], "expectations": {"sourcePages": 1},
        }],
    }), encoding="utf-8")
    loaded, cases = benchmark.load_manifest(str(source), str(manifest))
    assert loaded["trainingPolicy"] == "exclude_all_cases"
    assert cases[0]["caseId"] == "case-01"
    pdf.write_bytes(b"%PDF-1.4\nchanged")
    try:
        benchmark.load_manifest(str(source), str(manifest))
        assert False, "changed benchmark file must be rejected"
    except ValueError as exc:
        assert "摘要不匹配" in str(exc)


def test_evaluation_reports_expectation_failures_and_baseline_regression():
    cases = [{"caseId": "case-01", "expectations": {
        "sourcePages": 2, "outputRequired": True,
        "allowedDocumentTypes": ["vector"], "staticContentRequired": True,
    }}]
    baseline = {"results": [{
        "caseId": "case-01", "status": "NEEDS_REVIEW", "outputAvailable": True,
        "failureCategories": [],
        "reviewMetrics": {"measureCount": 20, "noteEvents": 40,
                          "rhythmGaps": 0, "rhythmOverflows": 0},
    }]}
    aggregate = {"results": [{
        "caseId": "case-01", "status": "CRASHED", "outputAvailable": False,
        "failureCategories": ["pipeline_exception"],
        "sourceMetrics": {"pages": 1, "documentType": "scan"},
        "staticContent": {"status": "skipped"},
        "reviewMetrics": {"measureCount": None, "noteEvents": None,
                          "rhythmGaps": None, "rhythmOverflows": None},
    }]}
    benchmark.attach_evaluation(aggregate, cases, baseline)
    assert aggregate["evaluation"]["passed"] is False
    assert aggregate["evaluation"]["expectationFailures"] == 5
    assert aggregate["evaluation"]["regressionCount"] == 1


def test_runner_can_select_one_manifest_case(tmp_path, monkeypatch):
    cases = [
        {"caseId": "one", "path": str(tmp_path / "one.pdf"), "sha256": "a" * 64,
         "tags": [], "metadata": {}, "expectations": {}, "request": {}},
        {"caseId": "two", "path": str(tmp_path / "two.pdf"), "sha256": "b" * 64,
         "tags": [], "metadata": {}, "expectations": {}, "request": {}},
    ]
    for case in cases:
        Path(case["path"]).write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.setattr(runner, "load_manifest",
                        lambda *_: ({"schemaVersion": 1}, cases))
    monkeypatch.setattr(runner, "preflight_pdf", lambda path, _work: (path, {}))
    monkeypatch.setattr(runner, "inspect_score_pdf", lambda *_: {
        "scoreProfile": {"documentType": "vector"}})

    def process(_source, workspace, *_args, **_kwargs):
        output = Path(workspace, "output.pdf")
        output.write_bytes(b"%PDF-1.4\n%%EOF")
        return str(output), {}, {}

    monkeypatch.setattr(runner, "process_score_pdf", process)
    monkeypatch.setattr(runner, "inspect_rendered_score_pdf", lambda *_: {})
    monkeypatch.setattr(runner, "preserve_score_headers",
                        lambda _w, _s, output: (output, {}))
    monkeypatch.setattr(runner, "read_pipeline_report", lambda *_: {
        "pipeline": {"overallStatus": "NEEDS_REVIEW", "stage": "review"},
        "verification": {},
    })
    monkeypatch.setattr(runner, "write_pipeline_report", lambda *_: None)
    monkeypatch.setattr(runner, "get_pdf_page_count", lambda _: 1)

    result = runner.run(str(tmp_path), str(tmp_path / "out"),
                        manifest_path="fixed.json", case_ids=["two"])
    assert [row["caseId"] for row in result["results"]] == ["two"]
    with pytest.raises(ValueError, match="案例不存在"):
        runner.run(str(tmp_path), str(tmp_path / "other"),
                   manifest_path="fixed.json", case_ids=["missing"])
