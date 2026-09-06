"""Run and merge optional local visual-model evidence (Python 3.6 compatible)."""
from __future__ import division

import json
import os
import subprocess
from itertools import combinations
from fractions import Fraction


CLASS_DURATIONS = {
    "maxima_rest": Fraction(32), "long_rest": Fraction(16),
    "breve_rest": Fraction(8), "whole_rest": Fraction(4),
    "half_rest": Fraction(2), "quarter_rest": Fraction(1),
    "eighth_rest": Fraction(1, 2), "16th_rest": Fraction(1, 4),
    "32nd_rest": Fraction(1, 8), "64th_rest": Fraction(1, 16),
    "128th_rest": Fraction(1, 32),
}

CLASS_SUPPORT_THRESHOLDS = {
    "quarter_rest": 0.85, "eighth_rest": 0.88, "16th_rest": 0.92,
    "whole_rest": 0.94, "half_rest": 0.94, "breve_rest": 0.96,
    "32nd_rest": 0.96, "64th_rest": 0.97, "128th_rest": 0.98,
    "maxima_rest": 0.98, "long_rest": 0.98,
}

CLASS_REVIEW_THRESHOLDS = {
    "quarter_rest": 0.60, "eighth_rest": 0.55, "16th_rest": 0.65,
    "whole_rest": 0.70, "half_rest": 0.70, "breve_rest": 0.75,
    "32nd_rest": 0.75, "64th_rest": 0.80, "128th_rest": 0.85,
    "maxima_rest": 0.85, "long_rest": 0.85,
}


def _fraction(value):
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def dotted_duration(base, dots):
    result, addition = base, base
    for _ in range(max(0, int(dots or 0))):
        addition /= 2
        result += addition
    return result


def visual_duration_matches(class_name, result, dots=0):
    missing = _fraction(result.get("gapDuration"))
    expected = _fraction(result.get("expectedMeasureDuration"))
    if class_name == "whole_rest" and result.get("position") == "full_measure":
        return missing is not None and expected is not None and missing == expected
    if class_name == "multi_measure_rest":
        return False
    base = CLASS_DURATIONS.get(class_name)
    return missing is not None and base is not None and dotted_duration(base, dots) == missing


def box_iou(one, two):
    if not one or not two:
        return 0.0
    left, top = max(one[0], two[0]), max(one[1], two[1])
    right, bottom = min(one[2], two[2]), min(one[3], two[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_one = max(0.0, one[2] - one[0]) * max(0.0, one[3] - one[1])
    area_two = max(0.0, two[2] - two[0]) * max(0.0, two[3] - two[1])
    union = area_one + area_two - intersection
    return intersection / union if union > 0 else 0.0


def staff_geometry_consistency(detection, result):
    """Check the engraving position that distinguishes whole and half rests."""
    class_name = detection.get("class")
    if class_name not in ("whole_rest", "half_rest"):
        return None
    geometry = result.get("staffGeometry") or {}
    lines, box = geometry.get("lineYs"), detection.get("bboxPdf")
    spacing = _fraction(geometry.get("spacing"))
    if not isinstance(lines, list) or len(lines) != 5 or not box or spacing is None:
        return None
    spacing = float(spacing)
    tolerance = max(0.8 * spacing, 1.2)
    try:
        if class_name == "whole_rest":
            return abs(float(box[1]) - float(lines[1])) <= tolerance
        return abs(float(box[3]) - float(lines[2])) <= tolerance
    except (TypeError, ValueError, IndexError):
        return None


def class_support_threshold(class_name, fallback=0.85):
    return CLASS_SUPPORT_THRESHOLDS.get(class_name, fallback)


def class_review_threshold(class_name, fallback=0.65):
    return CLASS_REVIEW_THRESHOLDS.get(class_name, fallback)


def visual_rest_sequence(detections, result):
    """Find a non-overlapping rest sequence whose written values fill the gap."""
    missing = _fraction(result.get("gapDuration"))
    if missing is None:
        return None
    candidates = [value for value in detections
                  if value.get("class") in CLASS_DURATIONS
                  and value.get("score", 0) >= class_review_threshold(value.get("class"))]
    candidates = sorted(candidates, key=lambda value: value.get("score", 0), reverse=True)[:10]
    for size in range(2, min(6, len(candidates)) + 1):
        matches = []
        for values in combinations(candidates, size):
            if any(box_iou(one.get("bboxPdf"), two.get("bboxPdf")) > 0.15
                   for one, two in combinations(values, 2)):
                continue
            if sum((CLASS_DURATIONS[value["class"]] for value in values), Fraction(0)) != missing:
                continue
            ordered = sorted(values, key=lambda value: value.get("bboxPdf", [0])[0])
            matches.append(ordered)
        if matches:
            return max(matches, key=lambda values: min(value.get("score", 0) for value in values))
    return None


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
                "staffGeometry": region.get("staffGeometry"),
                "mappingBasis": region.get("mappingBasis"),
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
        "cropOutputDir": crop_dir, "dpi": 400, "adaptiveDpi": 700,
        "scoreThreshold": 0.05,
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
        existing = item.get("suggestedNotation")
        existing_dots = item.get("suggestedDots", 0) if existing else 0
        exact = []
        for value in detections:
            dots = existing_dots if value.get("class") == existing else 0
            value["durationDotsUsed"] = dots
            value["staffGeometryConsistent"] = staff_geometry_consistency(value, result)
            if (visual_duration_matches(value.get("class"), result, dots)
                    and value["staffGeometryConsistent"] is not False):
                exact.append(value)
        reviewable_exact = [value for value in exact
                            if value.get("score", 0) >=
                            class_review_threshold(value.get("class"))]
        selected = (max(reviewable_exact, key=lambda value: value.get("score", 0))
                    if reviewable_exact else None)
        sequence = visual_rest_sequence(detections, result) if not selected else None
        selected_threshold = (class_support_threshold(selected.get("class"), support_threshold)
                              if selected else None)
        visual = {
            "modelVersion": model_report.get("modelVersion"),
            "modelSha256": model_report.get("modelSha256"),
            "crop": result.get("crop"), "detections": detections[:12],
            "durationMatchedDetections": len(exact),
            "reviewableDurationMatchedDetections": len(reviewable_exact),
            "selectedEvidence": selected,
            "supportThreshold": selected_threshold,
            "sequenceCandidate": sequence,
        }
        item["visualModel"] = visual
        if selected and selected.get("score", 0) >= selected_threshold:
            if existing and existing != selected.get("class"):
                item["status"] = "conflicting_visual_evidence"
                visual_conflicts += 1
            else:
                item["status"] = ("supported_by_omr_and_visual_model" if existing
                                  else "supported_by_visual_model")
                item["suggestedNotation"] = selected.get("class")
                item["selectedVisualEvidence"] = selected
                visual_supported += 1
        elif (selected and selected.get("score", 0) >=
              class_review_threshold(selected.get("class")) and not existing):
            item["status"] = "visual_review_candidate"
            item["suggestedNotation"] = selected.get("class")
            item["selectedVisualEvidence"] = selected
        elif sequence and not existing:
            item["status"] = "visual_rest_sequence_candidate"
            item["suggestedNotationSequence"] = [value.get("class") for value in sequence]
            item["selectedVisualSequence"] = sequence
        elif sequence:
            visual["sequenceConflictsWithOmr"] = True
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
    summary["visualSequenceCandidateCount"] = counts.get("visual_rest_sequence_candidate", 0)
    summary["visualReviewCandidateCount"] = counts.get("visual_review_candidate", 0)
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
