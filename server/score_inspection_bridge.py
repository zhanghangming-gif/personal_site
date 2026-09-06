"""Run multi-scale inspection in the isolated modern Python environment."""
import json
import os
import subprocess


def inspect_score_pdf(input_pdf, job_dir, preflight=None):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_inspection.py')
    report = os.path.join(job_dir, 'inspection', 'inspection.json')
    preflight_path = os.path.join(job_dir, 'preflight.json')
    preview_dpi = int(os.environ.get('SCORE_PREVIEW_DPI', '150'))
    analysis_dpi = int(os.environ.get('SCORE_ANALYSIS_DPI', '400'))
    pages = int((preflight or {}).get('pages') or 1)
    timeout = min(600, 45 + pages * 25)
    command = [python, '-X', 'utf8', script, input_pdf, '--job-dir', job_dir,
               '--preview-dpi', str(preview_dpi), '--analysis-dpi', str(analysis_dpi)]
    if os.path.isfile(preflight_path):
        command.extend(['--preflight', preflight_path])
    try:
        log_path = os.path.join(job_dir, 'logs', 'inspection.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:
            raise RuntimeError('PDF视觉工作区生成失败')
        with open(report, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError('PDF视觉工作区暂时不可用或处理超时') from exc


def inspect_rendered_score_pdf(output_pdf, job_dir, pages=1):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_inspection.py')
    report = os.path.join(job_dir, 'inspection', 'target-inspection.json')
    preview_dpi = int(os.environ.get('SCORE_PREVIEW_DPI', '150'))
    analysis_dpi = int(os.environ.get('SCORE_ANALYSIS_DPI', '400'))
    command = [python, '-X', 'utf8', script, output_pdf, '--job-dir', job_dir,
               '--preview-dpi', str(preview_dpi), '--analysis-dpi', str(analysis_dpi),
               '--role', 'target']
    try:
        log_path = os.path.join(job_dir, 'logs', 'target-inspection.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=min(600, 45 + int(pages or 1) * 25))
        if result.returncode:
            raise RuntimeError('输出PDF视觉检查失败')
        with open(report, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError('输出PDF视觉检查暂时不可用或处理超时') from exc


def render_score_region(input_pdf, job_dir, page, bbox, dpi=800):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_inspection.py')
    command = [python, '-X', 'utf8', script, input_pdf, '--job-dir', job_dir,
               '--page', str(page), '--bbox'] + [str(value) for value in bbox] + [
               '--dpi', str(dpi)]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('局部谱面渲染失败')
        return json.loads(result.stdout.decode('utf-8'))
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError('局部谱面渲染暂时不可用或处理超时') from exc


def prepare_omr_variant(input_pdf, job_dir, dpi=300):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_inspection.py')
    command = [python, '-X', 'utf8', script, input_pdf, '--job-dir', job_dir,
               '--prepare-omr-variant', '--dpi', str(dpi)]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=300, check=False)
        if result.returncode:
            raise RuntimeError('扫描谱识谱增强失败')
        report = json.loads(result.stdout.decode('utf-8'))
        path = os.path.join(job_dir, *report['path'].split('/'))
        if not os.path.isfile(path):
            raise RuntimeError('扫描谱识谱增强没有生成文件')
        return path, report
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        raise RuntimeError('扫描谱识谱增强暂时不可用或处理超时') from exc
