import json
import xml.etree.ElementTree as ET

import pytest


def tree(ties=False):
    return ET.fromstring('''<score-partwise><part id="P1"><measure number="1">
      <attributes><divisions>4</divisions><key><fifths>0</fifths></key></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type>%s</note>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type>%s</note>
      <note><rest/><duration>8</duration><type>half</type></note>
      </measure></part></score-partwise>''' % ('<tie type="start"/>' if ties else '', '<tie type="stop"/>' if ties else ''))


def change(event='p1-m1-n1', step='D', alter=0, octave=5):
    return {'eventId': event, 'pitch': {'step': step, 'alter': alter, 'octave': octave}}


def test_pitch_edits_preserve_duration_rest_and_original_tree_file(api, tmp_path):
    from score_editor import apply_edits, editor_data
    from score_ir import score_ir
    root = tree()
    xml = tmp_path / 'transposed.musicxml'
    ET.ElementTree(root).write(xml)
    before = xml.read_bytes()
    data = editor_data(str(tmp_path), api.read_musicxml_root)
    log = apply_edits(root, [change(alter=-1)])
    assert xml.read_bytes() == before
    events = score_ir(root)['parts'][0]['measures'][0]['events']
    assert events[0]['pitch'] == {'step': 'D', 'alter': -1, 'octave': 5}
    assert [e['duration'] for e in events] == ['1', '1', '2']
    assert events[2]['kind'] == 'rest'
    assert root.find('.//accidental').text == 'flat'
    assert len(log) == 1 and len(data['revision']) == 64


def test_editor_exposes_bounded_structure_gap_without_auto_applying_it(api, tmp_path):
    from score_editor import editor_data
    xml = tmp_path / 'transposed.musicxml'
    ET.ElementTree(rest_tree()).write(xml)
    report = {
        'verification': {'omr': {'multirestRepair': {'unresolvedGaps': [{
            'id': 'p2-s7', 'page': 2, 'system': 7, 'lineStart': 275,
            'nextLineStart': 283, 'missingMeasures': 7,
            'reason': '多个候选休止位置', 'contentKnown': False,
            'candidateMeasures': [
                {'measureId': 'p1-m1', 'measureNumber': '1', 'positionInSystem': 1, 'isRest': True},
                {'measureId': '', 'measureNumber': '2', 'positionInSystem': 2},
            ],
            'systemMeasures': [{'measureId': 'p1-m1', 'measureNumber': '1', 'positionInSystem': 1}],
        }]}}}
    }
    (tmp_path / 'pipeline-report.json').write_text(json.dumps(report), encoding='utf-8')
    data = editor_data(str(tmp_path), api.read_musicxml_root)
    assert data['structureGaps'] == [{
        'id': 'p2-s7', 'page': 2, 'system': 7, 'lineStart': 275,
        'nextLineStart': 283, 'missingMeasures': 7,
        'reason': '多个候选休止位置', 'contentKnown': False,
        'requiresConfirmation': True,
        'candidateMeasures': [
            {'measureId': 'p1-m1', 'measureNumber': '1', 'positionInSystem': 1, 'isRest': True}
        ],
        'systemMeasures': [{'measureId': 'p1-m1', 'measureNumber': '1', 'positionInSystem': 1}],
    }]
    assert len(data['measures']) == 2


def test_tied_notes_must_be_corrected_together(api):
    from score_editor import apply_edits
    with pytest.raises(ValueError, match='延音线'):
        apply_edits(tree(True), [change()])
    log = apply_edits(tree(True), [change(), change('p1-m1-n2')])
    assert len(log) == 2


def rest_tree():
    root = tree()
    attrs = root.find('.//attributes')
    time = ET.SubElement(attrs, 'time')
    ET.SubElement(time, 'beats').text = '6'
    ET.SubElement(time, 'beat-type').text = '8'
    m = ET.SubElement(root.find('part'), 'measure', number='2')
    ET.SubElement(m, 'print', {'new-page': 'yes'})
    return root


def test_insert_rest_bars_keeps_notes_breaks_meter_and_shifts_numbers(api):
    from score_editor import apply_edits
    root = rest_tree()
    original = ET.tostring(root.find('.//measure'))
    log = apply_edits(root, [{'type': 'insertRests', 'measureId': 'p1-m1', 'count': 7}])
    measures = root.findall('.//measure')
    assert len(measures) == 9
    assert ET.tostring(measures[0]) == original
    assert [m.get('number') for m in measures] == list(map(str, range(1, 10)))
    assert all(m.find('note/rest').get('measure') == 'yes' for m in measures[1:8])
    assert all(m.findtext('note/duration') == '12' for m in measures[1:8])
    assert measures[-1].find('print').get('new-page') == 'yes'
    assert log[0]['count'] == 7


@pytest.mark.parametrize('count', [0, 65, True, 1.5])
def test_invalid_rest_count_does_not_mutate_score(api, count):
    from score_editor import apply_edits
    root = rest_tree()
    before = ET.tostring(root)
    with pytest.raises(ValueError):
        apply_edits(root, [{'type': 'insertRests', 'measureId': 'p1-m1', 'count': count}])
    assert ET.tostring(root) == before


def test_missing_meter_or_polyphonic_part_not_guessed(api):
    from score_editor import apply_edits
    root = tree()
    with pytest.raises(ValueError, match='拍号'):
        apply_edits(root, [{'type': 'insertRests', 'measureId': 'p1-m1', 'count': 7}])
    root = rest_tree()
    ET.SubElement(root, 'part', id='P2')
    with pytest.raises(ValueError, match='单乐器声部'):
        apply_edits(root, [{'type': 'insertRests', 'measureId': 'p1-m1', 'count': 7}])


def gap_suggestion(position='trailing', onset='3', duration='1', status='supported_by_omr_object'):
    supported = {'supported_by_omr_object', 'supported_by_visual_model',
                 'supported_by_omr_and_visual_model'}
    return {
        'gapId': 'rhythm-gap-p1-m1-v1-1', 'measureId': 'p1-m1',
        'location': {'part': 1, 'measure': '1', 'page': 1, 'system': 1},
        'voice': '1', 'onset': onset, 'duration': duration, 'position': position,
        'status': status, 'notation': 'quarter_rest', 'notationLabel': '四分休止符',
        'dots': 0, 'riskReasons': [], 'confirmable': status in supported,
    }


def three_quarters(with_forward=False):
    middle = '<forward><duration>4</duration></forward>' if with_forward else ''
    return ET.fromstring('''<score-partwise><part id="P1"><measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      %s
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <barline location="right"><bar-style>light-heavy</bar-style></barline>
    </measure></part></score-partwise>''' % middle)


def test_confirmed_trailing_rest_uses_server_evidence_and_precedes_barline(api):
    from score_editor import apply_edits
    root = three_quarters()
    suggestion = gap_suggestion()
    log = apply_edits(root, [{'type': 'confirmRest', 'gapId': suggestion['gapId']}],
                      {suggestion['gapId']: suggestion})
    children = list(root.find('.//measure'))
    rest_note = children[-2]
    assert rest_note.find('rest') is not None
    assert rest_note.findtext('duration') == '4'
    assert rest_note.findtext('voice') == '1'
    assert rest_note.findtext('type') == 'quarter'
    assert children[-1].tag == 'barline'
    assert log[0]['type'] == 'confirmRest'


@pytest.mark.parametrize('status', [
    'supported_by_visual_model', 'supported_by_omr_and_visual_model'])
def test_confirmed_visual_rest_still_requires_server_bound_evidence(api, status):
    from score_editor import apply_edits
    root = three_quarters()
    suggestion = gap_suggestion(status=status)
    apply_edits(root, [{'type': 'confirmRest', 'gapId': suggestion['gapId']}],
                {suggestion['gapId']: suggestion})
    assert root.find('.//measure/note[last()]/rest') is not None


def test_confirmed_internal_rest_replaces_exact_forward_without_moving_notes(api):
    from score_editor import apply_edits
    root = three_quarters(True)
    suggestion = gap_suggestion('internal', '1', '1')
    apply_edits(root, [{'type': 'confirmRest', 'gapId': suggestion['gapId']}],
                {suggestion['gapId']: suggestion})
    measure = root.find('.//measure')
    assert measure.find('forward') is None
    assert [node.findtext('pitch/step') if node.find('pitch') is not None else 'rest'
            for node in measure.findall('note')] == ['C', 'rest', 'D', 'E']


def test_confirmed_trailing_rest_can_replace_trailing_forward(api):
    from score_editor import apply_edits
    root = three_quarters()
    measure = root.find('.//measure')
    barline = measure.find('barline')
    forward = ET.Element('forward')
    ET.SubElement(forward, 'duration').text = '4'
    measure.insert(list(measure).index(barline), forward)
    suggestion = gap_suggestion()
    apply_edits(root, [{'type': 'confirmRest', 'gapId': suggestion['gapId']}],
                {suggestion['gapId']: suggestion})
    assert measure.find('forward') is None
    assert measure.findall('note')[-1].find('rest') is not None


def test_untrusted_or_weak_rest_confirmation_is_rejected_without_mutation(api):
    from score_editor import apply_edits
    root = three_quarters()
    before = ET.tostring(root)
    with pytest.raises(ValueError, match='不存在'):
        apply_edits(root, [{'type': 'confirmRest', 'gapId': 'forged'}], {})
    suggestion = gap_suggestion(status='weak_omr_candidate')
    with pytest.raises(ValueError, match='证据不足'):
        apply_edits(root, [{'type': 'confirmRest', 'gapId': suggestion['gapId']}],
                    {suggestion['gapId']: suggestion})
    assert ET.tostring(root) == before


def test_editor_exposes_rest_suggestion_and_carries_unresolved_items(api, tmp_path):
    from score_editor import editor_data, carry_rest_review
    xml = tmp_path / 'transposed.musicxml'
    ET.ElementTree(three_quarters()).write(xml)
    review = tmp_path / 'review'
    review.mkdir()
    suggestion = gap_suggestion()
    gap = dict(suggestion, id=suggestion['gapId'], expectedMeasureDuration='4',
               riskReasons=[], reviewRegion={'page': 1, 'bbox': [10, 20, 30, 40]})
    (review / 'rhythm-gaps.json').write_text(json.dumps({'gaps': [gap], 'overflows': [], 'summary': {'gapCount': 1}}), encoding='utf-8')
    classified = {'classifications': [{
        'gapId': suggestion['gapId'], 'status': suggestion['status'],
        'suggestedNotation': 'quarter_rest', 'suggestedDots': 0,
        'selectedEvidence': {'grade': .8, 'contextGrade': .9},
    }], 'summary': {'gapCount': 1}}
    (review / 'rest-classification.json').write_text(json.dumps(classified), encoding='utf-8')
    data = editor_data(str(tmp_path), api.read_musicxml_root)
    assert data['restSuggestions'][0]['confirmable'] is True
    assert data['restSuggestions'][0]['reviewRegion']['bbox'] == [10, 20, 30, 40]
    child_dir = tmp_path / 'child'
    carry_rest_review(str(tmp_path), str(child_dir), [suggestion['gapId']])
    carried = json.loads((child_dir / 'review' / 'rhythm-gaps.json').read_text(encoding='utf-8'))
    assert carried['gaps'] == [] and carried['summary']['gapCount'] == 0


@pytest.mark.parametrize('changes', [[], [change(octave=10)], [change(alter=True)],
                                     [change(step='C; import os')], [change('../output.pdf')],
                                     [change('p1-m1-n99')], [change(), change()],
                                     [change('p1-m1-n3')], [{'eventId': 'p1-m1-n1', 'code': 'x'}]])
def test_untrusted_or_unsupported_edits_rejected(api, changes):
    from score_editor import apply_edits
    with pytest.raises(ValueError):
        apply_edits(tree(), changes)


def test_unverified_candidate_can_be_exported_but_hash_is_bound(api, tmp_path):
    from score_editor import candidate_info
    output = tmp_path / 'output.pdf'
    output.write_bytes(b'%PDF-1.4\nfixture')
    assert candidate_info(str(tmp_path), 'processing', lambda _: 1) is None
    assert candidate_info(str(tmp_path), 'failed', lambda _: 1)['verified'] is False
    output.write_bytes(b'%PDF-1.4\nchanged')
    assert candidate_info(str(tmp_path), 'needs_review', lambda _: 1) is None
    assert not api.score_output_authorization(str(tmp_path))[0]


def test_missing_or_unreadable_pdf_is_never_substituted_with_source(api, tmp_path):
    from score_editor import candidate_info
    (tmp_path / 'input.pdf').write_bytes(b'%PDF-1.4\noriginal')
    assert candidate_info(str(tmp_path), 'failed', lambda _: 1) is None
    (tmp_path / 'output.pdf').write_bytes(b'not a pdf')
    assert candidate_info(str(tmp_path), 'failed', lambda _: 1) is None


def test_checklist_distinguishes_no_located_errors_from_verified(api):
    from score_editor import report_text
    report = report_text({'jobId': 'test', 'status': 'needs_review'}, {'issues': [], 'checks': []})
    assert '不表示整份谱正确' in report
    report = report_text({}, {'issues': [{'message': '第 7 小节', 'expected': 'D5', 'actual': 'C5'}]})
    assert '第 7 小节' in report and 'D5' in report and 'C5' in report


def test_get_status_exposes_candidate_without_changing_verification(api, tmp_path, monkeypatch):
    import threading
    from urllib.request import urlopen
    job_id = '11111111-1111-1111-1111-111111111111'
    directory = tmp_path / job_id
    directory.mkdir()
    (directory / 'output.pdf').write_bytes(b'%PDF-1.4\nfixture')
    job = {'jobId': job_id, 'status': 'needs_review', 'pipelineStatus': 'NEEDS_REVIEW',
           'outputAllowed': False, 'outputUrl': '', 'verification': {'checks': [], 'issues': []}}
    monkeypatch.setattr(api, 'SCORE_DIR', str(tmp_path))
    monkeypatch.setattr(api.SCORE_JOBS, 'read', lambda _: dict(job))
    monkeypatch.setattr(api, 'get_pdf_page_count', lambda _: 1)
    server = api.ThreadingHTTPServer(('127.0.0.1', 0), api.Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = 'http://127.0.0.1:%s/api/score/transpositions/%s' % (server.server_port, job_id)
        with urlopen(base) as response:
            data = json.load(response)['data']
        assert data['candidateAvailable'] and not data['outputAllowed'] and data['status'] == 'needs_review'
        with urlopen(base + '/candidate') as response:
            assert response.read().startswith(b'%PDF-')
            assert "UTF-8''" in response.headers['Content-Disposition']
        with urlopen(base + '/review-report') as response:
            assert '未经完整逐音核验' in response.read().decode('utf-8-sig')
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
