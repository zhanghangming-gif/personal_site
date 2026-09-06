import json
from pathlib import Path


def test_instrument_intent_preserves_sounding_pitch(api):
    from score_contracts import build_transposition_intent

    intent = build_transposition_intent({
        'transposeMode': 'instrument',
        'sourceInstrument': 'clarinet_a',
        'targetInstrument': 'clarinet_bb',
        'semitones': -1,
        'accidentalPreference': 'flats',
    })
    assert intent['mode'] == 'instrument_rewrite'
    assert intent['preserve'] == 'sounding_pitch'
    assert intent['interval']['chromaticSemitones'] == -1
    assert intent['interval']['diatonicSteps'] == -1
    assert intent['layoutPolicy']['preservePageCount'] is True


def test_custom_intent_is_not_instrument_rewrite(api):
    from score_contracts import build_transposition_intent

    intent = build_transposition_intent({
        'transposeMode': 'custom',
        'sourceInstrument': 'clarinet_a',
        'targetInstrument': 'clarinet_bb',
        'semitones': 1,
        'accidentalPreference': 'auto',
    })
    assert intent['mode'] == 'interval_transpose'
    assert intent['preserve'] == 'written_interval'
    assert intent['sourceInstrument'] is None
    assert intent['interval']['diatonicSteps'] is None


def test_workspace_separates_contract_artifacts(api, tmp_path):
    from score_contracts import build_transposition_intent
    from score_workspace import ScoreWorkspace

    source = tmp_path / 'input.pdf'
    source.write_bytes(b'%PDF-1.4\nfixture')
    request = {'name': 'score.pdf', 'transposeMode': 'custom', 'semitones': 2,
               'accidentalPreference': 'auto', 'sourceInstrument': 'concert_c',
               'targetInstrument': 'concert_c'}
    workspace = ScoreWorkspace(str(tmp_path))
    workspace.initialize('job-1', str(source), request, build_transposition_intent(request))
    evidence = tmp_path / 'evidence' / 'source-evidence.json'
    evidence.write_text(json.dumps({'immutable': True}), encoding='utf-8')
    workspace.register_artifact('source-evidence', str(evidence), 'sourceEvidence')
    manifest = workspace.update_stage('inspecting', '检查PDF', 12)

    assert manifest['contracts']['sourceEvidence'] == 'source-evidence'
    assert manifest['contracts']['canonicalSourceScore'] is None
    assert manifest['pipeline']['stage'] == 'inspecting'
    assert manifest['artifacts']['source-evidence']['path'] == 'evidence/source-evidence.json'


def test_workspace_records_reproducible_score_version_chain(api, tmp_path):
    from score_contracts import build_transposition_intent
    from score_workspace import ScoreWorkspace

    source = tmp_path / 'input.pdf'
    source.write_bytes(b'%PDF-1.4\nfixture')
    request = {'name': 'score.pdf', 'transposeMode': 'custom', 'semitones': 2,
               'accidentalPreference': 'auto', 'sourceInstrument': 'concert_c',
               'targetInstrument': 'concert_c'}
    workspace = ScoreWorkspace(str(tmp_path))
    workspace.initialize('job-1', str(source), request, build_transposition_intent(request))
    canonical = tmp_path / 'scores' / 'source' / 'canonical-score.json'
    target = tmp_path / 'scores' / 'target' / 'target-score.json'
    canonical.write_text('{"score":"source"}', encoding='utf-8')
    target.write_text('{"score":"target"}', encoding='utf-8')
    first = workspace.register_score_version('canonical_source', str(canonical))
    second = workspace.register_score_version('target_transposed', str(target), first['versionId'])
    workspace.register_score_version('target_transposed', str(target), first['versionId'])
    manifest = workspace.read()
    assert len(manifest['scoreVersions']) == 2
    assert second['parentVersionId'] == first['versionId']
    assert second['artifact'] == 'scores/target/target-score.json'
