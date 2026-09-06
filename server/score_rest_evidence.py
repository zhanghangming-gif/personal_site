"""Match rhythm gaps to rest objects retained in an Audiveris OMR book.

Audiveris can recognize a rest glyph in its internal graph yet omit the event
from exported MusicXML when stack/voice assembly fails.  This module recovers
that observation as review evidence.  It never edits the score.
"""
import re
import zipfile
from collections import defaultdict
from fractions import Fraction
from xml.etree import ElementTree as ET


REST_DURATIONS = {
    "MAXIMA_REST": Fraction(32),
    "LONG_REST": Fraction(16),
    "BREVE_REST": Fraction(8),
    "WHOLE_REST": Fraction(4),
    "HALF_REST": Fraction(2),
    "QUARTER_REST": Fraction(1),
    "EIGHTH_REST": Fraction(1, 2),
    "ONE_16TH_REST": Fraction(1, 4),
    "ONE_32ND_REST": Fraction(1, 8),
    "ONE_64TH_REST": Fraction(1, 16),
    "ONE_128TH_REST": Fraction(1, 32),
}

NOTATION_NAMES = {
    "MAXIMA_REST": "maxima_rest", "LONG_REST": "long_rest",
    "BREVE_REST": "breve_rest", "WHOLE_REST": "whole_rest",
    "HALF_REST": "half_rest", "QUARTER_REST": "quarter_rest",
    "EIGHTH_REST": "eighth_rest", "ONE_16TH_REST": "16th_rest",
    "ONE_32ND_REST": "32nd_rest", "ONE_64TH_REST": "64th_rest",
    "ONE_128TH_REST": "128th_rest",
}


def local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rational(value):
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None


def fraction_text(value):
    return str(value.numerator) if value.denominator == 1 else "%s/%s" % (
        value.numerator, value.denominator)


def bounds(element):
    child = next((item for item in list(element) if local(item.tag) == "bounds"), None)
    if child is None:
        return None
    x, y = number(child.get("x")), number(child.get("y"))
    width, height = number(child.get("w", child.get("width"))), number(child.get("h", child.get("height")))
    if None in (x, y, width, height) or width <= 0 or height <= 0:
        return None
    return [x, y, x + width, y + height]


def dotted_duration(base, dots):
    result, addition = base, base
    for _ in range(max(0, int(dots))):
        addition /= 2
        result += addition
    return result


def audiveris_rest_objects(book_path):
    pages = []
    if not book_path or not zipfile.is_zipfile(book_path):
        return pages
    with zipfile.ZipFile(book_path) as archive:
        sheets = sorted(
            (name for name in archive.namelist()
             if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", name)),
            key=lambda name: int(re.search(r"sheet#(\d+)", name).group(1)))
        for page_number, name in enumerate(sheets, 1):
            root = ET.fromstring(archive.read(name))
            picture = next((item for item in root.iter() if local(item.tag) == "picture"), None)
            page = {
                "page": page_number,
                "imageWidth": int(number(picture.get("width"), 0)) if picture is not None else 0,
                "imageHeight": int(number(picture.get("height"), 0)) if picture is not None else 0,
                "systems": [],
            }
            for system_number, system in enumerate(
                    (item for item in root.iter() if local(item.tag) == "system"), 1):
                staff_ids = []
                for staff in (item for item in system.iter() if local(item.tag) == "staff"):
                    identifier = staff.get("id")
                    if identifier and identifier not in staff_ids:
                        staff_ids.append(identifier)
                dot_ids = {
                    item.get("id") for item in system.iter()
                    if local(item.tag) == "augmentation-dot" and item.get("id")
                }
                dot_targets = defaultdict(int)
                for relation in (item for item in system.iter() if local(item.tag) == "relation"):
                    source, target = relation.get("source"), relation.get("target")
                    if source in dot_ids and any(local(item.tag) == "augmentation" for item in list(relation)):
                        dot_targets[target] += 1
                rests = []
                for item in system.iter():
                    if local(item.tag) != "rest" or item.get("shape") not in REST_DURATIONS:
                        continue
                    box = bounds(item)
                    if box is None:
                        continue
                    shape = item.get("shape")
                    dots = dot_targets.get(item.get("id"), 0)
                    staff_id = item.get("staff")
                    rests.append({
                        "id": item.get("id"), "shape": shape,
                        "notation": NOTATION_NAMES[shape], "dots": dots,
                        "duration": fraction_text(dotted_duration(REST_DURATIONS[shape], dots)),
                        "bboxImage": box,
                        "grade": number(item.get("grade"), 0.0),
                        "contextGrade": number(item.get("ctx-grade"), number(item.get("grade"), 0.0)),
                        "pitch": number(item.get("pitch")),
                        "staffId": staff_id,
                        "staffPosition": staff_ids.index(staff_id) + 1 if staff_id in staff_ids else None,
                    })
                stacks = []
                for item in list(system):
                    if local(item.tag) != "stack":
                        continue
                    stacks.append({"left": number(item.get("left"), 0),
                                   "right": number(item.get("right"), 0),
                                   "special": item.get("special", "")})
                page["systems"].append({"system": system_number, "rests": rests, "stacks": stacks})
            pages.append(page)
    return pages


def page_geometry(preflight, page_number):
    for page in (preflight or {}).get("pageDetails", []):
        if page.get("page") == page_number:
            geometry = page.get("geometry") or {}
            if geometry.get("width") and geometry.get("height"):
                return geometry
    return None


def pdf_bbox(image_bbox, page, geometry):
    if not page.get("imageWidth") or not page.get("imageHeight") or not geometry:
        return None
    sx = float(geometry["width"]) / page["imageWidth"]
    sy = float(geometry["height"]) / page["imageHeight"]
    return [round(image_bbox[0] * sx, 4), round(image_bbox[1] * sy, 4),
            round(image_bbox[2] * sx, 4), round(image_bbox[3] * sy, 4)]


def center_in(box, region, padding=0.0):
    if not box or not region:
        return False
    x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return (region[0] - padding <= x <= region[2] + padding
            and region[1] - padding <= y <= region[3] + padding)


def rest_position_consistent(rest):
    pitch = rest.get("pitch")
    if pitch is None:
        return False if rest.get("shape") in ("WHOLE_REST", "HALF_REST") else True
    if rest.get("shape") == "WHOLE_REST":
        return pitch <= -0.9
    if rest.get("shape") == "HALF_REST":
        return pitch > -0.9
    return True


def duration_matches(rest, gap):
    actual, missing = rational(rest.get("duration")), rational(gap.get("duration"))
    expected = rational(gap.get("expectedMeasureDuration"))
    if None in (actual, missing):
        return False, None
    if (rest.get("shape") == "WHOLE_REST" and gap.get("position") == "full_measure"
            and expected is not None and missing == expected):
        return True, "whole_measure_rest"
    return actual == missing, "written_duration"


def classify_rest_gaps(rhythm_report, book_path, preflight=None):
    pages = audiveris_rest_objects(book_path)
    page_index = {page["page"]: page for page in pages}
    results = []
    for gap in rhythm_report.get("gaps", []):
        location = gap.get("location") or {}
        page_number, system_number = location.get("page"), location.get("system")
        page = page_index.get(page_number)
        system = next((item for item in (page or {}).get("systems", [])
                       if item.get("system") == system_number), None)
        region = (gap.get("reviewRegion") or {}).get("bbox")
        geometry = page_geometry(preflight, page_number)
        staff_values = {str(value) for value in gap.get("staffs", [])}
        candidates = []
        for rest in (system or {}).get("rests", []):
            item = dict(rest)
            item["bboxPdf"] = pdf_bbox(item["bboxImage"], page, geometry)
            spatial = center_in(item.get("bboxPdf"), region, 3.0) if region else False
            if not spatial:
                position = location.get("positionInSystem")
                stacks = (system or {}).get("stacks", [])
                if isinstance(position, int) and 0 < position <= len(stacks):
                    stack = stacks[position - 1]
                    center_x = (item["bboxImage"][0] + item["bboxImage"][2]) / 2
                    spatial = stack["left"] - 5 <= center_x <= stack["right"] + 5
            staff_match = (item.get("staffPosition") is None
                           or str(item.get("staffPosition")) in staff_values)
            duration_match, duration_basis = duration_matches(item, gap)
            if spatial and staff_match:
                item["durationMatchesGap"] = duration_match
                item["durationBasis"] = duration_basis
                item["staffPositionConsistent"] = rest_position_consistent(item)
                candidates.append(item)
        exact = [item for item in candidates
                 if item["durationMatchesGap"] and item["staffPositionConsistent"]]
        strong = [item for item in exact
                  if item.get("grade", 0) >= 0.65 and item.get("contextGrade", 0) >= 0.70]
        if len(strong) == 1:
            status, selected = "supported_by_omr_object", strong[0]
        elif len(exact) == 1:
            status, selected = "weak_omr_candidate", exact[0]
        elif len(exact) > 1:
            status, selected = "ambiguous_candidates", None
        else:
            status, selected = "visual_confirmation_required", None
        results.append({
            "gapId": gap.get("id"), "measureId": gap.get("measureId"),
            "location": location, "gapDuration": gap.get("duration"),
            "status": status,
            "suggestedNotation": selected.get("notation") if selected else None,
            "suggestedDots": selected.get("dots") if selected else None,
            "selectedEvidence": selected,
            "candidateCount": len(candidates), "exactCandidateCount": len(exact),
            "candidates": candidates[:12],
            "autoRepairAllowed": False,
            "nextAction": ("confirm_notation_and_position" if selected
                           else "inspect_800dpi_source_region"),
        })
    counts = {status: sum(item["status"] == status for item in results)
              for status in sorted(set(item["status"] for item in results))}
    return {
        "schemaVersion": 1, "engine": "audiveris_internal_rest_objects",
        "classifications": results,
        "summary": {"gapCount": len(results), "statusCounts": counts,
                    "supportedCount": counts.get("supported_by_omr_object", 0)},
        "limits": "OMR 内部对象是候选证据；未经原 PDF 视觉确认不自动写入休止符",
    }


def annotate_rhythm_gaps(rhythm_report, classification_report):
    """Attach compact candidate hints while keeping full evidence separate."""
    by_gap = {item.get("gapId"): item
              for item in classification_report.get("classifications", [])}
    for gap in rhythm_report.get("gaps", []):
        item = by_gap.get(gap.get("id"))
        if not item:
            continue
        selected = item.get("selectedEvidence") or {}
        gap["restEvidence"] = {
            "status": item.get("status"),
            "suggestedNotation": item.get("suggestedNotation"),
            "suggestedDots": item.get("suggestedDots"),
            "grade": selected.get("grade"),
            "contextGrade": selected.get("contextGrade"),
            "candidateCount": item.get("candidateCount", 0),
            "exactCandidateCount": item.get("exactCandidateCount", 0),
            "autoRepairAllowed": False,
            "artifact": "review/rest-classification.json",
        }
    return rhythm_report
