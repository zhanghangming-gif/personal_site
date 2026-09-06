import shutil
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "score_pipeline"

CASES = [
    ("nabucco1", -1, 329, 947, 3),
    ("complex", 1, 251, 980, 2),
    ("clarinet2", 1, 329, 702, 2),
    ("wanquanhe", 1, 68, 197, 1),
]


@pytest.mark.parametrize("name,semitones,measures,notes,pages", CASES)
def test_pitch_regressions_still_require_verified_original_layout(api, tmpdir, name, semitones, measures, notes, pages):
    tmp_path = Path(str(tmpdir))
    source = FIXTURE_DIR / f"{name}-source.musicxml"
    transposed = FIXTURE_DIR / f"{name}-transposed.musicxml"
    output = FIXTURE_DIR / f"{name}-output.pdf"
    assert source.exists() and transposed.exists() and output.exists()

    repair_report = {
        "valid": True,
        "fatal": False,
        "repairApplied": True,
        "repairValidationStatus": "PASSED",
    }
    verification = api.verify_score_transposition(
        str(source),
        str(transposed),
        semitones,
        pages,
        pages,
        omr_analysis={
            "exportErrors": [],
            "multirestMissing": [],
            "ocrIssue": False,
            "bookIssue": "",
            "recognizedLineNumbers": [],
            "multirestRepair": repair_report,
        },
        original_musicxml=str(source),
        repair_report=repair_report,
    )
    pipeline = api.build_pipeline_status(verification, repair_report)

    assert verification["status"] == "failed"
    checks = {check["id"]: check["passed"] for check in verification["checks"]}
    assert checks["pitch_shift"] and checks["measure_count"] and checks["measure_timeline"]
    assert checks["system_layout"] is False
    assert verification["repair_validation_status"] == "PASSED"
    assert verification["source_integrity_status"] == "PARTIALLY_VALIDATED"
    assert verification["transpose_consistency_status"] == "PASSED"
    assert verification["source"]["measures"] == measures
    assert verification["output"]["measures"] == measures
    assert verification["source"]["noteEvents"] == notes
    assert verification["output"]["noteEvents"] == notes
    assert pipeline.stage == "final_validation"
    assert pipeline.fatal is False
    assert pipeline.overall_status == api.PIPELINE_NEEDS_REVIEW
    assert pipeline.output_allowed is False
    assert api.get_pdf_page_count(str(output)) == pages

    job_dir = tmp_path / name
    job_dir.mkdir()
    shutil.copyfile(output, job_dir / "output.pdf")
    api.write_pipeline_report(str(job_dir), pipeline, verification=verification)
    assert api.score_output_authorization(str(job_dir))[0] is False
