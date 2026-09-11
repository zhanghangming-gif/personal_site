"""Run the production score pipeline against a directory of PDF fixtures.

This is intentionally data-agnostic: filenames and known musical content are
never consulted. Each PDF receives an isolated workspace and the aggregate
report records only pipeline evidence, timings and failure categories.
Python 3.6 compatible.
"""
import argparse
import json
import os
import shutil
import time
import traceback

from message_api import (
    get_pdf_page_count,
    inspect_rendered_score_pdf, inspect_score_pdf, preflight_pdf,
    prepare_omr_variant, preserve_score_headers, process_score_pdf,
    read_pipeline_report, write_pipeline_report,
)
from score_benchmark import (attach_evaluation, directory_cases, load_manifest)


def write_json(path, payload):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def failure_categories(report):
    verification = report.get("verification") or {}
    categories = []
    for check in verification.get("checks") or []:
        if check.get("passed") is False and check.get("id"):
            categories.append(check["id"])
    repair = (verification.get("omr") or {}).get("multirestRepair") or {}
    if repair.get("unresolvedGaps"):
        categories.append("unresolved_structure_gap")
    return sorted(set(categories))


def safe_page_count(path):
    try:
        return get_pdf_page_count(path)
    except (OSError, RuntimeError, ValueError):
        return None


def run(input_dir, output_dir, limit=0, manifest_path=None, baseline_path=None,
        case_ids=None, resume=False):
    os.makedirs(output_dir, exist_ok=True)
    manifest, cases = (load_manifest(input_dir, manifest_path)
                       if manifest_path else (None, directory_cases(input_dir)))
    if case_ids:
        selected = set(case_ids)
        known = set(case["caseId"] for case in cases)
        unknown = sorted(selected - known)
        if unknown:
            raise ValueError("评测案例不存在：%s" % ", ".join(unknown))
        cases = [case for case in cases if case["caseId"] in selected]
    if limit:
        cases = cases[:limit]
    summary_path = os.path.join(output_dir, "regression-report.json")
    previous_results = []
    if resume and os.path.isfile(summary_path):
        with open(summary_path, encoding="utf-8") as stream:
            previous = json.load(stream)
        previous_results = previous.get("results") or []
        if not isinstance(previous_results, list):
            raise ValueError("续跑报告中的 results 不是数组")
    completed = {}
    for row in previous_results:
        case_id = row.get("caseId")
        if case_id and row.get("sourceSha256"):
            completed[case_id] = row
    aggregate = {"schemaVersion": 2, "startedAt": time.time(),
                 "inputCount": len(cases), "manifest": manifest_path,
                 "resumed": bool(resume), "results": []}
    for case in cases:
        existing = completed.get(case["caseId"])
        if existing and existing.get("sourceSha256") == case["sha256"]:
            aggregate["results"].append(existing)
    for index, case in enumerate(cases, 1):
        existing = completed.get(case["caseId"])
        if existing and existing.get("sourceSha256") == case["sha256"]:
            continue
        source = case["path"]
        stem = "%03d" % index
        workspace = os.path.join(output_dir, stem)
        if resume and os.path.exists(workspace):
            attempt = 1
            while os.path.exists(os.path.join(
                    output_dir, "%s-resume-%d" % (stem, attempt))):
                attempt += 1
            stem = "%s-resume-%d" % (stem, attempt)
            workspace = os.path.join(output_dir, stem)
        os.makedirs(workspace, exist_ok=True)
        copied = os.path.join(workspace, "input.pdf")
        shutil.copyfile(source, copied)
        started = time.time()
        row = {"index": index, "caseId": case["caseId"],
               "name": os.path.basename(source), "workspace": stem,
               "sourceSha256": case["sha256"], "tags": case["tags"],
               "metadata": case["metadata"]}
        try:
            prepared, preflight = preflight_pdf(copied, workspace)
            try:
                inspection = inspect_score_pdf(copied, workspace, preflight)
            except (RuntimeError, OSError, ValueError) as exc:
                inspection = {"status": "unavailable", "reason": str(exc)}
            omr_variant = None
            if (inspection.get("scoreProfile") or {}).get("documentType") in ("scan", "mixed"):
                try:
                    omr_variant, _variant_report = prepare_omr_variant(copied, workspace, 300)
                except (RuntimeError, OSError, ValueError):
                    omr_variant = None
            request = case.get("request") or {}
            output_pdf, _summary, verification = process_score_pdf(
                prepared, workspace, int(request.get("semitones", 0)),
                request.get("accidentalPreference", "auto"),
                source_instrument=request.get("sourceInstrument"),
                target_instrument=request.get("targetInstrument"),
                preflight=preflight, inspection=inspection, omr_variant=omr_variant)
            try:
                inspect_rendered_score_pdf(
                    output_pdf, workspace, (_summary or {}).get("outputPages") or 1)
                preserved_pdf, static_content = preserve_score_headers(
                    workspace, copied, output_pdf)
                if os.path.abspath(preserved_pdf) != os.path.abspath(output_pdf):
                    shutil.copyfile(preserved_pdf, output_pdf)
                static_content["status"] = "applied"
            except (RuntimeError, OSError, ValueError) as exc:
                static_content = {
                    "status": "skipped", "reason": str(exc),
                    "semanticVerification": False,
                }
            verification["staticContentPreservation"] = static_content
            current_report = read_pipeline_report(workspace)
            write_pipeline_report(
                workspace, current_report.get("pipeline") or {}, verification,
                current_report.get("artifacts") or {},
            )
            report = read_pipeline_report(workspace)
            pipeline = report.get("pipeline") or {}
            verification = report.get("verification") or {}
            omr = verification.get("omr") or {}
            decision = omr.get("recognitionDecision") or {}
            attempts = []
            for attempt in omr.get("recognitionAttempts") or []:
                metrics = attempt.get("metrics") or {}
                attempts.append({
                    "attemptId": attempt.get("attemptId"),
                    "selected": bool(attempt.get("selected")),
                    "representation": (attempt.get("input") or {}).get("representation"),
                    "noteEvents": metrics.get("noteEvents"),
                    "timelineGaps": metrics.get("timelineGaps"),
                    "timelineOverflows": metrics.get("timelineOverflows"),
                    "lineNumberCoverage": metrics.get("lineNumberCoverage"),
                })
            rhythm = verification.get("rhythmGapDetection") or {}
            # ``verification.summary`` is the human-readable review sentence.
            # Machine-readable counts live in ``verification.output``.  Keep the
            # regression runner tolerant of older reports that used a mapping in
            # ``summary`` so a completed pipeline is never mislabeled as crashed
            # merely while its metrics are being collected.
            output_metrics = verification.get("output") or {}
            if not isinstance(output_metrics, dict):
                output_metrics = {}
            legacy_summary = verification.get("summary") or {}
            if not isinstance(legacy_summary, dict):
                legacy_summary = {}
            row.update({
                "status": pipeline.get("overallStatus", "UNKNOWN"),
                "stage": pipeline.get("stage", ""),
                "outputAvailable": os.path.isfile(os.path.join(workspace, "output.pdf")),
                "failureCategories": failure_categories(report),
                "sourceMetrics": {
                    "pages": safe_page_count(copied),
                    "documentType": (inspection.get("scoreProfile") or {}).get("documentType"),
                },
                "staticContent": {
                    "status": static_content.get("status"),
                    "preservedPages": static_content.get("preservedPages"),
                },
                "recognition": {
                    "selectedAttemptId": decision.get("selectedAttemptId"),
                    "attempts": attempts,
                },
                "reviewMetrics": {
                    "rhythmGaps": rhythm.get("gapCount"),
                    "rhythmOverflows": rhythm.get("overflowCount"),
                    "measureCount": output_metrics.get("measures", legacy_summary.get("measures")),
                    "noteEvents": output_metrics.get("noteEvents", legacy_summary.get("notes")),
                },
            })
        except Exception as exc:
            row.update({
                "status": "CRASHED", "stage": "exception", "outputAvailable": False,
                "failureCategories": ["pipeline_exception"], "error": str(exc),
            })
            with open(os.path.join(workspace, "exception.log"), "w", encoding="utf-8") as stream:
                stream.write(traceback.format_exc())
        row["elapsedSeconds"] = round(time.time() - started, 3)
        aggregate["results"].append(row)
        write_json(summary_path, aggregate)
    aggregate["finishedAt"] = time.time()
    aggregate["counts"] = {
        status: sum(row.get("status") == status for row in aggregate["results"])
        for status in sorted(set(row.get("status") for row in aggregate["results"]))
    }
    baseline = None
    if baseline_path:
        with open(baseline_path, encoding="utf-8") as stream:
            baseline = json.load(stream)
    attach_evaluation(aggregate, cases, baseline)
    write_json(summary_path, aggregate)
    return aggregate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--manifest")
    parser.add_argument("--baseline")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        if not args.manifest:
            parser.error("--validate-only requires --manifest")
        manifest, cases = load_manifest(args.input_dir, args.manifest)
        result = {"schemaVersion": 1, "valid": True,
                  "benchmarkId": manifest.get("benchmarkId"),
                  "caseCount": len(cases), "caseIds": [case["caseId"] for case in cases]}
    else:
        result = run(args.input_dir, args.output_dir, args.limit,
                     args.manifest, args.baseline, args.case_id, args.resume)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
