def test_render_plan_does_not_equate_vector_pdf_with_safe_local_patch(api):
    plan = api.build_render_plan(
        {'scoreProfile': {'documentType': 'vector'}},
        {'systems': [{'page': 1, 'system': 1, 'staffCount': 1, 'lineStart': 1}]},
        {'intentId': 'intent-test'},
        {'fullScoreRenderer': True},
    )
    assert plan['selectedMode'] == 'full_score_reengrave'
    assert plan['capabilityGates']['sourceIsVector'] is True
    assert plan['capabilityGates']['eventObjectMapping'] is False
    assert plan['outputTrust'] == 'candidate_until_independently_verified'
    assert plan['affectedSystems'][0]['dependencyRegion'] == 'system'


def test_render_plan_allows_local_patch_only_after_all_dependency_gates(api):
    plan = api.build_render_plan(
        {'scoreProfile': {'documentType': 'mixed'}}, {'systems': []},
        {'intentId': 'intent-test'},
        {'fullScoreRenderer': True, 'eventObjectMapping': True,
         'renderDependencyGraph': True, 'vectorPatchEngine': True},
    )
    assert plan['selectedMode'] == 'vector_region_patch'


def test_render_plan_allows_system_recompose_after_layout_correspondence(api):
    plan = api.build_render_plan(
        {'scoreProfile': {'documentType': 'scan'}}, {'systems': []},
        {'intentId': 'intent-test'},
        {'fullScoreRenderer': True, 'systemRenderer': True,
         'systemCorrespondence': True},
    )
    assert plan['selectedMode'] == 'system_recompose'
    assert plan['capabilityGates']['eventObjectMapping'] is False
    assert plan['capabilityGates']['systemCorrespondence'] is True
