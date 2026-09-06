import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def write_minimal_musicxml(path):
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
  <part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice></note>
  </measure></part>
</score-partwise>""",
        encoding="utf-8",
    )


def test_repair_failure_continues_original_as_unverified_candidate(api, monkeypatch, tmpdir):
    tmp_path = Path(str(tmpdir))
    input_pdf = tmp_path / "input.pdf"
    input_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    musicxml = tmp_path / "source.musicxml"
    write_minimal_musicxml(musicxml)
    omr = tmp_path / "source.omr"
    omr.write_bytes(b"omr")
    calls = {"transpose": False, "render": False}

    monkeypatch.setattr(api, "find_audiveris_command", lambda: ["audiveris"])
    monkeypatch.setattr(api, "find_musescore_command", lambda: ["musescore"])
    monkeypatch.setattr(api, "run_command", lambda *args, **kwargs: "")
    monkeypatch.setattr(api, "newest_musicxml_file", lambda path: str(musicxml))
    monkeypatch.setattr(api, "newest_omr_file", lambda path: str(omr))
    monkeypatch.setattr(api, "analyze_audiveris_output", lambda output: {"exportErrors": []})
    monkeypatch.setattr(api, "analyze_audiveris_book", lambda path: {
        "systems": [{"page": 1, "system": 1, "lineStart": 1}],
        "recognizedLineNumbers": [1],
        "bookIssue": "",
    })
    monkeypatch.setattr(api, "get_pdf_page_count", lambda path: 1)
    monkeypatch.setattr(api, "repair_musicxml_structure", lambda *args, **kwargs: {
        "valid": False,
        "fatal": True,
        "reason": "ambiguous repair",
        "repairValidationStatus": "FAILED",
    })

    def transpose(*args, **kwargs):
        calls["transpose"] = True
        assert args[0] == str(musicxml)
        Path(args[1]).write_bytes(musicxml.read_bytes())
        return {}

    def render(*args, **kwargs):
        calls["render"] = True
        Path(args[2]).write_bytes(b'%PDF-1.4\nfixture')
        return 1, {}

    monkeypatch.setattr(api, "transpose_musicxml", transpose)
    monkeypatch.setattr(api, "render_preserved_score_pdf", render)

    monkeypatch.setattr(api, "verify_score_transposition", lambda *a, **k: {'status': 'failed', 'checks': []})
    monkeypatch.setattr(api, "write_score_review", lambda *a, **k: {})
    monkeypatch.setattr(api, "attach_review", lambda *a: None)
    api.process_score_pdf(str(input_pdf), str(tmp_path), 1, "auto")

    assert calls == {"transpose": True, "render": True}
    report = json.loads((tmp_path / api.PIPELINE_REPORT_NAME).read_text(encoding="utf-8"))
    assert report["pipeline"]["overallStatus"] == api.PIPELINE_NEEDS_REVIEW
    assert report["pipeline"]["outputAllowed"] is False
    assert 'ambiguous repair' in report['pipeline']['warnings']
    assert (tmp_path / 'output.pdf').exists()


def write_status(api, job_dir, status, output_allowed):
    job_dir.mkdir()
    (job_dir / "output.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    api.write_pipeline_report(
        str(job_dir),
        api.PipelineStatus(
            stage="completed",
            overall_status=status,
            fatal=status == api.PIPELINE_REJECTED,
            output_allowed=output_allowed,
        ),
    )


def test_rejected_output_cannot_download(api, tmpdir):
    tmp_path = Path(str(tmpdir))
    job_dir = tmp_path / "rejected"
    write_status(api, job_dir, api.PIPELINE_REJECTED, False)
    assert api.score_output_authorization(str(job_dir))[0] is False


def test_needs_review_output_cannot_download(api, tmpdir):
    tmp_path = Path(str(tmpdir))
    job_dir = tmp_path / "needs-review"
    write_status(api, job_dir, api.PIPELINE_NEEDS_REVIEW, False)
    assert api.score_output_authorization(str(job_dir))[0] is False


def test_verified_output_can_download(api, tmpdir):
    tmp_path = Path(str(tmpdir))
    job_dir = tmp_path / "verified"
    write_status(api, job_dir, api.PIPELINE_VERIFIED, True)
    allowed, status, _ = api.score_output_authorization(str(job_dir))
    assert allowed is True
    assert status == api.PIPELINE_VERIFIED


def make_measure(number, rest=True, pitch=False, attributes=False, multirest=None):
    measure = ET.Element("measure", {"number": str(number)})
    if attributes or multirest:
        attrs = ET.SubElement(measure, "attributes")
        ET.SubElement(attrs, "divisions").text = "1"
        if attributes:
            key = ET.SubElement(attrs, "key")
            ET.SubElement(key, "fifths").text = "2"
            time = ET.SubElement(attrs, "time")
            ET.SubElement(time, "beats").text = "4"
            ET.SubElement(time, "beat-type").text = "4"
            ET.SubElement(attrs, "clef")
        if multirest:
            style = ET.SubElement(attrs, "measure-style")
            ET.SubElement(style, "multiple-rest").text = str(multirest)
    note = ET.SubElement(measure, "note")
    if pitch:
        pitch_node = ET.SubElement(note, "pitch")
        ET.SubElement(pitch_node, "step").text = "C"
        ET.SubElement(pitch_node, "octave").text = "4"
    elif rest:
        ET.SubElement(note, "rest", {"measure": "yes"})
    ET.SubElement(note, "duration").text = "4"
    ET.SubElement(note, "voice").text = "1"
    return measure


def make_score(part_measures):
    root = ET.Element("score-partwise")
    for index, measures in enumerate(part_measures, start=1):
        part = ET.SubElement(root, "part", {"id": f"P{index}"})
        for measure in measures:
            part.append(measure)
    return root


def test_repair_is_atomic(api):
    root = make_score([
        [make_measure(1), make_measure(2)],
        [make_measure(1)],
    ])
    before = ET.tostring(root)
    assert api.remove_measure_indexes(root, [1]) is False
    assert ET.tostring(root) == before


def test_multirest_cross_part_regression(api):
    root = make_score([
        [make_measure(1, multirest=2), make_measure(2)],
        [make_measure(1, multirest=2), make_measure(2, rest=False, pitch=True)],
    ])
    before = ET.tostring(root)
    with pytest.raises(api.UnsafeRepairError):
        api.collapse_expanded_multirests(root)
    assert ET.tostring(root) == before


def test_merge_preserves_attributes(api):
    root = make_score([
        [make_measure(1, rest=False, pitch=True), make_measure(2, rest=False, pitch=True, attributes=True)],
        [make_measure(1), make_measure(2, attributes=True)],
    ])
    assert api.merge_measure_indexes(root, [1]) is True
    for part in api.score_parts(root):
        measures = api.part_measures(part)
        assert len(measures) == 1
        assert api.protected_measure_attributes(measures[0])
        assert any(api.local_name(item.tag) == "attributes" for item in list(measures[0]))


def test_multirest_insert_preserves_attributes(api):
    root = make_score([
        [make_measure(1, rest=False, pitch=True, attributes=True)],
        [make_measure(1, attributes=True)],
    ])
    reference = api.first_part_measures(root)[0]
    inserted = api.insert_multirest_before(root, reference, 4)
    assert inserted is not None
    for part in api.score_parts(root):
        measures = api.part_measures(part)
        assert len(measures) == 2
        assert api.protected_measure_attributes(measures[0])
        assert api.protected_measure_attributes(measures[1])
        assert api.multiple_rest_value(measures[0]) == 4


def test_verified_multirest_survives_unrelated_ambiguous_gap(api, tmp_path):
    first = make_measure(1)
    second = make_measure(2, rest=False, pitch=True)
    third = make_measure(3, rest=False, pitch=True)
    fourth = make_measure(4)
    fourth.insert(0, ET.Element('print', {'new-system': 'yes'}))
    root = make_score([[first, second, third, fourth]])
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'partial.musicxml'
    ET.ElementTree(root).write(source, encoding='utf-8', xml_declaration=True)
    analysis = {'systems': [
        {'page': 1, 'system': 1, 'lineStart': 1,
         'stacks': [{'special': 'MULTI_REST'}, {'special': ''}, {'special': ''}],
         'restCounts': [{'stackIndex': 0, 'value': 4, 'rawValue': 4, 'ocrValue': 4}]},
        {'page': 1, 'system': 2, 'lineStart': 7,
         'stacks': [{'special': ''}], 'restCounts': []},
    ]}
    unresolved = {'reason': 'later system is ambiguous', 'unresolvedGaps': [{'id': 'p2-s3'}]}
    report = api.apply_verified_multirest_repairs(
        str(source), str(output), analysis, unresolved)
    signature = api.score_signature(str(output))
    assert report['safePartialOutput'] is True
    assert report['valid'] is False and report['candidateContinued'] is True
    assert report['partialRepairs'][0]['multipleRest'] == 4
    assert report['unresolvedGaps'] == [{'id': 'p2-s3'}]
    assert signature['measureCount'] == 7
    assert signature['lineStartNumbers'] == ['1', '7']


def test_partial_multirest_never_commits_ocr_only_count(api, tmp_path):
    first, second = make_measure(1), make_measure(2)
    second.insert(0, ET.Element('print', {'new-system': 'yes'}))
    source = tmp_path / 'source.musicxml'
    ET.ElementTree(make_score([[first, second]])).write(source)
    analysis = {'systems': [
        {'lineStart': 1, 'stacks': [{'special': 'MULTI_REST'}],
         'restCounts': [{'stackIndex': 0, 'value': 3, 'rawValue': None, 'ocrValue': 3}]},
        {'lineStart': 4, 'stacks': [{'special': ''}], 'restCounts': []},
    ]}
    report = api.apply_verified_multirest_repairs(
        str(source), str(tmp_path / 'output.musicxml'), analysis)
    assert report['safePartialOutput'] is False
    assert not (tmp_path / 'output.musicxml').exists()


def test_existing_multirest_does_not_make_missing_count_ambiguous(api, tmp_path):
    measures = [make_measure(1, multirest=2), make_measure(2), make_measure(3), make_measure(4)]
    measures[3].insert(0, ET.Element('print', {'new-system': 'yes'}))
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'output.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    analysis = {'systems': [
        {'page': 1, 'system': 1, 'lineStart': 1,
         'stacks': [{'special': 'MULTI_REST'}, {'special': 'MULTI_REST'}],
         'restCounts': [
             {'stackIndex': 0, 'value': 2, 'rawValue': 2, 'ocrValue': 2},
             {'stackIndex': 1, 'value': 3, 'rawValue': 3, 'ocrValue': 3},
         ]},
        {'page': 1, 'system': 2, 'lineStart': 6,
         'stacks': [{'special': ''}], 'restCounts': []},
    ]}
    report = api.apply_verified_multirest_repairs(str(source), str(output), analysis)
    assert report['safePartialOutput'] is True
    assert [item['multipleRest'] for item in report['partialRepairs']] == [3]
    assert api.score_signature(str(output))['lineStartNumbers'] == ['1', '6']


def test_merged_multirests_are_inserted_without_deleting_following_notes(api, tmp_path):
    measures = [
        make_measure(1, rest=False, pitch=True, attributes=True),
        make_measure(2, rest=False, pitch=True),
        make_measure(3, rest=False, pitch=True),
        make_measure(4, rest=False, pitch=True),
        ET.Element('measure', {'number': '5'}),
        make_measure(6, rest=False, pitch=True),
        make_measure(7, rest=False, pitch=True),
    ]
    ET.SubElement(measures[4], 'barline', {'location': 'right'})
    measures[6].insert(0, ET.Element('print', {'new-system': 'yes'}))
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'output.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    analysis = {'systems': [
        {'page': 1, 'system': 1, 'lineStart': 1, 'lineStartRaw': None,
         'stacks': [
             {'special': '', 'duration': '1', 'multirestBar': True},
             {'special': '', 'duration': '1'},
             {'special': '', 'duration': '1'},
             {'special': '', 'duration': '1'},
             {'special': '', 'duration': '0'},
             {'special': '', 'duration': '1', 'multirestBar': True},
         ],
         'restCounts': [
             {'stackIndex': 0, 'value': 8, 'rawValue': 8, 'ocrValue': 8,
              'geometry': 'raster-multirest-bar', 'ocrConsensus': True},
             {'stackIndex': 5, 'value': 11, 'rawValue': None, 'ocrValue': 11,
              'geometry': 'raster-multirest-bar', 'ocrConsensus': True},
         ]},
        {'page': 1, 'system': 2, 'lineStart': 25, 'lineStartRaw': 25,
         'stacks': [{'special': '', 'duration': '1'}], 'restCounts': []},
    ]}
    source_notes = api.score_signature(str(source))['noteCount']
    report = api.apply_verified_multirest_repairs(str(source), str(output), analysis)
    assert report['safePartialOutput'] is True, report
    signature = api.score_signature(str(output))
    assert sorted(item['multipleRest'] for item in report['partialRepairs']) == [8, 11]
    assert len(report['removedEmptySeparators']) == 1
    assert signature['noteCount'] == source_notes
    assert signature['lineStartNumbers'] == ['1', '25']
    assert signature['measureCount'] == 25
