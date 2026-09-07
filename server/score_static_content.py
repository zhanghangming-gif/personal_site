"""Preserve source PDF headers when a score must be fully re-engraved."""
import argparse
import hashlib
import json
from pathlib import Path

import pymupdf


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_first_systems(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    result = {}
    for page in value.get("pages", []):
        systems = page.get("systems") or []
        if not systems:
            continue
        bbox = systems[0].get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            result[int(page.get("page"))] = {
                "bbox": [float(item) for item in bbox],
                "staffSpacing": float(systems[0].get("staffSpacing") or 0),
            }
    return result


def preserve_headers(source_pdf, target_pdf, source_structures, target_structures, output_pdf):
    """Copy the safe band above the first staff from source into target pages.

    The bottom edge is the smaller of the source and target first-system tops,
    so this operation cannot paint over re-engraved notation.  It works for
    vector, scanned and mixed PDFs because the source region is embedded as a
    PDF clip instead of being reconstructed from OCR text.
    """
    source_first = read_first_systems(source_structures)
    target_first = read_first_systems(target_structures)
    source = pymupdf.open(source_pdf)
    target = pymupdf.open(target_pdf)
    if source.needs_pass or target.needs_pass or not len(source):
        raise ValueError("PDF 无法读取或需要密码")
    if len(source) != len(target):
        raise ValueError("源谱与候选谱页数不一致")

    output = pymupdf.open()
    pages = []
    for index, (source_page, target_page) in enumerate(zip(source, target), 1):
        source_rect, target_rect = source_page.rect, target_page.rect
        width_delta = abs(source_rect.width - target_rect.width)
        height_delta = abs(source_rect.height - target_rect.height)
        if width_delta > 2 or height_delta > 2:
            raise ValueError("源谱与候选谱页面尺寸不一致")
        page = output.new_page(width=source_rect.width, height=source_rect.height)
        source_box = source_first.get(index)
        target_box = target_first.get(index)
        if not source_box or not target_box:
            page.show_pdf_page(page.rect, target, index - 1, keep_proportion=False)
            pages.append({"page": index, "status": "skipped", "reason": "缺少首个谱表坐标"})
            continue
        source_bbox, target_bbox = source_box["bbox"], target_box["bbox"]
        source_spacing = source_box.get("staffSpacing") or 0
        target_spacing = target_box.get("staffSpacing") or 0
        # Raster structure boxes extend five staff spaces above the first line.
        # Copy through the half-space above that line so tempo and title text
        # come from the source, while the target crop starts at the equivalent
        # point and does not duplicate those first-system directions.
        source_bottom = min(
            float(source_bbox[1]) + (4.5 * source_spacing if source_spacing else 0),
            source_rect.height)
        target_top = min(
            float(target_bbox[1]) + (4.5 * target_spacing if target_spacing else 0),
            target_rect.height)
        reflowed = (
            source_bottom > target_top + 2
            and source_bottom < source_rect.height - 18
            and target_top < target_rect.height - 18
        )
        if reflowed:
            # Reserve the source's complete title/running-header band. The
            # target notation begins at its detected first-system band and is
            # fitted into the remaining page, so preserving a taller source
            # title never paints over the first staff.
            target_clip = pymupdf.Rect(0, target_top, target_rect.width, target_rect.height)
            target_destination = pymupdf.Rect(
                0, source_bottom, source_rect.width, source_rect.height)
            page.show_pdf_page(target_destination, target, index - 1,
                               clip=target_clip, keep_proportion=False)
            bottom = source_bottom
        else:
            page.show_pdf_page(page.rect, target, index - 1, keep_proportion=False)
            bottom = min(source_bottom, target_top)
        # Very small bands contain neither a title nor a usable running header.
        if bottom < 18:
            pages.append({"page": index, "status": "skipped", "reason": "安全标题区过小"})
            continue
        clip = pymupdf.Rect(0, 0, source_rect.width, bottom)
        destination = pymupdf.Rect(0, 0, target_rect.width, bottom)
        page.draw_rect(destination, color=None, fill=(1, 1, 1), overlay=True)
        page.show_pdf_page(destination, source, index - 1, clip=clip,
                           keep_proportion=False, overlay=True)
        pages.append({
            "page": index,
            "status": "preserved",
            "bbox": [round(value, 4) for value in destination],
            "targetNotationFittedBelowHeader": reflowed,
        })

    output_path = Path(output_pdf)
    output.save(output_path, garbage=4, deflate=True)
    output.close()
    source.close()
    target.close()
    preserved = sum(item["status"] == "preserved" for item in pages)
    if not preserved:
        if output_path.exists():
            output_path.unlink()
        raise ValueError("没有可安全保留的页眉区域")
    return {
        "schemaVersion": 1,
        "mode": "source_header_preservation",
        "sourceSha256": digest(source_pdf),
        "targetSha256": digest(target_pdf),
        "outputSha256": digest(output_path),
        "pages": pages,
        "preservedPages": preserved,
        "preservesRasterAndVectorContent": True,
        "semanticVerification": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_pdf")
    parser.add_argument("target_pdf")
    parser.add_argument("source_structures")
    parser.add_argument("target_structures")
    parser.add_argument("output_pdf")
    parser.add_argument("report")
    arguments = parser.parse_args()
    report = preserve_headers(
        arguments.source_pdf, arguments.target_pdf,
        arguments.source_structures, arguments.target_structures,
        arguments.output_pdf,
    )
    Path(arguments.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"preservedPages": report["preservedPages"]}))


if __name__ == "__main__":
    main()
