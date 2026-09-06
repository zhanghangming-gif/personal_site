"""Independent candidate-only comparison of source and target PDF layout."""
import json
import os


def _read(path):
    with open(path, encoding='utf-8') as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError('视觉版式数据格式无效')
    return value


def _page_heights(coordinates):
    result = {}
    for page in coordinates.get('pages', []):
        rect = ((page.get('sourceSpace') or {}).get('pageRect') or [0, 0, 1, 1])
        try:
            result[int(page.get('page'))] = max(1.0, float(rect[3]) - float(rect[1]))
        except (TypeError, ValueError, IndexError):
            continue
    return result


def _page_rows(structures, heights):
    rows = []
    for page in structures.get('pages', []):
        number = int(page.get('page') or 0)
        height = heights.get(number, 1.0)
        systems = sorted(page.get('systems') or [], key=lambda item: (item.get('bbox') or [0, 0])[1])
        centers, measure_counts, bases = [], [], []
        for system in systems:
            bbox = system.get('bbox') or [0, 0, 0, 0]
            try:
                centers.append(round(((float(bbox[1]) + float(bbox[3])) / 2.0) / height, 5))
            except (TypeError, ValueError, IndexError):
                centers.append(None)
            measure_counts.append(len(system.get('measures') or []))
            bases.append(system.get('basis'))
        rows.append({'page': number, 'systems': len(systems), 'centers': centers,
                     'measureCandidates': measure_counts, 'bases': bases})
    return rows


def compare_visual_layout(job_dir, tolerance=0.08):
    source_structures = _read(os.path.join(job_dir, 'inspection', 'structure-candidates.json'))
    target_structures = _read(os.path.join(job_dir, 'inspection', 'target-structure-candidates.json'))
    source_coordinates = _read(os.path.join(job_dir, 'layout', 'source', 'coordinate-map.json'))
    target_coordinates = _read(os.path.join(job_dir, 'layout', 'target', 'coordinate-map.json'))
    source = _page_rows(source_structures, _page_heights(source_coordinates))
    target = _page_rows(target_structures, _page_heights(target_coordinates))
    page_count_equal = len(source) == len(target)
    source_counts = [item['systems'] for item in source]
    target_counts = [item['systems'] for item in target]
    system_counts_equal = page_count_equal and source_counts == target_counts
    deltas = []
    if system_counts_equal:
        for before, after in zip(source, target):
            for first, second in zip(before['centers'], after['centers']):
                if first is not None and second is not None:
                    deltas.append(abs(first - second))
    maximum_delta = max(deltas) if deltas else None
    vertical_comparable = bool(deltas) and system_counts_equal
    vertical_passed = vertical_comparable and maximum_delta <= tolerance

    same_basis = bool(source) and bool(target) and all(
        before['bases'] == after['bases']
        for before, after in zip(source, target)
    )
    source_measures = [item['measureCandidates'] for item in source]
    target_measures = [item['measureCandidates'] for item in target]
    measure_passed = same_basis and source_measures == target_measures
    checks = [
        {'id': 'visual_page_count', 'passed': page_count_equal,
         'detail': '源谱 %s 页，候选谱 %s 页' % (len(source), len(target))},
        {'id': 'visual_system_count', 'passed': system_counts_equal,
         'detail': '源谱每页系统 %s；候选谱 %s' % (source_counts, target_counts)},
        {'id': 'visual_system_positions', 'passed': vertical_passed,
         'comparable': vertical_comparable,
         'detail': ('最大归一化纵向偏差 %.4f' % maximum_delta) if maximum_delta is not None
                   else '系统数量不同，不能逐行比较纵向位置'},
        {'id': 'visual_measure_candidates', 'passed': measure_passed,
         'comparable': same_basis,
         'detail': '仅在源谱与候选谱使用相同几何检测方法时比较小节候选'},
    ]
    return {
        'schemaVersion': 1,
        'status': 'passed' if page_count_equal and system_counts_equal and vertical_passed else 'needs_review',
        'evidenceLevel': 'layout_candidates_only',
        'semanticVerification': False,
        'tolerance': tolerance,
        'source': source,
        'target': target,
        'checks': checks,
        'limits': '本审计比较页面几何，不证明音符、节奏或演奏标记正确',
    }
