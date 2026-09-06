"""Download provenance-recorded open scores and run Audiveris for annotation.

Source PDFs and scans remain in a private runtime directory.  They are not
copied into the Git repository or the exported COCO training archive.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pymupdf as fitz


USER_AGENT = "hangminglab-score-research/1.0"


def load_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def request_bytes(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pdf(source, destination):
    data = request_bytes(source["url"])
    if not data.startswith(b"%PDF"):
        raise RuntimeError("source did not return a PDF: %s" % source["id"])
    destination.write_bytes(data)


def loc_scan_pdf(source, destination):
    metadata = json.loads(request_bytes(source["url"]).decode("utf-8"))
    resources = metadata.get("resources") or []
    files = resources[0].get("files") if resources and isinstance(resources[0], dict) else []
    page_urls = []
    for variants in files or []:
        if not isinstance(variants, list):
            continue
        jpeg = next((item for item in variants if item.get("mimetype") == "image/jpeg" and
                     int(item.get("width") or 0) >= 1800 and int(item.get("width") or 0) <= 3000), None)
        if jpeg:
            page_urls.append(jpeg["url"])
    maximum = max(1, min(12, int(source.get("maxPages") or 5)))
    if not page_urls:
        raise RuntimeError("Library of Congress item has no usable page images")
    output = fitz.open()
    try:
        for url in page_urls[:maximum]:
            image = fitz.open(stream=request_bytes(url), filetype="jpeg")
            page_pdf = fitz.open("pdf", image.convert_to_pdf())
            output.insert_pdf(page_pdf)
            page_pdf.close(); image.close()
        output.save(str(destination), garbage=4, deflate=True)
    finally:
        output.close()


def newest_omr(folder):
    files = list(folder.rglob("*.omr"))
    return max(files, key=lambda item: item.stat().st_mtime) if files else None


def run_audiveris(source_pdf, omr_dir, command, timeout):
    omr_dir.mkdir(parents=True, exist_ok=True)
    args = list(command) + [
        "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
        "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true",
        "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.multiWholeHeadChords=true",
        "-batch", "-export", "-output", str(omr_dir), str(source_pdf),
    ]
    completed = subprocess.run(args, cwd=str(source_pdf.parent), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError("Audiveris failed: %s" % (completed.stdout or "")[-900:])
    generated = newest_omr(omr_dir)
    if generated is None:
        raise RuntimeError("Audiveris did not generate an OMR archive")
    target = omr_dir / "input.omr"
    if generated.resolve() != target.resolve():
        shutil.copyfile(str(generated), str(target))
    return target


def ingest(source, output, audiveris, timeout):
    if not re.fullmatch(r"[a-z0-9-]{3,100}", source.get("id", "")):
        raise ValueError("invalid source id")
    job = output / source["id"]
    job.mkdir(parents=True, exist_ok=True)
    pdf = job / "input.pdf"
    if not pdf.is_file():
        if source["kind"] == "pdf":
            download_pdf(source, pdf)
        elif source["kind"] == "loc_iiif":
            loc_scan_pdf(source, pdf)
        else:
            raise ValueError("unsupported source kind: %s" % source["kind"])
    document = fitz.open(str(pdf)); pages = len(document); document.close()
    provenance = dict(source, downloadedSha256=sha256(pdf), pages=pages,
                      sourcePdfStoredPrivately=True, includedInCocoExport=False)
    (job / "source.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    omr = job / "omr" / "input.omr"
    if not omr.is_file():
        run_audiveris(pdf, job / "omr", audiveris, timeout)
    return {"id": source["id"], "pages": pages, "sha256": provenance["downloadedSha256"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audiveris", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    sources = load_json(args.manifest)
    if not isinstance(sources, list):
        raise SystemExit("manifest must be an array")
    command = [args.audiveris]
    results = []
    for source in sources:
        print("processing %s" % source.get("id"), flush=True)
        try:
            results.append(dict(ingest(source, args.output.resolve(), command, args.timeout), status="ok"))
        except Exception as exc:
            results.append({"id": source.get("id"), "status": "failed", "error": str(exc)[-500:]})
            print("failed %s: %s" % (source.get("id"), exc), flush=True)
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
