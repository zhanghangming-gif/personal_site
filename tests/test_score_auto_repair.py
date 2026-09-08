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
        'onset': '1', 'duration': '1', 'position': 'internal',
        'location': {'part': 1, 'measureIndex': 1, 'measure': '1'},
        'riskReasons': ['multiple_voices'] if with_risk else [],
    }
    return root, {'gaps': [gap], 'overflows': []}


def classification(grade=.78):
    return {'classifications': [{
        'gapId': 'rhythm-gap-p1-m1-v1-1', 'status': 'supported_by_omr_object',
        'suggestedNotation': 'quarter_rest', 'suggestedDots': 0,
        'candidateCount': 1, 'exactCandidateCount': 1,
        'selectedEvidence': {
            'grade': grade, 'contextGrade': grade, 'durationMatchesGap': True,
            'staffPositionConsistent': True,
        },
    }]}


def test_auto_repair_inserts_only_unique_high_grade_source_rest(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    report = apply_safe_rhythm_repairs(root, gaps, classification())
    assert report['appliedCount'] == 1
    assert '后端依据原谱对象证据' in report['applied'][0]['changes'][0]['after']
    assert '用户' not in report['applied'][0]['changes'][0]['after']
    assert root.find('.//forward') is None
    rests = [note for note in root.findall('.//note') if note.find('rest') is not None]
    assert len(rests) == 1 and rests[0].findtext('duration') == '4'


def test_auto_repair_rejects_low_confidence_and_rhythm_risks(api):
    from score_auto_repair import apply_safe_rhythm_repairs
    root, gaps = source_tree()
    before = ET.tostring(root)
    assert apply_safe_rhythm_repairs(root, gaps, classification(.74))['appliedCount'] == 0
    assert ET.tostring(root) == before
    root, gaps = source_tree(True)
    assert apply_safe_rhythm_repairs(root, gaps, classification())['appliedCount'] == 0


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
