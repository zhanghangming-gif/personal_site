"""Export provenance-bound rhythm-gap crops for human annotation.

Audiveris candidates are prelabels only.  Existing human annotation fields are
preserved when the exporter is run again.  Raw PDFs remain in the score job
workspace and are never copied into the dataset directory.
"""
import argparse
import hashlib
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz
from PIL import Image


VALID_STATES = {"unreviewed", "accepted", "corrected", "rejected", "skipped"}
OMR_REST_CLASSES = {
    "MAXIMA_REST": "maxima_rest", "LONG_REST": "long_rest",
    "BREVE_REST": "breve_rest", "WHOLE_REST": "whole_rest",
    "HALF_REST": "half_rest", "QUARTER_REST": "quarter_rest",
    "EIGHTH_REST": "eighth_rest", "ONE_16TH_REST": "16th_rest",
    "ONE_32ND_REST": "32nd_rest", "ONE_64TH_REST": "64th_rest",
    "ONE_128TH_REST": "128th_rest", "MULTIPLE_REST": "multi_measure_rest",
}


def load_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-.")[:120]


def classification_index(report):
    return {item.get("gapId"): item for item in report.get("classifications", [])
            if isinstance(item, dict) and item.get("gapId")}


def existing_records(path):
    records = {}
    if not path.is_file():
        return records
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            if item.get("sampleId"):
                records[item["sampleId"]] = item
    return records


def deduplicated_records(records):
    unique = {}
    for record in records:
        current = unique.get(record["sampleId"])
        if current is None or (current.get("state") == "unreviewed" and
                               record.get("state") != "unreviewed"):
            unique[record["sampleId"]] = record
    return sorted(unique.values(),
                  key=lambda item: (item["documentSha256"], item["page"], item["gapId"]))


def clipped_box(box, width, height):
    if not isinstance(box, list) or len(box) != 4:
        return None
    values = [float(value) for value in box]
    values = [max(0.0, values[0]), max(0.0, values[1]),
              min(float(width), values[2]), min(float(height), values[3])]
    return values if values[2] > values[0] and values[3] > values[1] else None


def relative_pixel_box(object_box, crop_box, dpi, image_width, image_height):
    if not isinstance(object_box, list) or len(object_box) != 4:
        return None
    scale = float(dpi) / 72.0
    pixel = [(float(object_box[0]) - crop_box[0]) * scale,
             (float(object_box[1]) - crop_box[1]) * scale,
             (float(object_box[2]) - crop_box[0]) * scale,
             (float(object_box[3]) - crop_box[1]) * scale]
    return clipped_box(pixel, image_width, image_height)


def crop_omr_binary(archive, page_number, object_box, output_path):
    name = "sheet#%s/BINARY.png" % page_number
    if archive is None or name not in archive.namelist():
        return None
    with Image.open(io.BytesIO(archive.read(name))) as image:
        image.load()
        box = clipped_box(object_box, image.width, image.height)
        if box is None:
            return None
        width, height = box[2] - box[0], box[3] - box[1]
        crop = clipped_box([box[0] - max(120.0, width * 8),
                            box[1] - max(55.0, height * 2.5),
                            box[2] + max(120.0, width * 8),
                            box[3] + max(55.0, height * 2.5)],
                           image.width, image.height)
        if crop is None:
            return None
        integer_crop = tuple(int(round(value)) for value in crop)
        result = image.crop(integer_crop).convert("RGB")
        result.save(output_path)
        prelabel = clipped_box([box[0] - integer_crop[0], box[1] - integer_crop[1],
                                box[2] - integer_crop[0], box[3] - integer_crop[1]],
                               result.width, result.height)
        return {"crop": list(integer_crop), "width": result.width,
                "height": result.height, "prelabelBox": prelabel}


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def omr_rest_candidates(archive):
    candidates = []
    if archive is None:
        return candidates
    for name in archive.namelist():
        match = re.fullmatch(r"sheet#(\d+)/sheet#\1\.xml", name)
        if not match:
            continue
        try:
            root = ET.fromstring(archive.read(name))
        except (ET.ParseError, KeyError):
            continue
        page = int(match.group(1))
        for element in root.iter():
            if local_name(element.tag) not in ("rest", "multiple-rest"):
                continue
            class_name = OMR_REST_CLASSES.get(element.get("shape", "").upper())
            bounds = next((child for child in element if local_name(child.tag) == "bounds"), None)
            if class_name is None or bounds is None:
                continue
            try:
                x, y = float(bounds.get("x")), float(bounds.get("y"))
                width, height = float(bounds.get("w")), float(bounds.get("h"))
                box = [x, y, x + width, y + height]
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            candidates.append({
                "page": page, "interId": element.get("id"), "class": class_name,
                "bboxImage": box, "grade": element.get("grade"),
                "contextGrade": element.get("ctx-grade"), "staff": element.get("staff"),
            })
    return candidates


def sampled_omr_candidates(archive, document_hash, maximum_per_class):
    grouped = defaultdict(list)
    for candidate in omr_rest_candidates(archive):
        material = "%s|%s|%s|%s" % (
            document_hash, candidate["page"], candidate.get("interId"), candidate["bboxImage"])
        candidate["sortKey"] = hashlib.sha256(material.encode("utf-8")).hexdigest()
        grouped[candidate["class"]].append(candidate)
    selected = []
    for class_name in sorted(grouped):
        selected.extend(sorted(grouped[class_name], key=lambda item: item["sortKey"])
                        [:maximum_per_class])
    return sorted(selected, key=lambda item: (item["page"], item["class"], item["sortKey"]))


def job_directories(root):
    if (root / "input.pdf").is_file():
        return [root]
    return sorted(path for path in root.iterdir()
                  if path.is_dir() and (path / "input.pdf").is_file())


def export_job(job_dir, image_dir, dpi, previous, include_all_omr=False,
               maximum_omr_per_class=25):
    rhythm_path = job_dir / "review" / "rhythm-gaps.json"
    rest_path = job_dir / "review" / "rest-classification.json"
    pdf_path = job_dir / "input.pdf"
    omr_path = job_dir / "omr" / "input.omr"
    if (not rhythm_path.is_file() or not rest_path.is_file()) and not (
            include_all_omr and omr_path.is_file()):
        return []
    rhythm = load_json(rhythm_path) if rhythm_path.is_file() else {"gaps": []}
    rest = load_json(rest_path) if rest_path.is_file() else {"classifications": []}
    classes = classification_index(rest)
    document_hash = sha256(pdf_path)
    document = fitz.open(str(pdf_path))
    archive = zipfile.ZipFile(str(omr_path)) if omr_path.is_file() and zipfile.is_zipfile(str(omr_path)) else None
    records = []
    used_omr_boxes = set()
    try:
        for gap in rhythm.get("gaps", []):
            if not isinstance(gap, dict) or not gap.get("id"):
                continue
            item = classes.get(gap["id"], {})
            evidence = item.get("selectedEvidence") or {}
            region = gap.get("reviewRegion") or {}
            page_number = region.get("page") or (gap.get("location") or {}).get("page")
            if not isinstance(page_number, int) or not 1 <= page_number <= len(document):
                continue
            page = document[page_number - 1]
            source_kind = ("audiveris_binary" if archive is not None and
                           isinstance(evidence.get("bboxImage"), list) else "source_pdf")
            seed_box = evidence.get("bboxImage") if source_kind == "audiveris_binary" else region.get("bbox")
            if not seed_box:
                continue
            sample_id = hashlib.sha256((document_hash + "|" + gap["id"] + "|" +
                                        source_kind + "|" + json.dumps(seed_box)).encode("utf-8")).hexdigest()[:24]
            image_name = "%s-%s.png" % (sample_id, safe_name(gap["id"]))
            image_path = image_dir / image_name
            if source_kind == "audiveris_binary":
                used_omr_boxes.add((page_number,) + tuple(round(float(value), 2)
                                                           for value in evidence.get("bboxImage")))
                rendered = crop_omr_binary(archive, page_number, evidence.get("bboxImage"), image_path)
                if rendered is None:
                    continue
                crop, crop_basis = rendered["crop"], "audiveris_binary_same_coordinate_space"
                image_width, image_height = rendered["width"], rendered["height"]
                prelabel_box = rendered["prelabelBox"]
                image_dpi = None
            else:
                crop = clipped_box(region.get("bbox"), page.rect.width, page.rect.height)
                if crop is None:
                    continue
                crop_basis = region.get("basis")
                pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0),
                                         clip=fitz.Rect(crop), alpha=False)
                pixmap.save(str(image_path))
                image_width, image_height = pixmap.width, pixmap.height
                prelabel_box, image_dpi = None, dpi
            prelabel = None
            if item.get("suggestedNotation") and prelabel_box:
                prelabel = {
                    "class": item.get("suggestedNotation"), "bboxXyxy": prelabel_box,
                    "dots": item.get("suggestedDots") or 0,
                    "grade": evidence.get("grade"),
                    "contextGrade": evidence.get("contextGrade"),
                    "source": "audiveris_internal_object",
                }
            old = previous.get(sample_id, {})
            state = old.get("state") if old.get("state") in VALID_STATES else "unreviewed"
            record = {
                "schemaVersion": 1, "sampleId": sample_id,
                "image": "images/" + image_name,
                "imageWidth": image_width, "imageHeight": image_height,
                "documentSha256": document_hash,
                "sourceJobId": job_dir.name, "sourcePdfStored": False,
                "gapId": gap["id"], "measureId": gap.get("measureId"),
                "page": page_number, "voice": str(gap.get("voice") or "1"),
                "onset": gap.get("onset"), "duration": gap.get("duration"),
                "position": gap.get("position"), "crop": crop,
                "cropCoordinateSystem": ("audiveris_image_pixels" if source_kind == "audiveris_binary"
                                           else "pdf_points_top_left"),
                "cropBasis": crop_basis, "imageSource": source_kind, "dpi": image_dpi,
                "prelabel": prelabel, "classificationStatus": item.get("status"),
                "state": state, "annotation": old.get("annotation"),
                "annotator": old.get("annotator"), "reviewedAt": old.get("reviewedAt"),
            }
            records.append(record)
        if include_all_omr:
            for candidate in sampled_omr_candidates(
                    archive, document_hash, maximum_omr_per_class):
                page_number, box = candidate["page"], candidate["bboxImage"]
                key = (page_number,) + tuple(round(float(value), 2) for value in box)
                if key in used_omr_boxes:
                    continue
                sample_id = hashlib.sha256((
                    document_hash + "|omr-rest|" + str(page_number) + "|" +
                    str(candidate.get("interId")) + "|" + json.dumps(box)
                ).encode("utf-8")).hexdigest()[:24]
                image_name = "%s-omr-rest-p%s-%s.png" % (
                    sample_id, page_number, safe_name(candidate.get("interId") or "unknown"))
                image_path = image_dir / image_name
                rendered = crop_omr_binary(archive, page_number, box, image_path)
                if rendered is None:
                    continue
                old = previous.get(sample_id, {})
                state = old.get("state") if old.get("state") in VALID_STATES else "unreviewed"
                records.append({
                    "schemaVersion": 1, "sampleId": sample_id,
                    "image": "images/" + image_name,
                    "imageWidth": rendered["width"], "imageHeight": rendered["height"],
                    "documentSha256": document_hash, "sourceJobId": job_dir.name,
                    "sourcePdfStored": False,
                    "gapId": "omr-rest-p%s-%s" % (page_number, candidate.get("interId") or sample_id),
                    "measureId": None, "page": page_number,
                    "voice": None, "onset": None, "duration": None,
                    "position": "omr_candidate", "crop": rendered["crop"],
                    "cropCoordinateSystem": "audiveris_image_pixels",
                    "cropBasis": "audiveris_binary_same_coordinate_space",
                    "imageSource": "audiveris_binary", "dpi": None,
                    "prelabel": {
                        "class": candidate["class"],
                        "bboxXyxy": rendered["prelabelBox"], "dots": 0,
                        "grade": candidate.get("grade"),
                        "contextGrade": candidate.get("contextGrade"),
                        "source": "audiveris_internal_object",
                    },
                    "classificationStatus": "omr_candidate",
                    "state": state, "annotation": old.get("annotation"),
                    "annotator": old.get("annotator"), "reviewedAt": old.get("reviewedAt"),
                })
    finally:
        if archive is not None:
            archive.close()
        document.close()
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=800, choices=(400, 600, 800))
    parser.add_argument("--include-all-omr-rests", action="store_true")
    parser.add_argument("--max-omr-per-class-per-document", type=int, default=5)
    args = parser.parse_args()
    root, output = args.jobs_root.resolve(), args.output.resolve()
    if not root.is_dir():
        raise SystemExit("jobs root does not exist: %s" % root)
    image_dir = output / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    queue_path = output / "queue.jsonl"
    previous = existing_records(queue_path)
    records = []
    for job_dir in job_directories(root):
        records.extend(export_job(
            job_dir, image_dir, args.dpi, previous, args.include_all_omr_rests,
            max(1, min(200, args.max_omr_per_class_per_document))))
    records = deduplicated_records(records)
    with queue_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    states = {state: sum(item["state"] == state for item in records)
              for state in sorted(VALID_STATES)}
    manifest = {
        "schemaVersion": 1, "dpi": args.dpi, "sampleCount": len(records),
        "documentCount": len({item["documentSha256"] for item in records}),
        "stateCounts": states,
        "prelabelCount": sum(item["prelabel"] is not None for item in records),
        "sourcePdfCopied": False,
    }
    with (output / "manifest.json").open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
