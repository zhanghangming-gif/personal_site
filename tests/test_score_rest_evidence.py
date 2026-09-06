import zipfile


def make_book(path, rests, relations=""):
    rows = []
    for identifier, shape, x, y, width, height, grade, pitch in rests:
        rows.append(
            '<rest id="%s" shape="%s" staff="4" grade="%s" ctx-grade="0.8" pitch="%s">'
            '<bounds x="%s" y="%s" w="%s" h="%s"/></rest>'
            % (identifier, shape, grade, pitch, x, y, width, height))
    xml = ('<sheet><picture width="1200" height="1600"/><system><staff id="4"/>'
           '<stack left="300" right="600"/><sig><inters>%s</inters>'
           '<relations>%s</relations></sig></system></sheet>') % (''.join(rows), relations)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('sheet#1/sheet#1.xml', xml)


def gap(duration='1', position='internal', bbox=None, expected='4'):
    value = {
        'id': 'rhythm-gap-p1-m2-v1-1', 'measureId': 'p1-m2',
        'duration': duration, 'expectedMeasureDuration': expected, 'position': position,
        'staffs': ['1'],
        'location': {'page': 1, 'system': 1, 'positionInSystem': 1,
                     'measure': '2', 'voice': '1'},
    }
    if bbox:
        value['reviewRegion'] = {'page': 1, 'bbox': bbox}
    return value


def preflight():
    return {'pageDetails': [{'page': 1, 'geometry': {'width': 600, 'height': 800}}]}


def test_unique_exact_raw_omr_rest_becomes_supported_review_evidence(api, tmp_path):
    from score_rest_evidence import annotate_rhythm_gaps, audiveris_rest_objects, classify_rest_gaps
    from score_rhythm_gaps import rhythm_gap_issues
    book = tmp_path / 'score.omr'
    make_book(book, [('10', 'QUARTER_REST', 400, 500, 24, 60, .75, -.3)])
    pages = audiveris_rest_objects(str(book))
    assert pages[0]['systems'][0]['rests'][0]['staffPosition'] == 1
    report = classify_rest_gaps({'gaps': [gap(bbox=[190, 230, 220, 300])]}, str(book), preflight())
    result = report['classifications'][0]
    assert result['status'] == 'supported_by_omr_object'
    assert result['suggestedNotation'] == 'quarter_rest'
    assert result['autoRepairAllowed'] is False
    assert result['selectedEvidence']['durationMatchesGap'] is True
    rhythm = {'gaps': [gap(bbox=[190, 230, 220, 300])]}
    annotate_rhythm_gaps(rhythm, report)
    assert rhythm['gaps'][0]['restEvidence']['suggestedNotation'] == 'quarter_rest'
    assert '疑似四分休止符' in rhythm_gap_issues(rhythm)[0]['message']


def test_whole_rest_can_represent_a_full_three_four_measure(api, tmp_path):
    from score_rest_evidence import classify_rest_gaps
    book = tmp_path / 'score.omr'
    make_book(book, [('11', 'WHOLE_REST', 400, 500, 30, 14, .79, -1.4)])
    report = classify_rest_gaps(
        {'gaps': [gap(duration='3', expected='3', position='full_measure')]},
        str(book), preflight())
    selected = report['classifications'][0]['selectedEvidence']
    assert selected['durationBasis'] == 'whole_measure_rest'
    assert selected['notation'] == 'whole_rest'


def test_dot_relation_changes_written_rest_duration(api, tmp_path):
    from score_rest_evidence import classify_rest_gaps
    book = tmp_path / 'score.omr'
    relation = ('<augmentation-dot id="20" shape="AUGMENTATION_DOT"><bounds x="430" y="510" w="5" h="5"/>'
                '</augmentation-dot><relation source="20" target="10"><augmentation/></relation>')
    make_book(book, [('10', 'QUARTER_REST', 400, 500, 24, 60, .75, -.3)], relation)
    report = classify_rest_gaps({'gaps': [gap(duration='3/2')]}, str(book), preflight())
    result = report['classifications'][0]
    assert result['suggestedNotation'] == 'quarter_rest'
    assert result['suggestedDots'] == 1


def test_multiple_exact_candidates_remain_ambiguous(api, tmp_path):
    from score_rest_evidence import classify_rest_gaps
    book = tmp_path / 'score.omr'
    make_book(book, [
        ('10', 'QUARTER_REST', 390, 500, 24, 60, .75, -.3),
        ('11', 'QUARTER_REST', 450, 500, 24, 60, .78, -.3),
    ])
    report = classify_rest_gaps({'gaps': [gap()]}, str(book), preflight())
    result = report['classifications'][0]
    assert result['status'] == 'ambiguous_candidates'
    assert result['suggestedNotation'] is None
    assert result['autoRepairAllowed'] is False


def test_wrong_duration_or_staff_position_cannot_support_candidate(api, tmp_path):
    from score_rest_evidence import classify_rest_gaps
    book = tmp_path / 'score.omr'
    make_book(book, [('10', 'HALF_REST', 400, 500, 30, 14, .8, -1.4)])
    report = classify_rest_gaps({'gaps': [gap(duration='2')]}, str(book), preflight())
    result = report['classifications'][0]
    assert result['status'] == 'visual_confirmation_required'
    assert result['candidates'][0]['durationMatchesGap'] is True
    assert result['candidates'][0]['staffPositionConsistent'] is False
