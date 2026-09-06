"""Multi-scale PDF inspection for the isolated score Python environment."""
import argparse
import io
import hashlib
import json
import os
import statistics
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def rect_value(rect):
    return [round(float(value), 4) for value in rect]


def matrix_value(matrix):
    return [round(float(value), 8) for value in matrix]


def atomic_json(path, value):
    temporary = str(path) + '.tmp'
    Path(temporary).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def text_objects(page, limit=30000):
    objects = []
    raw = page.get_text('rawdict')
    for block in raw.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                for char in span.get('chars', []):
                    objects.append({
                        'char': char.get('c', ''),
                        'bbox': rect_value(char.get('bbox', (0, 0, 0, 0))),
                        'origin': [round(float(x), 4) for x in char.get('origin', (0, 0))],
                        'font': span.get('font', ''),
                        'size': round(float(span.get('size', 0)), 3),
                        'flags': int(span.get('flags', 0)),
                    })
                    if len(objects) >= limit:
                        return objects, True
    return objects, False


def drawing_objects(page, limit=12000):
    result = []
    drawings = page.get_drawings()
    for drawing in drawings[:limit]:
        result.append({
            'bbox': rect_value(drawing.get('rect', (0, 0, 0, 0))),
            'type': drawing.get('type', ''),
            'itemCount': len(drawing.get('items', [])),
            'width': round(float(drawing.get('width') or 0), 4),
            'fill': list(drawing['fill']) if drawing.get('fill') else None,
            'color': list(drawing['color']) if drawing.get('color') else None,
        })
    return result, len(drawings) > limit


def image_objects(page):
    values = []
    for item in page.get_image_info(xrefs=True):
        values.append({
            'xref': int(item.get('xref') or 0),
            'bbox': rect_value(item.get('bbox', (0, 0, 0, 0))),
            'width': int(item.get('width') or 0),
            'height': int(item.get('height') or 0),
            'colorspace': int(item.get('colorspace') or 0),
        })
    return values


def page_kind(page, characters, drawings, images):
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    raster_area = 0.0
    for image in images:
        box = image['bbox']
        raster_area += max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    raster_coverage = min(1.0, raster_area / page_area)
    vector_signal = len(drawings) + len(characters)
    if raster_coverage >= 0.72 and vector_signal < 40:
        kind = 'scan'
    elif raster_coverage >= 0.12 and vector_signal >= 20:
        kind = 'mixed'
    else:
        kind = 'vector'
    return kind, round(raster_coverage, 4)


def render_page(page, output, dpi, grayscale=False):
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csGRAY if grayscale else pymupdf.csRGB,
        alpha=False,
    )
    pixmap.save(str(output))
    return {
        'path': str(output).replace('\\', '/'),
        'dpi': dpi,
        'scale': dpi / 72.0,
        'pixelWidth': pixmap.width,
        'pixelHeight': pixmap.height,
        'sha256': digest(output),
    }


def render_region(source, job_dir, page_number, bbox, dpi=800, grayscale=True):
    """Render an exact PDF-point region for adaptive visual inspection."""
    if type(page_number) is not int or page_number < 1:
        raise ValueError('页码无效')
    if type(dpi) is not int or not 144 <= dpi <= 800:
        raise ValueError('局部渲染 DPI 必须在 144 至 800 之间')
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError('局部坐标必须包含四个数值')
    values = [float(value) for value in bbox]
    document = pymupdf.open(source)
    if document.needs_pass or page_number > len(document):
        raise ValueError('PDF 页码无效或需要密码')
    page = document[page_number - 1]
    requested = pymupdf.Rect(values)
    clipped = requested & page.rect
    if clipped.is_empty or clipped.width < 2 or clipped.height < 2:
        raise ValueError('局部坐标不在页面范围内')
    token = hashlib.sha256(json.dumps(
        [page_number, rect_value(clipped), dpi, bool(grayscale)],
        separators=(',', ':')).encode()).hexdigest()[:20]
    output_dir = Path(job_dir) / 'renders' / 'regions'
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ('page-%04d-%s.png' % (page_number, token))
    pixmap = page.get_pixmap(
        dpi=dpi, clip=clipped,
        colorspace=pymupdf.csGRAY if grayscale else pymupdf.csRGB,
        alpha=False,
    )
    pixmap.save(str(output))
    return {
        'schemaVersion': 1,
        'page': page_number,
        'bbox': rect_value(clipped),
        'coordinateSystem': 'pymupdf_unrotated_points_top_left',
        'dpi': dpi,
        'scale': dpi / 72.0,
        'pixelWidth': pixmap.width,
        'pixelHeight': pixmap.height,
        'path': output.relative_to(Path(job_dir)).as_posix(),
        'sha256': digest(output),
    }


def prepare_omr_variant(source, job_dir, dpi=300):
    """Create a page-size-preserving grayscale/autocontrast OMR candidate."""
    if type(dpi) is not int or not 200 <= dpi <= 400:
        raise ValueError('识谱增强 DPI 必须在 200 至 400 之间')
    document = pymupdf.open(source)
    if document.needs_pass or not 1 <= len(document) <= 20:
        raise ValueError('PDF 页数无效或需要密码')
    output_path = Path(job_dir) / 'inspection' / 'omr-normalized.pdf'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = pymupdf.open()
    page_rows = []
    for page_number, page in enumerate(document, 1):
        pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        picture = Image.frombytes('L', (pixmap.width, pixmap.height), pixmap.samples)
        enhanced = ImageOps.autocontrast(picture, cutoff=0.5)
        stream = io.BytesIO()
        enhanced.save(stream, format='JPEG', quality=92, optimize=True)
        target = output.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=stream.getvalue())
        page_rows.append({'page': page_number, 'pixelWidth': pixmap.width,
                          'pixelHeight': pixmap.height, 'dpi': dpi})
        enhanced.close()
        picture.close()
    output.save(output_path, garbage=4, deflate=True)
    output.close()
    if output_path.stat().st_size > 40 * 1024 * 1024:
        output_path.unlink()
        raise ValueError('识谱增强副本超过任务大小限制')
    return {
        'schemaVersion': 1,
        'path': output_path.relative_to(Path(job_dir)).as_posix(),
        'sha256': digest(output_path),
        'size': output_path.stat().st_size,
        'pages': page_rows,
        'representation': 'grayscale_autocontrast_raster_pdf',
        'semanticVerification': False,
    }


def grouped_centers(values):
    groups = []
    for value in values:
        if not groups or value > groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [sum(group) / len(group) for group in groups]


def raster_structure_candidates(image_path, page_rect, rotation=0):
    """Find likely five-line staves in scans. Results remain unverified evidence."""
    if rotation or not page_rect[2] or not page_rect[3]:
        return []
    with Image.open(image_path) as opened:
        image = opened.convert('L')
        width, height = image.size
        ink = image.point([255 if value < 165 else 0 for value in range(256)])
        row_projection = ink.resize((1, height), Image.Resampling.BOX)
        row_hits = [y for y in range(height) if row_projection.getpixel((0, y)) >= 75]
        lines = grouped_centers(row_hits)
        scale_x = width / float(page_rect[2])
        scale_y = height / float(page_rect[3])
        systems, position = [], 0
        while position + 4 < len(lines):
            group = lines[position:position + 5]
            gaps = [group[index + 1] - group[index] for index in range(4)]
            spacing = statistics.median(gaps)
            tolerance = max(2.0, spacing * 0.28)
            if 4 <= spacing <= height / 25.0 and max(abs(gap - spacing) for gap in gaps) <= tolerance:
                upper = max(0, int(group[0] - 2))
                lower = min(height, int(group[-1] + 3))
                band = ink.crop((0, upper, width, lower))
                column_projection = band.resize((width, 1), Image.Resampling.BOX)
                column_hits = [x for x in range(width)
                               if column_projection.getpixel((x, 0)) >= 185]
                barlines = grouped_centers(column_hits)
                left_px = max(0.0, min(barlines) if barlines else width * 0.04)
                right_px = min(float(width), max(barlines) if barlines else width * 0.96)
                top_px = max(0.0, group[0] - 5 * spacing)
                bottom_px = min(float(height), group[-1] + 6 * spacing)
                pdf_box = [left_px / scale_x, top_px / scale_y,
                           right_px / scale_x, bottom_px / scale_y]
                pdf_barlines = [value / scale_x for value in barlines
                                if left_px <= value <= right_px]
                edges = [pdf_box[0]] + [value for value in pdf_barlines
                                        if value > pdf_box[0] + 2 * spacing / scale_x]
                if not edges or edges[-1] < pdf_box[2] - 2 * spacing / scale_x:
                    edges.append(pdf_box[2])
                measures = [
                    {'candidateIndex': index, 'bbox': rect_value((start, pdf_box[1], end, pdf_box[3])),
                     'basis': 'raster_staff_and_vertical_line_candidate', 'semanticVerification': False}
                    for index, (start, end) in enumerate(zip(edges[:-1], edges[1:]), 1)
                    if end - start > 2 * spacing / scale_x
                ]
                systems.append({
                    'candidateIndex': len(systems) + 1,
                    'bbox': rect_value(pdf_box),
                    'staffSpacing': round(spacing / scale_y, 4),
                    'barlines': [round(value, 4) for value in pdf_barlines],
                    'measures': measures,
                    'basis': 'raster_projection_candidate',
                    'semanticVerification': False,
                })
                position += 5
            else:
                position += 1
        return systems


def inspect_pdf(source, job_dir, preflight=None, preview_dpi=150, analysis_dpi=400, role='source'):
    if role not in ('source', 'target'):
        raise ValueError('PDF 检查角色无效')
    job = Path(job_dir)
    inspection_dir = job / 'inspection'
    preview_dir = job / 'renders' / ('preview-150' if role == 'source' else 'target-preview-150')
    analysis_dir = job / 'renders' / ('analysis-400' if role == 'source' else 'target-analysis-400')
    for directory in (
        inspection_dir, preview_dir, analysis_dir, job / 'renders' / 'regions',
        job / 'evidence', job / 'layout' / role,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    document = pymupdf.open(source)
    if document.needs_pass:
        raise ValueError('PDF 需要密码，无法建立视觉工作区')
    preflight = preflight or {}
    preflight_pages = {item.get('page'): item for item in preflight.get('pageDetails', [])}
    page_reports, object_pages, coordinate_pages, structure_pages = [], [], [], []
    all_fonts, staff_spacings, measures_per_system = set(), [], []

    for index, page in enumerate(document, 1):
        characters, text_truncated = text_objects(page)
        drawings, drawings_truncated = drawing_objects(page)
        images = image_objects(page)
        fonts = sorted(set(str(item[3]) for item in page.get_fonts(full=True) if len(item) > 3 and item[3]))
        all_fonts.update(fonts)
        kind, raster_coverage = page_kind(page, characters, drawings, images)
        preview_path = preview_dir / ('page-%04d.png' % index)
        analysis_path = analysis_dir / ('page-%04d.png' % index)
        preview = render_page(page, preview_path, preview_dpi, False)
        analysis = render_page(page, analysis_path, analysis_dpi, True)
        preview['path'] = preview_path.relative_to(job).as_posix()
        analysis['path'] = analysis_path.relative_to(job).as_posix()

        vector_geometry = preflight_pages.get(index, {}).get('geometry', {})
        system_candidates = []
        for staff_index, staff in enumerate(vector_geometry.get('staves', []), 1):
            if staff.get('spacing'):
                staff_spacings.append(float(staff['spacing']))
            if staff.get('barlines'):
                measures_per_system.append(len(staff['barlines']))
            spacing = float(staff.get('spacing') or 0)
            if spacing <= 0:
                continue
            page_width = float(vector_geometry.get('width') or page.rect.width)
            page_height = float(vector_geometry.get('height') or page.rect.height)
            left = max(0.0, float(staff.get('left') or 0) - spacing)
            right = min(page_width, float(staff.get('right') or page_width) + spacing)
            top = max(0.0, float(staff.get('top') or 0) - 5 * spacing)
            bottom = min(page_height, float(staff.get('top') or 0) + 10 * spacing)
            barlines = sorted(float(value) for value in staff.get('barlines', [])
                              if left <= float(value) <= right)
            edges = [left] + [value for value in barlines if value > left + 2 * spacing]
            if not edges or edges[-1] < right - 2 * spacing:
                edges.append(right)
            measures = [
                {'candidateIndex': position, 'bbox': rect_value((start, top, end, bottom)),
                 'basis': 'pdf_vector_staff_and_barlines', 'semanticVerification': False}
                for position, (start, end) in enumerate(zip(edges[:-1], edges[1:]), 1)
                if end - start > 2 * spacing
            ]
            system_candidates.append({
                'candidateIndex': staff_index,
                'bbox': rect_value((left, top, right, bottom)),
                'staffSpacing': round(spacing, 4),
                'barlines': [round(value, 4) for value in barlines],
                'measures': measures,
                'basis': 'pdf_vector_geometry',
                'semanticVerification': False,
            })
        if not system_candidates:
            system_candidates = raster_structure_candidates(
                analysis_path, rect_value(page.rect), int(page.rotation))
        structure_pages.append({'page': index, 'systems': system_candidates})

        source_space = {
            'coordinateSystem': 'pymupdf_unrotated_points_top_left',
            'mediaBox': rect_value(page.mediabox),
            'cropBox': rect_value(page.cropbox),
            'pageRect': rect_value(page.rect),
            'rotation': int(page.rotation),
            'rotationMatrix': matrix_value(page.rotation_matrix),
            'derotationMatrix': matrix_value(page.derotation_matrix),
        }
        coordinate_pages.append({
            'page': index,
            'sourceSpace': source_space,
            'renders': {'preview': preview, 'analysis': analysis},
        })
        object_pages.append({
            'page': index,
            'fonts': fonts,
            'characters': characters,
            'charactersTruncated': text_truncated,
            'drawings': drawings,
            'drawingsTruncated': drawings_truncated,
            'images': images,
        })
        page_reports.append({
            'page': index,
            'type': kind,
            'rasterCoverage': raster_coverage,
            'characterObjects': len(characters),
            'drawingObjects': len(drawings),
            'imageObjects': len(images),
            'fonts': fonts,
            'preview': preview,
            'analysis': analysis,
            'vectorStaffSystems': len(vector_geometry.get('staves', [])),
        })

    profile = {
        'schemaVersion': 1,
        'documentType': (
            page_reports[0]['type'] if page_reports and all(x['type'] == page_reports[0]['type'] for x in page_reports)
            else 'mixed'
        ),
        'pages': len(page_reports),
        'pageTypes': [x['type'] for x in page_reports],
        'musicFonts': sorted(all_fonts),
        'vectorStaffSystems': sum(x['vectorStaffSystems'] for x in page_reports),
        'structureCandidateSystems': sum(len(x['systems']) for x in structure_pages),
        'structureCandidateMeasures': sum(
            len(system['measures']) for item in structure_pages for system in item['systems']),
        'staffSpacingPdfPointsMedian': round(statistics.median(staff_spacings), 4) if staff_spacings else None,
        'measuresPerSystemMedian': round(statistics.median(measures_per_system), 2) if measures_per_system else None,
        'recognitionPlan': {
            'previewDpi': preview_dpi,
            'analysisDpi': analysis_dpi,
            'detailDpi': 800,
            'adaptiveRegionRendering': True,
        },
        'confidence': {
            'classification': 'measured',
            'structure': 'candidate_only',
            'musicSemantics': 'unverified',
        },
    }
    object_evidence = {
        'schemaVersion': 1,
        'immutable': True,
        'role': role,
        'sourceSha256': digest(source),
        'pages': object_pages,
    }
    coordinate_map = {'schemaVersion': 1, 'pages': coordinate_pages}
    structure_candidates = {
        'schemaVersion': 1,
        'coordinateSystem': 'pymupdf_unrotated_points_top_left',
        'status': 'candidate_only',
        'pages': structure_pages,
    }
    evidence_name = 'source-evidence.json' if role == 'source' else 'target-render-evidence.json'
    coordinate_name = 'layout/%s/coordinate-map.json' % role
    profile_name = 'score-profile.json' if role == 'source' else 'target-score-profile.json'
    structures_name = 'structure-candidates.json' if role == 'source' else 'target-structure-candidates.json'
    inspection_name = 'inspection.json' if role == 'source' else 'target-inspection.json'
    report = {
        'schemaVersion': 1,
        'role': role,
        'engine': {'name': 'PyMuPDF', 'version': pymupdf.VersionBind},
        'sourceSha256': digest(source),
        'pageCount': len(page_reports),
        'pages': page_reports,
        'scoreProfile': profile,
        'artifacts': {
            'objectEvidence': 'evidence/' + evidence_name,
            'coordinateMap': coordinate_name,
            'scoreProfile': 'inspection/' + profile_name,
            'structureCandidates': 'inspection/' + structures_name,
        },
    }
    atomic_json(job / 'evidence' / evidence_name, object_evidence)
    atomic_json(job / 'layout' / role / 'coordinate-map.json', coordinate_map)
    atomic_json(inspection_dir / profile_name, profile)
    atomic_json(inspection_dir / structures_name, structure_candidates)
    atomic_json(inspection_dir / inspection_name, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--job-dir', required=True)
    parser.add_argument('--preflight')
    parser.add_argument('--preview-dpi', type=int, default=150)
    parser.add_argument('--analysis-dpi', type=int, default=400)
    parser.add_argument('--page', type=int)
    parser.add_argument('--bbox', nargs=4, type=float)
    parser.add_argument('--dpi', type=int, default=800)
    parser.add_argument('--role', choices=('source', 'target'), default='source')
    parser.add_argument('--prepare-omr-variant', action='store_true')
    arguments = parser.parse_args()
    loaded = {}
    if arguments.preflight and os.path.isfile(arguments.preflight):
        loaded = json.loads(Path(arguments.preflight).read_text(encoding='utf-8'))
    if arguments.prepare_omr_variant:
        result = prepare_omr_variant(arguments.source, arguments.job_dir, arguments.dpi)
        print(json.dumps(result))
    elif arguments.page is not None or arguments.bbox is not None:
        if arguments.page is None or arguments.bbox is None:
            raise ValueError('局部渲染需要同时提供页码和坐标')
        result = render_region(
            arguments.source, arguments.job_dir, arguments.page, arguments.bbox, arguments.dpi)
        print(json.dumps(result))
    else:
        result = inspect_pdf(arguments.source, arguments.job_dir, loaded, arguments.preview_dpi,
                             arguments.analysis_dpi, arguments.role)
        print(json.dumps({'pages': result['pageCount'], 'documentType': result['scoreProfile']['documentType']}))
