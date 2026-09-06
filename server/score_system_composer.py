"""Compose verified target system clips into the original PDF page geometry."""
import argparse
import hashlib
import json
from pathlib import Path

import pymupdf


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_structures(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    pages = []
    for page in value.get('pages', []):
        systems = []
        for system in page.get('systems') or []:
            bbox = system.get('bbox')
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError('系统区域坐标无效')
            systems.append([float(item) for item in bbox])
        pages.append({'page': int(page.get('page')), 'systems': systems})
    return pages


def compose_systems(source_pdf, target_pdf, source_structures, target_structures, output_pdf):
    source_pages = read_structures(source_structures)
    target_pages = read_structures(target_structures)
    source = pymupdf.open(source_pdf)
    target = pymupdf.open(target_pdf)
    if source.needs_pass or target.needs_pass or not len(source):
        raise ValueError('PDF 无法读取或需要密码')
    if not (len(source) == len(target) == len(source_pages) == len(target_pages)):
        raise ValueError('源谱、候选谱与结构映射页数不一致')
    output = pymupdf.open()
    mappings = []
    for index, (source_page, target_page, source_map, target_map) in enumerate(
            zip(source, target, source_pages, target_pages)):
        if source_map['page'] != index + 1 or target_map['page'] != index + 1:
            raise ValueError('结构映射页码不连续')
        if len(source_map['systems']) != len(target_map['systems']) or not source_map['systems']:
            raise ValueError('每页系统数量不一致，不能按系统贴回原页')
        page = output.new_page(width=source_page.rect.width, height=source_page.rect.height)
        page.show_pdf_page(page.rect, source, index, keep_proportion=False)
        previous_bottom = None
        for system_index, (source_bbox, target_bbox) in enumerate(
                zip(source_map['systems'], target_map['systems']), 1):
            destination = pymupdf.Rect(source_bbox) & page.rect
            clip = pymupdf.Rect(target_bbox) & target_page.rect
            if destination.is_empty or clip.is_empty or destination.width < 20 or clip.width < 20:
                raise ValueError('系统区域超出页面或尺寸过小')
            if previous_bottom is not None and destination.y0 < previous_bottom:
                raise ValueError('源谱系统区域存在重叠，不能安全贴回')
            previous_bottom = destination.y1
            source_ratio = destination.width / max(destination.height, 1.0)
            target_ratio = clip.width / max(clip.height, 1.0)
            ratio_delta = abs(source_ratio - target_ratio) / max(source_ratio, target_ratio, 1.0)
            if ratio_delta > 0.12:
                raise ValueError('源谱与候选谱系统长宽比差异过大，不能安全贴回')
            # Cover only the source staff region. Marginal printed measure
            # numbers, page numbers and headers outside this box remain intact.
            page.draw_rect(destination, color=None, fill=(1, 1, 1), overlay=True)
            page.show_pdf_page(destination, target, index, clip=clip,
                               keep_proportion=True, overlay=True)
            mappings.append({
                'page': index + 1, 'system': system_index,
                'sourceBbox': [round(value, 4) for value in destination],
                'targetBbox': [round(value, 4) for value in clip],
                'aspectRatioDelta': round(ratio_delta, 6),
            })
    output_path = Path(output_pdf)
    output.save(output_path, garbage=4, deflate=True)
    output.close()
    report = {
        'schemaVersion': 1,
        'mode': 'system_recompose',
        'sourceSha256': digest(source_pdf),
        'targetSha256': digest(target_pdf),
        'outputSha256': digest(output_path),
        'pages': len(source), 'systems': len(mappings), 'mappings': mappings,
        'preservedOutsideSystemRegions': True,
        'semanticVerification': False,
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_pdf')
    parser.add_argument('target_pdf')
    parser.add_argument('source_structures')
    parser.add_argument('target_structures')
    parser.add_argument('output_pdf')
    parser.add_argument('report')
    arguments = parser.parse_args()
    report = compose_systems(arguments.source_pdf, arguments.target_pdf,
                             arguments.source_structures, arguments.target_structures,
                             arguments.output_pdf)
    Path(arguments.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pages': report['pages'], 'systems': report['systems']}))


if __name__ == '__main__':
    main()
