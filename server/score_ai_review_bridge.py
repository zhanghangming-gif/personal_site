"""Python 3.6 bridge for bounded DeepSeek visual score review."""
import json
import os
import subprocess


def run_ai_visual_review(job_dir):
    if os.environ.get('SCORE_AI_VISUAL_REVIEW', '0') != '1':
        return None
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_ai_review_worker.py')
    allowed = ('PATH', 'LANG', 'DEEPSEEK_API_KEY', 'DEEPSEEK_API_URL',
               'SCORE_VISION_MODEL', 'SCORE_AI_REVIEW_REGIONS')
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    report_path = os.path.join(job_dir, 'review', 'ai-visual-review.json')
    try:
        log_path = os.path.join(job_dir, 'logs', 'ai-visual-review.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'wb') as log:
            result = subprocess.run([python, '-X', 'utf8', script, job_dir], env=environment,
                                    cwd=job_dir, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=240)
        if result.returncode:
            raise RuntimeError('AI 视觉复核未完成')
        with open(report_path, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('AI 视觉复核暂时不可用或超时') from exc
