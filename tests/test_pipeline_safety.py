import json
import xml.etree.ElementTree as ET
import zipfile
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


def test_recognition_timeline_risk_triggers_alternative_and_candidate_ranking(api, tmp_path):
    source = tmp_path / 'underfilled.musicxml'
    source.write_text(
        '''<score-partwise version="3.1">
<part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions>
<time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice></note>
</measure></part></score-partwise>''', encoding='utf-8')
    timeline = api.musicxml_timeline_risk(str(source))
    assert timeline['gapCount'] == 1
    assert timeline['overflowCount'] == 0
    weak = api.recognition_attempt(
        'weak', 'Bravura', {'timelineRisk': timeline}, 1)
    complete = api.recognition_attempt(
        'complete', 'Bravura', {'timelineRisk': {
            'analyzedMeasures': 1, 'gapCount': 0, 'overflowCount': 0,
        }}, 1)
    assert api.needs_alternative({'timelineRisk': timeline}, 1)
    assert api.recognition_decision([weak, complete])['selectedAttemptId'] == 'complete'


def test_candidate_ranking_minimizes_total_timeline_anomalies(api):
    fewer_total = api.recognition_attempt('fewer', 'Bravura', {
        'timelineRisk': {'analyzedMeasures': 200, 'gapCount': 25, 'overflowCount': 1},
    }, 317)
    no_overflow_but_more_gaps = api.recognition_attempt('more', 'Bravura', {
        'timelineRisk': {'analyzedMeasures': 200, 'gapCount': 38, 'overflowCount': 0},
    }, 321)
    decision = api.recognition_decision([fewer_total, no_overflow_but_more_gaps])
    assert decision['selectedAttemptId'] == 'fewer'


def test_export_retry_can_isolate_alternative_candidate(api, monkeypatch, tmp_path):
    book = tmp_path / 'candidate.omr'
    book.write_bytes(b'fixture')
    def sanitize(source, target):
        Path(target).write_bytes(b'safe')
        return 1

    monkeypatch.setattr(api, 'sanitize_audiveris_book', sanitize)
    monkeypatch.setattr(api, 'analyze_audiveris_output',
                        lambda output: {'exportErrors': []})

    def run(command, job_dir, timeout, label):
        output_index = command.index('-output') + 1
        directory = Path(command[output_index])
        (directory / 'sanitized.musicxml').write_text(
            '<score-partwise/>', encoding='utf-8')
        assert label == 'alternate retry'
        return ''

    monkeypatch.setattr(api, 'run_command', run)
    result, removed, _ = api.retry_audiveris_export(
        ['audiveris'], str(book), str(tmp_path), 30,
        'omr-alternative-export-retry', 'alternate retry')
    assert Path(result).parent.name == 'omr-alternative-export-retry'
    assert removed == 1


def test_audiveris_sanitizer_removes_only_malformed_grace_relations(api, tmp_path):
    source = tmp_path / 'source.omr'
    target = tmp_path / 'sanitized.omr'
    sheet = b'''<sheet><sig><inters>
      <head-chord id="1"/><small-chord id="2"/><small-chord id="3"/>
    </inters><relations>
      <relation source="1" target="2"><chord-grace/></relation>
      <relation source="2" target="3"><chord-grace/></relation>
      <relation source="1" target="3"><beam-stem/></relation>
    </relations></sig></sheet>'''
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('sheet#1/sheet#1.xml', sheet)
        archive.writestr('book.xml', b'<book/>')

    assert api.sanitize_audiveris_book(str(source), str(target)) == 1
    with zipfile.ZipFile(target) as archive:
        root = ET.fromstring(archive.read('sheet#1/sheet#1.xml'))
    relations = list(root.find('./sig/relations'))
    assert [(item.attrib['source'], item.attrib['target']) for item in relations] == [
        ('1', '2'), ('1', '3')]


def test_audiveris_sanitizer_normalizes_small_head_in_regular_chord(api, tmp_path):
    source = tmp_path / 'source.omr'
    target = tmp_path / 'sanitized.omr'
    sheet = b'''<sheet><sig><inters>
      <head shape="WHOLE_NOTE_SMALL" id="1"/><head-chord id="2"/>
    </inters><relations>
      <relation source="2" target="1"><containment/></relation>
    </relations></sig></sheet>'''
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('sheet#1/sheet#1.xml', sheet)

    assert api.sanitize_audiveris_book(str(source), str(target)) == 1
    with zipfile.ZipFile(target) as archive:
        root = ET.fromstring(archive.read('sheet#1/sheet#1.xml'))
    assert root.find('./sig/inters/head').attrib['shape'] == 'WHOLE_NOTE'


def test_musescore_layout_does_not_duplicate_imported_measure_numbers(api, tmp_path):
    source = tmp_path / 'source.mscx'
    target = tmp_path / 'target.mscx'
    source.write_text(
        '<museScore><Score><Style><showMeasureNumber>1</showMeasureNumber>'
        '</Style><Staff/></Score></museScore>', encoding='utf-8')
    api.patch_musescore_layout(str(source), str(target), 8.5, 11.0, 1.7)
    root = ET.parse(target).getroot()
    assert root.find('./Score/Style/showMeasureNumber').text == '0'


def test_generated_musescore_style_disables_automatic_measure_numbers(api, tmp_path):
    target = tmp_path / 'style.mss'
    api.write_musescore_style(str(target), 1.7)
    root = ET.parse(target).getroot()
    assert root.find('./Style/showMeasureNumber').text == '0'


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



def test_unique_semantic_multirest_count_is_derived_from_line_span_without_ocr(api, tmp_path):
    measures = [make_measure(1)]
    measures.extend(make_measure(index, rest=False, pitch=True) for index in range(2, 10))
    last = make_measure(10, rest=False, pitch=True)
    last.insert(0, ET.Element('print', {'new-system': 'yes'}))
    measures.append(last)
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'output.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    analysis = {'systems': [
        {'page': 2, 'system': 1, 'lineStart': 1, 'lineStartRaw': 1,
         'stacks': [
             {'special': 'MULTI_REST', 'duration': '0', 'multirestBar': True},
             *[{'special': '', 'duration': '1'} for _ in range(8)],
         ], 'restCounts': []},
        {'page': 2, 'system': 2, 'lineStart': 32, 'lineStartRaw': 32,
         'stacks': [{'special': '', 'duration': '1'}], 'restCounts': []},
    ]}
    report = api.apply_verified_multirest_repairs(str(source), str(output), analysis)
    assert report['safePartialOutput'] is True, report
    repair = report['partialRepairs'][0]
    assert repair['multipleRest'] == 23
    assert repair['rawValue'] is None and repair['ocrValue'] is None
    assert repair['evidence'] == (
        'audiveris-multirest+independent-line-start-span+unique-structural-equation')
    signature = api.score_signature(str(output))
    assert signature['measureCount'] == 32
    assert signature['lineStartNumbers'] == ['1', '32']


def test_two_unknown_semantic_multirests_are_not_guessed_from_one_span(api, tmp_path):
    measures = [
        make_measure(1), make_measure(2),
        make_measure(3, rest=False, pitch=True),
    ]
    last = make_measure(4, rest=False, pitch=True)
    last.insert(0, ET.Element('print', {'new-system': 'yes'}))
    measures.append(last)
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'output.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    analysis = {'systems': [
        {'page': 1, 'system': 1, 'lineStart': 1, 'lineStartRaw': 1,
         'stacks': [
             {'special': 'MULTI_REST', 'duration': '0'},
             {'special': 'MULTI_REST', 'duration': '0'},
             {'special': '', 'duration': '1'},
         ], 'restCounts': []},
        {'page': 1, 'system': 2, 'lineStart': 8, 'lineStartRaw': 8,
         'stacks': [{'special': '', 'duration': '1'}], 'restCounts': []},
    ]}
    report = api.apply_verified_multirest_repairs(str(source), str(output), analysis)
    assert report['safePartialOutput'] is False
    assert not output.exists()


def test_integer_ocr_consensus_uses_unique_majority(api):
    assert api.integer_ocr_consensus([3, 3, None, 4]) == (3, True)
    assert api.integer_ocr_consensus([3, 4]) == (None, False)
    assert api.integer_ocr_consensus([3]) == (None, False)


def test_page_end_raster_multirest_can_append_when_span_is_unique(api, tmp_path):
    measures = [make_measure(index) for index in range(1, 9)]
    measures[-1].insert(0, ET.Element('print', {'new-system': 'yes'}))
    source = tmp_path / 'source.musicxml'
    output = tmp_path / 'output.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    analysis = {'systems': [
        {'page': 1, 'system': 1, 'lineStart': 212, 'lineStartRaw': 212,
         'stacks': [
             *[{'special': '', 'duration': '1'} for _ in range(7)],
             {'special': 'CAUTIONARY', 'duration': '0', 'multirestBar': True},
         ],
         'restCounts': [{
             'stackIndex': 7, 'value': 3, 'rawValue': None, 'ocrValue': 3,
             'ocrConsensus': True, 'geometry': 'raster-multirest-bar',
         }]},
        {'page': 2, 'system': 1, 'lineStart': 222, 'lineStartRaw': 222,
         'stacks': [{'special': '', 'duration': '1'}], 'restCounts': []},
    ]}
    report = api.apply_verified_multirest_repairs(str(source), str(output), analysis)
    assert report['safePartialOutput'] is True, report
    assert report['partialRepairs'][0]['multipleRest'] == 3
    assert report['partialRepairs'][0]['inserted'] is True
    assert api.score_signature(str(output))['lineStartNumbers'] == ['1', '11']


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
              'geometry': 'targeted-rhythm-gap-ocr', 'ocrConsensus': True},
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


def test_expanded_multirest_gets_renderer_only_boundary_marker(api, tmp_path):
    measures = [make_measure(index, attributes=index == 1) for index in range(1, 16)]
    source = tmp_path / 'expanded.musicxml'
    render_input = tmp_path / 'render-input.musicxml'
    ET.ElementTree(make_score([measures])).write(source)
    path, applied = api.add_multirest_render_boundaries(
        str(source), str(render_input), {
            'multirestRepair': {
                'expandedForRendering': [{'measure': '2', 'multipleRest': 12}]
            }
        })
    assert path == str(render_input)
    assert applied == [{
        'measure': '2', 'multipleRest': 12,
        'museScoreImporterBoundary': 13, 'parts': 1,
    }]
    root = api.read_musicxml_root(str(render_input))
    target = api.first_part_measures(root)[1]
    assert next(
        item.text for item in target.iter()
        if api.local_name(item.tag) == 'multiple-rest'
    ) == '13'
    assert api.score_signature(str(source))['measureCount'] == 15
