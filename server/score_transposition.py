"""Deterministic MusicXML transposition, independent of PDF or recognition format.

Pitch spelling follows the target key rather than a pitch-class lookup. The
integer written octave belongs to the letter name, including B-sharp/C-flat.
Compatible with the production API's Python 3.6 runtime.
"""
import xml.etree.ElementTree as ET
from fractions import Fraction

LETTERS = 'CDEFGAB'
NATURALS = (0, 2, 4, 5, 7, 9, 11)
ACCIDENTALS = {-2: 'flat-flat', -1: 'flat', 0: 'natural', 1: 'sharp', 2: 'double-sharp'}
INSTRUMENTS = {
    'concert_c': (0, 0), 'piccolo': (12, 7),
    'clarinet_a': (-3, -2), 'clarinet_bb': (-2, -1),
    'bass_clarinet_bb': (-14, -8), 'trumpet_bb': (-2, -1),
    'soprano_sax_bb': (-2, -1), 'tenor_sax_bb': (-14, -8),
    'sax_eb': (-9, -5), 'baritone_sax_eb': (-21, -12),
    'horn_f': (-7, -4), 'english_horn_f': (-7, -4),
}


def local(tag):
    return tag.rsplit('}', 1)[-1]


def child(node, name):
    return next((item for item in node if local(item.tag) == name), None)


def tag(node, name):
    return node.tag.rsplit('}', 1)[0] + '}' + name if node.tag.startswith('{') else name


def value(node, name, default=''):
    item = child(node, name)
    return item.text.strip() if item is not None and item.text else default


def integer(value, label):
    try:
        number = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ValueError('%s 格式无效' % label)
    if number.denominator != 1:
        raise ValueError('暂不支持微分音：%s 必须为整数' % label)
    return int(number)


def pitch_number(step, alter, octave):
    if step not in LETTERS:
        raise ValueError('无法识别的音名：%s' % step)
    return 12 * (integer(octave, '八度') + 1) + NATURALS[LETTERS.index(step)] + integer(alter, '变音')


def transpose_pitch(step, alter, octave, chromatic, diatonic):
    original = pitch_number(step, alter, octave)
    letter_number = integer(octave, '八度') * 7 + LETTERS.index(step) + diatonic
    new_octave, new_index = divmod(letter_number, 7)
    new_alter = original + chromatic - (12 * (new_octave + 1) + NATURALS[new_index])
    if new_alter not in ACCIDENTALS:
        raise ValueError('目标音需要超过重升或重降的记谱，请选择自动升降号或其他等音调')
    return LETTERS[new_index], new_alter, new_octave


def key_plan(fifths, semitones, preference='auto', preferred_steps=None):
    """Choose an enharmonic key, returning its fifths and the letter displacement."""
    fifths = integer(fifths, '调号')
    if semitones % 12 == 0 and preference == 'auto':
        return fifths, 7 * (semitones // 12)
    candidates = []
    for target in range(-7, 8):
        delta = fifths + 7 * semitones - target
        if delta % 12:
            continue
        steps = delta // 12
        sign_penalty = int((preference == 'sharps' and target < 0) or
                           (preference == 'flats' and target > 0))
        interval_penalty = abs(steps - preferred_steps) if preferred_steps is not None else 0
        candidates.append(((sign_penalty, interval_penalty, abs(target), target < 0), target, steps))
    _, target, steps = min(candidates)
    return target, steps


def put(node, name, text, before=()):
    item = child(node, name)
    if item is None:
        item = ET.Element(tag(node, name))
        position = next((i for i, entry in enumerate(node) if local(entry.tag) in before), len(node))
        node.insert(position, item)
    item.text = str(text)
    return item


def put_pitch(node, pitch):
    step, alter, octave = pitch
    put(node, 'step', step, ('alter', 'octave'))
    if alter:
        put(node, 'alter', alter, ('octave',))
    elif child(node, 'alter') is not None:
        node.remove(child(node, 'alter'))
    put(node, 'octave', octave)


def set_instrument_transposition(attributes, instrument):
    chromatic, diatonic = INSTRUMENTS[instrument]
    # The octave-change holds complete octaves; -14 = -2 plus one octave down.
    octaves = int(chromatic / 12)
    for entry in list(attributes):
        if local(entry.tag) == 'transpose':
            attributes.remove(entry)
    transposition = ET.Element(tag(attributes, 'transpose'))
    put(transposition, 'diatonic', diatonic - octaves * 7)
    put(transposition, 'chromatic', chromatic - octaves * 12)
    if octaves:
        put(transposition, 'octave-change', octaves)
    position = next((i for i, item in enumerate(attributes)
                     if local(item.tag) in ('directive', 'measure-style')), len(attributes))
    attributes.insert(position, transposition)


def transpose_tree(root, semitones, preference='auto', source_instrument=None, target_instrument=None):
    semitones = integer(semitones, '转调半音数')
    if preference not in ('auto', 'sharps', 'flats'):
        raise ValueError('升降号偏好无效')
    instrument_mode = source_instrument is not None and target_instrument is not None
    preferred_steps = None
    if instrument_mode:
        if source_instrument not in INSTRUMENTS or target_instrument not in INSTRUMENTS:
            raise ValueError('乐器无效')
        source_offset = INSTRUMENTS[source_instrument]
        target_offset = INSTRUMENTS[target_instrument]
        if source_offset[0] - target_offset[0] != semitones:
            raise ValueError('乐器与转调音程不一致')
        preferred_steps = source_offset[1] - target_offset[1]

    count, measure_count = 0, 0
    parts = [part for part in root if local(part.tag) == 'part']
    if not parts:
        raise ValueError('乐谱缺少可处理的声部')
    for part in parts:
        keys = {'1': key_plan(0, semitones, preference, preferred_steps)}
        active_ties = {}
        measures = [m for m in part if local(m.tag) == 'measure']
        measure_count = max(measure_count, len(measures))
        has_pitch = any(local(item.tag) == 'pitch' for item in part.iter())
        if not has_pitch:
            continue
        initial_attributes = False
        for measure in measures:
            if not initial_attributes and has_pitch:
                attrs = child(measure, 'attributes')
                if attrs is None:
                    attrs = ET.Element(tag(measure, 'attributes'))
                    position = 1 if len(measure) and local(measure[0].tag) == 'print' else 0
                    measure.insert(position, attrs)
                if not any(local(item.tag) == 'key' for item in attrs):
                    key = ET.Element(tag(attrs, 'key'))
                    put(key, 'fifths', 0)
                    position = 1 if len(attrs) and local(attrs[0].tag) == 'divisions' else 0
                    attrs.insert(position, key)
                if instrument_mode:
                    set_instrument_transposition(attrs, target_instrument)
                initial_attributes = True
            for item in measure:
                kind = local(item.tag)
                if kind == 'attributes':
                    for key in [entry for entry in item if local(entry.tag) == 'key']:
                        if child(key, 'cancel') is not None:
                            # Engraving software regenerates cancellation from adjacent keys.
                            key.remove(child(key, 'cancel'))
                        fifths_node = child(key, 'fifths')
                        if fifths_node is None:
                            raise ValueError('此乐谱使用非传统调号，需要单独校对')
                        plan = key_plan(fifths_node.text, semitones, preference, preferred_steps)
                        if key.get('number'):
                            keys[key.get('number')] = plan
                        else:
                            keys = {staff: plan for staff in keys}
                            keys['1'] = plan
                        fifths_node.text = str(plan[0])
                    if instrument_mode and child(item, 'transpose') is not None:
                        set_instrument_transposition(item, target_instrument)
                elif kind == 'note':
                    pitch = child(item, 'pitch')
                    if pitch is None:
                        continue  # Untuned percussion and all rests retain their notation.
                    staff = value(item, 'staff', '1')
                    step, alter, octave = value(pitch, 'step'), integer(value(pitch, 'alter', '0'), '变音'), integer(value(pitch, 'octave'), '八度')
                    voice = value(item, 'voice', '1')
                    before_midi = pitch_number(step, alter, octave)
                    tie_key = (staff, voice, before_midi)
                    ties = {entry.get('type') for entry in item if local(entry.tag) == 'tie'}
                    if 'stop' in ties and tie_key in active_ties:
                        result = active_ties[tie_key]
                    else:
                        result = transpose_pitch(step, alter, octave, semitones, keys.get(staff, keys['1'])[1])
                    put_pitch(pitch, result)
                    accidental = child(item, 'accidental')
                    if accidental is not None:
                        accidental.text = ACCIDENTALS[result[1]]
                    if 'stop' in ties:
                        active_ties.pop(tie_key, None)
                    if 'start' in ties:
                        active_ties[tie_key] = result
                    count += 1
                elif kind == 'harmony':
                    staff = value(item, 'staff', '1')
                    steps = keys.get(staff, keys['1'])[1]
                    for name in ('root', 'bass'):
                        node = child(item, name)
                        if node is None:
                            continue
                        step = value(node, name + '-step')
                        alter = integer(value(node, name + '-alter', '0'), '和弦变音')
                        new_step, new_alter, _ = transpose_pitch(step, alter, 4, semitones, steps)
                        put(node, name + '-step', new_step, (name + '-alter',))
                        if new_alter:
                            put(node, name + '-alter', new_alter)
                        elif child(node, name + '-alter') is not None:
                            node.remove(child(node, name + '-alter'))
    return {'noteEvents': count, 'measures': measure_count}
