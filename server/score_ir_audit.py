"""Localized semantic comparisons. A matching export is not PDF recognition proof."""
from collections import Counter, defaultdict
from copy import deepcopy
import json

from score_ir import token


FIELDS = ('kind', 'pitch', 'unpitched', 'onset', 'duration', 'staff', 'voice',
          'grace', 'cue', 'visible', 'ties', 'lyrics', 'notations')
LABELS = {'pitch': '音高或等音拼写', 'midi': '转调音高', 'duration': '时值', 'onset': '起始位置',
          'voice': '声部归属', 'staff': '谱表', 'kind': '音符或休止', 'grace': '装饰音',
          'cue': '提示音', 'ties': '延音线', 'lyrics': '歌词', 'notations': '奏法标记',
          'visible': '符号显示', 'context': '调号、拍号或谱号', 'marks': '演奏标记',
          'spanners': '连线或连音组', 'event': '音符或休止', 'measure': '小节', 'part': '乐器声部'}


def describe(value):
    if value is None:
        return '无'
    if isinstance(value, str):
        return value[:700]
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, dict) and {'step', 'alter', 'octave'} <= set(value):
        return '%s%s%s' % (value['step'], {-2: '♭♭', -1: '♭', 0: '', 1: '♯', 2: '♯♯'}.get(value['alter'], str(value['alter'])), value['octave'])
    if isinstance(value, dict) and 'key' in value and isinstance(value['key'], int):
        n = value['key']
        return '调号：无升降号' if n == 0 else '调号：%s 个%s号' % (abs(n), '升' if n > 0 else '降')
    if isinstance(value, dict) and 'data' in value:
        return describe(value['data'])
    if isinstance(value, list):
        if not value:
            return '无'
        # Canonical XML node: name, attributes, text, children.
        if len(value) == 4 and isinstance(value[0], str) and isinstance(value[1], list) and isinstance(value[2], str) and isinstance(value[3], list):
            name, attrs, text, children = value
            names = {'dynamics': '力度', 'words': '文字', 'rehearsal': '排练标记', 'lyric': '歌词',
                     'text': '', 'syllabic': '音节', 'bar-style': '小节线', 'metronome': '速度',
                     'beat-unit': '拍单位', 'per-minute': '每分钟', 'sound': '演奏速度',
                     'wedge': '渐强渐弱', 'fermata': '延长记号', 'slur': '连线',
                     'articulations': '奏法', 'accent': '重音', 'staccato': '断奏'}
            detail = text or '、'.join(describe(x) for x in children) or '、'.join('%s=%s' % tuple(x) for x in attrs)
            return (names.get(name, name) + ('：' if detail and names.get(name, name) else '') + detail)[:700]
        return '、'.join(describe(x) for x in value)[:700]
    return token(value)[:700]


def event_signature(event, fields=FIELDS):
    return token([event.get(field) for field in fields])


def voice_mapping(before, after):
    """Allow a consistent bijective voice renumbering, never a split or merger."""
    a, b = defaultdict(set), defaultdict(set)
    anchors = defaultdict(list)
    votes = Counter()
    for mi, measure in enumerate(before):
        for event in measure['events']:
            a[event['staff']].add(event['voice'])
            anchors[(mi, event_signature(event, ('staff', 'onset', 'duration', 'pitch', 'kind', 'grace')))].append(event)
    for mi, measure in enumerate(after):
        for event in measure['events']:
            b[event['staff']].add(event['voice'])
            for other in anchors.get((mi, event_signature(event, ('staff', 'onset', 'duration', 'pitch', 'kind', 'grace'))), []):
                votes[(event['staff'], other['voice'], event['voice'])] += 1
    mapping = {}
    for staff in a:
        available_a, available_b = set(a[staff]), set(b[staff])
        choices = sorted(((-count, x != y, x, y) for (s, x, y), count in votes.items() if s == staff))
        for _, _, x, y in choices:
            if x in available_a and y in available_b:
                mapping[(staff, y)] = x
                available_a.remove(x)
                available_b.remove(y)
        for same in sorted(available_a & available_b):
            mapping[(staff, same)] = same
            available_a.remove(same)
            available_b.remove(same)
        if len(available_a) == len(available_b) == 1:
            mapping[(staff, next(iter(available_b)))] = next(iter(available_a))
    return mapping


def spanner_links(part):
    active, links = {}, Counter()
    for measure in part['measures']:
        for event in measure['events']:
            endpoint = [event['location']['measureIndex'], event['staff'], event['onset'], event['pitch']]
            for span in event['spanners']:
                key = (span['kind'], span['number'])
                if span['type'] == 'start':
                    if key in active:
                        links[token([span['kind'], 'unclosed', active[key]])] += 1
                    active[key] = endpoint
                elif span['type'] == 'stop':
                    links[token([span['kind'], active.pop(key, None), endpoint])] += 1
                else:
                    links[token([span['kind'], span['type'], endpoint])] += 1
    for (kind, _), endpoint in active.items():
        links[token([kind, 'unclosed', endpoint])] += 1
    return links


def compare_ir(expected, actual, limit=200, phase='render'):
    issues, count = [], 0

    def issue(field, before, after, item=None, status='changed'):
        nonlocal count
        count += 1
        if len(issues) >= limit:
            return
        location = (item or {}).get('location', {})
        where = '第 %s 小节' % location.get('measure', '?')
        if location.get('staff'):
            where += '，谱表 %s、声部 %s、小节起点后 %s 个四分音符' % (
                location['staff'], location.get('voice', '?'), location.get('onsetQuarter', '?'))
        issues.append({'id': '%s-%s' % (phase, count), 'phase': phase, 'code': status + '_' + field,
                       'eventId': (item or {}).get('id'), 'location': location, 'field': field,
                       'expected': describe(before), 'actual': describe(after),
                       'message': '%s：%s%s' % (where, LABELS.get(field, field), {'missing': '缺失', 'extra': '多出', 'changed': '不一致'}[status])})

    left, right = expected['parts'], actual['parts']
    if len(left) != len(right):
        issue('part', len(left), len(right))
    for pi, a in enumerate(left):
        if pi >= len(right):
            break
        b = deepcopy(right[pi])
        aliases = voice_mapping(a['measures'], b['measures'])
        for measure in b['measures']:
            for event in measure['events']:
                event['voice'] = aliases.get((event['staff'], event['voice']), '__unmapped_' + event['voice'])
        if len(a['measures']) != len(b['measures']):
            issue('measure', len(a['measures']), len(b['measures']),
                  (a['measures'] or b['measures'] or [{}])[0])
        number_mismatches = [
            (index + 1, before['location']['measure'], b['measures'][index]['location']['measure'])
            for index, before in enumerate(a['measures'][:len(b['measures'])])
            if before['location']['measure'] != b['measures'][index]['location']['measure']
        ]
        if number_mismatches:
            first = number_mismatches[0]
            issue('measure', '第 %s 项起，应为 %s；共 %s 处编号差异' %
                  (first[0], first[1], len(number_mismatches)),
                  '第 %s 项为 %s' % (first[0], first[2]),
                  a['measures'][first[0] - 1])
        for mi, before in enumerate(a['measures']):
            if mi >= len(b['measures']):
                break
            after = b['measures'][mi]
            remaining = list(after['events'])
            unmatched = []
            fields = tuple('midi' if f == 'pitch' and phase == 'transpose' else f for f in FIELDS)
            for event in before['events']:
                found = next((i for i, other in enumerate(remaining)
                              if event_signature(event, fields) == event_signature(other, fields)), None)
                if found is None:
                    unmatched.append(event)
                else:
                    other = remaining.pop(found)
                    # Context is compared even when pitches/rhythm match.
                    for name, datum in event['context'].items():
                        if datum is not None and not (phase == 'transpose' and name == 'key') and datum != other['context'].get(name):
                            issue('context', {name: datum}, {name: other['context'].get(name)}, event)
            for event in unmatched:
                candidates = [(i, other) for i, other in enumerate(remaining)
                              if other['staff'] == event['staff'] and other['onset'] == event['onset']]
                if not candidates:
                    issue('event', event['pitch'] or event['kind'], None, event, 'missing')
                    continue
                i, other = min(candidates, key=lambda pair: sum(event.get(f) != pair[1].get(f) for f in fields))
                remaining.pop(i)
                for field in fields:
                    if event.get(field) != other.get(field):
                        issue(field, event.get(field), other.get(field), event)
                for name, datum in event['context'].items():
                    if datum is not None and not (phase == 'transpose' and name == 'key') and datum != other['context'].get(name):
                        issue('context', {name: datum}, {name: other['context'].get(name)}, event)
            for other in remaining:
                issue('event', None, other['pitch'] or other['kind'], other, 'extra')
            # Harmony roots intentionally change in the transpose comparison.
            marks_a = Counter(token(x) for x in before['marks'] if phase != 'transpose' or x['kind'] != 'harmony')
            marks_b = Counter(token(x) for x in after['marks'] if phase != 'transpose' or x['kind'] != 'harmony')
            for mark, copies in (marks_a - marks_b).items():
                for _ in range(copies):
                    issue('marks', json.loads(mark), None, before, 'missing')
            for mark, copies in (marks_b - marks_a).items():
                for _ in range(copies):
                    issue('marks', None, json.loads(mark), after, 'extra')
        if phase != 'transpose' and spanner_links(a) != spanner_links(b):
            missing = [json.loads(x) for x in (spanner_links(a) - spanner_links(b)).elements()]
            extra = [json.loads(x) for x in (spanner_links(b) - spanner_links(a)).elements()]
            endpoint = next((x[-1] for x in missing + extra if isinstance(x[-1], list)), None)
            measure = a['measures'][endpoint[0] - 1] if endpoint and 0 < endpoint[0] <= len(a['measures']) else (a['measures'] or [{}])[0]
            def endpoints(spans):
                return '；'.join('%s：%s' % (span[0], ' → '.join(
                    '第 %s 小节，位置 %s' % (point[0], point[2]) if isinstance(point, list) else str(point)
                    for point in span[1:])) for span in spans[:8]) or '无'
            issue('spanners', endpoints(missing), endpoints(extra), measure)
    return {'passed': count == 0, 'issueCount': count, 'issues': issues,
            'truncated': count > len(issues), 'basis': 'musicxml_comparison',
            'independentPdfVerification': False}


def compare_transposition(source, target, semitones):
    expected = deepcopy(source)
    for part in expected['parts']:
        for measure in part['measures']:
            for event in measure['events']:
                if event['midi'] is not None:
                    event['midi'] += semitones
    return compare_ir(expected, target, phase='transpose')
