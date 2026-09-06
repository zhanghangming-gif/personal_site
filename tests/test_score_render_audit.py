import xml.etree.ElementTree as ET


def tree(notes, divisions=1, direction=''):
    return ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>%s</divisions></attributes>%s%s</measure></part></score-partwise>' % (divisions, direction, notes))


def note(step='C', duration=1, extra=''):
    return '<note>%s<pitch><step>%s</step><octave>4</octave></pitch><duration>%s</duration><type>quarter</type></note>' % (extra, step, duration)


def test_export_divisions_and_chord_order_do_not_change_music(api):
    from score_render_audit import compare_rendered_score
    a = tree(note('C') + note('E', extra='<chord/>'))
    b = tree(note('E', 480) + note('C', 480, '<chord/>'), 480)
    assert compare_rendered_score(a, b)['eventsMatch']


def test_detects_missing_note_changed_rest_duration_and_dynamic(api):
    from score_render_audit import compare_rendered_score
    direction = '<direction><direction-type><dynamics><f/></dynamics></direction-type></direction>'
    expected = tree(note() + '<note><rest/><duration>3</duration></note>', direction=direction)
    for other in (tree(note()), tree(note('D') + '<note><rest/><duration>3</duration></note>'),
                  tree(note() + '<note><rest/><duration>2</duration></note>')):
        audit = compare_rendered_score(expected, other)
        assert not audit['eventsMatch'] and not audit['marksMatch']


def test_export_breaks_are_systems_not_staves(api):
    from score_render_audit import exported_layout
    root = ET.fromstring('''<score-partwise><identification><encoding>
        <supports element="print" attribute="new-page" type="yes" value="yes"/>
        <supports element="print" attribute="new-system" type="yes" value="yes"/>
        </encoding></identification><part id="P1">
        <measure number="1"><attributes><staves>2</staves></attributes></measure>
        <measure number="2"><print new-system="yes"/></measure>
        <measure number="3"><print new-page="yes"/></measure>
        </part><part id="P2"><measure number="1"/></part></score-partwise>''')
    result = exported_layout(root)
    assert result['breaksDeclared']
    assert result['systemsPerPage'] == [2, 1]
    assert result['pageSystemStarts'] == [['1', '2'], ['3']]


def test_renderer_cannot_drop_slurs_or_tempo(api):
    from score_render_audit import compare_rendered_score
    expected=tree(note().replace('</note>','<notations><slur type="start" number="1"/></notations></note>'),
                  direction='<direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>120</per-minute></metronome></direction-type></direction>')
    audit=compare_rendered_score(expected,tree(note()))
    assert not audit['eventsMatch'] and not audit['marksMatch']
