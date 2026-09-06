import json
from reportlab.pdfgen import canvas


def make_pdf(path, header, system_text):
    pdf = canvas.Canvas(str(path), pagesize=(300, 200))
    pdf.drawString(20, 180, header)
    for y in (80, 85, 90, 95, 100):
        pdf.line(30, y, 270, y)
    pdf.drawString(120, 90, system_text)
    pdf.save()


def test_system_composer_preserves_source_page_and_uses_target_system(api, tmp_path):
    import pymupdf
    from score_system_composer import compose_systems

    source, target, output = tmp_path / 'source.pdf', tmp_path / 'target.pdf', tmp_path / 'output.pdf'
    make_pdf(source, 'SOURCE HEADER', 'OLD')
    make_pdf(target, 'TARGET HEADER', 'NEW')
    structures = {'pages': [{'page': 1, 'systems': [{'bbox': [25, 90, 275, 135]}]}]}
    source_map, target_map = tmp_path / 'source.json', tmp_path / 'target.json'
    source_map.write_text(json.dumps(structures), encoding='utf-8')
    target_map.write_text(json.dumps(structures), encoding='utf-8')
    report = compose_systems(source, target, source_map, target_map, output)
    document = pymupdf.open(output)
    text = document[0].get_text()
    assert list(document[0].rect) == [0.0, 0.0, 300.0, 200.0]
    assert 'SOURCE HEADER' in text
    assert 'TARGET HEADER' not in text
    assert 'NEW' in text
    assert report['pages'] == 1 and report['systems'] == 1
    assert report['semanticVerification'] is False


def test_system_composer_rejects_different_system_counts(api, tmp_path):
    import pytest
    from score_system_composer import compose_systems

    source, target = tmp_path / 'source.pdf', tmp_path / 'target.pdf'
    make_pdf(source, 'SOURCE', 'OLD')
    make_pdf(target, 'TARGET', 'NEW')
    first = {'pages': [{'page': 1, 'systems': [{'bbox': [20, 70, 280, 130]}]}]}
    second = {'pages': [{'page': 1, 'systems': []}]}
    a, b = tmp_path / 'a.json', tmp_path / 'b.json'
    a.write_text(json.dumps(first), encoding='utf-8')
    b.write_text(json.dumps(second), encoding='utf-8')
    with pytest.raises(ValueError, match='系统数量'):
        compose_systems(source, target, a, b, tmp_path / 'output.pdf')
