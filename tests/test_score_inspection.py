import json

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas


def test_multiscale_inspection_creates_evidence_and_coordinate_maps(api, tmp_path):
    from score_contracts import build_transposition_intent
    from score_inspection import inspect_pdf
    from score_workspace import ScoreWorkspace

    source = tmp_path / 'input.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(300, 400))
    pdf.setFont('Helvetica', 10)
    pdf.drawString(30, 360, '12')
    for y in (250, 255, 260, 265, 270):
        pdf.line(30, y, 270, y)
    for x in (90, 150, 210, 270):
        pdf.line(x, 250, x, 270)
    pdf.save()

    request = {'name': 'score.pdf', 'transposeMode': 'custom', 'semitones': 2,
               'accidentalPreference': 'auto', 'sourceInstrument': 'concert_c',
               'targetInstrument': 'concert_c'}
    ScoreWorkspace(str(tmp_path)).initialize(
        'job-inspection', str(source), request, build_transposition_intent(request))
    preflight = {'pageDetails': [{'page': 1, 'geometry': {
        'width': 300, 'height': 400, 'staves': [{
            'left': 30, 'right': 270, 'top': 130, 'spacing': 5,
            'barlines': [30, 90, 150, 210, 270],
        }],
    }}]}
    report = inspect_pdf(str(source), str(tmp_path), preflight, preview_dpi=72, analysis_dpi=144)

    assert report['pageCount'] == 1
    assert report['pages'][0]['preview']['pixelWidth'] == 300
    assert report['pages'][0]['analysis']['pixelWidth'] == 600
    assert (tmp_path / 'renders' / 'preview-150' / 'page-0001.png').is_file()
    assert (tmp_path / 'renders' / 'analysis-400' / 'page-0001.png').is_file()
    evidence = json.loads((tmp_path / 'evidence' / 'source-evidence.json').read_text(encoding='utf-8'))
    coordinates = json.loads((tmp_path / 'layout' / 'source' / 'coordinate-map.json').read_text(encoding='utf-8'))
    structures = json.loads((tmp_path / 'inspection' / 'structure-candidates.json').read_text(encoding='utf-8'))
    assert evidence['immutable'] is True
    assert any(item['char'] == '1' for item in evidence['pages'][0]['characters'])
    assert coordinates['pages'][0]['sourceSpace']['rotation'] == 0
    assert coordinates['pages'][0]['renders']['analysis']['scale'] == 2.0
    assert report['scoreProfile']['structureCandidateSystems'] == 1
    assert len(structures['pages'][0]['systems'][0]['measures']) == 4

    target = inspect_pdf(str(source), str(tmp_path), preview_dpi=72, analysis_dpi=144, role='target')
    assert target['role'] == 'target'
    assert (tmp_path / 'inspection' / 'target-inspection.json').is_file()
    assert (tmp_path / 'evidence' / 'target-render-evidence.json').is_file()
    assert (tmp_path / 'layout' / 'target' / 'coordinate-map.json').is_file()
    assert (tmp_path / 'renders' / 'target-analysis-400' / 'page-0001.png').is_file()


def test_adaptive_region_render_uses_pdf_coordinates(api, tmp_path):
    from score_inspection import render_region

    source = tmp_path / 'input.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(300, 400))
    pdf.drawString(30, 360, 'measure 12')
    pdf.save()

    result = render_region(str(source), str(tmp_path), 1, [20, 20, 170, 120], dpi=144)

    assert result['bbox'] == [20.0, 20.0, 170.0, 120.0]
    assert result['pixelWidth'] == 300
    assert result['pixelHeight'] == 200
    assert (tmp_path / result['path']).is_file()


def test_raster_staff_detection_creates_unverified_structure_candidates(api, tmp_path):
    from score_inspection import raster_structure_candidates

    path = tmp_path / 'scan.png'
    image = Image.new('L', (600, 400), 255)
    draw = ImageDraw.Draw(image)
    for y in (150, 160, 170, 180, 190):
        draw.line((40, y, 560, y), fill=0, width=2)
    for x in (40, 220, 390, 560):
        draw.line((x, 150, x, 190), fill=0, width=2)
    image.save(path)

    systems = raster_structure_candidates(str(path), [0, 0, 300, 200])

    assert len(systems) == 1
    assert systems[0]['basis'] == 'raster_projection_candidate'
    assert systems[0]['semanticVerification'] is False
    assert len(systems[0]['measures']) == 3


def test_scan_omr_variant_preserves_page_geometry_and_records_nonsemantic_input(api, tmp_path):
    import pymupdf
    from score_inspection import prepare_omr_variant

    source = tmp_path / 'scan.pdf'
    pdf = canvas.Canvas(str(source), pagesize=(300, 400))
    pdf.setFillGray(0.65)
    for y in (150, 155, 160, 165, 170):
        pdf.line(30, y, 270, y)
    pdf.save()

    report = prepare_omr_variant(str(source), str(tmp_path), dpi=200)
    output = pymupdf.open(tmp_path / report['path'])
    original = pymupdf.open(source)
    assert len(output) == len(original) == 1
    assert list(output[0].rect) == list(original[0].rect)
    assert report['representation'] == 'grayscale_autocontrast_raster_pdf'
    assert report['semanticVerification'] is False
