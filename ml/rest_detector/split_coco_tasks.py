"""Split the reviewed score-object COCO export into task-specific datasets.

The source archive contains both object-centric rest crops and full staff-system
crops.  Training separate detectors prevents abundant barlines from changing
the rest classifier's output space, while retaining hard negatives from each
task's own crops.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path


REST_CLASSES = {
    "maxima_rest", "long_rest", "breve_rest", "whole_rest", "half_rest",
    "quarter_rest", "eighth_rest", "16th_rest", "32nd_rest", "64th_rest",
    "128th_rest", "multi_measure_rest",
}
STRUCTURE_CLASSES = {
    "barline", "measure_number", "multi_measure_rest_number",
    "rehearsal_mark", "time_signature", "staff_system",
}
TASK_CLASSES = {"rest": REST_CLASSES, "structure": STRUCTURE_CLASSES}


def load_split(root: Path, split: str):
    return json.loads((root / "annotations" / f"{split}.json").read_text(encoding="utf-8"))


def selected_class_names(payloads, task):
    names = {int(item["id"]): item["name"] for item in payloads[0]["categories"]}
    present = Counter()
    for payload in payloads:
        present.update(names[int(item["category_id"])] for item in payload["annotations"])
    return [name for name in TASK_CLASSES[task] if present[name] > 0]


def split_dataset(source: Path, output: Path, task: str):
    splits = ("train", "validation", "test")
    payloads = {split: load_split(source, split) for split in splits}
    ordered_names = selected_class_names(list(payloads.values()), task)
    # Keep the source category order so checkpoints remain deterministic.
    source_categories = payloads["train"]["categories"]
    ordered_names.sort(key=lambda name: next(
        int(item["id"]) for item in source_categories if item["name"] == name))
    output_categories = [{"id": index + 1, "name": name}
                         for index, name in enumerate(ordered_names)]
    output_ids = {item["name"]: item["id"] for item in output_categories}
    output.mkdir(parents=True, exist_ok=True)
    (output / "annotations").mkdir(exist_ok=True)
    (output / "images").mkdir(exist_ok=True)
    manifest = {"schemaVersion": 1, "task": task, "classes": ordered_names,
                "splits": {}, "source": str(source)}
    annotation_id = 1
    for split, payload in payloads.items():
        source_names = {int(item["id"]): item["name"] for item in payload["categories"]}
        annotations_by_image = {}
        for annotation in payload["annotations"]:
            name = source_names[int(annotation["category_id"])]
            if name in TASK_CLASSES[task]:
                annotations_by_image.setdefault(int(annotation["image_id"]), []).append((annotation, name))
        images, annotations = [], []
        for image in payload["images"]:
            image_id = int(image["id"])
            relevant = annotations_by_image.get(image_id, [])
            is_task_crop = image.get("task_type", "rest") == task
            if not relevant and not is_task_crop:
                continue
            new_image = dict(image)
            images.append(new_image)
            source_image = source / "images" / image["file_name"]
            target_image = output / "images" / image["file_name"]
            target_image.parent.mkdir(parents=True, exist_ok=True)
            if not target_image.exists():
                shutil.copy2(source_image, target_image)
            for annotation, name in relevant:
                new_annotation = dict(annotation)
                new_annotation["id"] = annotation_id
                new_annotation["category_id"] = output_ids[name]
                annotations.append(new_annotation)
                annotation_id += 1
        result = {"images": images, "annotations": annotations,
                  "categories": output_categories}
        (output / "annotations" / f"{split}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["splits"][split] = {"images": len(images),
                                     "annotations": len(annotations)}
    (output / "dataset-task-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task", required=True, choices=sorted(TASK_CLASSES))
    args = parser.parse_args()
    print(json.dumps(split_dataset(args.source, args.output, args.task),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
