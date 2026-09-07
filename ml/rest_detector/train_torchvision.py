"""Train the first rest-object detector from a reviewed COCO export.

The split must already be document-level.  This script intentionally keeps the
model advisory: deployment thresholds and score-editing policy live elsewhere.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageFilter
from torch.utils.data import DataLoader, Dataset, Sampler
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_FPN_Weights,
    fasterrcnn_mobilenet_v3_large_fpn,
)
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.transforms.functional import pil_to_tensor


class CocoRestDataset(Dataset):
    def __init__(self, root: Path, split: str, augment: bool = False):
        self.root = root
        self.split = split
        self.augment = augment
        payload = json.loads((root / "annotations" / f"{split}.json").read_text(encoding="utf-8"))
        self.categories = {int(item["id"]): item["name"] for item in payload["categories"]}
        self.images = payload["images"]
        self.annotations = defaultdict(list)
        for item in payload["annotations"]:
            self.annotations[int(item["image_id"])].append(item)

    def __len__(self):
        return len(self.images)

    def __getitem__(self, index):
        info = self.images[index]
        image = Image.open(self.root / "images" / info["file_name"]).convert("RGB")
        if self.augment:
            image = self._photometric_augment(image)
        boxes, labels = [], []
        for item in self.annotations[int(info["id"])]:
            x, y, width, height = item["bbox"]
            boxes.append([x, y, x + width, y + height])
            labels.append(int(item["category_id"]))
        target = {
            "boxes": torch.as_tensor(boxes, dtype=torch.float32).reshape(-1, 4),
            "labels": torch.as_tensor(labels, dtype=torch.int64),
            "image_id": torch.tensor([int(info["id"])], dtype=torch.int64),
            "area": torch.as_tensor([(b[2] - b[0]) * (b[3] - b[1]) for b in boxes],
                                    dtype=torch.float32),
            "iscrowd": torch.zeros((len(boxes),), dtype=torch.int64),
        }
        return pil_to_tensor(image).float().div(255.0), target

    @staticmethod
    def _photometric_augment(image):
        if random.random() < 0.7:
            image = ImageEnhance.Contrast(image).enhance(random.uniform(0.78, 1.25))
        if random.random() < 0.5:
            image = ImageEnhance.Brightness(image).enhance(random.uniform(0.90, 1.08))
        if random.random() < 0.2:
            image = image.filter(ImageFilter.GaussianBlur(random.uniform(0.2, 0.7)))
        return image


def collate(batch):
    return tuple(zip(*batch))


class PositiveAwareBatchSampler(Sampler):
    """Shuffle every epoch while avoiding batches made only from negative crops."""

    def __init__(self, dataset, batch_size, seed):
        self.dataset = dataset
        self.batch_size = max(1, int(batch_size))
        self.seed = int(seed)
        self.epoch = 0

    def __len__(self):
        return math.ceil(len(self.dataset) / self.batch_size)

    def _is_positive(self, index):
        image_id = int(self.dataset.images[index]["id"])
        return bool(self.dataset.annotations[image_id])

    def __iter__(self):
        indices = list(range(len(self.dataset)))
        random.Random(self.seed + self.epoch).shuffle(indices)
        self.epoch += 1
        batches = [indices[start:start + self.batch_size]
                   for start in range(0, len(indices), self.batch_size)]
        for batch in batches:
            if any(self._is_positive(index) for index in batch):
                continue
            donor = next((candidate for candidate in batches
                          if sum(self._is_positive(index) for index in candidate) >= 2), None)
            if donor is None:
                continue
            donor_position = next(index for index, value in enumerate(donor)
                                  if self._is_positive(value))
            donor[donor_position], batch[0] = batch[0], donor[donor_position]
        yield from batches


def box_iou(one, two):
    left = max(one[0], two[0])
    top = max(one[1], two[1])
    right = min(one[2], two[2])
    bottom = min(one[3], two[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = ((one[2] - one[0]) * (one[3] - one[1]) +
             (two[2] - two[0]) * (two[3] - two[1]) - intersection)
    return intersection / union if union > 0 else 0.0


def average_precision(recalls, precisions):
    if not recalls:
        return 0.0
    values = []
    for threshold in np.linspace(0.0, 1.0, 101):
        values.append(max((p for r, p in zip(recalls, precisions) if r >= threshold), default=0.0))
    return float(np.mean(values))


@torch.inference_mode()
def evaluate(model, loader, device, category_names, score_threshold=0.05, iou_threshold=0.5):
    model.eval()
    ground_truth = defaultdict(lambda: defaultdict(list))
    detections = defaultdict(list)
    image_count = 0
    for images, targets in loader:
        outputs = model([image.to(device) for image in images])
        for target, output in zip(targets, outputs):
            image_id = int(target["image_id"].item())
            image_count += 1
            for box, label in zip(target["boxes"].tolist(), target["labels"].tolist()):
                ground_truth[int(label)][image_id].append(box)
            for box, label, score in zip(output["boxes"].cpu().tolist(),
                                         output["labels"].cpu().tolist(),
                                         output["scores"].cpu().tolist()):
                if score >= score_threshold:
                    detections[int(label)].append((float(score), image_id, box))

    per_class = {}
    aps = []
    for category_id, name in category_names.items():
        truth_count = sum(len(boxes) for boxes in ground_truth[category_id].values())
        if truth_count == 0:
            continue
        matched = {image_id: [False] * len(boxes)
                   for image_id, boxes in ground_truth[category_id].items()}
        tp, fp = [], []
        for score, image_id, predicted in sorted(detections[category_id], reverse=True):
            candidates = ground_truth[category_id].get(image_id, [])
            best_index, best_iou = -1, 0.0
            for index, expected in enumerate(candidates):
                value = box_iou(predicted, expected)
                if not matched[image_id][index] and value > best_iou:
                    best_index, best_iou = index, value
            if best_index >= 0 and best_iou >= iou_threshold:
                matched[image_id][best_index] = True
                tp.append(1)
                fp.append(0)
            else:
                tp.append(0)
                fp.append(1)
        cumulative_tp = np.cumsum(tp)
        cumulative_fp = np.cumsum(fp)
        recalls = (cumulative_tp / max(1, truth_count)).tolist()
        precisions = (cumulative_tp / np.maximum(1, cumulative_tp + cumulative_fp)).tolist()
        ap = average_precision(recalls, precisions)
        aps.append(ap)
        per_class[name] = {
            "groundTruth": truth_count,
            "detections": len(detections[category_id]),
            "ap50": round(ap, 6),
            "maxRecall50": round(max(recalls, default=0.0), 6),
        }
    return {
        "imageCount": image_count,
        "map50": round(float(np.mean(aps)) if aps else 0.0, 6),
        "perClass": per_class,
    }


def create_model(num_classes, min_size, max_size):
    model = fasterrcnn_mobilenet_v3_large_fpn(
        weights=FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT,
        min_size=min_size,
        max_size=max_size,
        trainable_backbone_layers=3,
    )
    features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(features, num_classes)
    return model


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--min-size", type=int, default=320)
    parser.add_argument("--max-size", type=int, default=960)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--max-non-finite-batches", type=int, default=3,
                        help="Abort an epoch after this many non-finite batches")
    parser.add_argument("--resume", type=Path,
                        help="Initialize model weights from a compatible training checkpoint")
    parser.add_argument("--amp", action="store_true",
                        help="Enable mixed precision; leave off if detection losses become unstable")
    return parser.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_data = CocoRestDataset(args.data, "train", augment=True)
    validation_data = CocoRestDataset(args.data, "validation")
    test_data = CocoRestDataset(args.data, "test")
    if not train_data or not validation_data or not test_data:
        raise SystemExit("train/validation/test must each contain at least one image")
    loaders = {
        "train": DataLoader(
            train_data,
            batch_sampler=PositiveAwareBatchSampler(train_data, args.batch_size, args.seed),
            num_workers=args.workers, collate_fn=collate, pin_memory=device.type == "cuda"),
        "validation": DataLoader(validation_data, batch_size=1, shuffle=False,
                                 num_workers=args.workers, collate_fn=collate),
        "test": DataLoader(test_data, batch_size=1, shuffle=False,
                           num_workers=args.workers, collate_fn=collate),
    }
    category_names = train_data.categories
    model = create_model(max(category_names) + 1, args.min_size, args.max_size).to(device)
    initialized_from = None
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        checkpoint_categories = {int(key): value
                                 for key, value in checkpoint.get("categories", {}).items()}
        if checkpoint_categories != category_names:
            raise SystemExit("resume checkpoint categories do not match the training dataset")
        model.load_state_dict(checkpoint["model"])
        initialized_from = str(args.resume.resolve())
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate,
                                  weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))
    use_amp = bool(args.amp and device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    args.output.mkdir(parents=True, exist_ok=True)
    history, best_map, stale = [], -1.0, 0
    non_finite_batches = []
    started = time.time()
    stop_reason = "epochs_completed"
    print(json.dumps({"device": str(device), "train": len(train_data),
                      "validation": len(validation_data), "test": len(test_data)}))
    for epoch in range(1, args.epochs + 1):
        model.train()
        losses = []
        epoch_non_finite = 0
        for batch_index, (images, targets) in enumerate(loaders["train"], start=1):
            images = [image.to(device, non_blocking=True) for image in images]
            targets = [{key: value.to(device) for key, value in target.items()}
                       for target in targets]
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=use_amp):
                loss_map = model(images, targets)
                loss = sum(loss_map.values())
            if not math.isfinite(float(loss.detach())):
                epoch_non_finite += 1
                incident = {
                    "epoch": epoch,
                    "batch": batch_index,
                    "imageIds": [int(target["image_id"].item()) for target in targets],
                }
                non_finite_batches.append(incident)
                optimizer.zero_grad(set_to_none=True)
                print(json.dumps({"warning": "non_finite_batch", **incident}), flush=True)
                if epoch_non_finite >= args.max_non_finite_batches:
                    stop_reason = "too_many_non_finite_batches_epoch_%d" % epoch
                    break
                continue
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach()))
        if not losses or stop_reason.startswith("too_many_non_finite"):
            break
        scheduler.step()
        metrics = evaluate(model, loaders["validation"], device, category_names)
        entry = {"epoch": epoch, "loss": round(float(np.mean(losses)), 6),
                 "learningRate": optimizer.param_groups[0]["lr"], "validation": metrics}
        history.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if metrics["map50"] > best_map + 1e-6:
            best_map, stale = metrics["map50"], 0
            torch.save({
                "model": model.state_dict(), "categories": category_names,
                "architecture": "fasterrcnn_mobilenet_v3_large_fpn",
                "minSize": args.min_size, "maxSize": args.max_size,
                "epoch": epoch, "validation": metrics,
            }, args.output / "best.pt")
        else:
            stale += 1
            if stale >= args.patience:
                stop_reason = "early_stopping"
                break

    checkpoint = torch.load(args.output / "best.pt", map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model"])
    final = {
        "architecture": checkpoint["architecture"], "device": str(device),
        "bestEpoch": checkpoint["epoch"], "elapsedSeconds": round(time.time() - started, 2),
        "stopReason": stop_reason, "mixedPrecision": use_amp,
        "initializedFrom": initialized_from,
        "nonFiniteBatches": non_finite_batches,
        "dataset": {"train": len(train_data), "validation": len(validation_data),
                    "test": len(test_data)},
        "validation": evaluate(model, loaders["validation"], device, category_names),
        "test": evaluate(model, loaders["test"], device, category_names),
        "history": history,
    }
    (args.output / "metrics.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
