import json

from reportlab.pdfgen import canvas


def make_pdf(path, header, system_text):
    pdf = canvas.Canvas(str(path), pagesize=(300, 200))
    pdf.drawString(20, 180, header)
    for y in (80, 85, 90, 95, 100):
        pdf.line(30, y, 270, y)
    pdf.drawString(120, 90, system_text)
    pdf.save()


def test_header_preservation_keeps_source_title_and_target_music(api, tmp_path):
    import pymupdf
    from score_static_content import preserve_headers

    source = tmp_path / "source.pdf"
    target = tmp_path / "target.pdf"
    output = tmp_path / "output.pdf"
    make_pdf(source, "SOURCE TITLE", "OLD MUSIC")
    make_pdf(target, "LOST TITLE", "NEW MUSIC")
    structures = {"pages": [{"page": 1, "systems": [{"bbox": [25, 90, 275, 135]}]}]}
    source_map = tmp_path / "source.json"
    target_map = tmp_path / "target.json"
    source_map.write_text(json.dumps(structures), encoding="utf-8")
    target_map.write_text(json.dumps(structures), encoding="utf-8")

    report = preserve_headers(source, target, source_map, target_map, output)
    document = pymupdf.open(output)
    text = document[0].get_text()
    assert "SOURCE TITLE" in text
    assert "NEW MUSIC" in text
    assert report["preservedPages"] == 1


def test_taller_source_title_band_moves_target_notation_below_it(api, tmp_path):
    import pymupdf
    from score_static_content import preserve_headers

    source = tmp_path / "source-tall.pdf"
    target = tmp_path / "target-high.pdf"
    output = tmp_path / "output-fitted.pdf"
    make_pdf(source, "COMPLETE SOURCE TITLE", "OLD MUSIC")
    make_pdf(target, "BROKEN TITLE", "NEW MUSIC")
    source_map = tmp_path / "source-tall.json"
    target_map = tmp_path / "target-high.json"
    source_map.write_text(json.dumps({
        "pages": [{"page": 1, "systems": [{"bbox": [25, 75, 275, 135]}]}]
    }), encoding="utf-8")
    target_map.write_text(json.dumps({
        "pages": [{"page": 1, "systems": [{"bbox": [25, 25, 275, 85]}]}]
    }), encoding="utf-8")

    report = preserve_headers(source, target, source_map, target_map, output)
    document = pymupdf.open(output)
    text = document[0].get_text()
    assert "COMPLETE SOURCE TITLE" in text
    assert "NEW MUSIC" in text
    assert "BROKEN TITLE" not in text
    assert report["pages"][0]["targetNotationFittedBelowHeader"] is True


def test_vector_staff_fallback_prevents_sparse_first_system_from_being_covered(api, tmp_path):
    import pymupdf
    from score_static_content import preserve_headers

    source = tmp_path / "source-vector.pdf"
    target = tmp_path / "target-vector.pdf"
    output = tmp_path / "output-vector.pdf"
    for path, label in ((source, "SOURCE TITLE"), (target, "TARGET TITLE")):
        document = pymupdf.open()
        page = document.new_page(width=300, height=200)
        page.insert_text((20, 20), label)
        for y in (60, 65, 70, 75, 80):
            page.draw_line((20, y), (280, y), width=0.5)
        document.save(path)
        document.close()
    source_map = tmp_path / "source-vector.json"
    target_map = tmp_path / "target-vector.json"
    source_map.write_text(json.dumps({
        "pages": [{"page": 1, "systems": [{"bbox": [20, 70, 280, 130], "staffSpacing": 4}]}]
    }), encoding="utf-8")
    # Deliberately simulate a projection detector that skipped the first staff.
    target_map.write_text(json.dumps({
        "pages": [{"page": 1, "systems": [{"bbox": [20, 120, 280, 180], "staffSpacing": 4}]}]
    }), encoding="utf-8")

    report = preserve_headers(source, target, source_map, target_map, output)
    assert report["pages"][0]["targetNotationFittedBelowHeader"] is True
    assert report["pages"][0]["targetBoundaryEvidence"] == "earliest-vector-staff"


def test_musicxml_layout_keeps_all_nonempty_credits(api):
    import xml.etree.ElementTree as ET

    root = ET.fromstring("""<score-partwise>
      <credit page="1"><credit-type>title</credit-type><credit-words>Work</credit-words></credit>
      <credit page="1"><credit-type>part name</credit-type><credit-words>Clarinet in A</credit-words></credit>
      <credit page="1"><credit-words>Fourth untyped line</credit-words></credit>
      <credit page="2"><credit-words>Running title</credit-words></credit>
      <credit page="2"><credit-words>2</credit-words></credit>
      <credit page="2"><credit-words>   </credit-words></credit>
    </score-partwise>""")
    api.normalize_musicxml_layout(root)
    values = [" ".join((node.text or "").strip() for node in item if api.local_name(node.tag) == "credit-words")
              for item in root if api.local_name(item.tag) == "credit"]
    assert values == ["Work", "Clarinet in A", "Fourth untyped line", "Running title", "2"]
