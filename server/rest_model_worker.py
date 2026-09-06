"""Isolated PyTorch CPU worker for rest detection on PDF measure crops.

This process is launched after OMR has finished and exits after one score.  It
never edits MusicXML; its JSON output is additional review evidence.
"""
import argparse
import hashlib
import json
import os
import re
import time

import fitz
import torch
from PIL import Image
from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.transforms.functional import pil_to_tensor


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_model(checkpoint):
    categories = {int(key): value for key, value in checkpoint["categories"].items()}
    model = fasterrcnn_mobilenet_v3_large_fpn(
        weights=None, weights_backbone=None,
        min_size=int(checkpoint["minSize"]), max_size=int(checkpoint["maxSize"]),
    )
    features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(features, max(categories) + 1)
    model.load_state_dict(checkpoint["model"])
    return model.eval(), categories


def valid_box(value, page):
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        box = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    box = [max(0.0, box[0]), max(0.0, box[1]),
           min(float(page.rect.width), box[2]), min(float(page.rect.height), box[3])]
    return box if box[2] > box[0] and box[3] > box[1] else None


def safe_name(value):
    return re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or "gap"))[:100]


def infer_region(model, page, box, dpi, threshold):
    scale = float(dpi) / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                             clip=fitz.Rect(box), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    tensor = pil_to_tensor(image).float().div(255.0)
    with torch.inference_mode():
        prediction = model([tensor])[0]
    rows = []
    for detected_box, label, score in zip(
            prediction["boxes"].tolist(), prediction["labels"].tolist(),
            prediction["scores"].tolist()):
        if score < threshold or len(rows) >= 24:
            continue
        pdf_box = [box[0] + detected_box[0] / scale,
                   box[1] + detected_box[1] / scale,
                   box[0] + detected_box[2] / scale,
                   box[1] + detected_box[3] / scale]
        rows.append((detected_box, int(label), float(score), pdf_box))
    return image, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("response")
    args = parser.parse_args()
    started = time.time()
    with open(args.request, encoding="utf-8") as stream:
        request = json.load(stream)
    checkpoint_path = request["checkpoint"]
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    torch.set_num_threads(max(1, min(2, int(request.get("threads", 1)))))
    torch.set_num_interop_threads(1)
    model, categories = create_model(checkpoint)
    threshold = max(0.01, min(0.99, float(request.get("scoreThreshold", 0.05))))
    dpi = max(144, min(600, int(request.get("dpi", 400))))
    adaptive_dpi = max(dpi, min(800, int(request.get("adaptiveDpi", dpi))))
    output_dir = request.get("cropOutputDir")
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    results = []
    document = fitz.open(request["pdfPath"])
    try:
        for gap in request.get("gaps", [])[:128]:
            page_number = gap.get("page")
            if not isinstance(page_number, int) or not 1 <= page_number <= len(document):
                continue
            page = document[page_number - 1]
            box = valid_box(gap.get("bboxPdf"), page)
            if box is None:
                continue
            used_dpi = dpi
            image, rows = infer_region(model, page, box, used_dpi, threshold)
            adaptive_retry = False
            if (adaptive_dpi > dpi and gap.get("position") == "full_measure"
                    and not any(row[2] >= 0.35 for row in rows)):
                used_dpi = adaptive_dpi
                image, rows = infer_region(model, page, box, used_dpi, threshold)
                adaptive_retry = True
            crop_name = safe_name(gap.get("gapId")) + ".png"
            if output_dir:
                image.save(os.path.join(output_dir, crop_name))
            detections = []
            for detected_box, label, score, pdf_box in rows:
                detections.append({
                    "class": categories.get(int(label), "unknown"),
                    "score": round(float(score), 6),
                    "bboxCropPixels": [round(float(value), 2) for value in detected_box],
                    "bboxPdf": [round(float(value), 4) for value in pdf_box],
                })
            results.append({
                "gapId": gap.get("gapId"), "page": page_number,
                "bboxPdf": box, "crop": crop_name if output_dir else None,
                "gapDuration": gap.get("gapDuration"), "position": gap.get("position"),
                "expectedMeasureDuration": gap.get("expectedMeasureDuration"),
                "staffGeometry": gap.get("staffGeometry"),
                "mappingBasis": gap.get("mappingBasis"),
                "dpi": used_dpi, "adaptiveRetry": adaptive_retry,
                "detections": detections,
            })
    finally:
        document.close()
    response = {
        "schemaVersion": 1, "engine": "pytorch_fasterrcnn_cpu",
        "modelVersion": os.path.basename(checkpoint_path),
        "modelSha256": file_digest(checkpoint_path),
        "dpi": dpi, "adaptiveDpi": adaptive_dpi, "scoreThreshold": threshold,
        "processedGapCount": len(results), "results": results,
        "elapsedSeconds": round(time.time() - started, 3),
    }
    temporary = args.response + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(response, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, args.response)


if __name__ == "__main__":
    main()
