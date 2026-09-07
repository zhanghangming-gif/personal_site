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

from message_api import process_score_pdf, read_pipeline_report


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


def run(input_dir, output_dir, limit=0):
    os.makedirs(output_dir, exist_ok=True)
    paths = [
        os.path.join(input_dir, name) for name in sorted(os.listdir(input_dir))
        if name.lower().endswith(".pdf") and os.path.isfile(os.path.join(input_dir, name))
    ]
    if limit:
        paths = paths[:limit]
    aggregate = {"schemaVersion": 1, "startedAt": time.time(), "inputCount": len(paths), "results": []}
    summary_path = os.path.join(output_dir, "regression-report.json")
    for index, source in enumerate(paths, 1):
        stem = "%03d" % index
        workspace = os.path.join(output_dir, stem)
        os.makedirs(workspace, exist_ok=True)
        copied = os.path.join(workspace, "input.pdf")
        shutil.copyfile(source, copied)
        started = time.time()
        row = {"index": index, "name": os.path.basename(source), "workspace": stem}
        try:
            process_score_pdf(copied, workspace, 0, "auto")
            report = read_pipeline_report(workspace)
            pipeline = report.get("pipeline") or {}
            row.update({
                "status": pipeline.get("overallStatus", "UNKNOWN"),
                "stage": pipeline.get("stage", ""),
                "outputAvailable": os.path.isfile(os.path.join(workspace, "output.pdf")),
                "failureCategories": failure_categories(report),
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
    write_json(summary_path, aggregate)
    return aggregate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.input_dir, args.output_dir, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
