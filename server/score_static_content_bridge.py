"""Python 3.6 bridge for source PDF static-header preservation."""
import json
import os
import subprocess


def preserve_score_headers(job_dir, source_pdf, target_pdf):
    python = os.environ.get("SCORE_SKILL_PYTHON", "/opt/score-tools/score-venv/bin/python")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score_static_content.py")
    source_structures = os.path.join(job_dir, "inspection", "structure-candidates.json")
    target_structures = os.path.join(job_dir, "inspection", "target-structure-candidates.json")
    output = os.path.join(job_dir, "candidates", "header-preserved.pdf")
    report = os.path.join(job_dir, "review", "static-content-preservation.json")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    os.makedirs(os.path.dirname(report), exist_ok=True)
    command = [python, "-X", "utf8", script, source_pdf, target_pdf,
               source_structures, target_structures, output, report]
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=120, check=False)
        if completed.returncode:
            raise RuntimeError("原谱标题区保留失败")
        with open(report, encoding="utf-8") as stream:
            value = json.load(stream)
        if not os.path.isfile(output):
            raise RuntimeError("原谱标题区保留没有生成候选 PDF")
        return output, value
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("原谱标题区保留暂时不可用") from exc
