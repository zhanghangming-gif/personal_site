import copy
import json
import xml.etree.ElementTree as ET

import pytest


def note(step='C', alter=0, octave=5, duration=1, voice='1', extra=''):
    return ('<note>%s<pitch><step>%s</step><alter>%s</alter><octave>%s</octave></pitch>'
            '<duration>%s</duration><voice>%s</voice><type>quarter</type></note>'
            % (extra, step, alter, octave, duration, voice))


def score(content, divisions=1, prefix=''):
    return ET.fromstring('<score-partwise><part id="P1"><measure number="17"><attributes>'
                         '<divisions>%s</divisions></attributes>%s%s</measure></part></score-partwise>'
                         % (divisions, prefix, content))


def compare(api, left, right):
    from score_ir import score_ir
    from score_ir_audit import compare_ir
    return compare_ir(score_ir(left), score_ir(right))


def test_rational_chords_backups_and_provenance(api):
    from score_ir import score_ir
    root = score(note('C', duration=1) + note('E', duration=1, extra='<chord/>') +
                 '<backup><duration>1</duration></backup>' + note('G', duration=2, voice='2'), 3)
    ir = score_ir(root, 'omr-export', 'a' * 64)
    events = ir['parts'][0]['measures'][0]['events']
    assert [e['onset'] for e in events] == ['0', '0', '0']
    assert [e['duration'] for e in events] == ['1/3', '1/3', '2/3']
    assert len({e['id'] for e in events}) == 3
    assert ir == score_ir(copy.deepcopy(root), 'omr-export', 'a' * 64)
    assert not ir['sourceRecognitionVerified']
    assert all(e['evidence']['bbox'] is None for e in events)


def test_instrument_and_composition_specs_are_distinct(api):
    from score_ir import specification
    assert specification(-1, 'auto', 'clarinet_a', 'clarinet_bb')['soundingSemitones'] == 0
    assert specification(-1, 'auto', 'clarinet_a', 'clarinet_bb')['preferredDiatonicSteps'] == -1
    assert specification(1)['soundingSemitones'] == 1
    for bad in (True, 1.5, 49):
        with pytest.raises(ValueError):
            specification(bad)
    with pytest.raises(ValueError):
        specification(1, 'auto', 'clarinet_a', 'clarinet_bb')


def test_chord_reordering_and_divisions_do_not_false_alarm(api):
    a = score(note() + note('E', extra='<chord/>'))
    b = score(note('E', duration=480) + note(duration=480, extra='<chord/>'), 480)
    assert compare(api, a, b)['passed']


def test_same_sound_wrong_spelling_is_localized(api):
    audit = compare(api, score(note('C', octave=5)), score(note('B', alter=1, octave=4)))
    assert audit['issueCount'] == 1
    issue = audit['issues'][0]
    assert issue['field'] == 'pitch' and issue['expected'] == 'C5' and issue['actual'] == 'B♯4'
    assert issue['location']['measure'] == '17' and issue['eventId'] == 'p1-m1-n1'


def test_consistent_voice_alias_allowed_but_split_rejected(api):
    a = score(note(voice='1') + note('D', voice='1'))
    b = score(note(voice='3') + note('D', voice='3'))
    split = score(note(voice='1') + note('D', voice='2'))
    assert compare(api, a, b)['passed']
    assert any(i['field'] == 'voice' for i in compare(api, a, split)['issues'])


def test_missing_note_does_not_shift_every_comparison(api):
    a = score(note() + note('D') + note('E'))
    b = score(note() + '<forward><duration>1</duration></forward>' + note('E'))
    report = compare(api, a, b)
    assert report['issueCount'] == 1 and report['issues'][0]['code'] == 'missing_event'
    assert report['issues'][0]['location']['onsetQuarter'] == '1'


def test_lyrics_staff_dynamics_and_key_are_checked(api):
    lyric = '<lyric><syllabic>single</syllabic><text>河</text></lyric>'
    assert any(x['field'] == 'lyrics' for x in compare(api, score(note(extra=lyric)), score(note()))['issues'])
    dynamic = '<direction><direction-type><dynamics><f/></dynamics></direction-type><staff>%s</staff></direction>'
    assert not compare(api, score(note(), prefix=dynamic % 1), score(note(), prefix=dynamic % 2))['passed']
    a, b = score(note()), score(note())
    ET.SubElement(b.find('.//attributes'), 'key').append(ET.fromstring('<fifths>2</fifths>'))
    assert any(x['field'] == 'context' for x in compare(api, a, b)['issues'])


def test_slur_number_can_change_but_endpoints_cannot(api):
    def slurred(last, number):
        notes = [note('C', extra='<notations><slur type="start" number="%s"/></notations>' % number), note('D'), note('E')]
        notes[last] = notes[last].replace('</note>', '<notations><slur type="stop" number="%s"/></notations></note>' % number)
        return score(''.join(notes))
    assert compare(api, slurred(2, 1), slurred(2, 7))['passed']
    assert any(x['field'] == 'spanners' for x in compare(api, slurred(2, 1), slurred(1, 1))['issues'])


def test_transposition_checks_rest_and_lyrics_not_just_midi(api):
    from score_ir import score_ir
    from score_ir_audit import compare_transposition
    source = score_ir(score(note() + '<note><rest/><duration>3</duration></note>'))
    target = score_ir(score(note('B', octave=4) + '<note><rest/><duration>2</duration></note>'))
    result = compare_transposition(source, target, -1)
    assert any(i['field'] == 'duration' for i in result['issues'])
    assert not any(i['field'] == 'midi' for i in result['issues'])


def test_issue_cap_never_hides_failure_count(api):
    from score_ir import score_ir
    from score_ir_audit import compare_ir
    report = compare_ir(score_ir(score(note() * 40)), score_ir(score(note('D') * 40)), limit=2)
    assert report['issueCount'] == 40 and len(report['issues']) == 2 and report['truncated']


def test_measure_number_cascade_is_reported_as_one_root_issue(api):
    from score_ir import score_ir
    from score_ir_audit import compare_ir
    before = score_ir(score(note()))
    after = copy.deepcopy(before)
    before_measure = before['parts'][0]['measures'][0]
    after_measure = after['parts'][0]['measures'][0]
    before['parts'][0]['measures'] = [copy.deepcopy(before_measure) for _ in range(12)]
    after['parts'][0]['measures'] = [copy.deepcopy(after_measure) for _ in range(12)]
    for index, measure in enumerate(before['parts'][0]['measures'], 1):
        measure['location']['measure'] = str(index)
    for index, measure in enumerate(after['parts'][0]['measures'], 1):
        measure['location']['measure'] = str(index + 1)
    report = compare_ir(before, after)
    measure_issues = [item for item in report['issues'] if item['field'] == 'measure']
    assert len(measure_issues) == 1
    assert '共 12 处编号差异' in measure_issues[0]['expected']


def test_candidate_export_agreement_does_not_prove_source_pdf(api, tmp_path):
    from score_review import write_score_review, attach_review
    # The XML pairs agree. Neither input nor candidate PDF has been recognized.
    (tmp_path / 'input.pdf').write_bytes(b'original pdf placeholder')
    (tmp_path / 'output.pdf').write_bytes(b'candidate pdf placeholder')
    ET.ElementTree(score(note())).write(tmp_path / 'source.xml')
    ET.ElementTree(score(note('B', octave=4))).write(tmp_path / 'target.xml')
    report = write_score_review(str(tmp_path), str(tmp_path / 'input.pdf'), str(tmp_path / 'source.xml'),
                                str(tmp_path / 'target.xml'), str(tmp_path / 'target.xml'),
                                api.read_musicxml_root, -1, output_pdf=str(tmp_path / 'output.pdf'))
    assert report['issueCount'] == 0
    assert report['sourceRecognition']['verifiedEvents'] == 0
    assert not report['outputAllowed']
    verification = attach_review({'status': 'passed', 'checks': []}, report)
    assert not api.build_pipeline_status(verification).output_allowed
    saved = json.loads((tmp_path / 'source-score-ir.json').read_text(encoding='utf-8'))
    assert saved['documentSha256'] == report['sourcePdfSha256']
    assert report['artifacts']['source']['sha256']
    canonical = json.loads((tmp_path / 'scores' / 'source' / 'canonical-score.json').read_text(encoding='utf-8'))
    canonical_event = canonical['parts'][0]['measures'][0]['events'][0]
    assert 'location' not in canonical_event
    assert 'evidence' not in canonical_event
    evidence = json.loads((tmp_path / 'evidence' / 'evidence-graph.json').read_text(encoding='utf-8'))
    layout = json.loads((tmp_path / 'layout' / 'source' / 'source-layout-map.json').read_text(encoding='utf-8'))
    proof = json.loads((tmp_path / 'review' / 'transformation-proof.json').read_text(encoding='utf-8'))
    assert evidence['immutableSourceObservations'] is True
    assert layout['coordinateMapRef'] == 'layout/source/coordinate-map.json'
    assert proof['passed'] is True


def test_invalid_timing_stops_indexing(api):
    from score_ir import score_ir
    for root in (score(note(duration=0)), score('<backup><duration>1</duration></backup>' + note()),
                 score(note(extra='<chord/>')), score(note(), divisions=0)):
        with pytest.raises(ValueError):
            score_ir(root)


def test_measure_regions_require_matching_independent_anchors(api):
    from score_ir import score_ir
    from score_review import attach_measure_regions
    ir = score_ir(score(note()))
    system = {'page': 1, 'system': 1, 'staffCount': 1, 'lineStartPdf': 17,
              'rawMeasures': 1, 'stacks': [{}],
              'pdfStaff': {'left': 30, 'right': 500, 'top': 100, 'spacing': 5, 'barlines': [30, 500]}}
    preflight = {'pageDetails': [{'page': 1, 'geometry': {'width': 600, 'height': 800}}]}
    attach_measure_regions(ir, {'systems': [system]}, preflight)
    measure = ir['parts'][0]['measures'][0]
    assert measure['sourceRegion']['page'] == 1
    assert measure['sourceRegion']['bbox'] == [25, 75, 505, 150]
    assert measure['events'][0]['evidence']['bbox'] is None  # Not a note box.
    assert not measure['sourceRegion']['semanticVerification']
    for change in ({'lineStartPdf': 18}, {'staffCount': 2}, {'rawMeasures': 2},
                   {'stacks': [{'special': 'MULTI_REST'}]}):
        other = score_ir(score(note()))
        attach_measure_regions(other, {'systems': [dict(system, **change)]}, preflight)
        assert 'sourceRegion' not in other['parts'][0]['measures'][0]
