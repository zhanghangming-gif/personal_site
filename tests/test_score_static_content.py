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
