"""Bounded automatic repairs for evidence-backed rhythm gaps.

This module never infers a rest from missing duration alone.  A repair must be
supported by a unique OMR object, a high-confidence visual detection, or both;
the existing editor then enforces MusicXML cursor, meter, staff and voice
constraints before any mutation is made.
"""
from fractions import Fraction

from score_editor import REST_LABELS, REST_TYPES, apply_edits


SUPPORTED = {
    "supported_by_omr_object",
    "supported_by_visual_model",
    "supported_by_omr_and_visual_model",
}


def rational(value):
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return Fraction(0)


def _eligible(gap, classification, omr_grade, visual_score):
    if classification.get("status") not in SUPPORTED:
        return False, "unsupported_evidence_status"
    if classification.get("suggestedNotation") not in REST_TYPES:
        return False, "unsupported_rest_notation"
    if gap.get("riskReasons"):
        return False, "rhythm_exception_or_polyphony"
    if gap.get("position") not in ("leading", "internal", "trailing", "full_measure"):
        return False, "unknown_gap_position"

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
    strong_visual = (
        visual.get("class") == classification.get("suggestedNotation")
        and visual.get("staffGeometryConsistent") is not False
        and float(visual.get("score") or 0) >= visual_score
    )
    if status == "supported_by_omr_and_visual_model":
        if unique_omr and strong_visual:
            return True, "omr_and_visual_agree"
        return False, "dual_evidence_below_auto_threshold"
    if status == "supported_by_omr_object":
        return (True, "unique_high_grade_omr_object") if unique_omr else (
            False, "omr_evidence_below_auto_threshold")
    return (True, "high_confidence_visual_model") if strong_visual else (
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
                    "后端依据原谱对象证据，在第 %s 小节声部 %s、起点 %s 补入%s；"
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
        "thresholds": {"omrGrade": omr_grade, "visualScore": visual_score},
        "limits": "Only source-evidenced rests are inserted; every result requires a fresh timeline and PDF validation pass.",
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
