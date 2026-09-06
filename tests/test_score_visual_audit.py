import json


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixtures(tmp_path, target_centers=(105, 205), target_count=2):
    def structure(centers, count):
        return {'pages': [{'page': 1, 'systems': [
            {'bbox': [10, center - 5, 290, center + 5], 'basis': 'raster_projection_candidate',
             'measures': [{}, {}]} for center in centers[:count]
        ]}]}
    coordinates = {'pages': [{'page': 1, 'sourceSpace': {'pageRect': [0, 0, 300, 400]}}]}
    write(tmp_path / 'inspection' / 'structure-candidates.json', structure((100, 200), 2))
    write(tmp_path / 'inspection' / 'target-structure-candidates.json', structure(target_centers, target_count))
    write(tmp_path / 'layout' / 'source' / 'coordinate-map.json', coordinates)
    write(tmp_path / 'layout' / 'target' / 'coordinate-map.json', coordinates)


def test_visual_layout_audit_compares_normalized_system_geometry(api, tmp_path):
    fixtures(tmp_path)
    report = api.compare_visual_layout(str(tmp_path))
    assert report['status'] == 'passed'
    assert report['semanticVerification'] is False
    assert all(item['passed'] for item in report['checks'])


def test_visual_layout_audit_reports_extra_system_without_claiming_semantics(api, tmp_path):
    fixtures(tmp_path, target_centers=(100,), target_count=1)
    report = api.compare_visual_layout(str(tmp_path))
    assert report['status'] == 'needs_review'
    checks = {item['id']: item for item in report['checks']}
    assert checks['visual_system_count']['passed'] is False
    assert checks['visual_system_positions']['comparable'] is False
    assert report['evidenceLevel'] == 'layout_candidates_only'


def test_system_composition_requires_every_layout_gate(api):
    target = {'scoreProfile': {'documentType': 'vector'}}
    audit = {'status': 'passed', 'checks': [
        {'id': name, 'passed': True} for name in (
            'visual_page_count', 'visual_system_count', 'visual_system_positions',
            'visual_measure_candidates')
    ]}
    assert api.system_composition_eligibility(target, audit)[0] is True
    audit['checks'][-1]['passed'] = False
    allowed, reason = api.system_composition_eligibility(target, audit)
    assert allowed is False
    assert 'visual_measure_candidates' in reason
