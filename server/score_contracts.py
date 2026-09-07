"""Versioned data contracts for the score compiler pipeline.

The source evidence, canonical music, transformation result and layout maps are
separate artifacts.  This module is Python 3.6 compatible because the public
API service still runs on the system interpreter.
"""
import hashlib
import json
import time
from copy import deepcopy

from score_transposition import INSTRUMENTS, integer


CONTRACT_VERSION = 1
MANIFEST_VERSION = 1


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def value_id(prefix, value):
    digest = hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()[:20]
    return '%s-%s' % (prefix, digest)


def build_transposition_intent(request):
    """Turn the public request into an unambiguous musical transformation."""
    mode = request.get('transposeMode', 'instrument')
    preference = request.get('accidentalPreference', 'auto')
    if mode not in ('instrument', 'custom'):
        raise ValueError('转调模式无效')
    if preference not in ('auto', 'sharps', 'flats'):
        raise ValueError('升降号偏好无效')
    semitones = integer(request.get('semitones'), '转调半音数')
    if not -48 <= semitones <= 48:
        raise ValueError('转调范围为上下 48 个半音')

    source = request.get('sourceInstrument')
    target = request.get('targetInstrument')
    diatonic = None
    preserve = 'written_interval'
    public_mode = 'interval_transpose'
    if mode == 'instrument':
        if source not in INSTRUMENTS or target not in INSTRUMENTS:
            raise ValueError('乐器无效')
        expected = INSTRUMENTS[source][0] - INSTRUMENTS[target][0]
        if semitones != expected:
            raise ValueError('乐器与转调音程不一致')
        diatonic = INSTRUMENTS[source][1] - INSTRUMENTS[target][1]
        preserve = 'sounding_pitch'
        public_mode = 'instrument_rewrite'

    interval = {
        'chromaticSemitones': semitones,
        'diatonicSteps': diatonic,
        'octaveDisplacement': int(semitones / 12),
    }
    value = {
        'schemaVersion': CONTRACT_VERSION,
        'mode': public_mode,
        'preserve': preserve,
        'sourceInstrument': source if mode == 'instrument' else None,
        'targetInstrument': target if mode == 'instrument' else None,
        'interval': interval,
        'spellingPolicy': {
            'accidentalPreference': preference,
            'strategy': 'target_key_context',
        },
        'layoutPolicy': {
            'preservePageCount': True,
            'preserveSystemBreaks': True,
            'preserveMeasureNumbers': True,
            'preserveNonPitchMarks': True,
        },
        'pageSelection': {
            'mode': request.get('pageSelectionMode', 'all'),
            'sourcePageCount': request.get('sourcePageCount'),
            'selectedPages': list(request.get('selectedPages') or []),
        },
    }
    value['intentId'] = value_id('intent', value)
    return value


def new_manifest(job_id, source_sha256, source_name, intent):
    now = time.time()
    return {
        'schemaVersion': MANIFEST_VERSION,
        'jobId': job_id,
        'createdAt': now,
        'updatedAt': now,
        'source': {
            'sha256': source_sha256,
            'name': source_name,
            'artifact': 'input.pdf',
        },
        'intent': intent,
        'pipeline': {
            'stage': 'uploaded',
            'progress': 0,
            'message': 'PDF 已上传',
            'history': [{'stage': 'uploaded', 'progress': 0, 'at': now}],
        },
        'contracts': {
            'sourceEvidence': None,
            'evidenceGraph': None,
            'canonicalSourceScore': None,
            'targetScore': None,
            'sourceLayoutMap': None,
            'targetLayoutMap': None,
            'transformationProof': None,
        },
        'artifacts': {},
        'engineVersions': {'scoreCompilerContracts': CONTRACT_VERSION},
        'modelVersions': {},
        'parameters': {},
        'scoreVersions': [],
        'patches': [],
    }


SEMANTIC_EVENT_FIELDS = (
    'id', 'kind', 'pitch', 'midi', 'unpitched', 'onset', 'duration', 'staff',
    'voice', 'grace', 'cue', 'visible', 'ties', 'lyrics', 'notations', 'spanners',
    'writtenType', 'dots', 'accidental', 'beams', 'timeModification', 'context',
)


def canonical_score_from_ir(index, role):
    """Create a music-only score contract without PDF or renderer coordinates."""
    parts = []
    for part in index.get('parts', []):
        measures = []
        for position, measure in enumerate(part.get('measures', []), 1):
            measures.append({
                'id': measure['id'],
                'index': position,
                'number': measure.get('location', {}).get('measure', str(position)),
                'events': [
                    {name: deepcopy(event.get(name)) for name in SEMANTIC_EVENT_FIELDS}
                    for event in measure.get('events', [])
                ],
                'marks': deepcopy(measure.get('marks', [])),
            })
        parts.append({'id': part['id'], 'sourcePartId': part.get('sourcePartId'), 'measures': measures})
    value = {
        'schemaVersion': CONTRACT_VERSION,
        'role': role,
        'sourceArtifactSha256': index.get('artifactSha256'),
        'parts': parts,
        'counts': deepcopy(index.get('counts', {})),
        'warnings': deepcopy(index.get('warnings', [])),
    }
    value['scoreId'] = value_id('score', value)
    return value


def evidence_graph_from_ir(index):
    """Keep recognition observations separate from canonical music semantics."""
    observations, links = [], []
    for part in index.get('parts', []):
        for measure in part.get('measures', []):
            region = measure.get('sourceRegion')
            for event in measure.get('events', []):
                evidence = event.get('evidence') or {}
                observation = {
                    'evidenceId': value_id('evidence', [event['id'], evidence]),
                    'kind': 'recognition_candidate',
                    'producer': evidence.get('origin', index.get('origin', 'unknown')),
                    'status': evidence.get('status', 'unverified'),
                    'candidateEventId': event['id'],
                    'sourceRegion': deepcopy(evidence.get('measureRegion') or region),
                    'pdfObjects': deepcopy(evidence.get('pdfObjects', [])),
                    'confidence': None,
                }
                observations.append(observation)
                links.append({'evidenceId': observation['evidenceId'], 'eventId': event['id'],
                              'relation': 'supports_candidate'})
    return {
        'schemaVersion': CONTRACT_VERSION,
        'immutableSourceObservations': True,
        'observations': observations,
        'links': links,
        'verificationStatus': 'unverified',
    }


def layout_map_from_ir(index, role, coordinate_map_ref=None):
    measures = []
    for part in index.get('parts', []):
        for measure in part.get('measures', []):
            location = measure.get('location', {})
            measures.append({
                'measureId': measure['id'],
                'page': location.get('page'),
                'system': location.get('system'),
                'bbox': deepcopy((measure.get('sourceRegion') or {}).get('bbox')),
                'coordinateSystem': (measure.get('sourceRegion') or {}).get('coordinateSystem'),
                'basis': (measure.get('sourceRegion') or {}).get('basis', 'musicxml_breaks'),
                'eventIds': [event['id'] for event in measure.get('events', [])],
            })
    return {
        'schemaVersion': CONTRACT_VERSION,
        'role': role,
        'coordinateMapRef': coordinate_map_ref,
        'measures': measures,
        'bboxCoverage': sum(item['bbox'] is not None for item in measures),
    }


def transformation_proof(source, target, intent):
    expected_shift = intent['interval']['chromaticSemitones']
    mappings, issues = [], []
    target_events = {
        event['id']: event
        for part in target.get('parts', [])
        for measure in part.get('measures', [])
        for event in measure.get('events', [])
    }
    for part in source.get('parts', []):
        for measure in part.get('measures', []):
            for event in measure.get('events', []):
                other = target_events.get(event['id'])
                expected = event['midi'] + expected_shift if event.get('midi') is not None else event.get('midi')
                actual = other.get('midi') if other else None
                passed = other is not None and (
                    actual == expected if event.get('midi') is not None
                    else other.get('kind') == event.get('kind') and other.get('duration') == event.get('duration')
                )
                mapping = {
                    'sourceEventId': event['id'],
                    'targetEventId': other.get('id') if other else None,
                    'sourcePitch': deepcopy(event.get('pitch')),
                    'targetPitch': deepcopy(other.get('pitch')) if other else None,
                    'expectedMidi': expected,
                    'actualMidi': actual,
                    'passed': passed,
                }
                mappings.append(mapping)
                if not passed:
                    issues.append(mapping)
    return {
        'schemaVersion': CONTRACT_VERSION,
        'intentId': intent['intentId'],
        'passed': not issues,
        'eventMappings': mappings,
        'issueCount': len(issues),
        'issues': issues[:200],
    }
