"""Python 3.6 bridge for guarded system-level PDF composition."""
import json
import os
import subprocess


def compose_score_systems(job_dir, source_pdf, target_pdf):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_system_composer.py')
    source_structures = os.path.join(job_dir, 'inspection', 'structure-candidates.json')
    target_structures = os.path.join(job_dir, 'inspection', 'target-structure-candidates.json')
    output = os.path.join(job_dir, 'candidates', 'system-composed.pdf')
    report = os.path.join(job_dir, 'review', 'system-composition.json')
    os.makedirs(os.path.dirname(output), exist_ok=True)
    command = [python, '-X', 'utf8', script, source_pdf, target_pdf,
               source_structures, target_structures, output, report]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=180, check=False)
        if completed.returncode:
            raise RuntimeError('按系统贴回原页失败')
        with open(report, encoding='utf-8') as stream:
            value = json.load(stream)
        if not os.path.isfile(output):
            raise RuntimeError('按系统贴回原页没有生成候选 PDF')
        return output, value
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('按系统贴回原页暂时不可用') from exc
