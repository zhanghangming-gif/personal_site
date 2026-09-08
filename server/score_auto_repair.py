"""Bounded automatic repairs for evidence-backed rhythm gaps.

This module never infers a rest from missing duration alone.  A repair must be
supported by a unique OMR object, a high-confidence visual detection, or both;
the existing editor then enforces MusicXML cursor, meter, staff and voice
constraints before any mutation is made.
"""
from fractions import Fraction

from score_editor import REST_LABELS, REST_TYPES, apply_edits


SUPPORTED = {"supported_by_visual_model", "supported_by_omr_and_visual_model"}

# Conservative production policy.  These are deliberately stricter than the
# detector's review thresholds and remain versioned in every repair report.
# Multi-measure rests stay review-only until their count has independent OCR
# and measure-sequence support.
CLASS_AUTO_THRESHOLDS = {
    "quarter_rest": 0.92, "eighth_rest": 0.94, "16th_rest": 0.96,
    "half_rest": 0.97, "whole_rest": 0.97, "breve_rest": 0.98,
    "32nd_rest": 0.98, "64th_rest": 0.99, "128th_rest": 0.99,
    "maxima_rest": 0.99, "long_rest": 0.99,
}


def rational(value):
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return Fraction(0)


def _center_in(box, region):
    if not isinstance(box, list) or len(box) != 4 or not isinstance(region, list) or len(region) != 4:
        return False
    try:
        center_x = (float(box[0]) + float(box[2])) / 2
        center_y = (float(box[1]) + float(box[3])) / 2
        return (float(region[0]) <= center_x <= float(region[2]) and
                float(region[1]) <= center_y <= float(region[3]))
    except (TypeError, ValueError):
        return False


def _eligible(gap, classification, omr_grade, visual_score):
    if classification.get("status") not in SUPPORTED:
        return False, "independent_visual_evidence_required"
    if classification.get("suggestedNotation") not in REST_TYPES:
        return False, "unsupported_rest_notation"
    if int(classification.get("suggestedDots") or 0):
        return False, "dotted_rest_requires_independent_dot_evidence"
    if gap.get("riskReasons"):
        return False, "rhythm_exception_or_polyphony"
    if gap.get("position") not in ("leading", "internal", "trailing", "full_measure"):
        return False, "unknown_gap_position"

    onset = rational(gap.get("onset"))
    duration = rational(gap.get("duration"))
    expected = rational(gap.get("expectedMeasureDuration"))
    if duration <= 0 or expected <= 0 or onset < 0 or onset + duration > expected:
        return False, "invalid_or_ambiguous_timeline_window"
    region = gap.get("reviewRegion") or {}
    if (not region.get("mappingBasis") or
            not isinstance(region.get("bbox"), list) or len(region["bbox"]) != 4):
        return False, "source_region_mapping_required"

    status = classification.get("status")
    omr = classification.get("selectedEvidence") or {}
    visual = classification.get("selectedVisualEvidence") or {}
    unique_omr = (
        classification.get("exactCandidateCount") == 1
        and classification.get("candidateCount") == 1
        and omr.get("durationMatchesGap") is True
        and omr.get("staffPositionConsistent") is True
        and float(omr.get("grade") or 0) >= omr_grade
        and float(omr.get("contextGrade") or 0) >= omr_grade
    )
    notation = classification.get("suggestedNotation")
    class_threshold = max(float(visual_score or 0), CLASS_AUTO_THRESHOLDS.get(notation, 0.99))
    geometry = visual.get("staffGeometryConsistent")
    geometry_ok = geometry is True if notation in ("whole_rest", "half_rest") else geometry is not False
    strong_visual = (
        visual.get("class") == classification.get("suggestedNotation")
        and geometry_ok
        and _center_in(visual.get("bboxPdf"), region.get("bbox"))
        and float(visual.get("score") or 0) >= class_threshold
    )
    if status == "supported_by_omr_and_visual_model":
        if unique_omr and strong_visual:
            return True, "timeline_omr_visual_geometry_agree"
        return False, "dual_evidence_below_auto_threshold"
    return (True, "timeline_visual_geometry_agree") if strong_visual else (
        False, "visual_evidence_below_auto_threshold")


def apply_safe_rhythm_repairs(root, rhythm_report, classification_report,
                              omr_grade=0.75, visual_score=0.94):
    """Apply only candidates that pass evidence and editor safety gates."""
    gaps = {item.get("id"): item for item in rhythm_report.get("gaps", [])
            if isinstance(item, dict) and item.get("id")}
    classifications = [item for item in classification_report.get("classifications", [])
                       if isinstance(item, dict) and item.get("gapId") in gaps]
    classifications.sort(key=lambda item: (
        int((gaps[item["gapId"]].get("location") or {}).get("part") or 0),
        int((gaps[item["gapId"]].get("location") or {}).get("measureIndex") or 0),
        rational(gaps[item["gapId"]].get("onset")),
    ))
    applied, rejected = [], []
    for item in classifications:
        gap = gaps[item["gapId"]]
        allowed, basis = _eligible(gap, item, omr_grade, visual_score)
        if not allowed:
            rejected.append({"gapId": item["gapId"], "reason": basis})
            continue
        suggestion = {
            "gapId": item["gapId"], "measureId": gap.get("measureId"),
            "location": gap.get("location") or {}, "voice": str(gap.get("voice") or "1"),
            "onset": gap.get("onset"), "duration": gap.get("duration"),
            "position": gap.get("position"), "status": item.get("status"),
            "notation": item.get("suggestedNotation"),
            "dots": int(item.get("suggestedDots") or 0),
            "riskReasons": list(gap.get("riskReasons") or []),
        }
        try:
            changes = apply_edits(
                root, [{"type": "confirmRest", "gapId": item["gapId"]}],
                {item["gapId"]: suggestion},
            )
            label = REST_LABELS.get(item["suggestedNotation"], item["suggestedNotation"])
            for change in changes:
                change["after"] = (
                    "后端依据原谱局部视觉、时值窗口与谱表几何证据，在第 %s 小节声部 %s、起点 %s 补入%s；"
                    "已进入重新排版与复核"
                    % ((gap.get("location") or {}).get("measure", "?"),
                       suggestion["voice"], suggestion["onset"], label)
                )
            applied.append({"gapId": item["gapId"], "basis": basis,
                            "notation": item.get("suggestedNotation"),
                            "changes": changes})
        except ValueError as exc:
            rejected.append({"gapId": item["gapId"],
                             "reason": "musicxml_safety_gate: " + str(exc)})
    return {
        "status": "applied_pending_validation" if applied else "no_safe_candidate",
        "evaluatedCount": len(classifications), "appliedCount": len(applied),
        "applied": applied, "rejected": rejected,
        "policyVersion": "source-rest-and-gate-v2",
        "thresholds": {"omrGrade": omr_grade, "visualFloor": visual_score,
                       "perClassVisual": CLASS_AUTO_THRESHOLDS},
        "limits": "A rhythm gap, exact time window, mapped PDF region, compatible local visual detection, staff geometry and risk-free voice context are all required; OMR confidence alone never authorizes a patch.",
    }


def _source_semantics(index):
    measures, pitched, marks, rest_count = [], [], [], 0
    for part in index.get("parts", []):
        for measure in part.get("measures", []):
            location = measure.get("location") or {}
            measures.append((location.get("part"), location.get("measure")))
            marks.append(measure.get("marks") or [])
            for event in measure.get("events", []):
                if event.get("kind") == "rest":
                    rest_count += 1
                elif event.get("pitch") is not None:
                    pitched.append((
                        location.get("part"), location.get("measure"), event.get("onset"),
                        event.get("duration"), event.get("voice"), event.get("staff"),
                        event.get("pitch"), event.get("grace"), event.get("ties"),
                    ))
    return measures, pitched, marks, rest_count


def validate_source_repair_result(before_gaps, after_gaps, applied, before_ir, after_ir):
    """Prove a source patch only filled the promised gaps before transposition."""
    applied_ids = {item.get("gapId") for item in applied if item.get("gapId")}
    remaining_ids = {item.get("id") for item in after_gaps.get("gaps", [])}
    before_semantics = _source_semantics(before_ir)
    after_semantics = _source_semantics(after_ir)
    checks = {
        "appliedGapsRemoved": not (applied_ids & remaining_ids),
        "gapCountReduced": len(after_gaps.get("gaps", [])) <=
                           len(before_gaps.get("gaps", [])) - len(applied_ids),
        "overflowNotIncreased": len(after_gaps.get("overflows", [])) <=
                                len(before_gaps.get("overflows", [])),
        "measureSequencePreserved": before_semantics[0] == after_semantics[0],
        "pitchedEventsPreserved": before_semantics[1] == after_semantics[1],
        "marksPreserved": before_semantics[2] == after_semantics[2],
        "onlyExpectedRestsAdded": after_semantics[3] == before_semantics[3] + len(applied_ids),
    }
    accepted = bool(applied_ids) and all(checks.values())
    return accepted, {
        "accepted": accepted, "phase": "source_reconstruction",
        "reason": ("源谱修复只补入了 %s 个有视觉证据的休止符，其他音乐语义保持不变" % len(applied_ids)
                   if accepted else "源谱修复未通过语义隔离检查，未进入转调阶段"),
        "checks": checks,
        "beforeGapCount": len(before_gaps.get("gaps", [])),
        "afterGapCount": len(after_gaps.get("gaps", [])),
        "beforeOverflowCount": len(before_gaps.get("overflows", [])),
        "afterOverflowCount": len(after_gaps.get("overflows", [])),
        "unresolvedAppliedGapIds": sorted(applied_ids & remaining_ids),
    }


def validate_repair_result(before_gaps, after_gaps, applied, verification):
    """Accept a candidate only when the promised gaps disappear without regression."""
    applied_ids = {item.get("gapId") for item in applied if item.get("gapId")}
    remaining_ids = {item.get("id") for item in after_gaps.get("gaps", [])}
    unresolved = sorted(applied_ids & remaining_ids)
    before_count = len(before_gaps.get("gaps", []))
    after_count = len(after_gaps.get("gaps", []))
    before_overflow = len(before_gaps.get("overflows", []))
    after_overflow = len(after_gaps.get("overflows", []))
    failed = {item.get("id") for item in verification.get("checks", [])
              if not item.get("passed")}
    core_failures = sorted(failed & {
        "pitch_shift", "measure_count", "measure_sequence", "measure_timeline",
        "omr_export", "page_count",
    })
    accepted = (
        bool(applied_ids)
        and not unresolved
        and after_count <= before_count - len(applied_ids)
        and after_overflow <= before_overflow
        and not core_failures
    )
    reason = (
        "已消除 %s 处有原谱证据的节奏缺口，并通过重新转调、排版和基础结构检查" % len(applied_ids)
        if accepted else
        "自动修复后的独立校验未达到安全门槛，已撤销本轮修改"
    )
    return accepted, {
        "accepted": accepted, "reason": reason,
        "beforeGapCount": before_count, "afterGapCount": after_count,
        "beforeOverflowCount": before_overflow, "afterOverflowCount": after_overflow,
        "unresolvedAppliedGapIds": unresolved, "coreFailures": core_failures,
    }
