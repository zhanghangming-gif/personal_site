"""Bounded DeepSeek visual review of already-located score conflicts.

The model observes source/target crops and proposes review notes. It cannot
modify score data, approve a PDF, or access credentials through generated code.
"""
import argparse
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from score_inspection import render_region


MODEL = 'deepseek-v4-flash-vision-exp'
SYSTEM = """你是乐谱视觉复核器。输入是同一转调任务中已定位的原谱与候选谱局部图。
只描述可见证据：谱号、调号、拍号、音符/休止数量、临时记号、符梁、连线、力度、文字、
小节线和编号。不要把看不清的内容猜成确定结论，不执行代码，不声明整份乐谱正确。
当 kind=source_rhythm_gap 时，只判断标注区域可见的休止符候选、音符时值或多声部迹象；
没有清晰字形时必须写不确定，不能根据缺少时值直接猜休止符种类。
返回 JSON 对象：summary、regions。regions 每项包含 id、sourceObservations、
targetObservations、differences、confidence（high/medium/low）、manualReviewRequired。
"""


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        value = json.load(stream)
    return value if isinstance(value, dict) else {}


def structure_index(path):
    result = {}
    for page in read_json(path).get('pages', []):
        for position, system in enumerate(page.get('systems') or [], 1):
            result[(int(page.get('page') or 0), position)] = system
    return result


def risky_locations(job_dir, limit=6):
    pipeline = read_json(Path(job_dir) / 'pipeline-report.json')
    verification = pipeline.get('verification') or {}
    rows = []
    repair = ((verification.get('omr') or {}).get('multirestRepair') or {})
    for gap in repair.get('unresolvedGaps') or []:
        rows.append({'page': gap.get('page'), 'system': gap.get('system'),
                     'reason': gap.get('reason'), 'kind': 'structure_gap'})
    for issue in verification.get('issues') or []:
        location = issue.get('location') or {}
        if location.get('page') and location.get('system'):
            region = issue.get('pdfRegion') or {}
            rows.append({'page': location.get('page'), 'system': location.get('system'),
                         'reason': issue.get('message'),
                         'kind': ('source_rhythm_gap' if issue.get('code') == 'missing_rhythm_duration'
                                  else issue.get('phase', 'verification')),
                         'sourceBboxHint': region.get('bbox')})
    unique = []
    seen = set()
    for row in rows:
        try:
            key = (int(row['page']), int(row['system']))
        except (TypeError, ValueError):
            continue
        if key not in seen:
            seen.add(key)
            row.update(page=key[0], system=key[1])
            unique.append(row)
        if len(unique) >= limit:
            break
    return unique


def prepare_regions(job_dir, limit=6):
    job = Path(job_dir)
    source_index = structure_index(job / 'inspection' / 'structure-candidates.json')
    target_index = structure_index(job / 'inspection' / 'target-structure-candidates.json')
    rows = []
    for position, location in enumerate(risky_locations(job, limit), 1):
        key = (location['page'], location['system'])
        source_system, target_system = source_index.get(key), target_index.get(key)
        if not source_system or not target_system:
            continue
        source_bbox = location.get('sourceBboxHint') or source_system.get('bbox')
        source_dpi = 800 if location.get('kind') == 'source_rhythm_gap' else 300
        source = render_region(job / 'input.pdf', job, key[0], source_bbox, source_dpi, False)
        target = render_region(job / 'output.pdf', job, key[0], target_system.get('bbox'), 300, False)
        rows.append(dict(location, id='region-%03d' % position,
                         sourceImage=source['path'], targetImage=target['path'],
                         sourceBbox=source['bbox'], targetBbox=target['bbox']))
    return rows


def image_part(path):
    data = base64.b64encode(Path(path).read_bytes()).decode('ascii')
    return {'type': 'image_url', 'image_url': {
        'url': 'data:image/png;base64,' + data, 'detail': 'original'}}


def call_model(job_dir, regions):
    job = Path(job_dir)
    content = [{'type': 'text', 'text': '逐区域比较。每对图片顺序都是原谱、候选谱。区域元数据：' +
                json.dumps([{k: row.get(k) for k in ('id', 'page', 'system', 'reason', 'kind')}
                            for row in regions], ensure_ascii=False)}]
    for row in regions:
        content.append({'type': 'text', 'text': row['id'] + ' 原谱'})
        content.append(image_part(job / row['sourceImage']))
        content.append({'type': 'text', 'text': row['id'] + ' 候选谱'})
        content.append(image_part(job / row['targetImage']))
    url = os.environ.get('DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions')
    payload = json.dumps({
        'model': os.environ.get('SCORE_VISION_MODEL', MODEL),
        'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': content}],
        'response_format': {'type': 'json_object'}, 'temperature': 0,
        'max_tokens': 4000,
    }, ensure_ascii=False).encode('utf-8')
    request = Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY'],
    })
    try:
        with urlopen(request, timeout=150) as response:
            raw = response.read(2 * 1024 * 1024)
    except HTTPError as exc:
        raise RuntimeError('AI 视觉复核请求失败（HTTP %s）' % exc.code)
    except (URLError, TimeoutError):
        raise RuntimeError('AI 视觉复核连接失败或超时')
    result = json.loads(raw.decode('utf-8'))
    text = result['choices'][0]['message']['content']
    observation = json.loads(text)
    if not isinstance(observation, dict) or not isinstance(observation.get('regions'), list):
        raise RuntimeError('AI 视觉复核返回格式无效')
    return observation, result.get('usage') or {}, result.get('model')


def run(job_dir):
    if not os.environ.get('DEEPSEEK_API_KEY'):
        raise RuntimeError('AI 视觉复核没有配置 API Key')
    regions = prepare_regions(job_dir, min(8, max(1, int(os.environ.get('SCORE_AI_REVIEW_REGIONS', '6')))))
    if not regions:
        return {'schemaVersion': 1, 'status': 'skipped', 'outputAllowed': False,
                'reason': '没有可同时定位到源谱与候选谱的冲突区域'}
    observation, usage, model = call_model(job_dir, regions)
    return {
        'schemaVersion': 1, 'status': 'observed', 'outputAllowed': False,
        'verificationAuthority': 'none', 'model': model or os.environ.get('SCORE_VISION_MODEL', MODEL),
        'regions': regions, 'modelOutput': observation, 'usage': usage,
        'limits': '模型观察只能生成复核建议，不能批准候选 PDF 或代替独立音乐语义验证',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job_dir')
    arguments = parser.parse_args()
    report = run(Path(arguments.job_dir).resolve())
    output = Path(arguments.job_dir) / 'review' / 'ai-visual-review.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({'status': report['status'], 'regions': len(report.get('regions', []))}))


if __name__ == '__main__':
    main()
