import copy
import xml.etree.ElementTree as ET

import pytest


def core(api):
    import score_transposition
    return score_transposition


def make_score(fifths=0, notes='C D E F G A B'):
    root = ET.fromstring('<score-partwise><part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>4</divisions><key><fifths>%s</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><direction><direction-type><dynamics><p/></dynamics></direction-type></direction></measure></part></score-partwise>' % fifths)
    measure = root.find('part/measure')
    for step in notes.split():
        ET.SubElement(measure, 'note').extend([
            ET.fromstring('<pitch><step>%s</step><octave>4</octave></pitch>' % step),
            ET.fromstring('<duration>4</duration>'), ET.fromstring('<voice>1</voice>'),
            ET.fromstring('<type>quarter</type>')])
    return root


def number(pitch):
    return 12 * (int(pitch.findtext('octave')) + 1) + {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[pitch.findtext('step')] + int(pitch.findtext('alter', '0'))


def test_octave_boundaries_and_double_accidentals(api):
    c = core(api)
    assert c.pitch_number('B', 1, 4) == 72
    assert c.pitch_number('C', -1, 4) == 59
    assert c.transpose_pitch('B', 1, 4, -1, -1) == ('A', 2, 4)
    assert c.transpose_pitch('C', -1, 4, -1, -1) == ('B', -1, 3)
    assert c.transpose_pitch('C', 0, 4, -1, -1) == ('B', 0, 3)


@pytest.mark.parametrize('shift', list(range(-24, 25)) + [-33, 33, -48, 48])
def test_all_key_signatures_and_transposition_directions(api, shift):
    c = core(api)
    for fifths in range(-7, 8):
        root = make_score(fifths)
        before = [number(p) for p in root.iter('pitch')]
        c.transpose_tree(root, shift)
        assert [number(p) for p in root.iter('pitch')] == [n + shift for n in before]
        assert -7 <= int(root.findtext('part/measure/attributes/key/fifths')) <= 7
        if shift % 12 == 0:
            assert root.findtext('part/measure/attributes/key/fifths') == str(fifths)


def test_contextual_spelling_and_written_instrument_pitch(api):
    c = core(api)
    root = make_score(0)
    c.transpose_tree(root, 2)
    assert root.findtext('part/measure/attributes/key/fifths') == '2'
    assert [(p.findtext('step'), p.findtext('alter', '0')) for p in root.iter('pitch')] == [
        ('D','0'),('E','0'),('F','1'),('G','0'),('A','0'),('B','0'),('C','1')]
    for source, (source_chromatic, _) in c.INSTRUMENTS.items():
        for target, (target_chromatic, _) in c.INSTRUMENTS.items():
            root = make_score(0, 'C')
            c.transpose_tree(root, source_chromatic-target_chromatic, source_instrument=source, target_instrument=target)
            pitch = root.find('part/measure/note/pitch')
            attrs = root.find('part/measure/attributes/transpose')
            offset = int(attrs.findtext('chromatic')) + 12*int(attrs.findtext('octave-change','0'))
            assert number(pitch) + offset == 60 + source_chromatic


def test_rhythm_dynamics_and_unpitched_percussion_are_preserved(api):
    c = core(api)
    root = make_score(0, 'C')
    measure = root.find('part/measure')
    measure.append(ET.fromstring('<note><rest/><duration>12</duration><voice>2</voice><type>half</type><dot/></note>'))
    measure.append(ET.fromstring('<note><unpitched><display-step>F</display-step><display-octave>4</display-octave></unpitched><duration>4</duration><voice>3</voice><type>quarter</type></note>'))
    second = ET.fromstring('<part id="P2"><measure number="1"><attributes><key><fifths>0</fifths></key></attributes><note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched></note></measure></part>')
    root.append(second)
    before = copy.deepcopy(root)
    c.transpose_tree(root, -3)
    assert ET.tostring(second) == ET.tostring(before.findall('part')[1])
    for name in ('duration','voice','type','dot','rest','unpitched','direction','time','clef'):
        assert [ET.tostring(x) for x in root.iter(name)] == [ET.tostring(x) for x in before.iter(name)]


def test_tie_across_key_change_retains_spelling_and_courtesy(api):
    c = core(api)
    root = make_score(0, 'C')
    first = root.find('part/measure/note')
    ET.SubElement(first, 'tie', {'type':'start'})
    root.find('part').append(ET.fromstring('<measure number="2"><attributes><key><fifths>5</fifths></key></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type><tie type="stop"/><accidental parentheses="yes">natural</accidental></note></measure>'))
    c.transpose_tree(root, 1)
    pitches = list(root.iter('pitch'))
    assert ET.tostring(pitches[0]) == ET.tostring(pitches[1])
    accidental = root.find('part/measure[2]/note/accidental')
    assert accidental.text == 'flat' and accidental.get('parentheses') == 'yes'


def test_harmony_and_minor_mode(api):
    c = core(api)
    root = make_score(0, 'A')
    ET.SubElement(root.find('part/measure/attributes/key'), 'mode').text='minor'
    root.find('part/measure').insert(1, ET.fromstring('<harmony><root><root-step>A</root-step></root><kind>minor</kind><bass><bass-step>C</bass-step></bass></harmony>'))
    c.transpose_tree(root, 2)
    assert root.findtext('part/measure/attributes/key/mode') == 'minor'
    assert root.findtext('part/measure/harmony/root/root-step') == 'B'
    assert root.findtext('part/measure/harmony/bass/bass-step') == 'D'


def test_microtones_are_not_truncated(api):
    c=core(api)
    root=make_score(0,'C')
    ET.SubElement(root.find('part/measure/note/pitch'),'alter').text='0.5'
    with pytest.raises(ValueError,match='微分音'):
        c.transpose_tree(root,1)
