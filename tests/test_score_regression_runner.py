import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import score_regression_runner as runner


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
