def test_public_score_verification_keeps_summary_and_drops_heavy_geometry(api):
    verification = {
        'checks': [{'id': 'pitch', 'passed': True}],
        'issues': [{'id': str(index)} for index in range(80)],
        'omr': {
            'systems': [{'large': 'value'} for _ in range(40)],
            'rawPages': [{'systems': [8, 9]}],
            'recognitionAttempts': [{'family': 'Bravura'}],
            'multirestRepair': {'valid': False, 'reason': 'ambiguous',
                                'detectedRestCounts': [{}, {}]},
        },
        'preflight': {
            'pages': 3, 'changed': False, 'pageDetails': [{'geometry': {'large': 'value'}}],
            'repairs': [], 'issues': [],
        },
        'layout': {
            'expectedSystemsPerPage': [12, 14, 14],
            'outputSystemsPerPage': [13, 14, 14],
            'renderAudit': {'semanticAudit': {'passed': False, 'issueCount': 336,
                                              'issues': [{'large': 'value'}] * 200}},
        },
    }

    public = api.public_score_verification(verification)

    assert len(public['issues']) == 50
    assert public['omr']['systemCount'] == 40
    assert 'systems' not in public['omr']
    assert 'pageDetails' not in public['preflight']
    assert public['layout']['renderAudit']['semanticAudit']['issueCount'] == 336
    assert 'issues' not in public['layout']['renderAudit']['semanticAudit']
    assert len(verification['issues']) == 80


def test_layout_probe_compares_staff_totals_instead_of_page_count_only(api):
    omr = {'systems': [
        {'page': 1, 'staffCount': 1}, {'page': 1, 'staffCount': 2},
        {'page': 2, 'staffCount': 2}, {'page': 2, 'staffCount': 2},
    ]}
    assert api.expected_system_counts(omr) == [2, 2]
    assert api.expected_staff_counts(omr) == [3, 4]
    assert api.layout_count_distance([4, 4], [3, 4], 2) == 1
    assert api.layout_count_distance([3, 4], [3, 4], 2) == 0
    assert api.layout_count_distance([3], [3, 4], 2) > 100
