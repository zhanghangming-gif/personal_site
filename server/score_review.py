"""Persist provenance-bound IR and review issues without trusting model claims."""
import hashlib
import json
import os

from score_ir import score_ir, specification
from score_ir_audit import compare_ir, compare_transposition
from score_rhythm_gaps import detect_rhythm_gaps, rhythm_gap_issues
from score_rest_evidence import annotate_rhythm_gaps, classify_rest_gaps
from score_contracts import (
    build_transposition_intent,
    canonical_score_from_ir,
    evidence_graph_from_ir,
    layout_map_from_ir,
    transformation_proof,
)


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, data):
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def attach_measure_regions(index, analysis, preflight):
    """Map only anchored, single-staff systems with unambiguous bar counts.

    A measure crop is spatial evidence, not a note identification or confidence
    estimate. Expanded multirests and changed structures deliberately remain
    unmapped instead of reusing another measure's coordinates.
    """
    if len(index['parts']) != 1:
        return
    groups = {}
    for measure in index['parts'][0]['measures']:
        loc = measure['location']
        groups.setdefault((loc['page'], loc['system']), []).append(measure)
    pages = {p['page']: p.get('geometry', {}) for p in preflight.get('pageDetails', [])}
    mapped = 0
    for system in analysis.get('systems', []):
        measures = groups.get((system['page'], system['system']), [])
        staff, geometry = system.get('pdfStaff'), pages.get(system['page'], {})
        if not measures or not staff or system.get('staffCount') != 1:
            continue
        anchor = system.get('lineStartPdf')
        if anchor is None or str(anchor) != measures[0]['location']['measure']:
            continue
        if any(stack.get('special') for stack in system.get('stacks', [])):
            continue
        bars = [x for x in staff['barlines'] if x > staff['left'] + 2 * staff['spacing']]
        if (len(bars) != len(measures) or len(measures) != system.get('rawMeasures') or
                not bars or abs(bars[-1] - staff['right']) > staff['spacing']):
            continue
        if not geometry.get('width') or not geometry.get('height'):
            continue
        left = staff['left']
        for measure, right in zip(measures, bars):
            region = {'page': system['page'], 'coordinateSystem': 'pdf_points_top_left',
                      'bbox': [max(0, left - staff['spacing']), max(0, staff['top'] - 5 * staff['spacing']),
                               min(geometry['width'], right + staff['spacing']),
                               min(geometry['height'], staff['top'] + 10 * staff['spacing'])],
                      'basis': 'pdf_barlines_and_printed_measure_anchor',
                      'semanticVerification': False}
            measure['sourceRegion'] = region
            for event in measure['events']:
                event['evidence']['measureRegion'] = region
            mapped += 1
            left = right
    index['coverage']['mappedMeasures'] = mapped
    if mapped:
        index['coverage']['pdfObjectMapping'] = 'partial_measure_regions_only'


def write_score_review(job_dir, source_pdf, source_xml, target_xml, rendered_xml,
                       read_xml, semitones, preference='auto', source_instrument=None,
                       target_instrument=None, output_pdf=None, original_xml=None,
                       omr_analysis=None, preflight=None, intent=None, omr_book=None):
    """This branch imports OMR/XML. No imported self-rating can verify the PDF."""
    spec = specification(semitones, preference, source_instrument, target_instrument)
    pdf_sha = file_digest(source_pdf)
    indexes, artifacts = {}, {}
    for role, path, origin in [('original', original_xml or source_xml, 'omr-export'),
                               ('source', source_xml, 'omr-after-structure-repair'),
                               ('expected', target_xml, 'deterministic-transposition'),
                               ('rendered', rendered_xml, 'renderer-export')]:
        if not path or not os.path.isfile(path):
            continue
        index = score_ir(read_xml(path), origin, pdf_sha, file_digest(path))
        if role in ('original', 'source', 'expected'):
            attach_measure_regions(index, omr_analysis or {}, preflight or {})
        artifact = os.path.join(job_dir, role + '-score-ir.json')
        save_json(artifact, index)
        artifacts[role] = {'name': os.path.basename(artifact), 'sha256': file_digest(artifact),
                           'musicxmlSha256': index['artifactSha256']}
        indexes[role] = index
    rhythm_gaps = detect_rhythm_gaps(indexes['source'])
    rhythm_gap_path = os.path.join(job_dir, 'review', 'rhythm-gaps.json')
    os.makedirs(os.path.dirname(rhythm_gap_path), exist_ok=True)
    save_json(rhythm_gap_path, rhythm_gaps)
    rest_classification = classify_rest_gaps(
        rhythm_gaps, omr_book, preflight or {}) if omr_book else {
            'schemaVersion': 1, 'engine': 'unavailable', 'classifications': [],
            'summary': {'gapCount': len(rhythm_gaps.get('gaps', [])), 'supportedCount': 0},
            'limits': 'OMR 工程不可用，节奏缺口需要原 PDF 视觉确认'}
    rest_classification_path = os.path.join(job_dir, 'review', 'rest-classification.json')
    save_json(rest_classification_path, rest_classification)
    annotate_rhythm_gaps(rhythm_gaps, rest_classification)
    save_json(rhythm_gap_path, rhythm_gaps)
    rhythm_issues = rhythm_gap_issues(rhythm_gaps)
    transpose = compare_transposition(indexes['source'], indexes['expected'], semitones)
    rendered = compare_ir(indexes['expected'], indexes['rendered']) if 'rendered' in indexes else {
        'passed': False, 'issueCount': 1, 'issues': [{'id': 'render-unavailable', 'phase': 'render',
            'code': 'missing_render_export', 'location': {}, 'message': '缺少最终排版的回读数据',
            'expected': '最终排版数据', 'actual': '未取得'}]}
    issues = rhythm_issues + transpose['issues'] + rendered['issues']
    # Review scopes are positions in indexed XML, not invented PDF note boxes.
    grouped = {}
    source_measures = {(pi, mi): m for pi, p in enumerate(indexes['source']['parts'], 1)
                       for mi, m in enumerate(p['measures'], 1)}
    for issue in issues:
        location = issue.get('location', {})
        key = (issue['phase'], location.get('part'), location.get('measureIndex'))
        region = source_measures.get((location.get('part'), location.get('measureIndex')), {}).get('sourceRegion')
        entry = grouped.setdefault(key, {'phase': issue['phase'], 'location': location,
                                         'eventIds': [], 'issueIds': [], 'pdfRegion': region,
                                         'evidenceStatus': 'requires_source_mapping'})
        entry['issueIds'].append(issue['id'])
        if issue.get('eventId') and issue['eventId'] not in entry['eventIds']:
            entry['eventIds'].append(issue['eventId'])
    for measure in source_measures.values():
        if measure.get('sourceRegion'):
            loc = measure['location']
            grouped[('source', loc['part'], loc['measureIndex'])] = {
                'phase': 'source', 'location': loc, 'pdfRegion': measure['sourceRegion'],
                'eventIds': [e['id'] for e in measure['events']], 'issueIds': [],
                'evidenceStatus': 'region_located_music_unverified'}
    if intent is None:
        intent = build_transposition_intent({
            'transposeMode': 'instrument' if source_instrument is not None else 'custom',
            'sourceInstrument': source_instrument,
            'targetInstrument': target_instrument,
            'semitones': semitones,
            'accidentalPreference': preference,
        })
    canonical_source = canonical_score_from_ir(indexes['source'], 'canonical_source')
    target_score = canonical_score_from_ir(indexes['expected'], 'target')
    evidence_graph = evidence_graph_from_ir(indexes['original'])
    source_layout = layout_map_from_ir(
        indexes['source'], 'source', 'layout/source/coordinate-map.json')
    target_layout = layout_map_from_ir(
        indexes.get('rendered', indexes['expected']), 'target',
        'layout/target/coordinate-map.json')
    proof = transformation_proof(canonical_source, target_score, intent)
    contract_values = {
        'canonicalSourceScore': ('scores/source/canonical-score.json', canonical_source),
        'targetScore': ('scores/target/target-score.json', target_score),
        'evidenceGraph': ('evidence/evidence-graph.json', evidence_graph),
        'sourceLayoutMap': ('layout/source/source-layout-map.json', source_layout),
        'targetLayoutMap': ('layout/target/target-layout-map.json', target_layout),
        'transformationProof': ('review/transformation-proof.json', proof),
    }
    contract_artifacts = {}
    for name, (relative, value) in contract_values.items():
        path = os.path.join(job_dir, *relative.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_json(path, value)
        contract_artifacts[name] = {
            'path': relative,
            'sha256': file_digest(path),
        }

    report = {'schemaVersion': 1, 'specification': spec, 'intent': intent,
              'sourcePdfSha256': pdf_sha,
              'candidatePdfSha256': file_digest(output_pdf) if output_pdf else None,
              'artifacts': artifacts, 'contractArtifacts': contract_artifacts,
              'transposition': transpose, 'transformationProof': {
                  'passed': proof['passed'], 'issueCount': proof['issueCount']},
              'rhythmGapDetection': rhythm_gaps,
              'restClassification': rest_classification,
              'renderComparison': rendered,
              'sourceRecognition': {'status': 'PENDING', 'verifiedEvents': 0,
                                    'totalEvents': indexes['original']['counts']['events'],
                                    'reason': '识谱数据尚未与原 PDF 的全部音符及标记独立对应'},
              'outputPdfRecognition': {'status': 'PENDING',
                                       'reason': '当前回读来自排版软件导出，尚未从输出 PDF 独立识别'},
              'issues': issues, 'issueCount': len(rhythm_issues) + transpose['issueCount'] + rendered['issueCount'],
              'reviewQueue': list(grouped.values()), 'outputAllowed': False}
    save_json(os.path.join(job_dir, 'score-review.json'), report)
    return report


def attach_review(verification, review):
    """A valid transformation cannot certify an unverified transcription."""
    verification['issues'] = review['issues'][:50]
    verification['issueCount'] = review['issueCount']
    verification['reviewCoverage'] = {
        'sourceRecognition': review['sourceRecognition']['status'],
        'outputPdfRecognition': review['outputPdfRecognition']['status'],
        'transposition': 'PASSED' if review['transposition']['passed'] else 'FAILED',
        'renderComparison': 'PASSED' if review['renderComparison']['passed'] else 'FAILED',
        'verifiedSourceEvents': review['sourceRecognition']['verifiedEvents'],
        'totalSourceEvents': review['sourceRecognition']['totalEvents']}
    rhythm = review.get('rhythmGapDetection', {})
    verification['rhythmGapDetection'] = {
        'status': rhythm.get('status'),
        'gapCount': len(rhythm.get('gaps', [])),
        'overflowCount': len(rhythm.get('overflows', [])),
        'artifact': 'review/rhythm-gaps.json',
        'autoRepairApplied': False,
    }
    rest = review.get('restClassification', {})
    verification['restClassification'] = {
        'engine': rest.get('engine'),
        'supportedCount': (rest.get('summary') or {}).get('supportedCount', 0),
        'statusCounts': (rest.get('summary') or {}).get('statusCounts', {}),
        'artifact': 'review/rest-classification.json',
        'autoRepairApplied': False,
    }
    verification['checks'].extend([
        {'id': 'rhythm_gaps', 'label': '识谱声部时间轴',
         'passed': not review.get('rhythmGapDetection', {}).get('gaps') and
                   not review.get('rhythmGapDetection', {}).get('overflows'),
         'detail': ('没有发现可由当前拍号证明的声部时值缺口' if
                    not review.get('rhythmGapDetection', {}).get('gaps') and
                    not review.get('rhythmGapDetection', {}).get('overflows') else
                    '发现 %s 处时间轴缺口、%s 处超出拍号容量；其中 %s 处有高分 OMR 休止候选，均只加入复核队列' % (
                        len(review.get('rhythmGapDetection', {}).get('gaps', [])),
                        len(review.get('rhythmGapDetection', {}).get('overflows', [])),
                        (review.get('restClassification', {}).get('summary') or {}).get('supportedCount', 0)))},
        {'id': 'ir_transposition', 'label': '转调前后的音乐结构', 'passed': review['transposition']['passed'],
         'detail': '已核对识谱数据的音高变化、声部、节奏、休止和标记' if review['transposition']['passed'] else
         '转调过程中发现 %s 处音乐数据差异' % review['transposition']['issueCount']},
        {'id': 'source_music_evidence', 'label': '原 PDF 的逐音对应核验', 'passed': False,
         'detail': review['sourceRecognition']['reason']},
        {'id': 'output_pdf_evidence', 'label': '输出 PDF 的独立核验', 'passed': False,
         'detail': review['outputPdfRecognition']['reason']}])
    verification['status'] = 'failed'
    verification['summary'] = ('发现 %s 处音乐数据差异，并有原谱与输出 PDF 待核对项目。' % review['issueCount']
                               if review['issueCount'] else
                               '已完成的音乐数据检查未发现差异；原谱识别与输出 PDF 尚需独立核对。')
    return verification
