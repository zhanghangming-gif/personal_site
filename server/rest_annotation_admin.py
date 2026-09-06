"""Protected human-annotation store for the local rest detector.

The public API must never expose score job paths, job ids, source filenames, or
raw PDFs.  This module only returns cropped images and provenance-safe ids.
"""
from __future__ import division

import hashlib
import io
import json
import os
import subprocess
import tempfile
import threading
import zipfile
from collections import defaultdict
from datetime import datetime, timezone


VALID_STATES = {"unreviewed", "accepted", "corrected", "rejected", "skipped"}
TRAINING_STATES = {"accepted", "corrected", "rejected"}
REST_CLASSES = (
    "maxima_rest", "long_rest", "breve_rest", "whole_rest", "half_rest",
    "quarter_rest", "eighth_rest", "16th_rest", "32nd_rest", "64th_rest",
    "128th_rest", "multi_measure_rest",
)
_LOCK = threading.RLock()


def _utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _queue_path(dataset_dir):
    return os.path.join(dataset_dir, "queue.jsonl")


def _read_records(dataset_dir):
    path = _queue_path(dataset_dir)
    if not os.path.isfile(path):
        return []
    records = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(item, dict) and item.get("sampleId"):
                records.append(item)
    return records


def _write_records(dataset_dir, records):
    if not os.path.isdir(dataset_dir):
        os.makedirs(dataset_dir)
    path = _queue_path(dataset_dir)
    descriptor, temporary = tempfile.mkstemp(prefix="queue-", suffix=".jsonl", dir=dataset_dir)
    try:
        with io.open(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _revision(item):
    material = {
        "sampleId": item.get("sampleId"), "state": item.get("state"),
        "annotation": item.get("annotation"), "annotator": item.get("annotator"),
        "reviewedAt": item.get("reviewedAt"),
    }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _public_item(item):
    prelabel = item.get("prelabel") if isinstance(item.get("prelabel"), dict) else None
    result = {
        "sampleId": item.get("sampleId"),
        "imageUrl": "/api/admin/rest-annotations/%s/image" % item.get("sampleId"),
        "imageWidth": item.get("imageWidth"), "imageHeight": item.get("imageHeight"),
        "documentSha256": item.get("documentSha256"), "gapId": item.get("gapId"),
        "measureId": item.get("measureId"), "page": item.get("page"),
        "voice": item.get("voice"), "onset": item.get("onset"),
        "duration": item.get("duration"), "position": item.get("position"),
        "imageSource": item.get("imageSource"),
        "classificationStatus": item.get("classificationStatus"),
        "prelabel": prelabel, "state": item.get("state", "unreviewed"),
        "annotation": item.get("annotation"), "reviewedAt": item.get("reviewedAt"),
    }
    result["revision"] = _revision(item)
    return result


def _balanced_review_order(records):
    buckets = defaultdict(list)
    for item in records:
        class_name = (item.get("prelabel") or {}).get("class") or "no_prelabel"
        buckets[(item.get("documentSha256") or "", class_name)].append(item)
    for values in buckets.values():
        values.sort(key=lambda item: item.get("sampleId") or "")
    keys = sorted(buckets, key=lambda key: hashlib.sha256(
        (key[0] + "|" + key[1]).encode("utf-8")).hexdigest())
    ordered = []
    while keys:
        remaining = []
        for key in keys:
            values = buckets[key]
            if values:
                ordered.append(values.pop(0))
            if values:
                remaining.append(key)
        keys = remaining
    return ordered


def list_samples(dataset_dir, state="all", offset=0, limit=40):
    with _LOCK:
        records = _read_records(dataset_dir)
    state = state if state in VALID_STATES else "all"
    selected = records if state == "all" else [item for item in records if item.get("state", "unreviewed") == state]
    if state == "unreviewed":
        selected = _balanced_review_order(selected)
    offset = max(0, int(offset))
    limit = min(100, max(1, int(limit)))
    counts = {name: 0 for name in sorted(VALID_STATES)}
    for item in records:
        item_state = item.get("state", "unreviewed")
        if item_state in counts:
            counts[item_state] += 1
    counts["total"] = len(records)
    counts["trainingReady"] = sum(counts[name] for name in TRAINING_STATES)
    return {
        "items": [_public_item(item) for item in selected[offset:offset + limit]],
        "offset": offset, "limit": limit, "filteredTotal": len(selected),
        "counts": counts, "classes": list(REST_CLASSES),
    }


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError("%s必须是数字" % label)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s必须是数字" % label)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("%s无效" % label)
    return number


def _validate_target(target, width, height):
    if not isinstance(target, dict) or set(target) - {"class", "bboxXyxy", "dots"}:
        raise ValueError("目标标注格式无效")
    class_name = target.get("class")
    if class_name not in REST_CLASSES:
        raise ValueError("休止符类别无效")
    box = target.get("bboxXyxy")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("目标框必须包含四个坐标")
    box = [_number(value, "目标框坐标") for value in box]
    if (box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height or
            box[2] - box[0] < 2 or box[3] - box[1] < 2):
        raise ValueError("目标框超出图片或尺寸过小")
    dots = target.get("dots", 0)
    if isinstance(dots, bool) or not isinstance(dots, int) or not 0 <= dots <= 3:
        raise ValueError("附点数必须是 0 到 3 的整数")
    return {"class": class_name, "bboxXyxy": [round(value, 2) for value in box], "dots": dots}


def update_sample(dataset_dir, sample_id, payload):
    if not isinstance(payload, dict) or set(payload) - {"revision", "state", "targets", "reason"}:
        raise ValueError("标注请求格式无效")
    if payload.get("state") not in VALID_STATES - {"unreviewed"}:
        raise ValueError("标注状态无效")
    with _LOCK:
        records = _read_records(dataset_dir)
        item = next((record for record in records if record.get("sampleId") == sample_id), None)
        if item is None:
            raise ValueError("标注样本不存在")
        if payload.get("revision") != _revision(item):
            raise ValueError("该样本已被其他页面修改，请刷新后重试")
        state = payload["state"]
        width, height = float(item.get("imageWidth") or 0), float(item.get("imageHeight") or 0)
        targets = payload.get("targets", [])
        if not isinstance(targets, list) or len(targets) > 8:
            raise ValueError("每张裁片最多标注 8 个目标")
        if state in ("accepted", "corrected"):
            if not targets:
                raise ValueError("确认或修正样本至少需要一个目标框")
            targets = [_validate_target(target, width, height) for target in targets]
            if state == "accepted":
                prelabel = item.get("prelabel")
                if not isinstance(prelabel, dict):
                    raise ValueError("没有 OMR 预标的样本不能标记为直接接受")
                expected = _validate_target({
                    "class": prelabel.get("class"), "bboxXyxy": prelabel.get("bboxXyxy"),
                    "dots": prelabel.get("dots", 0),
                }, width, height)
                if targets != [expected]:
                    raise ValueError("修改过的预标必须保存为人工修正")
        elif targets:
            raise ValueError("拒绝或跳过样本不能包含目标框")
        reason = str(payload.get("reason") or "").strip()[:240]
        if state == "skipped" and not reason:
            raise ValueError("跳过样本时请填写原因")
        item["state"] = state
        item["annotation"] = {"targets": targets, "reason": reason}
        item["annotator"] = "site-admin"
        item["reviewedAt"] = _utcnow()
        _write_records(dataset_dir, records)
        return _public_item(item)


def sample_image_path(dataset_dir, sample_id):
    with _LOCK:
        item = next((record for record in _read_records(dataset_dir)
                     if record.get("sampleId") == sample_id), None)
    if item is None:
        raise ValueError("标注样本不存在")
    relative = item.get("image")
    if not isinstance(relative, str):
        raise ValueError("标注图片不存在")
    root = os.path.realpath(dataset_dir)
    path = os.path.realpath(os.path.join(root, relative.replace("/", os.sep)))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:
        inside = False
    if not inside or not os.path.isfile(path):
        raise ValueError("标注图片不存在")
    return path


def refresh_samples(dataset_dir, jobs_root, exporter_path, python_path, dpi=800):
    if not os.path.isfile(exporter_path):
        raise RuntimeError("训练样本导出器尚未部署")
    if not os.path.isdir(jobs_root):
        raise RuntimeError("乐谱任务目录不存在")
    if not os.path.isdir(dataset_dir):
        os.makedirs(dataset_dir)
    command = [python_path, exporter_path, "--jobs-root", jobs_root,
               "--output", dataset_dir, "--dpi", str(int(dpi)),
               "--include-all-omr-rests", "--max-omr-per-class-per-document", "5"]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=900, universal_newlines=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误").strip()[-600:]
        raise RuntimeError("刷新训练样本失败：%s" % detail)
    return list_samples(dataset_dir, "all", 0, 1)


def _document_split(document_hash):
    value = int(hashlib.sha256(document_hash.encode("ascii")).hexdigest()[:8], 16) % 100
    return "train" if value < 70 else ("validation" if value < 85 else "test")


def build_training_archive(dataset_dir):
    """Build a temporary COCO zip from reviewed samples only."""
    with _LOCK:
        records = [item for item in _read_records(dataset_dir)
                   if item.get("state") in TRAINING_STATES]
        if not records:
            raise ValueError("还没有可导出的人工确认样本")
        descriptor, archive_path = tempfile.mkstemp(prefix="rest-training-", suffix=".zip")
        os.close(descriptor)
        categories = [{"id": index + 1, "name": name}
                      for index, name in enumerate(REST_CLASSES)]
        category_ids = {item["name"]: item["id"] for item in categories}
        coco = {split: {"images": [], "annotations": [], "categories": categories}
                for split in ("train", "validation", "test")}
        annotation_id = 1
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for image_id, item in enumerate(records, 1):
                    split = _document_split(item.get("documentSha256", ""))
                    source = sample_image_path(dataset_dir, item["sampleId"])
                    filename = "%s/%s.png" % (split, item["sampleId"])
                    archive.write(source, "images/" + filename)
                    coco[split]["images"].append({
                        "id": image_id, "file_name": filename,
                        "width": item.get("imageWidth"), "height": item.get("imageHeight"),
                        "document_sha256": item.get("documentSha256"),
                        "sample_id": item.get("sampleId"),
                    })
                    targets = (item.get("annotation") or {}).get("targets") or []
                    for target in targets:
                        box = target["bboxXyxy"]
                        width, height = box[2] - box[0], box[3] - box[1]
                        coco[split]["annotations"].append({
                            "id": annotation_id, "image_id": image_id,
                            "category_id": category_ids[target["class"]],
                            "bbox": [box[0], box[1], width, height], "area": width * height,
                            "iscrowd": 0, "dots": target.get("dots", 0),
                        })
                        annotation_id += 1
                for split, payload in coco.items():
                    archive.writestr("annotations/%s.json" % split,
                                     json.dumps(payload, ensure_ascii=False, indent=2))
                archive.writestr("dataset-manifest.json", json.dumps({
                    "schemaVersion": 1, "createdAt": _utcnow(),
                    "sampleCount": len(records),
                    "documentCount": len(set(item.get("documentSha256") for item in records)),
                    "splitBy": "documentSha256", "sourcePdfIncluded": False,
                }, ensure_ascii=False, indent=2))
            return archive_path
        except Exception:
            try:
                os.unlink(archive_path)
            except OSError:
                pass
            raise
