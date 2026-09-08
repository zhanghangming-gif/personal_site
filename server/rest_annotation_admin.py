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
STRUCTURE_CLASSES = (
    "barline", "measure_number", "multi_measure_rest_number",
    "rehearsal_mark", "time_signature", "staff_system",
)
ANNOTATION_CLASSES = REST_CLASSES + STRUCTURE_CLASSES
TEXT_CLASSES = {
    "measure_number", "multi_measure_rest_number", "rehearsal_mark",
    "time_signature",
}
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
    prelabels = item.get("prelabels") if isinstance(item.get("prelabels"), list) else []
    prelabels = [value for value in prelabels if isinstance(value, dict)]
    if prelabel and not prelabels:
        prelabels = [prelabel]
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
        "taskType": item.get("taskType", "rest"),
        "prelabel": prelabel, "prelabels": prelabels,
        "state": item.get("state", "unreviewed"),
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
        "counts": counts, "classes": list(ANNOTATION_CLASSES),
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
    if not isinstance(target, dict) or set(target) - {"class", "bboxXyxy", "dots", "text"}:
        raise ValueError("目标标注格式无效")
    class_name = target.get("class")
    if class_name not in ANNOTATION_CLASSES:
        raise ValueError("乐谱目标类别无效")
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
    if class_name not in REST_CLASSES and dots:
        raise ValueError("结构目标不能设置休止符附点")
    text = str(target.get("text") or "").strip()[:24]
    if class_name in TEXT_CLASSES and not text:
        raise ValueError("数字、拍号或排练标记请填写框内文字")
    result = {"class": class_name, "bboxXyxy": [round(value, 2) for value in box], "dots": dots}
    if text:
        result["text"] = text
    return result


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
        if not isinstance(targets, list) or len(targets) > 32:
            raise ValueError("每张裁片最多标注 32 个目标")
        if state in ("accepted", "corrected"):
            if not targets:
                raise ValueError("确认或修正样本至少需要一个目标框")
            targets = [_validate_target(target, width, height) for target in targets]
            if state == "accepted":
                prelabel = item.get("prelabel")
                raw_prelabels = (item.get("prelabels")
                                 if isinstance(item.get("prelabels"), list) else [])
                if not raw_prelabels and isinstance(prelabel, dict):
                    raw_prelabels = [prelabel]
                if not raw_prelabels:
                    raise ValueError("没有 OMR 预标的样本不能标记为直接接受")
                expected_targets = [_validate_target({
                    "class": value.get("class"), "bboxXyxy": value.get("bboxXyxy"),
                    "dots": value.get("dots", 0), "text": value.get("text", ""),
                }, width, height) for value in raw_prelabels if isinstance(value, dict)]
                if targets != expected_targets:
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
    command.extend(["--include-structure-systems",
                    "--max-structure-systems-per-document", "6"])
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=900, universal_newlines=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误").strip()[-600:]
        raise RuntimeError("刷新训练样本失败：%s" % detail)
    return list_samples(dataset_dir, "all", 0, 1)


def _training_record_rank(item):
    targets = (item.get("annotation") or {}).get("targets") or []
    state_rank = {"corrected": 3, "accepted": 2, "rejected": 1}.get(item.get("state"), 0)
    return (len(targets), state_rank, item.get("reviewedAt") or "", item.get("sampleId") or "")


def _deduplicate_training_records(dataset_dir, records):
    """Keep one reviewed annotation for byte-identical crops.

    Repeated OMR jobs can produce the same crop under different sample ids.  A
    detector must not see those copies as independent evidence.  When humans
    drew slightly different boxes on identical pixels, prefer the annotation
    that covers more visible rests, then a corrected/newer annotation.
    """
    groups = defaultdict(list)
    for item in records:
        path = sample_image_path(dataset_dir, item["sampleId"])
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        groups[digest.hexdigest()].append(item)
    selected = []
    conflict_count = 0
    for image_hash, copies in groups.items():
        signatures = set()
        for item in copies:
            targets = (item.get("annotation") or {}).get("targets") or []
            signatures.add(json.dumps(targets, ensure_ascii=False, sort_keys=True))
        if len(signatures) > 1:
            conflict_count += 1
        winner = max(copies, key=_training_record_rank)
        winner = dict(winner)
        winner["trainingImageSha256"] = image_hash
        selected.append(winner)
    selected.sort(key=lambda item: item.get("sampleId") or "")
    return selected, len(records) - len(selected), conflict_count


def _assign_document_splits(records):
    """Assign whole documents while balancing both documents and sample volume."""
    documents = defaultdict(list)
    class_documents = defaultdict(set)
    for item in records:
        document = item.get("documentSha256") or "unknown"
        documents[document].append(item)
        for target in (item.get("annotation") or {}).get("targets") or []:
            if target.get("class"):
                class_documents[target["class"]].add(document)
    count = len(documents)
    if count == 1:
        return {next(iter(documents)): "train"}
    if count == 2:
        names = sorted(documents, key=lambda name: (-len(documents[name]), name))
        return {names[0]: "train", names[1]: "validation"}

    validation_slots = max(1, int(round(count * 0.15)))
    test_slots = max(1, int(round(count * 0.15)))
    if validation_slots + test_slots >= count:
        validation_slots = test_slots = 1
    slots = {
        "train": count - validation_slots - test_slots,
        "validation": validation_slots,
        "test": test_slots,
    }
    total = float(len(records))
    target_samples = {"train": total * 0.70, "validation": total * 0.15, "test": total * 0.15}
    assigned_documents = {name: 0 for name in slots}
    assigned_samples = {name: 0 for name in slots}
    result = {}
    must_train = set()
    for sources in class_documents.values():
        if len(sources) == 1:
            must_train.update(sources)
    class_counts = defaultdict(lambda: defaultdict(int))
    for document, items in documents.items():
        for item in items:
            for target in (item.get("annotation") or {}).get("targets") or []:
                if target.get("class"):
                    class_counts[target["class"]][document] += 1
    for counts in class_counts.values():
        must_train.add(max(counts, key=lambda name: (counts[name], name)))
    must_train.update(item.get("documentSha256") or "unknown" for item in records
                      if item.get("state") == "rejected")
    ranked = sorted(documents, key=lambda name: (-len(documents[name]), hashlib.sha256(
        ("rest-split-v2|" + name).encode("utf-8")).hexdigest()))
    ordered = [name for name in ranked if name in must_train]
    ordered.extend(name for name in ranked if name not in must_train)
    priority = {"train": 0, "validation": 1, "test": 2}
    for document in ordered:
        candidates = (["train"] if document in must_train and
                      assigned_documents["train"] < slots["train"] else
                      [name for name in slots if assigned_documents[name] < slots[name]])
        split = min(candidates, key=lambda name: (
            assigned_samples[name] / max(1.0, target_samples[name]), priority[name]))
        result[document] = split
        assigned_documents[split] += 1
        assigned_samples[split] += len(documents[document])
    return result


def load_excluded_document_hashes(manifest_path):
    """Read immutable evaluation document hashes without requiring the PDFs."""
    if not manifest_path or not os.path.isfile(manifest_path):
        return set()
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    if (not isinstance(manifest, dict) or
            manifest.get("trainingPolicy") != "exclude_all_cases"):
        raise ValueError("固定评测清单没有声明训练隔离")
    result = set()
    for item in manifest.get("cases") or []:
        digest = str(item.get("sha256") or "").lower() if isinstance(item, dict) else ""
        if len(digest) == 64 and all(character in "0123456789abcdef" for character in digest):
            result.add(digest)
    return result


def build_training_archive(dataset_dir, excluded_document_hashes=None):
    """Build a temporary COCO zip from reviewed samples only."""
    with _LOCK:
        records = [item for item in _read_records(dataset_dir)
                   if item.get("state") in TRAINING_STATES]
        if not records:
            raise ValueError("还没有可导出的人工确认样本")
        reviewed_count = len(records)
        excluded = set(excluded_document_hashes or ())
        excluded_sample_count = sum(
            (item.get("documentSha256") or "").lower() in excluded for item in records)
        records = [item for item in records
                   if (item.get("documentSha256") or "").lower() not in excluded]
        if not records:
            raise ValueError("人工确认样本均属于固定评测集，不能导入训练")
        records, duplicate_count, conflict_count = _deduplicate_training_records(dataset_dir, records)
        document_splits = _assign_document_splits(records)
        descriptor, archive_path = tempfile.mkstemp(prefix="rest-training-", suffix=".zip")
        os.close(descriptor)
        categories = [{"id": index + 1, "name": name}
                      for index, name in enumerate(ANNOTATION_CLASSES)]
        category_ids = {item["name"]: item["id"] for item in categories}
        coco = {split: {"images": [], "annotations": [], "categories": categories}
                for split in ("train", "validation", "test")}
        annotation_id = 1
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for image_id, item in enumerate(records, 1):
                    split = document_splits[item.get("documentSha256") or "unknown"]
                    source = sample_image_path(dataset_dir, item["sampleId"])
                    filename = "%s/%s.png" % (split, item["sampleId"])
                    archive.write(source, "images/" + filename)
                    coco[split]["images"].append({
                        "id": image_id, "file_name": filename,
                        "width": item.get("imageWidth"), "height": item.get("imageHeight"),
                        "document_sha256": item.get("documentSha256"),
                        "sample_id": item.get("sampleId"),
                        "image_sha256": item.get("trainingImageSha256"),
                        "review_state": item.get("state"),
                        "reviewed_at": item.get("reviewedAt"),
                        "task_type": item.get("taskType") or "rest",
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
                            "text": target.get("text", ""),
                        })
                        annotation_id += 1
                for split, payload in coco.items():
                    archive.writestr("annotations/%s.json" % split,
                                     json.dumps(payload, ensure_ascii=False, indent=2))
                archive.writestr("dataset-manifest.json", json.dumps({
                    "schemaVersion": 2, "createdAt": _utcnow(),
                    "sampleCount": len(records),
                    "reviewedSampleCount": reviewed_count,
                    "excludedEvaluationSampleCount": excluded_sample_count,
                    "evaluationDocumentsExcluded": len(excluded),
                    "duplicateSampleCount": duplicate_count,
                    "conflictingDuplicateGroupCount": conflict_count,
                    "documentCount": len(set(item.get("documentSha256") for item in records)),
                    "splitBy": "documentSha256", "sourcePdfIncluded": False,
                    "annotationClasses": list(ANNOTATION_CLASSES),
                    "splits": {name: sum(1 for item in records if
                                          document_splits[item.get("documentSha256") or "unknown"] == name)
                               for name in ("train", "validation", "test")},
                }, ensure_ascii=False, indent=2))
            return archive_path
        except Exception:
            try:
                os.unlink(archive_path)
            except OSError:
                pass
            raise
