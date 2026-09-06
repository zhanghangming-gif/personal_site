"""Bounded recognition candidates and evidence-based selection.

Multiple parameter runs from one OMR engine are an ensemble, not independent
ground truth.  The decision contract records both the selected candidate and
remaining disagreement so later verification can keep those claims separate.
"""


RISK_DIMENSIONS = (
    'emptyScore', 'exportErrors', 'pdfMeasureConflicts', 'bookStructureIssue',
    'unresolvedMultirests',
)


def recognition_families(preflight):
    family = (preflight or {}).get('musicFamily')
    return [family] if family else ['Bravura', 'Leland']


def recognition_risk(analysis, xml_notes):
    conflicts = analysis.get('pdfSourceAudit', {}).get('measureConflicts', [])
    return (int(xml_notes == 0), len(analysis.get('exportErrors', [])), len(conflicts),
            int(bool(analysis.get('bookIssue'))), len(analysis.get('multirestMissing', [])))


def needs_alternative(analysis, xml_notes):
    return any(recognition_risk(analysis, xml_notes))


def recognition_attempt(attempt_id, family, analysis, xml_notes, source_artifact='input.pdf',
                        representation='pdf'):
    risk = recognition_risk(analysis, xml_notes)
    return {
        'schemaVersion': 1,
        'attemptId': attempt_id,
        'family': family,
        'noteEvents': int(xml_notes),
        'engine': {'name': 'Audiveris', 'family': family},
        'input': {'artifact': source_artifact, 'representation': representation},
        'metrics': {
            'noteEvents': int(xml_notes),
            'systems': len(analysis.get('systems') or []),
            'lineNumberCoverage': analysis.get('lineNumberCoverage'),
            'recognizedLineNumbers': list(analysis.get('recognizedLineNumbers') or []),
            'exportErrors': len(analysis.get('exportErrors') or []),
            'measureConflicts': len((analysis.get('pdfSourceAudit') or {}).get('measureConflicts') or []),
            'unresolvedMultirests': len(analysis.get('multirestMissing') or []),
        },
        'risk': {name: risk[index] for index, name in enumerate(RISK_DIMENSIONS)},
        'riskTuple': list(risk),
        'riskLegacy': list(risk),
        'selected': False,
    }


def recognition_decision(attempts):
    if not attempts:
        raise ValueError('识谱至少需要一个候选结果')
    candidates = [dict(item) for item in attempts]
    for item in candidates:
        risk = item.get('riskTuple')
        if not isinstance(risk, list) or len(risk) != len(RISK_DIMENSIONS):
            raise ValueError('识谱候选缺少标准风险指标')
    selected = min(candidates, key=lambda item: (
        tuple(item['riskTuple']), -int((item.get('metrics') or {}).get('noteEvents') or 0),
        str(item.get('attemptId') or ''),
    ))
    for item in candidates:
        item['selected'] = item.get('attemptId') == selected.get('attemptId')
    disagreements = []
    selected_metrics = selected.get('metrics') or {}
    for item in candidates:
        if item['selected']:
            continue
        metrics = item.get('metrics') or {}
        for field in ('noteEvents', 'systems', 'recognizedLineNumbers', 'unresolvedMultirests'):
            if metrics.get(field) != selected_metrics.get(field):
                disagreements.append({
                    'attemptId': item.get('attemptId'), 'field': field,
                    'selected': selected_metrics.get(field), 'candidate': metrics.get(field),
                })
    selected_risk = selected.get('riskTuple') or []
    return {
        'schemaVersion': 1,
        'method': 'same_engine_parameter_ensemble',
        'independentRecognition': False,
        'selectedAttemptId': selected.get('attemptId'),
        'attempts': candidates,
        'disagreements': disagreements,
        'requiresReview': bool(any(selected_risk) or disagreements),
        'selectionRule': 'minimum ordered structural risk, then greater note coverage',
        'limits': '参数集成可减少单次配置失误，但不能作为独立原谱真值验证',
    }


def recognition_consensus(candidates, selected_attempt_id, limit=200):
    """Compare candidate semantics without treating correlated agreement as truth."""
    usable = [item for item in candidates if isinstance(item.get('signature'), dict)]
    selected = next((item for item in usable if item.get('attemptId') == selected_attempt_id), None)
    if not selected:
        return {'schemaVersion': 1, 'status': 'unavailable', 'issues': [], 'issueCount': 0}
    baseline = selected['signature']
    issues = []
    comparisons = []
    for item in usable:
        if item is selected:
            continue
        other = item['signature']
        same_measures = baseline.get('measureNumbers') == other.get('measureNumbers')
        same_notes = baseline.get('noteCount') == other.get('noteCount')
        pitch_mismatches = []
        if same_measures and same_notes:
            for index, (before, after) in enumerate(zip(
                    baseline.get('noteEvents', []), other.get('noteEvents', [])), 1):
                if before.get('midi') != after.get('midi'):
                    pitch_mismatches.append({
                        'eventIndex': index, 'measure': before.get('measureNumber'),
                        'selectedMidi': before.get('midi'), 'candidateMidi': after.get('midi'),
                    })
        comparison = {
            'attemptId': item.get('attemptId'),
            'measureSequenceEqual': same_measures,
            'noteCountEqual': same_notes,
            'selectedNoteEvents': baseline.get('noteCount'),
            'candidateNoteEvents': other.get('noteCount'),
            'pitchMismatchCount': len(pitch_mismatches),
            'pitchMismatchSamples': pitch_mismatches[:20],
        }
        comparisons.append(comparison)
        if not same_measures:
            issues.append({'attemptId': item.get('attemptId'), 'field': 'measureSequence',
                           'message': '识谱候选的小节序列不一致'})
        if not same_notes:
            issues.append({'attemptId': item.get('attemptId'), 'field': 'noteCount',
                           'message': '识谱候选的音符数量不一致'})
        for mismatch in pitch_mismatches:
            issues.append(dict(mismatch, attemptId=item.get('attemptId'), field='pitch',
                               message='识谱候选在同一事件位置给出不同音高'))
    return {
        'schemaVersion': 1,
        'status': 'compared' if comparisons else 'single_candidate',
        'selectedAttemptId': selected_attempt_id,
        'correlatedEvidenceOnly': True,
        'comparisons': comparisons,
        'issueCount': len(issues),
        'issues': issues[:limit],
        'truncated': len(issues) > limit,
    }
