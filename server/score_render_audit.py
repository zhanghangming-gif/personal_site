"""Check the score re-exported by the PDF renderer, not just its input XML.

Durations are rational quarter-note values, so changes to MusicXML divisions
and chord serialization do not create false mismatches. Python 3.6 compatible.
"""
from collections import Counter
from fractions import Fraction
from score_transposition import local, child, value, pitch_number
from score_ir import score_ir
from score_ir_audit import compare_ir


def semantic_measures(root):
    parts = []
    for part in (p for p in root if local(p.tag) == 'part'):
        divisions = Fraction(1)
        measures = []
        for measure in (m for m in part if local(m.tag) == 'measure'):
            position, previous = Fraction(0), Fraction(0)
            events, marks = Counter(), Counter()
            for node in measure:
                kind = local(node.tag)
                if kind == 'attributes':
                    divisions = Fraction(value(node, 'divisions', str(divisions)))
                    if divisions <= 0:
                        raise ValueError('Invalid MusicXML divisions')
                elif kind in ('backup', 'forward'):
                    position += Fraction(value(node, 'duration', '0')) / divisions * (-1 if kind == 'backup' else 1)
                elif kind == 'note':
                    duration = Fraction(value(node, 'duration', '0')) / divisions
                    grace = child(node, 'grace') is not None
                    chord = child(node, 'chord') is not None
                    onset = previous if chord else position
                    pitch, unpitched = child(node, 'pitch'), child(node, 'unpitched')
                    if pitch is not None:
                        identity = ('pitch', pitch_number(value(pitch, 'step'), value(pitch, 'alter', '0'), value(pitch, 'octave')))
                    elif unpitched is not None:
                        identity = ('unpitched', value(unpitched, 'display-step'), value(unpitched, 'display-octave'))
                    else:
                        identity = ('rest',)
                    ties = tuple(sorted(item.get('type', '') for item in node if local(item.tag) == 'tie'))
                    articulations = tuple(sorted(local(item.tag) for group in node.iter()
                                                if local(group.tag) in ('articulations', 'ornaments') for item in group))
                    notation_details = []
                    for item in node.iter():
                        name = local(item.tag)
                        if name == 'slur':
                            notation_details.append(('slur', item.get('type', '')))
                        elif name in ('fermata', 'tremolo'):
                            notation_details.append((name, (item.text or '').strip(), item.get('type', '')))
                    # Voices may be renumbered by import, but staff, onset,
                    # duration and simultaneous pitches must survive.
                    events[(str(onset), str(duration), value(node, 'staff', '1'), identity, grace, ties, articulations, tuple(sorted(notation_details)))] += 1
                    previous = onset
                    if not grace and not chord:
                        position += duration
                elif kind == 'direction':
                    offset = Fraction(value(node, 'offset', '0')) / divisions
                    onset = str(position + offset)
                    for item in node.iter():
                        name = local(item.tag)
                        if name == 'dynamics':
                            for dynamic in item:
                                marks[(onset, 'dynamic', local(dynamic.tag))] += 1
                        elif name in ('words', 'rehearsal'):
                            text = ''.join(item.itertext()).strip()
                            if text:
                                marks[(onset, name, ' '.join(text.split()))] += 1
                        elif name in ('wedge', 'pedal', 'octave-shift'):
                            marks[(onset, name, item.get('type', ''))] += 1
                        elif name == 'metronome':
                            marks[(onset, name, tuple((local(entry.tag), (entry.text or '').strip()) for entry in item))] += 1
                elif kind == 'barline':
                    for item in node:
                        if local(item.tag) == 'repeat':
                            marks[('barline', 'repeat', item.get('direction', ''))] += 1
                        elif local(item.tag) == 'ending':
                            marks[('barline', 'ending', item.get('number', ''), item.get('type', ''))] += 1
            measures.append((measure.get('number', ''), events, marks))
        parts.append(measures)
    return parts


def compare_rendered_score(expected, rendered):
    left, right = semantic_measures(expected), semantic_measures(rendered)
    events_ok = len(left) == len(right)
    marks_ok = events_ok
    examples = []
    for part_index, (before, after) in enumerate(zip(left, right), 1):
        if len(before) != len(after):
            events_ok = marks_ok = False
            examples.append('声部 %s：小节数 %s → %s' % (part_index, len(before), len(after)))
        for index, (a, b) in enumerate(zip(before, after), 1):
            if a[1] != b[1]:
                events_ok = False
                if len(examples) < 8:
                    examples.append('声部 %s，第 %s 小节：音符、时值或奏法发生变化' % (part_index, a[0] or index))
            if a[2] != b[2]:
                marks_ok = False
                if len(examples) < 8:
                    examples.append('声部 %s，第 %s 小节：演奏标记发生变化' % (part_index, a[0] or index))
    detailed = compare_ir(score_ir(expected, 'transposed-musicxml'), score_ir(rendered, 'renderer-export'))
    return {'eventsMatch': events_ok, 'marksMatch': marks_ok, 'differences': examples,
            'semanticAudit': detailed,
            'checks': [
                {'id': 'rendered_events', 'label': 'PDF 排版后的音符与节奏', 'passed': events_ok,
                 'detail': '已重新导出最终排版谱，核对全部声部的音高、时值、休止与延音' if events_ok else '排版导入或导出改变了音符、时值或奏法：' + '；'.join(examples)},
                {'id': 'rendered_marks', 'label': 'PDF 排版后的演奏标记', 'passed': marks_ok,
                 'detail': '力度、渐强渐弱、文字、排练与反复标记一致' if marks_ok else '排版后部分演奏标记发生变化，需要复核'},
                {'id': 'rendered_semantics', 'label': '输出乐谱的逐音对应', 'passed': detailed['passed'],
                 'detail': '排版导出数据中的音名、声部、歌词及标记一致；尚非从 PDF 独立识别' if detailed['passed'] else
                 '发现 %s 处差异：%s' % (detailed['issueCount'], '；'.join(x['message'] for x in detailed['issues'][:4]))},
            ]}


def exported_layout(root):
    """MuseScore's exported print elements describe computed page/system breaks."""
    supports = {item.get('attribute') for item in root.iter()
                if local(item.tag) == 'supports' and item.get('element') == 'print'
                and item.get('type') == 'yes' and item.get('value') == 'yes'}
    part = next((item for item in root if local(item.tag) == 'part'), None)
    pages = []
    if part is not None:
        for measure in (item for item in part if local(item.tag) == 'measure'):
            printing = child(measure, 'print')
            if not pages or (printing is not None and printing.get('new-page') == 'yes'):
                pages.append([measure.get('number')])
            elif printing is not None and printing.get('new-system') == 'yes':
                pages[-1].append(measure.get('number'))
    return {'breaksDeclared': {'new-page', 'new-system'} <= supports,
            'systemsPerPage': [len(page) for page in pages], 'pageSystemStarts': pages}
