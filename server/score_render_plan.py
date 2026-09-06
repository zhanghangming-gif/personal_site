"""Deterministic renderer planning for a score transformation.

Planning is separate from rendering.  A vector PDF is not enough to permit
local glyph replacement: event-to-object mapping and dependency coverage must
also exist.  Until those capabilities are present the plan explicitly chooses
re-engraving and requires layout plus semantic verification.
"""


def _affected_systems(omr_analysis):
    result = []
    for item in (omr_analysis or {}).get('systems', []):
        result.append({
            'page': item.get('page'),
            'system': item.get('system'),
            'staffCount': item.get('staffCount'),
            'lineStart': item.get('lineStart'),
            'dependencyRegion': 'system',
            'reason': '全谱音高变换可能影响变音记号、加线、符干、符梁和连线',
        })
    return result


def build_render_plan(inspection, omr_analysis, intent, capabilities=None):
    capabilities = dict(capabilities or {})
    profile = (inspection or {}).get('scoreProfile') or {}
    document_type = profile.get('documentType', 'unknown')
    event_mapping = bool(capabilities.get('eventObjectMapping'))
    dependency_graph = bool(capabilities.get('renderDependencyGraph'))
    vector_patch_engine = bool(capabilities.get('vectorPatchEngine'))
    system_renderer = bool(capabilities.get('systemRenderer'))
    system_correspondence = bool(capabilities.get('systemCorrespondence'))
    full_renderer = bool(capabilities.get('fullScoreRenderer', True))

    gates = {
        'sourceIsVector': document_type in ('vector', 'mixed'),
        'eventObjectMapping': event_mapping,
        'renderDependencyGraph': dependency_graph,
        'vectorPatchEngine': vector_patch_engine,
        'systemRenderer': system_renderer,
        'systemCorrespondence': system_correspondence,
        'fullScoreRenderer': full_renderer,
    }
    local_ready = all(gates[name] for name in (
        'sourceIsVector', 'eventObjectMapping', 'renderDependencyGraph', 'vectorPatchEngine'))
    if local_ready:
        mode = 'vector_region_patch'
        reason = '源 PDF 对象、乐谱事件与渲染依赖均可追踪，可按依赖区域局部替换'
    elif system_renderer and system_correspondence:
        mode = 'system_recompose'
        reason = '源谱与候选谱的页面、系统数和系统位置已建立对应，按谱表系统贴回原页'
    elif full_renderer:
        mode = 'full_score_reengrave'
        reason = '尚无可靠的逐事件 PDF 对象映射，使用完整制谱渲染并严格复核分页与语义'
    else:
        mode = 'unavailable'
        reason = '当前任务没有满足安全条件的渲染器'

    return {
        'schemaVersion': 1,
        'intentId': (intent or {}).get('intentId'),
        'sourceDocumentType': document_type,
        'selectedMode': mode,
        'reason': reason,
        'capabilityGates': gates,
        'affectedSystems': _affected_systems(omr_analysis),
        'verificationRequired': [
            'page_geometry', 'page_system_distribution', 'measure_sequence',
            'non_pitch_marks', 'target_pdf_semantics',
        ],
        'outputTrust': 'candidate_until_independently_verified',
    }
