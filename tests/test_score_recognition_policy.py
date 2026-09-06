def analysis(notes_missing=0, systems=2, line_numbers=None):
    return {
        'systems': [{} for _ in range(systems)],
        'recognizedLineNumbers': line_numbers or [1, 5],
        'lineNumberCoverage': 1.0,
        'exportErrors': [], 'bookIssue': '',
        'multirestMissing': ['x'] * notes_missing,
        'pdfSourceAudit': {'measureConflicts': []},
    }


def test_recognition_decision_selects_structurally_safer_attempt_and_keeps_disagreement(api):
    primary = api.recognition_attempt('primary', 'Bravura', analysis(notes_missing=2), 900)
    alternate = api.recognition_attempt('alternate', 'Leland', analysis(notes_missing=0), 890)
    decision = api.recognition_decision([primary, alternate])
    assert decision['selectedAttemptId'] == 'alternate'
    assert decision['independentRecognition'] is False
    assert decision['requiresReview'] is True
    assert any(item['field'] == 'noteEvents' for item in decision['disagreements'])
    assert [item['selected'] for item in decision['attempts']] == [False, True]


def test_recognition_decision_prefers_coverage_only_after_equal_structural_risk(api):
    lower = api.recognition_attempt('lower', 'Bravura', analysis(), 880)
    higher = api.recognition_attempt('higher', 'Leland', analysis(), 900)
    decision = api.recognition_decision([lower, higher])
    assert decision['selectedAttemptId'] == 'higher'
    assert decision['requiresReview'] is True


def test_recognition_attempt_records_input_representation(api):
    item = api.recognition_attempt('scan', 'Bravura', analysis(), 900,
                                   'inspection/omr-normalized.pdf',
                                   'grayscale_autocontrast_raster_pdf')
    assert item['input']['representation'] == 'grayscale_autocontrast_raster_pdf'


def test_recognition_consensus_surfaces_pitch_disagreement_without_certifying_truth(api):
    base = {'measureNumbers': ['0:1'], 'noteCount': 2,
            'noteEvents': [{'measureNumber': '1', 'midi': 60}, {'measureNumber': '1', 'midi': 62}]}
    other = {'measureNumbers': ['0:1'], 'noteCount': 2,
             'noteEvents': [{'measureNumber': '1', 'midi': 60}, {'measureNumber': '1', 'midi': 63}]}
    result = api.recognition_consensus([
        {'attemptId': 'a', 'signature': base}, {'attemptId': 'b', 'signature': other}], 'a')
    assert result['status'] == 'compared'
    assert result['correlatedEvidenceOnly'] is True
    assert result['issueCount'] == 1
    assert result['issues'][0]['field'] == 'pitch'
