"""Manifest validation and comparisons for the score blind benchmark.

The benchmark manifest is metadata only.  PDF files stay outside the source
repository and are addressed by a relative path plus an immutable SHA-256.
This module is Python 3.6 compatible.
"""
import hashlib
import json
import os
import re


CASE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
STATUS_RANK = {
    "CRASHED": 0, "FAILED": 0, "REJECTED": 0,
    "NEEDS_REVIEW": 1, "VERIFIED_WITH_WARNINGS": 2, "VERIFIED": 3,
}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contained_path(root, relative):
    if not isinstance(relative, str) or not relative or os.path.isabs(relative):
        raise ValueError("盲测文件必须使用输入目录内的相对路径")
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, relative))
    try:
        inside = os.path.commonpath([root, path]) == root
    except (AttributeError, ValueError):
        inside = path == root or path.startswith(root + os.sep)
    if not inside:
        raise ValueError("盲测文件不能离开输入目录")
    return path


def load_manifest(input_dir, manifest_path):
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise ValueError("盲测清单版本无效")
    if manifest.get("trainingPolicy") != "exclude_all_cases":
        raise ValueError("盲测清单必须明确禁止进入训练集")
    entries = manifest.get("cases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("盲测清单没有测试案例")
    cases, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("盲测案例格式无效")
        case_id = entry.get("caseId")
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id) or case_id in seen:
            raise ValueError("盲测案例编号无效或重复")
        seen.add(case_id)
        path = _contained_path(input_dir, entry.get("source"))
        if not os.path.isfile(path) or not path.lower().endswith(".pdf"):
            raise ValueError("盲测 PDF 不存在：%s" % entry.get("source"))
        expected_hash = str(entry.get("sha256") or "").lower()
        actual_hash = file_sha256(path)
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or actual_hash != expected_hash:
            raise ValueError("盲测 PDF 摘要不匹配：%s" % entry.get("source"))
        request = entry.get("request") or {}
        if not isinstance(request, dict):
            raise ValueError("盲测转调请求格式无效：%s" % case_id)
        cases.append({
            "caseId": case_id,
            "path": path,
            "source": entry["source"],
            "sha256": actual_hash,
            "tags": list(entry.get("tags") or []),
            "metadata": dict(entry.get("metadata") or {}),
            "expectations": dict(entry.get("expectations") or {}),
            "request": request,
        })
    return manifest, cases


def directory_cases(input_dir):
    return [{
        "caseId": "file-%03d" % index,
        "path": os.path.join(input_dir, name),
        "source": name,
        "sha256": file_sha256(os.path.join(input_dir, name)),
        "tags": [], "metadata": {}, "expectations": {}, "request": {},
    } for index, name in enumerate(sorted(os.listdir(input_dir)), 1)
        if name.lower().endswith(".pdf") and os.path.isfile(os.path.join(input_dir, name))]


def expectation_checks(row, case):
    expected = case.get("expectations") or {}
    source = row.get("sourceMetrics") or {}
    review = row.get("reviewMetrics") or {}
    checks = []

    def add(check_id, passed, expected_value, actual_value):
        checks.append({"id": check_id, "passed": bool(passed),
                       "expected": expected_value, "actual": actual_value})

    if "sourcePages" in expected:
        add("source_pages", source.get("pages") == expected["sourcePages"],
            expected["sourcePages"], source.get("pages"))
    if expected.get("outputRequired") is True:
        add("output_available", row.get("outputAvailable") is True, True,
            bool(row.get("outputAvailable")))
    allowed_types = expected.get("allowedDocumentTypes")
    if isinstance(allowed_types, list) and allowed_types:
        add("document_type", source.get("documentType") in allowed_types,
            allowed_types, source.get("documentType"))
    if "maxRhythmOverflows" in expected:
        actual = review.get("rhythmOverflows")
        add("rhythm_overflows", isinstance(actual, int) and actual <= expected["maxRhythmOverflows"],
            "<= %s" % expected["maxRhythmOverflows"], actual)
    if expected.get("staticContentRequired") is True:
        actual = (row.get("staticContent") or {}).get("status")
        add("static_content", actual == "applied", "applied", actual)
    add("pipeline_did_not_crash", row.get("status") != "CRASHED",
        "not CRASHED", row.get("status"))
    return checks


def compare_with_baseline(results, baseline):
    previous = {row.get("caseId"): row for row in (baseline or {}).get("results", [])}
    comparisons = []
    for row in results:
        old = previous.get(row.get("caseId"))
        if not old:
            comparisons.append({"caseId": row.get("caseId"), "status": "new_case",
                                "regressions": [], "observations": []})
            continue
        regressions, observations = [], []
        if STATUS_RANK.get(row.get("status"), 0) < STATUS_RANK.get(old.get("status"), 0):
            regressions.append("pipeline_status_worsened")
        if old.get("outputAvailable") and not row.get("outputAvailable"):
            regressions.append("output_became_unavailable")
        new_failures = sorted(set(row.get("failureCategories") or []) -
                              set(old.get("failureCategories") or []))
        if new_failures:
            regressions.append("new_failure_categories:" + ",".join(new_failures))
        for key in ("measureCount", "noteEvents", "rhythmGaps", "rhythmOverflows"):
            before = (old.get("reviewMetrics") or {}).get(key)
            after = (row.get("reviewMetrics") or {}).get(key)
            if before != after:
                observations.append({"metric": key, "before": before, "after": after})
        comparisons.append({"caseId": row.get("caseId"),
                            "status": "regressed" if regressions else "no_regression",
                            "regressions": regressions, "observations": observations})
    return comparisons


def attach_evaluation(aggregate, cases, baseline=None):
    by_id = {case["caseId"]: case for case in cases}
    failed_expectations = 0
    for row in aggregate.get("results", []):
        checks = expectation_checks(row, by_id[row["caseId"]])
        row["expectationChecks"] = checks
        row["expectationsPassed"] = all(check["passed"] for check in checks)
        failed_expectations += sum(not check["passed"] for check in checks)
    comparisons = compare_with_baseline(aggregate.get("results", []), baseline) if baseline else []
    regression_count = sum(item["status"] == "regressed" for item in comparisons)
    aggregate["evaluation"] = {
        "expectationFailures": failed_expectations,
        "regressionCount": regression_count,
        "passed": failed_expectations == 0 and regression_count == 0,
        "baselineCompared": bool(baseline),
        "comparisons": comparisons,
    }
    return aggregate
