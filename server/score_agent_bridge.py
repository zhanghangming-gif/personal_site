"""Python 3.6 bridge to the experimental per-document AI worker.

Activation is an operator setting, never an untrusted upload parameter.
No automatic fallback to OMR and no model-authored approval of a candidate.
"""
import json
import os
import shutil
import subprocess


def process_agent_score(job_dir, request, progress):
    python = os.environ.get("SCORE_SKILL_PYTHON", "/opt/score-tools/score-venv/bin/python")
    if not os.path.isfile(python):
        raise RuntimeError("逐谱 AI 运行环境尚未配置")
    with open(os.path.join(job_dir, "request.json"), "w", encoding="utf-8") as stream:
        json.dump(request, stream, ensure_ascii=False)
    progress("recognizing", "AI 正在逐谱分析、编写并执行专用脚本", 25)
    command = [python, "-u", os.path.join(os.path.dirname(__file__), "score_agent_worker.py"), job_dir]
    # The child controller needs the API credential; generated code is separately
    # isolated with an empty environment and has no access to this process.
    allowed = ("PATH", "LANG", "DEEPSEEK_API_KEY", "DEEPSEEK_API_URL", "SCORE_AGENT_MODEL", "SCORE_AGENT_MAX_CALLS")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    try:
        with open(os.path.join(job_dir, "agent-worker.log"), "wb") as log:
            completed = subprocess.run(command, env=environment, cwd=job_dir, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=960)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("逐谱 AI 任务未完成；没有退回旧识谱流程")
    path = os.path.join(job_dir, "agent-result.json")
    try:
        with open(path, encoding="utf-8") as stream:
            report = json.load(stream)
    except (OSError, ValueError):
        raise RuntimeError("逐谱 AI 未生成有效的处理记录")
    if completed.returncode or report.get("status") != "needs_review":
        raise RuntimeError(report.get("message", "逐谱 AI 未能完成处理"))
    candidate = os.path.join(job_dir, "agent-work", "candidate.pdf")
    if not os.path.isfile(candidate):
        raise RuntimeError("逐谱 AI 没有生成候选 PDF")
    output = os.path.join(job_dir, "output.pdf")
    shutil.copyfile(candidate, output)
    progress("verifying", "候选 PDF 已生成，等待独立核对原谱", 90)
    # Never use the model's own pass/fail fields to authorize public downloads.
    verification = {
        "engine": "deepseek-agent", "status": "needs_review", "summary": report["message"],
        "checks": [{"id": "independent_music_review", "label": "原谱独立复核", "passed": False,
                    "detail": "AI 自检不能代替对原谱全部音符和标记的独立核对"}],
        "agentReport": report,
        "pipeline": {"stage": "needs_review", "overallStatus": "NEEDS_REVIEW", "fatal": False,
                     "outputAllowed": False, "fallbackUsed": False, "warnings": [report["message"]]},
    }
    summary = {"sourcePages": report["sourcePages"], "outputPages": report["outputPages"],
               "engine": "deepseek-agent"}
    return output, summary, verification
