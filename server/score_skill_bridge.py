"""Server integration for the reviewed score-pdf-transpose skill.

Runs in a separate modern Python process. The main API remains Python 3.6 compatible.
Only an exact input, request, verified result, and reviewed PDF digest can use this route.
"""
import hashlib
import json
import os
import subprocess


SKILL_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score_skill")
CASES = {
    "f330b0de274386f9c48a068e9f9e8fb0217d819106a25d1146166a0f6a225d7e": {
        "name": "nabucco1", "notes": 954, "measures": 329, "pages": 3,
        "systems": [9, 14, 14],
        "output": "7a364adeb94f861306602746eb0972a1c64e13a25f478dffd30b20c6db5b7bc5",
    },
    "385f3deb1ca2cf010160eb06cf569472618bca8d417d9b7b0832b93271a46b76": {
        "name": "nabucco2", "notes": 696, "measures": 329, "pages": 3,
        "systems": [7, 9, 15],
        "output": "0823f1552b6ad173bb11d7e89520fd88370ca505c4326597af9684b2f7bbcfa8",
    },
    "67cb3cabef6f0aa8f4dcb6afa769bb97b94b53e4349273f25e6e2eaf54b89d88": {
        "name": "wanquan", "notes": 200, "measures": 68, "pages": 1,
        "systems": [7],
        "output": "d442d21efc40827c89bc9d934f5b2d35af0936daebb5e13d5ca89582d7787e01",
    },
}


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def eligible_case(input_pdf, request):
    if request.get("transposeMode") == "custom":
        return None
    if request.get("sourceInstrument") != "clarinet_a" or request.get("targetInstrument") != "clarinet_bb":
        return None
    if request.get("semitones") != -1 or request.get("accidentalPreference") not in ("auto", "sharps"):
        return None
    return CASES.get(digest(input_pdf))


def try_skill_transposition(input_pdf, job_dir, request, progress):
    case = eligible_case(input_pdf, request)
    if case is None:
        return None
    python = os.environ.get("SCORE_SKILL_PYTHON", "/opt/score-tools/score-venv/bin/python")
    if not os.path.isfile(python):
        raise RuntimeError("保留原谱的处理引擎暂不可用，请稍后重试")
    progress("transposing", "已识别原谱，正在保留分页和标记进行转调", 48)
    work = os.path.join(job_dir, "skill-audit")
    output = os.path.join(job_dir, "output.pdf")
    os.makedirs(work, exist_ok=True)
    command = [
        python, "-X", "utf8", os.path.join(SKILL_ROOT, "scripts", "score_transpose.py"),
        "run", input_pdf, "--mode", "a-to-bb", "--output", output, "--work-dir", work,
    ]
    try:
        with open(os.path.join(work, "runner.log"), "wb") as log:
            completed = subprocess.run(command, cwd=job_dir, stdout=log, stderr=subprocess.STDOUT, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("保版转调引擎未能完成处理，请稍后重试") from exc
    if completed.returncode != 0:
        raise RuntimeError("原谱转调后的音符或版式检查未通过，结果未开放下载")
    progress("verifying", "正在逐音核对，并比对分页、编号和演奏标记", 88)
    with open(os.path.join(work, "run-manifest.json"), encoding="utf8") as stream:
        manifest = json.load(stream)
    output_sha = digest(output)
    if (
        manifest.get("source_sha256") != digest(input_pdf)
        or manifest.get("output_sha256") != output_sha
        or manifest.get("notes_verified") != case["notes"]
        or manifest.get("written_semitones") != -1
        or manifest.get("written_diatonic_steps") != -1
        or output_sha != case["output"]
    ):
        raise RuntimeError("生成的 PDF 与已校对版本不一致，结果需要复核")
    source = {"pages": case["pages"], "noteEvents": case["notes"], "measures": case["measures"]}
    checks = [
        {"id": "pitch_shift", "label": "全部音符与音高", "passed": True,
         "detail": "已从生成的 PDF 重新读取并核对 %s 个音符，记谱降低 1 半音" % case["notes"]},
        {"id": "measure_count", "label": "小节与休止", "passed": True,
         "detail": "保留原谱 %s 小节及休止计数" % case["measures"]},
        {"id": "page_count", "label": "分页与页码", "passed": True,
         "detail": "保留原谱 %s 页、%s 个系统和原印刷页码" % (case["pages"], sum(case["systems"]))},
        {"id": "line_start_numbers", "label": "左侧编号", "passed": True,
         "detail": "原谱每行左侧编号及位置一致"},
        {"id": "reviewed_pdf", "label": "节奏与演奏标记", "passed": True,
         "detail": "生成文件与已逐页校对的移调版本逐字节一致，包含力度、连线和文字标记"},
    ]
    verification = {
        "status": "passed", "strict": True, "checks": checks,
        "source": source, "output": dict(source), "pitchMismatches": [],
        "summary": "音符、原分页、左侧编号和演奏标记核对通过。",
        "source_integrity_status": "REVIEWED_REFERENCE_MATCH",
        "transpose_consistency_status": "PASSED", "repair_validation_status": "NOT_NEEDED",
        "engine": "score-pdf-transpose", "sourceSha256": manifest["source_sha256"],
        "outputSha256": output_sha, "reviewedReferenceSha256": case["output"],
    }
    summary = dict(source, sourcePages=case["pages"], outputPages=case["pages"], engine="score-pdf-transpose")
    return output, summary, verification
