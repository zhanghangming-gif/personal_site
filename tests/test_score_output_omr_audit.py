from pathlib import Path


MUSICXML = '''<score-partwise version="3.1">
<part-list><score-part id="P1"><part-name>Test</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
</measure></part></score-partwise>'''


def test_output_pdf_omr_audit_is_observation_without_authority(api, monkeypatch, tmp_path):
    target = tmp_path / 'transposed.musicxml'
    output = tmp_path / 'output.pdf'
    target.write_text(MUSICXML, encoding='utf-8')
    output.write_bytes(b'%PDF synthetic candidate')
    monkeypatch.setattr(api, 'find_audiveris_command', lambda: ['audiveris'])

    def run(command, cwd, timeout, label):
        destination = Path(command[command.index('-output') + 1])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'recognized.musicxml').write_text(MUSICXML, encoding='utf-8')
        return ''

    monkeypatch.setattr(api, 'run_command', run)
    report, recognized, report_path = api.audit_output_pdf_with_omr(
        str(output), str(target), str(tmp_path))
    assert report['status'] == 'observed_match'
    assert report['outputAllowed'] is False
    assert report['verificationAuthority'] == 'none'
    assert Path(recognized).is_file()
    assert Path(report_path).is_file()


def test_output_pdf_omr_observation_updates_review_without_unlocking(api, tmp_path):
    review = {'outputPdfRecognition': {'status': 'PENDING'}, 'outputAllowed': False}
    (tmp_path / 'score-review.json').write_text(__import__('json').dumps(review), encoding='utf-8')
    verification = {'checks': [{'id': 'output_pdf_evidence', 'label': 'output',
                                'passed': False, 'detail': 'pending'}], 'reviewCoverage': {}}
    report = {
        'status': 'observed_match', 'evidenceLevel': 'pdf_rerecognition_same_omr_family',
        'comparison': {'checks': [{'id': 'rendered_events', 'label': 'events',
                                   'passed': True, 'detail': 'match'}]},
        'outputAllowed': False, 'verificationAuthority': 'none',
    }
    api.attach_output_pdf_omr_observation(str(tmp_path), verification, report)
    stored = __import__('json').loads((tmp_path / 'score-review.json').read_text(encoding='utf-8'))
    assert verification['reviewCoverage']['outputPdfRecognition'] == 'OBSERVED_MATCH'
    assert verification['checks'][0]['id'] == 'output_pdf_evidence'
    assert verification['checks'][0]['passed'] is True
    assert verification['checks'][1]['id'] == 'output_pdf_omr_rendered_events'
    assert stored['outputAllowed'] is False
    assert stored['outputPdfRecognition']['verificationAuthority'] == 'none'
