"""Run and merge optional local visual-model evidence (Python 3.6 compatible)."""
from __future__ import division

import json
import os
import subprocess
from fractions import Fraction


CLASS_DURATIONS = {
    "maxima_rest": Fraction(32), "long_rest": Fraction(16),
    "breve_rest": Fraction(8), "whole_rest": Fraction(4),
    "half_rest": Fraction(2), "quarter_rest": Fraction(1),
    "eighth_rest": Fraction(1, 2), "16th_rest": Fraction(1, 4),
    "32nd_rest": Fraction(1, 8), "64th_rest": Fraction(1, 16),
    "128th_rest": Fraction(1, 32),
}


def _fraction(value):
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def visual_duration_matches(class_name, result):
    missing = _fraction(result.get("gapDuration"))
    expected = _fraction(result.get("expectedMeasureDuration"))
    if class_name == "whole_rest" and result.get("position") == "full_measure":
        return missing is not None and expected is not None and missing == expected
    if class_name == "multi_measure_rest":
        return False
    return missing is not None and CLASS_DURATIONS.get(class_name) == missing


def run_rest_model(job_dir, source_pdf, rhythm_report, environ=None, timeout=240):
    environ = environ or os.environ
    python_path = environ.get("REST_MODEL_PYTHON", "")
    worker_path = environ.get("REST_MODEL_WORKER", "")
    checkpoint_path = environ.get("REST_MODEL_CHECKPOINT", "")
    gaps = []
    for gap in rhythm_report.get("gaps", []):
        region = gap.get("reviewRegion") or {}
        location = gap.get("location") or {}
        if isinstance(region.get("bbox"), list) and len(region["bbox"]) == 4:
            gaps.append({
                "gapId": gap.get("id"), "page": region.get("page") or location.get("page"),
                "bboxPdf": region["bbox"], "gapDuration": gap.get("duration"),
                "position": gap.get("position"),
                "expectedMeasureDuration": gap.get("expectedMeasureDuration"),
            })
    review_dir = os.path.join(job_dir, "review")
    if not os.path.isdir(review_dir):
        os.makedirs(review_dir)
    response_path = os.path.join(review_dir, "rest-model.json")

    def unavailable_report(reason, detail=None):
        report = {
            "schemaVersion": 1, "engine": "unavailable", "results": [],
            "processedGapCount": 0, "reason": reason,
        }
        if detail:
            report["detail"] = detail
        with open(response_path, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        return report

    if not gaps:
        return unavailable_report("no_mapped_rhythm_gaps")
    if not all(os.path.isfile(path) for path in
               (python_path, worker_path, checkpoint_path, source_pdf)):
        return unavailable_report("visual_model_not_configured")
    crop_dir = os.path.join(review_dir, "rest-model-crops")
    request_path = os.path.join(review_dir, "rest-model-request.json")
    request = {
        "schemaVersion": 1, "pdfPath": source_pdf, "checkpoint": checkpoint_path,
        "cropOutputDir": crop_dir, "dpi": 400, "scoreThreshold": 0.05,
        "threads": 1, "gaps": gaps,
    }
    with open(request_path, "w", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False, indent=2)
    try:
        completed = subprocess.run(
            [python_path, worker_path, request_path, response_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
            universal_newlines=True)
        if completed.returncode != 0 or not os.path.isfile(response_path):
            return unavailable_report(
                "visual_model_failed", (completed.stdout or "")[-500:])
        with open(response_path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return unavailable_report("visual_model_failed", str(exc)[-500:])


def merge_rest_model_evidence(classification_report, model_report, support_threshold=0.85):
    by_gap = {item.get("gapId"): item for item in model_report.get("results", [])}
    visual_supported = 0
    visual_conflicts = 0
    for item in classification_report.get("classifications", []):
        result = by_gap.get(item.get("gapId"))
        if not result:
            continue
        detections = result.get("detections", [])
        exact = [value for value in detections
                 if visual_duration_matches(value.get("class"), result)]
        selected = max(exact, key=lambda value: value.get("score", 0)) if exact else None
        existing = item.get("suggestedNotation")
        visual = {
            "modelVersion": model_report.get("modelVersion"),
            "modelSha256": model_report.get("modelSha256"),
            "crop": result.get("crop"), "detections": detections[:12],
            "durationMatchedDetections": len(exact), "selectedEvidence": selected,
            "supportThreshold": support_threshold,
        }
        item["visualModel"] = visual
        if selected and selected.get("score", 0) >= support_threshold:
            if existing and existing != selected.get("class"):
                item["status"] = "conflicting_visual_evidence"
                visual_conflicts += 1
            else:
                item["status"] = ("supported_by_omr_and_visual_model" if existing
                                  else "supported_by_visual_model")
                item["suggestedNotation"] = selected.get("class")
                item["selectedVisualEvidence"] = selected
                visual_supported += 1
        item["autoRepairAllowed"] = False
    counts = {status: sum(item.get("status") == status for item in
                          classification_report.get("classifications", []))
              for status in sorted(set(item.get("status") for item in
                                     classification_report.get("classifications", [])))}
    summary = classification_report.setdefault("summary", {})
    summary["statusCounts"] = counts
    summary["visualProcessedCount"] = model_report.get("processedGapCount", 0)
    summary["visualSupportedCount"] = visual_supported
    summary["visualConflictCount"] = visual_conflicts
    summary["visualModelAvailable"] = model_report.get("engine") != "unavailable"
    summary["supportedCount"] = sum(counts.get(name, 0) for name in (
        "supported_by_omr_object", "supported_by_visual_model",
        "supported_by_omr_and_visual_model"))
    classification_report["visualModel"] = {
        "engine": model_report.get("engine"), "modelVersion": model_report.get("modelVersion"),
        "modelSha256": model_report.get("modelSha256"),
        "processedGapCount": model_report.get("processedGapCount", 0),
        "elapsedSeconds": model_report.get("elapsedSeconds"),
        "reason": model_report.get("reason"), "artifact": "review/rest-model.json",
    }
    classification_report["engine"] = "%s+%s" % (
        classification_report.get("engine", "omr"), model_report.get("engine", "unavailable"))
    classification_report["limits"] = (
        "视觉模型是局部候选证据；必须同时满足节奏时值和位置约束，当前版本不自动写入休止符")
    return classification_report
