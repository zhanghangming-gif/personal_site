import copy
import inspect
import xml.etree.ElementTree as ET


def source_tree(with_risk=False):
    root = ET.fromstring('''<score-partwise><part id="P1"><measure number="1">
      <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>quarter</type></note>
      <forward><duration>4</duration></forward>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>8</duration><voice>1</voice><type>half</type></note>
    </measure></part></score-partwise>''')
    gap = {
        'id': 'rhythm-gap-p1-m1-v1-1', 'measureId': 'p1-m1', 'voice': '1',
        'onset': '1', 'duration': '1', 'expectedMeasureDuration': '4',
        'position': 'internal',
        'location': {'part': 1, 'measureIndex': 1, 'measure': '1'},
        'reviewRegion': {
            'bbox': [100, 100, 200, 200],
            'mappingBasis': 'test_measure_geometry',
        },
        'riskReasons': ['multiple_voices'] if with_risk else [],
    }
    return root, {'gaps': [gap], 'overflows': []}


def classification(score=.96, status='supported_by_omr_and_visual_model',
                   notation='quarter_rest', geometry=None):
    return {'classifications': [{
        'gapId': 'rhythm-gap-p1-m1-v1-1', 'status': status,
        'suggestedNotation': notation, 'suggestedDots': 0,
        'candidateCount': 1, 'exactCandidateCount': 1,
        'selectedEvidence': {
            'grade': .90, 'contextGrade': .90, 'durationMatchesGap': True,
            'staffPositionConsistent': True,
        },
        'selectedVisualEvidence': {
            'class': notation, 'score': score, 'bboxPdf': [130, 120, 150, 180],
            'staffGeometryConsistent': geometry,
        },
    }]}


def test_auto_repair_requires_full_source_evidence_and_gate(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    report = apply_safe_rhythm_repairs(root, gaps, classification())
    assert report['appliedCount'] == 1
    assert report['policyVersion'] == 'source-rest-and-gate-v2'
    assert '原谱局部视觉、时值窗口与谱表几何证据' in report['applied'][0]['changes'][0]['after']
    assert root.find('.//forward') is None
    rests = [note for note in root.findall('.//note') if note.find('rest') is not None]
    assert len(rests) == 1 and rests[0].findtext('duration') == '4'


def test_omr_confidence_alone_never_authorizes_source_patch(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    before = ET.tostring(root)
    report = apply_safe_rhythm_repairs(
        root, gaps, classification(status='supported_by_omr_object'))
    assert report['appliedCount'] == 0
    assert report['rejected'][0]['reason'] == 'independent_visual_evidence_required'
    assert ET.tostring(root) == before


def test_auto_repair_rejects_low_confidence_rhythm_risks_and_unmapped_detection(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    before = ET.tostring(root)
    assert apply_safe_rhythm_repairs(root, gaps, classification(.89))['appliedCount'] == 0
    assert ET.tostring(root) == before
    root, gaps = source_tree(True)
    assert apply_safe_rhythm_repairs(root, gaps, classification())['appliedCount'] == 0
    root, gaps = source_tree()
    evidence = classification()
    evidence['classifications'][0]['selectedVisualEvidence']['bboxPdf'] = [1, 1, 2, 2]
    assert apply_safe_rhythm_repairs(root, gaps, evidence)['appliedCount'] == 0


def test_whole_and_half_rests_require_staff_geometry(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    gaps['gaps'][0]['onset'] = '0'
    gaps['gaps'][0]['duration'] = '4'
    gaps['gaps'][0]['position'] = 'full_measure'
    assert apply_safe_rhythm_repairs(
        root, gaps, classification(.99, notation='whole_rest', geometry=None))['appliedCount'] == 0


def test_source_repair_validation_preserves_all_non_rest_semantics(api):
    from score_auto_repair import apply_safe_rhythm_repairs, validate_source_repair_result
    from score_ir import score_ir
    root, gaps = source_tree()
    before_ir = score_ir(copy.deepcopy(root))
    report = apply_safe_rhythm_repairs(root, gaps, classification())
    after_ir = score_ir(root)
    accepted, validation = validate_source_repair_result(
        gaps, {'gaps': [], 'overflows': []}, report['applied'], before_ir, after_ir)
    assert accepted
    assert all(validation['checks'].values())
    changed = copy.deepcopy(after_ir)
    changed['parts'][0]['measures'][0]['events'][0]['pitch']['step'] = 'E'
    accepted, validation = validate_source_repair_result(
        gaps, {'gaps': [], 'overflows': []}, report['applied'], before_ir, changed)
    assert not accepted and not validation['checks']['pitchedEventsPreserved']


def test_auto_repair_validation_requires_gap_removal_and_clean_core_checks(api):
    from score_auto_repair import validate_repair_result
    _, before = source_tree()
    accepted, report = validate_repair_result(
        before, {'gaps': [], 'overflows': []},
        [{'gapId': 'rhythm-gap-p1-m1-v1-1'}],
        {'checks': [{'id': 'pitch_shift', 'passed': True},
                    {'id': 'measure_count', 'passed': True}]})
    assert accepted and report['afterGapCount'] == 0
    accepted, report = validate_repair_result(
        before, {'gaps': [], 'overflows': []},
        [{'gapId': 'rhythm-gap-p1-m1-v1-1'}],
        {'checks': [{'id': 'pitch_shift', 'passed': False}]})
    assert not accepted and report['coreFailures'] == ['pitch_shift']


def test_source_repair_phase_precedes_transposition_and_rendering(api):
    pipeline = inspect.getsource(api.process_score_pdf)
    source_repair = pipeline.index('build_source_repair_evidence(')
    transposition = pipeline.index('summary = transpose_musicxml(')
    rendering = pipeline.index('output_pages, layout_info = render_preserved_score_pdf(')
    assert source_repair < transposition < rendering
