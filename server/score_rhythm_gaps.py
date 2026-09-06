"""Detect missing time in MusicXML-derived score IR without inventing rests.

The detector proves only that a voice timeline does not occupy the duration
declared by the active time signature.  It does not claim that the source PDF
contains a particular rest glyph: a wrong note duration, tuplet, voice, or
pickup interpretation can produce the same symptom.
"""
from collections import defaultdict
from fractions import Fraction


REST_LABELS = {
    "maxima_rest": "倍全休止符", "long_rest": "长休止符", "breve_rest": "二全休止符",
    "whole_rest": "全休止符", "half_rest": "二分休止符", "quarter_rest": "四分休止符",
    "eighth_rest": "八分休止符", "16th_rest": "十六分休止符",
    "32nd_rest": "三十二分休止符", "64th_rest": "六十四分休止符",
    "128th_rest": "一百二十八分休止符",
}


def rational(value):
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result


def fraction_text(value):
    return str(value.numerator) if value.denominator == 1 else "%s/%s" % (
        value.numerator, value.denominator)


def canonical_name(node):
    return node[0] if isinstance(node, list) and len(node) == 4 else ""


def canonical_text(node):
    return node[2] if isinstance(node, list) and len(node) == 4 else ""


def time_duration(value):
    """Return a time signature duration in quarter-note units."""
    if not isinstance(value, list) or any(canonical_name(item) == "senza-misura" for item in value):
        return None
    beats, units = [], []
    for item in value:
        name, text = canonical_name(item), canonical_text(item)
        if name == "beats":
            try:
                beats.append(sum(Fraction(part.strip()) for part in text.split("+") if part.strip()))
            except (ValueError, ZeroDivisionError):
                return None
        elif name == "beat-type":
            datum = rational(text)
            if datum is None or datum <= 0:
                return None
            units.append(datum)
    if not beats or len(beats) != len(units):
        return None
    return sum((count * 4 / unit for count, unit in zip(beats, units)), Fraction(0))


def expected_measure_duration(measure):
    time = (measure.get("context") or {}).get("time") or {}
    candidates = set()
    if isinstance(time, dict):
        for value in time.values():
            duration = time_duration(value)
            if duration is not None:
                candidates.add(duration)
    if len(candidates) == 1:
        return next(iter(candidates)), None
    return None, "missing_time_signature" if not candidates else "conflicting_staff_time_signatures"


def contains_canonical_name(value, expected):
    if canonical_name(value) == expected:
        return True
    if isinstance(value, list):
        return any(contains_canonical_name(item, expected) for item in value)
    if isinstance(value, dict):
        return any(contains_canonical_name(item, expected) for item in value.values())
    return False


def is_multirest(measure):
    return any(contains_canonical_name(mark.get("data"), "multiple-rest")
               for mark in measure.get("marks", []))


def merge_intervals(intervals, limit):
    clipped = sorted((max(Fraction(0), start), min(limit, end))
                     for start, end in intervals if end > 0 and start < limit and end > start)
    merged = []
    for start, end in clipped:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    return merged


def complement(intervals, limit):
    cursor, gaps = Fraction(0), []
    for start, end in merge_intervals(intervals, limit):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < limit:
        gaps.append((cursor, limit))
    return gaps


def coarse_review_region(measure, onset, duration, expected):
    source = measure.get("sourceRegion") or {}
    box = source.get("bbox")
    if not isinstance(box, list) or len(box) != 4 or expected <= 0:
        return None
    try:
        left, top, right, bottom = [float(value) for value in box]
    except (TypeError, ValueError):
        return None
    width = right - left
    if width <= 0 or bottom <= top:
        return None
    # Engraving spacing is nonlinear. Keep generous horizontal padding and
    # label the crop as a review hint rather than a proven glyph coordinate.
    padding = max(width * 0.08, 4.0)
    start = left + width * float(onset / expected)
    end = left + width * float((onset + duration) / expected)
    return {
        "page": source.get("page"),
        "coordinateSystem": source.get("coordinateSystem", "pdf_points_top_left"),
        "bbox": [max(left, start - padding), top, min(right, end + padding), bottom],
        "basis": "measure_bbox_linear_time_hint",
        "semanticVerification": False,
    }


def gap_position(onset, end, expected):
    if onset == 0 and end == expected:
        return "full_measure"
    if onset == 0:
        return "leading"
    if end == expected:
        return "trailing"
    return "internal"


def detect_rhythm_gaps(index, limit=500):
    gaps, overflows, exceptions = [], [], []
    analyzed = 0
    for part in index.get("parts", []):
        measures = part.get("measures", [])
        positions_in_system = defaultdict(int)
        for measure_position, measure in enumerate(measures):
            expected, problem = expected_measure_duration(measure)
            location = dict(measure.get("location") or {})
            system_key = (location.get("page"), location.get("system"))
            positions_in_system[system_key] += 1
            location["positionInSystem"] = positions_in_system[system_key]
            if problem:
                exceptions.append({"measureId": measure.get("id"), "location": location,
                                   "reason": problem})
                continue
            if measure.get("implicit") or measure.get("nonControlling"):
                exceptions.append({"measureId": measure.get("id"), "location": location,
                                   "reason": "implicit_or_non_controlling_measure"})
                continue
            if is_multirest(measure):
                exceptions.append({"measureId": measure.get("id"), "location": location,
                                   "reason": "multi_measure_rest"})
                continue
            events = [event for event in measure.get("events", [])
                      if not event.get("grace") and rational(event.get("duration"))]
            by_voice = defaultdict(list)
            for event in events:
                onset = rational(event.get("onset"))
                duration = rational(event.get("duration"))
                if onset is None or duration is None or duration <= 0:
                    continue
                by_voice[str(event.get("voice") or "1")].append((onset, onset + duration, event))
            if not by_voice:
                by_voice["1"] = []
            analyzed += 1
            multi_voice = len(by_voice) > 1
            for voice, rows in sorted(by_voice.items()):
                intervals = [(row[0], row[1]) for row in rows]
                maximum = max((end for _, end in intervals), default=Fraction(0))
                if maximum > expected:
                    overflows.append({
                        "id": "rhythm-overflow-%s-v%s" % (measure.get("id"), voice),
                        "type": "rhythm_overflow", "measureId": measure.get("id"),
                        "location": dict(location, voice=voice),
                        "expectedDuration": fraction_text(expected),
                        "actualEnd": fraction_text(maximum),
                        "status": "needs_timeline_confirmation", "autoRepairAllowed": False,
                    })
                for gap_index, (start, end) in enumerate(complement(intervals, expected), 1):
                    position = gap_position(start, end, expected)
                    possible_boundary_exception = (
                        (measure_position == 0 and position in ("leading", "trailing", "full_measure"))
                        or (measure_position == len(measures) - 1 and position in ("leading", "trailing", "full_measure")))
                    risk = []
                    if multi_voice:
                        risk.append("multiple_voices")
                    if possible_boundary_exception:
                        risk.append("possible_pickup_or_incomplete_final_measure")
                    if any(event.get("timeModification") for _, _, event in rows):
                        risk.append("tuplet_or_time_modification")
                    duration = end - start
                    gap = {
                        "id": "rhythm-gap-%s-v%s-%s" % (measure.get("id"), voice, gap_index),
                        "type": "implicit_silence", "measureId": measure.get("id"),
                        "location": dict(location, voice=voice, onsetQuarter=fraction_text(start)),
                        "voice": voice,
                        "staffs": sorted(set(str(row[2].get("staff") or "1") for row in rows)) or ["1"],
                        "onset": fraction_text(start), "duration": fraction_text(duration),
                        "expectedMeasureDuration": fraction_text(expected), "position": position,
                        "status": "needs_notation_confirmation",
                        "temporalEvidence": "musicxml_voice_timeline",
                        "notationConfidence": "unknown", "autoRepairAllowed": False,
                        "riskReasons": risk,
                    }
                    region = coarse_review_region(measure, start, duration, expected)
                    if region:
                        gap["reviewRegion"] = region
                    gaps.append(gap)
                    if len(gaps) >= limit:
                        break
                if len(gaps) >= limit:
                    break
            if len(gaps) >= limit:
                break
        if len(gaps) >= limit:
            break
    return {
        "schemaVersion": 1,
        "status": "gaps_found" if gaps or overflows else "no_timeline_gaps_detected",
        "gaps": gaps, "overflows": overflows, "exceptions": exceptions,
        "summary": {"analyzedMeasures": analyzed, "gapCount": len(gaps),
                    "overflowCount": len(overflows), "truncated": len(gaps) >= limit},
        "limits": "时间轴缺口不是休止符分类；未经原 PDF 局部证据确认不自动写入 MusicXML",
    }


def rhythm_gap_issues(report):
    issues = []
    for position, gap in enumerate(report.get("gaps", []), 1):
        location = gap.get("location") or {}
        evidence = gap.get("restEvidence") or {}
        suggestion = evidence.get("suggestedNotation")
        evidence_note = ""
        if suggestion:
            evidence_note = "；OMR 原始对象中发现疑似%s%s，仍需对照原 PDF 确认" % (
                REST_LABELS.get(suggestion, suggestion), "（%s 个附点）" % evidence.get("suggestedDots")
                if evidence.get("suggestedDots") else "")
        elif evidence.get("status") == "ambiguous_candidates":
            evidence_note = "；同一区域存在多个休止候选，无法唯一分类"
        elif evidence:
            evidence_note = "；OMR 原始对象未提供与缺失时值一致的唯一休止候选"
        issues.append({
            "id": "source-rhythm-gap-%s" % position,
            "phase": "source", "code": "missing_rhythm_duration",
            "eventId": gap.get("id"), "location": location,
            "field": "rhythm", "expected": gap.get("duration"),
            "actual": "未找到占用该时段的音符或休止符",
            "pdfRegion": gap.get("reviewRegion"),
            "message": "第 %s 小节，声部 %s，起点 %s：时间轴缺少 %s 个四分音符时值；需回看原谱确认休止符、音符时值或声部%s"
                       % (location.get("measure", "?"), gap.get("voice", "?"),
                          gap.get("onset", "?"), gap.get("duration", "?"), evidence_note),
        })
    for position, overflow in enumerate(report.get("overflows", []), 1):
        location = overflow.get("location") or {}
        issues.append({
            "id": "source-rhythm-overflow-%s" % position,
            "phase": "source", "code": "rhythm_duration_overflow",
            "eventId": overflow.get("id"), "location": location,
            "field": "rhythm", "expected": overflow.get("expectedDuration"),
            "actual": overflow.get("actualEnd"),
            "message": "第 %s 小节，声部 %s：识别时值超过当前拍号容量，需复核时值、连音或声部"
                       % (location.get("measure", "?"), location.get("voice", "?")),
        })
    return issues
