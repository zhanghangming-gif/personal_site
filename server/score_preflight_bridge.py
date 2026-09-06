"""Run PDF font preflight with the isolated modern Python interpreter."""
import json
import os
import subprocess


def preflight_pdf(input_pdf, job_dir):
    python = os.environ.get('SCORE_SKILL_PYTHON', '/opt/score-tools/score-venv/bin/python')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_pdf_preflight.py')
    output = os.path.join(job_dir, 'prepared.pdf')
    report = os.path.join(job_dir, 'preflight.json')
    try:
        with open(os.path.join(job_dir, 'preflight.log'), 'wb') as log:
            result = subprocess.run([python, '-X', 'utf8', script, input_pdf,
                                     '--output', output, '--report', report],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=60)
        if result.returncode:
            raise RuntimeError('PDF 预检未能完成，请检查文件是否损坏或受密码保护')
        with open(report, encoding='utf8') as stream:
            details = json.load(stream)
        # A broken embedded font can still be readable after rasterization. Keep
        # the defect as evidence and let recognition continue as a candidate;
        # it must not be silently treated as verified source music.
        return output if details['changed'] else input_pdf, details
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError('PDF 预检引擎暂时不可用或处理超时') from exc
