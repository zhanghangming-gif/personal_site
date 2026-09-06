"""MusicXML-backed score IR with explicit provenance. Python 3.6 compatible.

Quarter-note times are rational strings, never floats. Locations describe the
MusicXML layout, not proven coordinates in the uploaded PDF. The original XML
remains the lossless source; this index does not claim to support every symbol.
"""
import hashlib
import json
from copy import deepcopy
from fractions import Fraction
from xml.etree import ElementTree as ET

from score_transposition import child, local, value, pitch_number, integer, INSTRUMENTS


LAYOUT_ATTRIBUTES = {'default-x', 'default-y', 'relative-x', 'relative-y',
                     'font-family', 'font-size', 'font-style', 'font-weight',
                     'color', 'placement', 'orientation', 'justify', 'halign',
                     'valign', 'id', 'bezier-x', 'bezier-y', 'bezier-x2', 'bezier-y2',
                     'bezier-offset', 'bezier-offset2'}


def canonical(node):
    """Keep musical data while excluding renderer-specific coordinates."""
    return [local(node.tag), sorted((key, val) for key, val in node.attrib.items()
                                   if key not in LAYOUT_ATTRIBUTES),
            ' '.join(''.join(node.itertext()).split()) if not len(node) else '',
            [canonical(item) for item in node]]


def token(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def specification(semitones, preference='auto', source_instrument=None, target_instrument=None):
    if isinstance(semitones, bool):
        raise ValueError('转调半音数不能为布尔值')
    semitones = integer(semitones, '转调半音数')
    if not -48 <= semitones <= 48 or preference not in ('auto', 'sharps', 'flats'):
        raise ValueError('转调规格无效')
    if (source_instrument is None) != (target_instrument is None):
        raise ValueError('源乐器和目标乐器必须同时指定')
    instrument = source_instrument is not None
    diatonic = None
    if instrument:
        if source_instrument not in INSTRUMENTS or target_instrument not in INSTRUMENTS:
            raise ValueError('乐器无效')
        source, target = INSTRUMENTS[source_instrument], INSTRUMENTS[target_instrument]
        if semitones != source[0] - target[0]:
            raise ValueError('乐器与转调音程不一致')
        diatonic = source[1] - target[1]
    return {'mode': 'instrument' if instrument else 'custom',
            'writtenSemitones': semitones, 'preferredDiatonicSteps': diatonic,
            'soundingSemitones': 0 if instrument else semitones,
            'sourceInstrument': source_instrument, 'targetInstrument': target_instrument,
            'accidentalPreference': preference, 'preserveOriginalLayout': True}


def score_ir(root, origin='musicxml', document_sha256=None, artifact_sha256=None):
    if local(root.tag) != 'score-partwise':
        raise ValueError('只接受 partwise MusicXML 乐谱')
    xml_sha = artifact_sha256 or hashlib.sha256(ET.tostring(root, encoding='utf-8')).hexdigest()
    result = {'schemaVersion': 1, 'documentSha256': document_sha256,
              'artifactSha256': xml_sha, 'origin': origin,
              'sourceRecognitionVerified': False, 'parts': [], 'warnings': [],
              'coverage': {'pdfObjectMapping': 'unavailable',
                           'sourceMusicVerification': 'pending',
                           'scope': 'MusicXML event and notation index'}}
    for pi, part in enumerate((p for p in root if local(p.tag) == 'part'), 1):
        divisions, page, system = Fraction(1), 1, 1
        state = {'key': {'1': 0}, 'time': {}, 'clef': {}}
        indexed = {'id': 'p%s' % pi, 'sourcePartId': part.get('id'), 'measures': []}
        for mi, measure in enumerate((m for m in part if local(m.tag) == 'measure'), 1):
            printing = child(measure, 'print')
            if mi > 1 and printing is not None:
                if printing.get('new-page') == 'yes':
                    page, system = page + 1, 1
                elif printing.get('new-system') == 'yes':
                    system += 1
            mid = 'p%s-m%s' % (pi, mi)
            location = {'part': pi, 'measureIndex': mi, 'measure': measure.get('number', str(mi)),
                        'page': page, 'system': system, 'layoutBasis': 'musicxml_breaks'}
            current = {'id': mid, 'location': location, 'events': [], 'marks': [],
                       'implicit': measure.get('implicit') == 'yes',
                       'nonControlling': measure.get('non-controlling') == 'yes'}
            position, previous = Fraction(0), None
            for node in measure:
                kind = local(node.tag)
                if kind == 'attributes':
                    divisions = Fraction(value(node, 'divisions', str(divisions)))
                    if divisions <= 0:
                        raise ValueError('MusicXML divisions 必须大于零')
                    for entry in node:
                        name = local(entry.tag)
                        if name in state:
                            staff = entry.get('number', '1')
                            if name == 'key':
                                fifths = child(entry, 'fifths')
                                datum = integer(fifths.text, '调号') if fifths is not None else canonical(entry)
                                if fifths is None:
                                    result['warnings'].append({'code': 'nontraditional_key', 'location': location})
                            elif name == 'clef':
                                datum = [value(entry, 'sign'), value(entry, 'line'), value(entry, 'clef-octave-change', '0')]
                            else:
                                datum = [canonical(x) for x in entry]
                            if name == 'key' and 'number' not in entry.attrib:
                                state[name] = {k: datum for k in state[name]}
                            state[name][staff] = datum
                        elif name == 'measure-style':
                            current['marks'].append({'kind': name, 'onset': str(position),
                                                     'staff': entry.get('number', '1'), 'data': canonical(entry)})
                elif kind in ('backup', 'forward'):
                    delta = Fraction(value(node, 'duration', '0')) / divisions
                    if delta <= 0:
                        raise ValueError('MusicXML backup/forward 时值必须大于零')
                    position += delta * (-1 if kind == 'backup' else 1)
                    previous = None
                    if position < 0:
                        raise ValueError('第 %s 小节的声部时间轴越过小节起点' % location['measure'])
                elif kind == 'note':
                    grace, chord = child(node, 'grace') is not None, child(node, 'chord') is not None
                    duration = Fraction(value(node, 'duration', '0')) / divisions
                    if duration < 0 or (not grace and duration == 0):
                        raise ValueError('第 %s 小节存在无效音符时值' % location['measure'])
                    if chord and previous is None:
                        raise ValueError('和弦音缺少前置音符')
                    onset = previous if chord else position
                    staff, voice = value(node, 'staff', '1'), value(node, 'voice', '1')
                    pitch, unpitched = child(node, 'pitch'), child(node, 'unpitched')
                    spelling = None
                    if pitch is not None:
                        spelling = {'step': value(pitch, 'step'), 'alter': integer(value(pitch, 'alter', '0'), '变音'),
                                    'octave': integer(value(pitch, 'octave'), '八度')}
                    event = {'id': '%s-n%s' % (mid, len(current['events']) + 1),
                             'location': dict(location, staff=staff, voice=voice, onsetQuarter=str(onset)),
                             'kind': 'note' if pitch is not None else 'unpitched' if unpitched is not None else 'rest',
                             'pitch': spelling,
                             'midi': pitch_number(spelling['step'], spelling['alter'], spelling['octave']) if spelling else None,
                             'unpitched': canonical(unpitched) if unpitched is not None else None,
                             'onset': str(onset), 'duration': str(duration), 'staff': staff, 'voice': voice,
                             'grace': grace, 'cue': child(node, 'cue') is not None,
                             'visible': node.get('print-object', 'yes'),
                             'ties': sorted(x.get('type', '') for x in node if local(x.tag) == 'tie'),
                             'lyrics': [canonical(x) for x in node if local(x.tag) == 'lyric'],
                             'notations': [], 'spanners': [],
                             'writtenType': value(node, 'type'),
                             'dots': sum(local(x.tag) == 'dot' for x in node),
                             'accidental': canonical(child(node, 'accidental')) if child(node, 'accidental') is not None else None,
                             'beams': [canonical(x) for x in node if local(x.tag) == 'beam'],
                             'timeModification': canonical(child(node, 'time-modification')) if child(node, 'time-modification') is not None else None,
                             'context': {name: values.get(staff, values.get('1')) for name, values in state.items()},
                             'evidence': {'status': 'unverified', 'origin': origin, 'pdfObjects': [], 'bbox': None}}
                    for group in node:
                        if local(group.tag) != 'notations':
                            continue
                        for entry in group:
                            name = local(entry.tag)
                            if name in ('slur', 'glissando', 'slide', 'tuplet'):
                                event['spanners'].append({'kind': name, 'type': entry.get('type', ''),
                                                          'number': entry.get('number', '1')})
                            elif name != 'tied':  # Sounding ties are captured above; drawing endpoints in original XML.
                                event['notations'].append(canonical(entry))
                    current['events'].append(event)
                    previous = onset
                    if not grace and not chord:
                        position += duration
                elif kind in ('direction', 'harmony', 'figured-bass', 'barline'):
                    onset = str(position + Fraction(value(node, 'offset', '0')) / divisions)
                    staff = value(node, 'staff', '1')
                    for entry in node:
                        name = local(entry.tag)
                        if name in ('offset', 'staff', 'voice', 'footnote', 'level'):
                            continue
                        elements = list(entry) if name == 'direction-type' else [entry]
                        for element in elements:
                            if local(element.tag) == 'sound':
                                # Playback-only synthesizer defaults do not certify printed tempo.
                                data = ['sound', sorted((k, v) for k, v in element.attrib.items()
                                                         if k in ('tempo', 'dacapo', 'dalsegno', 'tocoda', 'fine')), '', []]
                                if not data[1]:
                                    continue
                            else:
                                data = canonical(element)
                            current['marks'].append({'kind': kind, 'onset': onset, 'staff': staff, 'data': data,
                                                     'side': node.get('location', 'right') if kind == 'barline' else ''})
                elif kind not in ('print', 'sound', 'bookmark', 'link'):
                    result['warnings'].append({'code': 'unindexed_measure_element', 'element': kind, 'location': location})
            current['context'] = deepcopy(state)
            indexed['measures'].append(current)
        result['parts'].append(indexed)
    if not result['parts']:
        raise ValueError('乐谱缺少声部')
    events = [e for p in result['parts'] for m in p['measures'] for e in m['events']]
    result['counts'] = {'parts': len(result['parts']), 'measures': sum(len(p['measures']) for p in result['parts']),
                        'notes': sum(e['kind'] == 'note' for e in events), 'rests': sum(e['kind'] == 'rest' for e in events),
                        'unpitched': sum(e['kind'] == 'unpitched' for e in events), 'events': len(events)}
    return result
