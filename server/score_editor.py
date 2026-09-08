"""Explicitly unverified candidate export and versioned, bounded note edits."""
import copy
import json
import os
import re
import xml.etree.ElementTree as ET
from fractions import Fraction

from score_ir import score_ir
from score_review import file_digest, save_json
from score_transposition import child, local, value, put, put_pitch, tag, ACCIDENTALS


EVENT_ID = re.compile(r'^p([1-9][0-9]*)-m([1-9][0-9]*)-n([1-9][0-9]*)$')
MEASURE_ID = re.compile(r'^p([1-9][0-9]*)-m([1-9][0-9]*)$')

REST_TYPES = {
    'maxima_rest': 'maxima', 'long_rest': 'long', 'breve_rest': 'breve',
    'whole_rest': 'whole', 'half_rest': 'half', 'quarter_rest': 'quarter',
    'eighth_rest': 'eighth', '16th_rest': '16th', '32nd_rest': '32nd',
    '64th_rest': '64th', '128th_rest': '128th',
}

REST_LABELS = {
    'maxima_rest': '倍全休止符', 'long_rest': '长休止符', 'breve_rest': '二全休止符',
    'whole_rest': '全休止符', 'half_rest': '二分休止符', 'quarter_rest': '四分休止符',
    'eighth_rest': '八分休止符', '16th_rest': '十六分休止符',
    '32nd_rest': '三十二分休止符', '64th_rest': '六十四分休止符',
    '128th_rest': '一百二十八分休止符',
}


def regular_file(job_dir, name):
    path = os.path.join(job_dir, name)
    return path if os.path.isfile(path) and not os.path.islink(path) and os.path.getsize(path) <= 25 * 1024 * 1024 else None


def candidate_info(job_dir, status, page_count):
    if status in ('queued', 'processing'):
        return None
    path = regular_file(job_dir, 'output.pdf')
    if not path:
        return None
    manifest = os.path.join(job_dir, 'candidate-manifest.json')
    try:
        digest = file_digest(path)
        if os.path.isfile(manifest):
            with open(manifest, encoding='utf-8') as stream:
                result = json.load(stream)
            return result if result.get('sha256') == digest else None
        with open(path, 'rb') as stream:
            if not stream.read(8).startswith(b'%PDF-'):
                return None
        pages = page_count(path)
        if not pages or not 1 <= pages <= 40:
            return None
        result = {'sha256': digest, 'pages': pages, 'verified': False}
        save_json(manifest, result)
        return result
    except (OSError, ValueError, RuntimeError):
        return None


def editor_data(job_dir, read_xml):
    path = regular_file(job_dir, 'transposed.musicxml')
    if not path:
        raise ValueError('这份结果没有可编辑的 MusicXML；仍可下载已生成的 PDF')
    digest = file_digest(path)
    index = score_ir(read_xml(path), 'editable-target', artifact_sha256=digest)
    measures = []
    for part in index['parts']:
        for measure in part['measures']:
            measures.append({'id': measure['id'], 'location': measure['location'],
                             'events': [{'id': e['id'], 'kind': e['kind'], 'pitch': e['pitch'],
                                         'duration': e['duration'], 'onset': e['onset'],
                                         'staff': e['staff'], 'voice': e['voice'], 'grace': e['grace'],
                                         'clef': e['context']['clef'], 'ties': e['ties']}
                                        for e in measure['events']]})
    structure_gaps = []
    try:
        with open(os.path.join(job_dir, 'pipeline-report.json'), encoding='utf-8') as stream:
            report = json.load(stream)
        repair = (((report.get('verification') or {}).get('omr') or {}).get('multirestRepair') or {})
        for gap in repair.get('unresolvedGaps') or []:
            if not isinstance(gap, dict):
                continue
            count = gap.get('missingMeasures')
            if type(count) is not int or not 1 <= count <= 64:
                continue
            candidates = [item for item in gap.get('candidateMeasures', [])
                          if isinstance(item, dict) and item.get('measureId')]
            system_measures = [item for item in gap.get('systemMeasures', [])
                               if isinstance(item, dict) and item.get('measureId')]
            structure_gaps.append({
                'id': str(gap.get('id') or 'gap-%s' % (len(structure_gaps) + 1)),
                'page': gap.get('page'), 'system': gap.get('system'),
                'lineStart': gap.get('lineStart'), 'nextLineStart': gap.get('nextLineStart'),
                'missingMeasures': count, 'reason': str(gap.get('reason') or ''),
                'contentKnown': False, 'requiresConfirmation': True,
                'candidateMeasures': candidates, 'systemMeasures': system_measures,
            })
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    rest_suggestions = []
    try:
        with open(os.path.join(job_dir, 'review', 'rhythm-gaps.json'), encoding='utf-8') as stream:
            rhythm = json.load(stream)
        with open(os.path.join(job_dir, 'review', 'rest-classification.json'), encoding='utf-8') as stream:
            classified = json.load(stream)
        by_gap = {item.get('gapId'): item for item in classified.get('classifications', [])
                  if isinstance(item, dict) and item.get('gapId')}
        for gap in rhythm.get('gaps', []):
            if not isinstance(gap, dict) or gap.get('id') not in by_gap:
                continue
            item = by_gap[gap['id']]
            notation = item.get('suggestedNotation')
            notation_sequence = [value for value in item.get('suggestedNotationSequence', [])
                                 if value in REST_TYPES]
            evidence = item.get('selectedEvidence') or {}
            risks = [str(value) for value in gap.get('riskReasons', [])]
            confirmable = (item.get('status') in (
                               'supported_by_omr_object',
                               'supported_by_visual_model',
                               'supported_by_omr_and_visual_model')
                           and notation in REST_TYPES and not risks)
            rest_suggestions.append({
                'gapId': gap['id'], 'measureId': gap.get('measureId'),
                'location': gap.get('location') or {}, 'voice': str(gap.get('voice') or '1'),
                'onset': gap.get('onset'), 'duration': gap.get('duration'),
                'position': gap.get('position'), 'reviewRegion': gap.get('reviewRegion'),
                'status': item.get('status'), 'notation': notation,
                'notationLabel': REST_LABELS.get(notation, notation),
                'notationSequence': notation_sequence,
                'notationSequenceLabels': [REST_LABELS.get(value, value)
                                           for value in notation_sequence],
                'dots': item.get('suggestedDots') or 0,
                'grade': evidence.get('grade'), 'contextGrade': evidence.get('contextGrade'),
                'riskReasons': risks, 'confirmable': confirmable,
                'requiresSourceConfirmation': True,
            })
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    source_path = regular_file(job_dir, os.path.join(
        'scores', 'source', 'canonical-source.musicxml'))
    intent = {}
    try:
        with open(os.path.join(job_dir, 'request.json'), encoding='utf-8') as stream:
            request = json.load(stream)
        intent = request.get('intent') or {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return {'revision': digest,
            'sourceRevision': file_digest(source_path) if source_path else None,
            'editBasis': 'canonical_source' if source_path else 'target_legacy',
            'canRetarget': bool(source_path and intent.get('mode') == 'instrument_rewrite'),
            'sourceInstrument': intent.get('sourceInstrument'),
            'targetInstrument': intent.get('targetInstrument'),
            'measures': measures, 'verified': False,
            'structureGaps': structure_gaps, 'restSuggestions': rest_suggestions,
            'scope': ('目标谱界面修改会回写源谱并重新执行确定性转调'
                      if source_path else
                      '旧版任务只修改目标谱；保持时值及小节结构')}


def carry_rest_review(parent_dir, child_dir, resolved_gap_ids):
    """Carry unresolved rest suggestions to a versioned edit job."""
    resolved = set(resolved_gap_ids or [])
    output_dir = os.path.join(child_dir, 'review')
    os.makedirs(output_dir, exist_ok=True)
    for filename in ('rhythm-gaps.json', 'rest-classification.json'):
        path = os.path.join(parent_dir, 'review', filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as stream:
                payload = json.load(stream)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if filename == 'rhythm-gaps.json':
            payload['gaps'] = [item for item in payload.get('gaps', [])
                               if item.get('id') not in resolved]
            summary = payload.setdefault('summary', {})
            summary['gapCount'] = len(payload['gaps'])
            payload['status'] = ('gaps_found' if payload['gaps'] or payload.get('overflows')
                                 else 'no_timeline_gaps_detected')
        else:
            payload['classifications'] = [item for item in payload.get('classifications', [])
                                          if item.get('gapId') not in resolved]
            counts = {}
            for item in payload['classifications']:
                status = item.get('status', 'unknown')
                counts[status] = counts.get(status, 0) + 1
            payload['summary'] = {
                'gapCount': len(payload['classifications']), 'statusCounts': counts,
                'supportedCount': sum(counts.get(status, 0) for status in (
                    'supported_by_omr_object', 'supported_by_visual_model',
                    'supported_by_omr_and_visual_model')),
            }
        save_json(os.path.join(output_dir, filename), payload)


def apply_edits(root, changes, rest_confirmations=None):
    """Edit target pitches only. No executable code or arbitrary XML accepted."""
    if not isinstance(changes, list) or not 1 <= len(changes) <= 200:
        raise ValueError('每次可修改 1 至 200 个音符')
    if len(changes) == 1 and isinstance(changes[0], dict) and changes[0].get('type') == 'insertRests':
        return insert_rests(root, changes[0])
    if len(changes) == 1 and isinstance(changes[0], dict) and changes[0].get('type') == 'confirmRest':
        return confirm_rest(root, changes[0], rest_confirmations or {})
    nodes = {}
    # Use the same traversal as the IR; IDs refer to the immutable parent XML.
    for pi, part in enumerate((p for p in root if local(p.tag) == 'part'), 1):
        for mi, measure in enumerate((m for m in part if local(m.tag) == 'measure'), 1):
            for ni, node in enumerate((n for n in measure if local(n.tag) == 'note'), 1):
                nodes['p%s-m%s-n%s' % (pi, mi, ni)] = node
    seen, log = set(), []
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'eventId', 'pitch'}:
            raise ValueError('修改格式无效')
        event_id, pitch = change['eventId'], change['pitch']
        if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id) or event_id in seen or event_id not in nodes:
            raise ValueError('音符编号不存在或重复，请重新载入乐谱')
        if not isinstance(pitch, dict) or set(pitch) != {'step', 'alter', 'octave'}:
            raise ValueError('音高格式无效')
        step, alter, octave = pitch['step'], pitch['alter'], pitch['octave']
        if (not isinstance(step, str) or step not in tuple('CDEFGAB') or type(alter) is not int or
                not -2 <= alter <= 2 or type(octave) is not int or not 0 <= octave <= 9):
            raise ValueError('请选择有效音名、升降号和 0 至 9 的八度')
        node = nodes[event_id]
        old_pitch = child(node, 'pitch')
        if old_pitch is None:
            raise ValueError('当前编辑器只修改有音高的音符，休止符和打击乐需在制谱软件中修改')
        previous = {'step': value(old_pitch, 'step'), 'alter': int(Fraction(value(old_pitch, 'alter', '0'))),
                    'octave': int(value(old_pitch, 'octave'))}
        put_pitch(old_pitch, (step, alter, octave))
        # Always make the chosen accidental explicit; including natural avoids a
        # preceding same-letter accidental overriding the user's correction.
        put(node, 'accidental', ACCIDENTALS[alter], ('time-modification', 'stem', 'notehead', 'staff', 'beam', 'notations', 'lyric'))
        seen.add(event_id)
        log.append({'eventId': event_id, 'before': previous, 'after': pitch})
    # Catch inconsistent edits to an existing tie rather than silently breaking it.
    active = {}
    for part in (p for p in root if local(p.tag) == 'part'):
        active.clear()
        for node in (n for n in part.iter() if local(n.tag) == 'note'):
            p = child(node, 'pitch')
            if p is None:
                continue
            key = (value(node, 'staff', '1'), value(node, 'voice', '1'),
                   value(p, 'step'), value(p, 'alter', '0'), value(p, 'octave'))
            ties = {t.get('type') for t in node if local(t.tag) == 'tie'}
            if 'stop' in ties and key not in active:
                raise ValueError('延音线两端音高不一致，请同时修改相连的音符')
            if 'stop' in ties:
                active.pop(key, None)
            if 'start' in ties:
                active[key] = True
    return log


def _active_divisions(root, part_position, measure_position):
    parts = [p for p in root if local(p.tag) == 'part']
    if not 0 <= part_position < len(parts):
        return None
    divisions = None
    measures = [m for m in parts[part_position] if local(m.tag) == 'measure']
    for measure in measures[:measure_position + 1]:
        attrs = child(measure, 'attributes')
        if attrs is not None and child(attrs, 'divisions') is not None:
            try:
                divisions = Fraction(value(attrs, 'divisions'))
            except (ValueError, ZeroDivisionError):
                return None
    return divisions


def _insertion_index(measure):
    children = list(measure)
    for position, node in enumerate(children):
        if local(node.tag) == 'barline' and node.get('location', 'right') == 'right':
            return position
    return len(children)


def confirm_rest(root, change, confirmations):
    """Insert one rest only from a server-side, source-confirmed suggestion.

    The browser supplies only a gap identifier.  Measure, voice, onset,
    duration and notation all come from the immutable review artifacts bound
    to the edited MusicXML revision.
    """
    if set(change) != {'type', 'gapId'} or not isinstance(change.get('gapId'), str):
        raise ValueError('休止符确认格式无效')
    suggestion = confirmations.get(change['gapId'])
    if not isinstance(suggestion, dict):
        raise ValueError('休止符建议不存在或已经处理，请重新载入')
    if (suggestion.get('status') not in (
                'supported_by_omr_object',
                'supported_by_visual_model',
                'supported_by_omr_and_visual_model')
            or suggestion.get('notation') not in REST_TYPES
            or suggestion.get('riskReasons')):
        raise ValueError('此项证据不足或存在节奏例外，不能快速补入；请下载 MusicXML 人工编辑')
    match = MEASURE_ID.fullmatch(str(suggestion.get('measureId') or ''))
    if not match:
        raise ValueError('休止符建议缺少可靠的小节位置')
    part_position, measure_position = int(match.group(1)) - 1, int(match.group(2)) - 1
    parts = [p for p in root if local(p.tag) == 'part']
    if not 0 <= part_position < len(parts):
        raise ValueError('目标声部不存在，请重新载入')
    measures = [m for m in parts[part_position] if local(m.tag) == 'measure']
    if not 0 <= measure_position < len(measures):
        raise ValueError('目标小节不存在，请重新载入')
    measure = measures[measure_position]
    divisions = _active_divisions(root, part_position, measure_position)
    onset, gap_duration = rational(suggestion.get('onset')), rational(suggestion.get('duration'))
    if divisions is None or divisions <= 0 or onset is None or gap_duration is None or gap_duration <= 0:
        raise ValueError('目标位置缺少可靠的时值单位')
    raw_duration = gap_duration * divisions
    if raw_duration.denominator != 1:
        raise ValueError('缺失时值无法用当前 MusicXML 时值单位精确表示')
    target_voice = str(suggestion.get('voice') or '1')
    notes = [node for node in measure if local(node.tag) == 'note']
    voices = {value(node, 'voice', '1') for node in notes}
    staffs = {value(node, 'staff', '1') for node in notes}
    if len(voices) > 1 or (voices and target_voice not in voices) or len(staffs) > 1:
        raise ValueError('该小节包含多声部或多谱表，不能用快速确认补入')
    if any(child(node, 'time-modification') is not None for node in notes):
        raise ValueError('该小节含连音时值，不能用快速确认补入')

    # Rebuild the one-voice XML cursor. A leading/internal gap must be backed
    # by one exact <forward>; replacing it preserves all following onsets.
    cursor, forward_node = Fraction(0), None
    for node in list(measure):
        name = local(node.tag)
        if name == 'backup':
            raise ValueError('该小节含并行声部时间轴，不能用快速确认补入')
        if name == 'forward':
            try:
                amount = Fraction(value(node, 'duration')) / divisions
            except (ValueError, ZeroDivisionError):
                raise ValueError('MusicXML forward 时值无效')
            if cursor == onset and amount == gap_duration:
                if forward_node is not None:
                    raise ValueError('缺失位置不唯一，请下载 MusicXML 人工编辑')
                forward_node = node
            cursor += amount
        elif name == 'note' and child(node, 'grace') is None and child(node, 'chord') is None:
            try:
                cursor += Fraction(value(node, 'duration')) / divisions
            except (ValueError, ZeroDivisionError):
                raise ValueError('MusicXML 音符时值无效')

    position = suggestion.get('position')
    if position in ('leading', 'internal') and forward_node is None:
        raise ValueError('无法在 MusicXML 时间游标中唯一定位这个休止符')
    if position in ('trailing', 'full_measure') and forward_node is None and cursor != onset:
        raise ValueError('当前版本的缺失起点已经变化，请重新识别或下载 MusicXML 编辑')
    if position not in ('leading', 'internal', 'trailing', 'full_measure'):
        raise ValueError('休止符位置类型无效')

    template = measure
    note = ET.Element(tag(template, 'note'))
    rest_attrs = {'measure': 'yes'} if position == 'full_measure' else {}
    ET.SubElement(note, tag(template, 'rest'), rest_attrs)
    ET.SubElement(note, tag(template, 'duration')).text = str(int(raw_duration))
    ET.SubElement(note, tag(template, 'voice')).text = target_voice
    ET.SubElement(note, tag(template, 'type')).text = REST_TYPES[suggestion['notation']]
    for _ in range(int(suggestion.get('dots') or 0)):
        ET.SubElement(note, tag(template, 'dot'))
    if staffs:
        ET.SubElement(note, tag(template, 'staff')).text = next(iter(staffs))
    if forward_node is not None:
        measure.insert(list(measure).index(forward_node), note)
        measure.remove(forward_node)
    else:
        measure.insert(_insertion_index(measure), note)
    label = REST_LABELS.get(suggestion['notation'], suggestion['notation'])
    return [{'eventId': change['gapId'], 'type': 'confirmRest',
             'before': '时间轴缺少 %s 个四分音符时值' % suggestion['duration'],
             'after': '用户对照原谱确认，在第 %s 小节声部 %s、起点 %s 补入%s；仍需核对新版 PDF'
                      % (measure.get('number', '?'), target_voice, suggestion['onset'], label),
             'gapId': change['gapId'], 'measureId': suggestion['measureId'],
             'voice': target_voice, 'onset': suggestion['onset'],
             'duration': suggestion['duration'], 'notation': suggestion['notation']}]


def rational(raw):
    try:
        return Fraction(str(raw))
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def insert_rests(root, change):
    """Insert a user-confirmed whole-bar or grouped multi-measure rest."""
    allowed = ({'type', 'measureId', 'count'},
               {'type', 'measureId', 'count', 'placement'})
    if (set(change) not in allowed or type(change.get('count')) is not int
            or not 1 <= change['count'] <= 64):
        raise ValueError('每次可补入 1 至 64 个整小节休止')
    placement = change.get('placement', 'after')
    if placement not in ('before', 'after'):
        raise ValueError('请选择在目标小节之前或之后补入')
    parts = [p for p in root if local(p.tag) == 'part']
    if len(parts) != 1:
        raise ValueError('补小节目前仅支持单乐器声部；多声部总谱请先导出 MusicXML 校正')
    part = parts[0]
    measures = [m for m in part if local(m.tag) == 'measure']
    ids = ['p1-m%s' % (i + 1) for i in range(len(measures))]
    if change['measureId'] not in ids:
        raise ValueError('小节编号不存在，请重新载入')
    position = ids.index(change['measureId'])
    reference = measures[position]
    divisions, time = None, None
    boundary = position if placement == 'before' else position + 1
    for m in measures[:position + 1]:
        attrs = child(m, 'attributes')
        if attrs is not None:
            if value(attrs, 'staves', '1') != '1':
                raise ValueError('补小节目前仅支持单谱表')
            if child(attrs, 'divisions') is not None:
                divisions = Fraction(value(attrs, 'divisions'))
            if child(attrs, 'time') is not None:
                time = child(attrs, 'time')
        for n in (n for n in m if local(n.tag) == 'note'):
            if value(n, 'staff', '1') != '1':
                raise ValueError('补小节目前仅支持单谱表')
    active_ties = set()
    for m in measures[:boundary]:
        for n in (n for n in m if local(n.tag) == 'note'):
            p = child(n, 'pitch')
            key = (value(n, 'voice', '1'), value(p, 'step'), value(p, 'alter', '0'), value(p, 'octave')) if p is not None else None
            for tie in (t for t in n if local(t.tag) == 'tie'):
                if tie.get('type') == 'stop':
                    active_ties.discard(key)
                elif tie.get('type') == 'start':
                    active_ties.add(key)
    if active_ties:
        raise ValueError('此处有跨小节延音，不能插入休止；请先在制谱软件中修正延音线')
    if time is None or divisions is None or divisions <= 0:
        raise ValueError('当前位置缺少可靠拍号或时值单位，暂不能自动创建整小节休止')
    if len([c for c in time if local(c.tag) == 'beats']) != 1 or child(time, 'senza-misura') is not None:
        raise ValueError('该拍号暂不支持补休止，请导出 MusicXML 编辑')
    try:
        beats = sum(int(b) for b in value(time, 'beats').split('+'))
        unit = int(value(time, 'beat-type'))
        if not 1 <= beats <= 64 or unit not in (1, 2, 4, 8, 16, 32, 64):
            raise ValueError()
        duration = divisions * beats * 4 / unit
        if duration.denominator != 1:
            raise ValueError()
    except (ValueError, ZeroDivisionError):
        raise ValueError('拍号与时值单位不兼容，暂不能补入整小节休止')
    multiple_rest_nodes = [n for n in reference.iter() if local(n.tag) == 'multiple-rest']
    reference_notes = [n for n in reference if local(n.tag) == 'note']
    reusable_placeholder = (
        placement == 'before'
        and len(multiple_rest_nodes) == 1
        and (multiple_rest_nodes[0].text or '').strip() == '1'
        and reference_notes
        and all(child(n, 'rest') is not None and
                child(n, 'rest').get('measure') == 'yes' for n in reference_notes)
    )
    if multiple_rest_nodes and not reusable_placeholder:
        raise ValueError('请选择相邻的普通小节作为插入位置；已有多小节休止请勿重复添加')
    number = reference.get('number', '')
    later = (measures[position + 1:] if reusable_placeholder
             else measures[position if placement == 'before' else position + 1:])
    if not number.isdigit() or any(not m.get('number', '').isdigit() for m in later):
        raise ValueError('此谱包含非数字小节号，暂不自动改动编号')

    # MuseScore needs both the grouping marker and every underlying empty
    # measure. The PDF collapses them to one bar labelled with the count, while
    # the MusicXML timeline and all later measure numbers remain truthful.
    count = change['count']
    shift = count - 1 if reusable_placeholder else count

    def rest_note(template):
        note = ET.Element(tag(template, 'note'))
        ET.SubElement(note, tag(template, 'rest'), {'measure': 'yes'})
        ET.SubElement(note, tag(template, 'duration')).text = str(int(duration))
        ET.SubElement(note, tag(template, 'voice')).text = '1'
        return note

    inserted_number = int(number) if placement == 'before' else int(number) + 1
    if reusable_placeholder:
        inserted = reference
        first_note = reference_notes[0]
        first_note.attrib.pop('print-object', None)
        if child(first_note, 'voice') is None:
            ET.SubElement(first_note, tag(reference, 'voice')).text = '1'
        multiple_rest_nodes[0].text = str(count)
        if count == 1:
            style = next((node for node in inserted.iter()
                          if local(node.tag) == 'measure-style'), None)
            if style is not None:
                style.remove(multiple_rest_nodes[0])
        insert_at = list(part).index(reference) + 1
        for offset in range(1, count):
            extra = ET.Element(tag(reference, 'measure'),
                               {'number': str(inserted_number + offset)})
            extra.append(rest_note(reference))
            part.insert(insert_at, extra)
            insert_at += 1
    else:
        insert_at = list(part).index(reference) + (1 if placement == 'after' else 0)
        for offset in range(count):
            inserted = ET.Element(tag(reference, 'measure'),
                                  {'number': str(inserted_number + offset)})
            if offset == 0 and placement == 'before':
                for layout_node in [node for node in list(reference)
                                    if local(node.tag) == 'print']:
                    reference.remove(layout_node)
                    inserted.append(layout_node)
                attrs = child(reference, 'attributes')
                if attrs is not None:
                    inserted.append(copy.deepcopy(attrs))
            if offset == 0 and count > 1:
                attrs = child(inserted, 'attributes')
                if attrs is None:
                    attrs = ET.SubElement(inserted, tag(reference, 'attributes'))
                style = child(attrs, 'measure-style')
                if style is None:
                    style = ET.SubElement(attrs, tag(reference, 'measure-style'))
                ET.SubElement(style, tag(reference, 'multiple-rest')).text = str(count)
            inserted.append(rest_note(reference))
            part.insert(insert_at, inserted)
            insert_at += 1

    for m in later:
        m.set('number', str(int(m.get('number')) + shift))
    placement_label = '之前' if placement == 'before' else '之后'
    return [{'eventId': change['measureId'], 'before': '目标小节%s' % placement_label,
             'after': '人工补入 %s 个整小节休止（%s/%s），后续数字小节号顺延；仍需核对原谱' % (count, beats, unit),
             'type': 'insertRests', 'count': count,
             'placement': placement, 'grouped': count > 1,
             'reusedPlaceholder': reusable_placeholder}]


def report_text(job, verification):
    lines = ['乐谱人工校对清单', '', '此文件为候选结果，未经完整逐音核验。',
             '任务：' + str(job.get('jobId', '')), '状态：' + str(job.get('status', '')),
             '', str(verification.get('summary') or job.get('message') or '处理未完成'), '']
    for check in verification.get('checks', []):
        if not check.get('passed'):
            lines.append('待核对：%s — %s' % (check.get('label', ''), check.get('detail', '')))
    for issue in verification.get('issues', []):
        lines.extend(['', issue.get('message', '待核对'), '应为：' + str(issue.get('expected', '')),
                      '检测到：' + str(issue.get('actual', ''))])
    if not verification.get('issues'):
        lines.extend(['', '尚无可可靠定位的逐音错误清单，不表示整份谱正确。',
                      '请对照原谱检查全部音符、休止、连线、力度、编号和分页。'])
    if verification.get('manualEdits'):
        lines.extend(['', '本版包含人工修改（不表示原谱问题已全部解决）：'])
        for change in verification['manualEdits']:
            lines.append('%s：%s → %s' % (change['eventId'], change['before'], change['after']))
    return '\n'.join(lines) + '\n'
