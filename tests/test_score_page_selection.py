import importlib.util
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter


SCRIPT = Path(__file__).resolve().parents[1] / "server" / "score_page_selection.py"
SPEC = importlib.util.spec_from_file_location("score_page_selection_under_test", SCRIPT)
PAGE_SELECTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAGE_SELECTION)


def make_pdf(path: Path, pages: int):
    writer = PdfWriter()
    for number in range(1, pages + 1):
        writer.add_blank_page(width=500 + number, height=700 + number)
    writer.add_metadata({"/Title": "Page selection fixture"})
    with path.open("wb") as stream:
        writer.write(stream)


def test_selects_only_requested_pages_and_keeps_their_source_mapping(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "selected.pdf"
    make_pdf(source, 5)

    report = PAGE_SELECTION.select_pdf_pages(str(source), str(output), [2, 5])

    selected = PdfReader(str(output))
    assert len(selected.pages) == 2
    assert [float(page.mediabox.width) for page in selected.pages] == [502.0, 505.0]
    assert report == {
        "schemaVersion": 1,
        "sourcePageCount": 5,
        "selectedPages": [2, 5],
        "selectedPageCount": 2,
        "mode": "custom",
    }


def test_all_pages_preserve_the_original_pdf_bytes(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "selected.pdf"
    make_pdf(source, 3)

    report = PAGE_SELECTION.select_pdf_pages(str(source), str(output))

    assert output.read_bytes() == source.read_bytes()
    assert report["selectedPages"] == [1, 2, 3]
    assert report["mode"] == "all"


@pytest.mark.parametrize("pages", [[], [0], [4], [1, 1], list(range(1, 22))])
def test_invalid_page_selections_are_rejected(tmp_path, pages):
    source = tmp_path / "source.pdf"
    make_pdf(source, 3)
    with pytest.raises(ValueError):
        PAGE_SELECTION.select_pdf_pages(str(source), str(tmp_path / "selected.pdf"), pages)


def test_all_pages_requires_an_explicit_selection_for_large_pdf(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source, 21)
    with pytest.raises(ValueError, match="指定"):
        PAGE_SELECTION.select_pdf_pages(str(source), str(tmp_path / "selected.pdf"))
