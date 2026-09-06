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
from pathlib import Path

import pymupdf as fitz
from PIL import Image


VALID_STATES = {"unreviewed", "accepted", "corrected", "rejected", "skipped"}


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


def job_directories(root):
    if (root / "input.pdf").is_file():
        return [root]
    return sorted(path for path in root.iterdir()
                  if path.is_dir() and (path / "input.pdf").is_file())


def export_job(job_dir, image_dir, dpi, previous):
    rhythm_path = job_dir / "review" / "rhythm-gaps.json"
    rest_path = job_dir / "review" / "rest-classification.json"
    pdf_path = job_dir / "input.pdf"
    if not rhythm_path.is_file() or not rest_path.is_file():
        return []
    rhythm, rest = load_json(rhythm_path), load_json(rest_path)
    classes = classification_index(rest)
    document_hash = sha256(pdf_path)
    document = fitz.open(str(pdf_path))
    omr_path = job_dir / "omr" / "input.omr"
    archive = zipfile.ZipFile(str(omr_path)) if omr_path.is_file() and zipfile.is_zipfile(str(omr_path)) else None
    records = []
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
        records.extend(export_job(job_dir, image_dir, args.dpi, previous))
    records.sort(key=lambda item: (item["documentSha256"], item["page"], item["gapId"]))
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
