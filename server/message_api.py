#!/usr/bin/env python3
"""Personal-site API: guestbook, analytics, runtime content and admin console."""

import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import smtplib
import sqlite3
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from fractions import Fraction
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from xml.etree import ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse, quote
from urllib.request import Request, urlopen


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_jobs import ScoreJobs, QueueFull
from score_agent_bridge import process_agent_score
from score_preflight_bridge import preflight_pdf
from score_page_selection_bridge import prepare_selected_pdf, validate_requested_pages
from score_inspection_bridge import (
    inspect_score_pdf, inspect_rendered_score_pdf, render_score_region,
    prepare_omr_variant,
)
from score_contracts import build_transposition_intent
from score_workspace import ScoreWorkspace
from score_render_plan import build_render_plan
from score_visual_audit import compare_visual_layout
from score_system_composer_bridge import compose_score_systems
from score_static_content_bridge import preserve_score_headers
from score_ai_review_bridge import run_ai_visual_review
from score_transposition import transpose_tree, pitch_number
from score_render_audit import compare_rendered_score, exported_layout
from score_source_audit import apply_pdf_anchors
from score_review import write_score_review, attach_review, build_source_repair_evidence
from score_ir import score_ir
from score_rhythm_gaps import detect_rhythm_gaps
from score_editor import (candidate_info, editor_data, apply_edits, report_text,
                          regular_file, carry_rest_review)
from score_source_versions import (assert_target_pitch_changes,
                                   canonical_source_musicxml,
                                   target_pitch_changes_to_source)
from score_auto_repair import (
    apply_safe_rhythm_repairs, validate_repair_result,
    validate_source_repair_result,
)
from score_omr_options import (
    recognition_families, recognition_risk, needs_alternative,
    recognition_attempt, recognition_decision, recognition_consensus,
)
from rest_annotation_admin import (
    build_training_archive, list_samples, load_excluded_document_hashes,
    refresh_samples, sample_image_path, update_sample,
)


DB_PATH = os.environ.get("MESSAGE_DB_PATH", "/var/lib/personal-site-messages/messages.db")
DATA_DIR = os.path.dirname(DB_PATH) or "."
CONTENT_PATH = os.environ.get("SITE_CONTENT_PATH", os.path.join(DATA_DIR, "site-content.json"))
UPLOAD_DIR = os.environ.get("SITE_UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
SCORE_DIR = os.environ.get("SCORE_WORK_DIR", os.path.join(DATA_DIR, "score-transpose"))
REST_ANNOTATION_DIR = os.environ.get(
    "REST_ANNOTATION_DIR", os.path.join(DATA_DIR, "rest-annotations", "review-v1"))
_REST_EXPORTER_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "rest_detector", "export_review_queue.py"),
    os.path.join(os.path.dirname(__file__), "ml", "rest_detector", "export_review_queue.py"),
)
REST_ANNOTATION_EXPORTER = os.environ.get(
    "REST_ANNOTATION_EXPORTER",
    next((path for path in _REST_EXPORTER_CANDIDATES if os.path.isfile(path)),
         _REST_EXPORTER_CANDIDATES[0]),
)
REST_ANNOTATION_PYTHON = os.environ.get(
    "REST_ANNOTATION_PYTHON", os.environ.get("SCORE_SKILL_PYTHON", "python3"))
_EVALUATION_MANIFEST_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(__file__)),
                 "benchmarks", "score-blind", "manifest.json"),
    os.path.join(os.path.dirname(__file__),
                 "benchmarks", "score-blind", "manifest.json"),
)
SCORE_EVALUATION_MANIFEST = os.environ.get(
    "SCORE_EVALUATION_MANIFEST",
    next((path for path in _EVALUATION_MANIFEST_CANDIDATES if os.path.isfile(path)),
         _EVALUATION_MANIFEST_CANDIDATES[0]))
HOST = os.environ.get("MESSAGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MESSAGE_PORT", "8787"))
IP_HASH_SALT = os.environ.get("MESSAGE_IP_HASH_SALT", "development-only-change-me")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
ADMIN_COOKIE = "__Host-zhm_admin_session"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions").strip()
PROFILE_CONTEXT_PATH = os.environ.get("PROFILE_CONTEXT_PATH", "/opt/personal-site-api/profile_context.json")
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER).strip()
SMTP_TLS = os.environ.get("SMTP_TLS", "ssl").strip().lower()
SENSITIVE_WORDS = [w.strip().lower() for w in os.environ.get(
    "SENSITIVE_WORDS", "赌博,博彩,代开发票,色情,裸聊,刷单,加微信,包赢,娱乐城"
).split(",") if w.strip()]
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ENTITY_RE = re.compile(r"^/api/(messages|replies)/([0-9a-f-]{36})/(likes|reports)$", re.I)
REPLY_RE = re.compile(r"^/api/messages/([0-9a-f-]{36})/replies$", re.I)
ADMIN_ENTITY_RE = re.compile(r"^/api/admin/(messages|replies)/([0-9a-f-]{36})$", re.I)
ADMIN_REST_SAMPLE_RE = re.compile(r"^/api/admin/rest-annotations/([0-9a-f]{24})$", re.I)
ADMIN_REST_IMAGE_RE = re.compile(r"^/api/admin/rest-annotations/([0-9a-f]{24})/image$", re.I)
SCORE_STATUS_RE = re.compile(r"^/api/score/transpositions/([0-9a-f-]{36})$", re.I)
SCORE_OUTPUT_RE = re.compile(r"^/api/score/transpositions/([0-9a-f-]{36})/output$", re.I)
SCORE_REVIEW_RE = re.compile(r"^/api/score/transpositions/([0-9a-f-]{36})/(candidate|review-report|editor|edits|retarget|musicxml|original|inspection|page-image|region-image)$", re.I)
INSTRUMENT_OFFSETS = {
    "concert_c": 0,
    "piccolo": 12,
    "clarinet_a": -3,
    "clarinet_bb": -2,
    "bass_clarinet_bb": -14,
    "trumpet_bb": -2,
    "soprano_sax_bb": -2,
    "tenor_sax_bb": -14,
    "sax_eb": -9,
    "baritone_sax_eb": -21,
    "horn_f": -7,
    "english_horn_f": -7,
}
STEP_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
PC_TO_FIFTHS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: 7, 5: -1, 10: -2, 3: -3, 8: -4}

PIPELINE_VERIFIED = "VERIFIED"
PIPELINE_VERIFIED_WITH_WARNINGS = "VERIFIED_WITH_WARNINGS"
PIPELINE_NEEDS_REVIEW = "NEEDS_REVIEW"
PIPELINE_REJECTED = "REJECTED"
PIPELINE_REPORT_NAME = "pipeline-report.json"
DOWNLOADABLE_PIPELINE_STATUSES = {
    PIPELINE_VERIFIED,
    PIPELINE_VERIFIED_WITH_WARNINGS,
}


class PipelineStatus:
    def __init__(
        self, stage, overall_status, fatal=False, warnings=None,
        output_allowed=False, fallback_used=False,
    ):
        self.stage = stage
        self.overall_status = overall_status
        self.fatal = bool(fatal)
        self.warnings = list(warnings or [])
        self.output_allowed = bool(output_allowed)
        self.fallback_used = bool(fallback_used)

    def to_dict(self):
        return {
            "stage": self.stage,
            "overallStatus": self.overall_status,
            "fatal": self.fatal,
            "warnings": list(self.warnings),
            "outputAllowed": self.output_allowed,
            "fallbackUsed": self.fallback_used,
        }


class PipelineRejected(RuntimeError):
    def __init__(self, message, pipeline_status=None):
        super().__init__(message)
        self.pipeline_status = pipeline_status or PipelineStatus(
            stage="rejected",
            overall_status=PIPELINE_REJECTED,
            fatal=True,
            warnings=[message],
            output_allowed=False,
        )


class UnsafeRepairError(RuntimeError):
    pass


def pipeline_report_path(job_dir):
    return os.path.join(job_dir, PIPELINE_REPORT_NAME)


def write_pipeline_report(job_dir, pipeline_status, verification=None, artifacts=None):
    os.makedirs(job_dir, exist_ok=True)
    payload = {
        "pipeline": pipeline_status.to_dict() if isinstance(pipeline_status, PipelineStatus) else pipeline_status,
        "verification": verification or {},
        "artifacts": artifacts or {},
        "updatedAt": utcnow(),
    }
    path = pipeline_report_path(job_dir)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)
    return payload


def read_pipeline_report(job_dir):
    try:
        with open(pipeline_report_path(job_dir), encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def score_output_authorization(job_dir):
    report = read_pipeline_report(job_dir)
    pipeline = report.get("pipeline") or {}
    status = str(pipeline.get("overallStatus") or "")
    allowed = bool(pipeline.get("outputAllowed")) and status in DOWNLOADABLE_PIPELINE_STATUSES
    if allowed:
        artifact = (report.get("artifacts") or {}).get("output") or {}
        expected = artifact.get("sha256")
        path = os.path.join(job_dir, "output.pdf")
        if expected and (not os.path.isfile(path) or file_sha256(path) != expected):
            return False, PIPELINE_REJECTED, "结果文件与校验记录不一致，请重新处理"
        return True, status, ""
    if not report:
        return False, PIPELINE_REJECTED, "结果缺少可信的流水线验证记录"
    return False, status or PIPELINE_REJECTED, "结果尚未通过可下载验证"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def add_column(db, table, declaration):
    name = declaration.split()[0]
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {declaration}")


def initialize_database():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(SCORE_DIR, exist_ok=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, nickname TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
          content TEXT NOT NULL, created_at TEXT NOT NULL, ip_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS replies (
          id TEXT PRIMARY KEY, message_id TEXT NOT NULL, nickname TEXT NOT NULL,
          content TEXT NOT NULL, created_at TEXT NOT NULL, ip_hash TEXT NOT NULL,
          FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS likes (
          entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, visitor_hash TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(entity_type, entity_id, visitor_hash)
        );
        CREATE TABLE IF NOT EXISTS site_stars (
          visitor_hash TEXT PRIMARY KEY, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rate_limits (action_key TEXT PRIMARY KEY, last_submit REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rate_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, actor_hash TEXT NOT NULL,
          entity_key TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rate_events ON rate_events(action, actor_hash, created_at);
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
          visitor_hash TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(entity_type, entity_id, visitor_hash)
        );
        CREATE TABLE IF NOT EXISTS admin_sessions (
          token_hash TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS page_views (
          id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, occurred_ts REAL NOT NULL,
          visitor_hash TEXT NOT NULL, session_hash TEXT NOT NULL, path TEXT NOT NULL,
          referrer_host TEXT NOT NULL DEFAULT '', device_type TEXT NOT NULL,
          browser TEXT NOT NULL, os TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_page_views_time ON page_views(occurred_ts);
        CREATE INDEX IF NOT EXISTS idx_page_views_path ON page_views(path);
        CREATE TABLE IF NOT EXISTS email_verifications (
          id TEXT PRIMARY KEY, visitor_hash TEXT NOT NULL, email_hash TEXT NOT NULL,
          code_hash TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, verified_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_email_verifications_lookup
          ON email_verifications(visitor_hash, email_hash, created_at);
        CREATE TABLE IF NOT EXISTS verified_identities (
          visitor_hash TEXT NOT NULL, email_hash TEXT NOT NULL, email TEXT NOT NULL,
          nickname TEXT NOT NULL DEFAULT '', verified_at TEXT NOT NULL,
          PRIMARY KEY(visitor_hash, email_hash)
        );
        """)
        for table in ("messages", "replies"):
            add_column(db, table, "status TEXT NOT NULL DEFAULT 'approved'")
            add_column(db, table, "report_count INTEGER NOT NULL DEFAULT 0")
        add_column(db, "messages", "pinned INTEGER NOT NULL DEFAULT 0")
        add_column(db, "messages", "email_verified INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE messages SET status='approved' WHERE status IS NULL OR status=''")
        db.execute("UPDATE replies SET status='approved' WHERE status IS NULL OR status=''")
        db.execute("DELETE FROM admin_sessions WHERE expires_at < ?", (utcnow(),))


def hash_value(value):
    return hmac.new(IP_HASH_SALT.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_password(password):
    try:
        scheme, iterations, salt, expected = ADMIN_PASSWORD_HASH.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def contains_sensitive(text):
    normalized = re.sub(r"\s+", "", text.lower())
    return any(word in normalized for word in SENSITIVE_WORDS)


def smtp_configured():
    return bool(SMTP_HOST and SMTP_FROM and (SMTP_USER or SMTP_TLS == "none"))


def send_verification_email(email, code):
    if not smtp_configured():
        raise RuntimeError("邮箱验证码服务尚未配置")
    message = EmailMessage()
    message["Subject"] = "张航铭个人网站留言邮箱验证码"
    message["From"] = SMTP_FROM
    message["To"] = email
    message.set_content(
        f"你的留言邮箱验证码是：{code}\n\n验证码 10 分钟内有效。"
        "\n如果不是你本人操作，可以忽略这封邮件。"
    )
    if SMTP_TLS == "starttls":
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=12) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
    elif SMTP_TLS == "none":
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=12) as server:
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
    else:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=12) as server:
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)


def parse_user_agent(ua):
    lower = ua.lower()
    if any(x in lower for x in ("bot", "spider", "crawler", "headless")):
        return "bot", "Bot", "Other"
    device = "mobile" if any(x in lower for x in ("mobile", "android", "iphone")) else "tablet" if "ipad" in lower else "desktop"
    browser = "Edge" if "edg/" in lower else "Chrome" if "chrome/" in lower else "Safari" if "safari/" in lower else "Firefox" if "firefox/" in lower else "WeChat" if "micromessenger" in lower else "Other"
    os_name = "Android" if "android" in lower else "iOS" if any(x in lower for x in ("iphone", "ipad")) else "Windows" if "windows" in lower else "macOS" if "mac os" in lower else "Linux" if "linux" in lower else "Other"
    return device, browser, os_name


def rate_allowed(db, action, actor, entity="", limit=1, window=10):
    cutoff = time.time() - window
    count = db.execute(
        "SELECT COUNT(*) FROM rate_events WHERE action=? AND actor_hash=? AND entity_key=? AND created_at>=?",
        (action, actor, entity, cutoff),
    ).fetchone()[0]
    if count >= limit:
        return False
    db.execute("INSERT INTO rate_events(action,actor_hash,entity_key,created_at) VALUES(?,?,?,?)", (action, actor, entity, time.time()))
    db.execute("DELETE FROM rate_events WHERE created_at < ?", (time.time() - 86400 * 2,))
    return True


def local_name(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def namespace_of(tag):
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def qname(parent, name):
    namespace = namespace_of(parent.tag)
    return "{%s}%s" % (namespace, name) if namespace else name


def child(element, name):
    for item in list(element):
        if local_name(item.tag) == name:
            return item
    return None


def child_text(element, name, default=""):
    item = child(element, name)
    return item.text.strip() if item is not None and item.text else default


def choose_spelling(pc, accidental_preference):
    candidates = []
    for step, base_pc in STEP_TO_PC.items():
        for alter in range(-2, 3):
            if (base_pc + alter) % 12 == pc:
                preference_cost = 0
                if accidental_preference == "flats" and alter > 0:
                    preference_cost = 2
                elif accidental_preference == "sharps" and alter < 0:
                    preference_cost = 2
                candidates.append((abs(alter) * 10 + preference_cost, step, alter))
    if not candidates:
        return "C", 0
    _, step, alter = sorted(candidates)[0]
    return step, alter


def transpose_pitch_values(step, alter, octave, semitones, accidental_preference):
    midi = pitch_number(step, alter, octave) + semitones
    new_pc = midi % 12
    new_step, new_alter = choose_spelling(new_pc, accidental_preference)
    return new_step, new_alter, (midi - STEP_TO_PC[new_step] - new_alter) // 12 - 1


def set_pitch_children(pitch, step, alter, octave):
    step_node = child(pitch, "step")
    if step_node is None:
        step_node = ET.SubElement(pitch, qname(pitch, "step"))
    step_node.text = step
    alter_node = child(pitch, "alter")
    if alter:
        if alter_node is None:
            alter_node = ET.Element(qname(pitch, "alter"))
            octave_node = child(pitch, "octave")
            children = list(pitch)
            insert_at = children.index(octave_node) if octave_node in children else len(children)
            pitch.insert(insert_at, alter_node)
        alter_node.text = str(alter)
    elif alter_node is not None:
        pitch.remove(alter_node)
    octave_node = child(pitch, "octave")
    if octave_node is None:
        octave_node = ET.SubElement(pitch, qname(pitch, "octave"))
    octave_node.text = str(octave)


def transpose_named_pitch(container, prefix, semitones, accidental_preference):
    step_node = child(container, "%s-step" % prefix)
    if step_node is None or not step_node.text:
        return
    alter_node = child(container, "%s-alter" % prefix)
    old_step = step_node.text.strip().upper()
    old_alter = int(float(alter_node.text)) if alter_node is not None and alter_node.text else 0
    new_step, new_alter = choose_spelling((STEP_TO_PC.get(old_step, 0) + old_alter + semitones) % 12, accidental_preference)
    step_node.text = new_step
    if new_alter:
        if alter_node is None:
            alter_node = ET.SubElement(container, qname(container, "%s-alter" % prefix))
        alter_node.text = str(new_alter)
    elif alter_node is not None:
        container.remove(alter_node)


def read_musicxml_root(input_path):
    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = None
            for item in container.iter():
                if local_name(item.tag) == "rootfile":
                    rootfile = item.attrib.get("full-path")
                    break
            if not rootfile:
                raise RuntimeError("MXL 文件缺少 MusicXML 根文件")
            return ET.fromstring(archive.read(rootfile))
    with open(input_path, "rb") as file:
        return ET.fromstring(file.read())


def transpose_musicxml(input_path, output_path, semitones, accidental_preference,
                       source_instrument=None, target_instrument=None):
    root = read_musicxml_root(input_path)
    namespace = namespace_of(root.tag)
    if namespace:
        ET.register_namespace("", namespace)
    try:
        summary = transpose_tree(root, semitones, accidental_preference, source_instrument, target_instrument)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    return summary


def midi_from_pitch(pitch):
    step = child_text(pitch, "step", "C").upper()
    return pitch_number(step, child_text(pitch, "alter", "0"), child_text(pitch, "octave", "4"))


def multiple_rest_value(measure):
    values = []
    for element in measure.iter():
        if local_name(element.tag) != "multiple-rest":
            continue
        try:
            values.append(max(1, int(float((element.text or "1").strip()))))
        except ValueError:
            values.append(1)
    return max(values or [1])


def set_multiple_rest_value(measure, value):
    changed = False
    for element in measure.iter():
        if local_name(element.tag) == "multiple-rest":
            element.text = str(max(1, int(value)))
            changed = True
    return changed


def measure_number_value(measure, fallback):
    return parse_measure_number_value(measure.attrib.get("number")) or fallback


def score_signature(musicxml_path):
    root = read_musicxml_root(musicxml_path)
    measure_numbers, line_start_numbers, expanded_measure_values, note_events = [], [], [], []
    part_index = -1
    for part in root.iter():
        if local_name(part.tag) != "part":
            continue
        part_index += 1
        measure_index = -1
        expanded_cursor = 1
        for measure in list(part):
            if local_name(measure.tag) != "measure":
                continue
            measure_index += 1
            measure_number = str(measure.attrib.get("number", measure_index + 1))
            measure_numbers.append("%s:%s" % (part_index, measure_number))
            numeric_measure = measure_number_value(measure, expanded_cursor)
            if part_index == 0:
                span = effective_measure_span(measure)
                expanded_measure_values.extend(range(numeric_measure, numeric_measure + span))
            if part_index == 0 and measure_index == 0:
                line_start_numbers.append(measure_number)
            for item in list(measure):
                if local_name(item.tag) == "print" and (item.attrib.get("new-system") == "yes" or item.attrib.get("new-page") == "yes"):
                    line_start_numbers.append(measure_number)
                    break
            expanded_cursor = numeric_measure + effective_measure_span(measure)
            for note in list(measure):
                if local_name(note.tag) != "note":
                    continue
                pitch = child(note, "pitch")
                if pitch is None:
                    continue
                note_events.append({
                    "part": part_index,
                    "measureIndex": measure_index,
                    "measureNumber": measure_number,
                    "midi": midi_from_pitch(pitch),
                })
    unique_measure_values = sorted(set(expanded_measure_values))
    timeline_continuous = bool(unique_measure_values) and unique_measure_values == list(
        range(unique_measure_values[0], unique_measure_values[-1] + 1)
    )
    return {
        "measureNumbers": measure_numbers,
        "lineStartNumbers": line_start_numbers,
        "expandedMeasureValues": expanded_measure_values,
        "measureCount": len(unique_measure_values) if unique_measure_values else len(measure_numbers),
        "timelineContinuous": timeline_continuous,
        "timelineStart": unique_measure_values[0] if unique_measure_values else None,
        "timelineEnd": unique_measure_values[-1] if unique_measure_values else None,
        "noteEvents": note_events,
        "noteCount": len(note_events),
    }


def parse_measure_number_value(value):
    cleaned = re.sub(r"[^0-9]", "", str(value or ""))
    if not cleaned:
        return None
    try:
        number = int(cleaned)
    except ValueError:
        return None
    return number if 0 < number < 10000 else None


def integer_ocr_consensus(values, minimum_votes=2):
    """Return a unique OCR majority without treating a failed pass as disagreement."""
    counts = {}
    for value in values:
        if type(value) is int:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None, False
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    winner, votes = ordered[0]
    tied = len(ordered) > 1 and ordered[1][1] == votes
    return (winner, True) if votes >= minimum_votes and not tied else (None, False)


def musicxml_timeline_risk(path):
    """Measure OMR completeness before choosing a recognition candidate.

    This is deliberately a detector, not a repair step. A timeline gap may be
    caused by a missed rest, note, tuplet or voice, so the result only triggers
    another recognition representation and keeps the candidate in review.
    """
    try:
        report = detect_rhythm_gaps(score_ir(read_musicxml_root(path), "omr-candidate"))
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        return {
            "status": "unavailable", "analyzedMeasures": 0,
            "gapCount": 0, "overflowCount": 0, "error": str(exc),
        }
    summary = report.get("summary") or {}
    return {
        "status": report.get("status"),
        "analyzedMeasures": int(summary.get("analyzedMeasures") or 0),
        "gapCount": int(summary.get("gapCount") or 0),
        "overflowCount": int(summary.get("overflowCount") or 0),
        "truncated": bool(summary.get("truncated")),
    }


def detect_multirest_visual_bar(image, left, right, staff_lines):
    """Find a flat multi-rest bar or an old-style rectangular rest group.

    The decision is deliberately geometric and scale-relative. Staff lines
    are ignored, and a candidate must keep nearly identical horizontal ends
    for several rows. Sloping beams therefore do not become evidence merely
    because they are thick. Musical-content checks and line-number arithmetic
    still decide whether the evidence may change MusicXML.
    """
    if image is None or right - left < 18 or len(staff_lines or []) < 2:
        return False
    lines = sorted(set(int(round(value)) for value in staff_lines))[:5]
    gaps = [b - a for a, b in zip(lines, lines[1:]) if b > a]
    if not gaps:
        return False
    spacing = sorted(gaps)[len(gaps) // 2]
    left = max(0, int(left))
    right = min(image.size[0], int(right))
    top = max(0, int(lines[0] - spacing * 0.25))
    bottom = min(image.size[1], int(lines[-1] + spacing * 0.25) + 1)
    minimum_run = max(12, int(spacing * 0.8))
    maximum_run = max(minimum_run, right - left - max(4, int(spacing * 0.45)))
    edge_margin = max(2, int(spacing * 0.12))
    def interior_stems(run, row_top, row_bottom):
        """Count note stems crossing a thick horizontal candidate.

        A multi-rest H bar has posts at its two ends. Beams have several note
        stems attached inside the beam. End posts are excluded by a
        staff-relative margin so the two shapes are not confused.
        """
        run_left, run_right = run
        margin = max(4, int(spacing * 0.50))
        scan_left, scan_right = run_left + margin, run_right - margin
        if scan_right <= scan_left:
            return 0
        required = max(6, int(spacing * 0.65))
        columns = []
        for x in range(scan_left, scan_right + 1):
            longest = current = 0
            for yy in range(top, bottom):
                if row_top <= yy <= row_bottom:
                    continue
                if image.getpixel((x, yy)) < 128:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 0
            if longest >= required:
                columns.append(x)
        groups = 0
        previous = None
        for x in columns:
            if previous is None or x > previous + 1:
                groups += 1
            previous = x
        return groups

    anchor = None
    consecutive = 0
    candidate_top = None
    for y in range(top, bottom):
        if any(abs(y - line) <= 2 for line in lines):
            continue
        runs = []
        start = None
        for x in range(left, right):
            black = image.getpixel((x, y)) < 128
            if black and start is None:
                start = x
            elif not black and start is not None:
                runs.append((start, x - 1))
                start = None
        if start is not None:
            runs.append((start, right - 1))
        runs = [
            run for run in runs
            if minimum_run <= run[1] - run[0] + 1 <= maximum_run
            and run[0] - left >= edge_margin and right - 1 - run[1] >= edge_margin
        ]
        current = max(runs, key=lambda run: run[1] - run[0], default=None)
        if current is not None and anchor is not None and current == anchor:
            consecutive += 1
        elif current is not None:
            consecutive = 1
            anchor = current
            candidate_top = y
        else:
            consecutive = 0
            anchor = None
            candidate_top = None
        if consecutive >= 5:
            candidate_bottom = y
            center_y = (candidate_top + candidate_bottom) / 2.0
            middle_line = lines[len(lines) // 2]
            # Multi-measure rest bars are centered on the staff. A flat beam
            # can satisfy the same run test, but normally sits near an outer
            # staff line and connects to note stems.
            centered = abs(center_y - middle_line) <= spacing
            if centered and interior_stems(anchor, candidate_top, candidate_bottom) == 0:
                return True
            consecutive = 0
            anchor = None
            candidate_top = None
    return False


def detect_boxed_number(image, marker, staff_spacing):
    """Confirm a numeric label surrounded by a printed rectangle.

    Boxed measure anchors occur throughout many orchestral parts. Requiring
    four raster edges avoids confusing tempo numbers, fingerings and rehearsal
    text with measure numbers.
    """
    if image is None or not marker or staff_spacing <= 0:
        return False
    try:
        x = int(marker.get("x")); y = int(marker.get("y"))
        width = max(1, int(marker.get("width") or 1))
        height = max(1, int(marker.get("height") or 1))
    except (TypeError, ValueError):
        return False

    def dark_ratio(points):
        usable = [(px, py) for px, py in points
                  if 0 <= px < image.size[0] and 0 <= py < image.size[1]]
        if not usable:
            return 0.0
        return sum(image.getpixel((px, py)) < 128 for px, py in usable) / float(len(usable))

    maximum_pad = max(4, int(round(staff_spacing * 0.8)))
    # Audiveris word bounds may enclose either the digits alone or the complete
    # box. Search a few pixels inside the reported bounds as well as outside.
    best = [0.0, 0.0, 0.0, 0.0]
    for pad in range(-3, maximum_pad + 1):
        left, right = x - pad, x + width - 1 + pad
        top, bottom = y - pad, y + height - 1 + pad
        if right <= left or bottom <= top:
            continue
        horizontal = range(left, right + 1)
        vertical = range(top, bottom + 1)
        ratios = (
            dark_ratio([(px, top) for px in horizontal]),
            dark_ratio([(px, bottom) for px in horizontal]),
            dark_ratio([(left, py) for py in vertical]),
            dark_ratio([(right, py) for py in vertical]),
        )
        best = [max(before, after) for before, after in zip(best, ratios)]
    # OCR bounds are frequently asymmetric around the surrounding rectangle,
    # so each edge may occur at a different offset.
    return min(best) >= 0.45


def analyze_audiveris_output(output):
    text = output or ""
    multirests = re.findall(r"Measure\{#([^}]+)\}\s+Multirest with no measure count", text)
    export_errors = sorted({
        int(value) for value in re.findall(r"Error visiting Measure\{#(\d+)\}", text)
    })
    line_numbers = []
    for match in re.finditer(r"Direction\}\s+([0-9][0-9'`.,\s]{0,10})(?:\n|$)", text):
        number = parse_measure_number_value(match.group(1))
        if number is not None:
            line_numbers.append(number)
    raw_pages = []
    for match in re.finditer(r"(\d+)\s+raw measures:\s+\[([^\]]+)\]", text):
        raw_pages.append({
            "rawMeasures": int(match.group(1)),
            "systems": [int(item) for item in re.findall(r"(\d+)\s+in system", match.group(2))],
        })
    ocr_issue = any(token in text for token in (
        "No installed OCR languages",
        "Missing support for 'eng'",
        "Could not initialize TessBaseAPI languages",
        "Tesseract couldn't load any languages",
    ))
    return {
        "ocrIssue": ocr_issue,
        "multirestMissing": multirests,
        "exportErrors": export_errors,
        "recognizedLineNumbers": sorted(set(line_numbers)),
        "rawPages": raw_pages,
    }


def analyze_audiveris_book(path):
    if not path or not zipfile.is_zipfile(path):
        return {"systems": [], "recognizedLineNumbers": [], "bookIssue": "Audiveris 工程文件不可用"}

    systems = []
    footer_lyrics = []
    tesseract = shutil.which("tesseract")
    try:
        from PIL import Image
    except ImportError:
        Image = None

    def crop_number(image, bounds, maximum, allow_multiple=False, psm="7"):
        if image is None or not tesseract or not bounds:
            return None
        left, top, right, bottom = bounds
        left = max(0, int(left))
        top = max(0, int(top))
        right = min(image.size[0], int(right))
        bottom = min(image.size[1], int(bottom))
        if right <= left or bottom <= top:
            return None
        crop = image.crop((left, top, right, bottom))
        crop = crop.resize((max(1, crop.size[0] * 5), max(1, crop.size[1] * 5)))
        payload = io.BytesIO()
        crop.save(payload, format="PNG")
        try:
            completed = subprocess.run(
                [
                    tesseract, "stdin", "stdout", "--psm", str(psm), "--dpi", "300",
                    "-c", "tessedit_char_whitelist=0123456789",
                ],
                input=payload.getvalue(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        values = re.findall(r"\d+", completed.stdout.decode("utf-8", "ignore"))
        if not values or (len(values) != 1 and not allow_multiple):
            return None
        try:
            value = int(values[0])
        except ValueError:
            return None
        return value if 0 < value <= maximum else None

    def increasing_indexes(page_systems):
        candidates = [
            (index, item.get("lineStartRaw"))
            for index, item in enumerate(page_systems)
            if item.get("lineStartRaw") is not None
        ]
        if not candidates:
            return set()
        best = []
        for position, (_, value) in enumerate(candidates):
            chain = [position]
            for previous in range(position):
                if candidates[previous][1] >= value:
                    continue
                previous_chain = best[previous]
                if len(previous_chain) + 1 > len(chain):
                    chain = previous_chain + [position]
            best.append(chain)
        selected = max(best, key=len)
        return {candidates[position][0] for position in selected}

    with zipfile.ZipFile(path) as archive:
        sheet_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", name)),
            key=lambda name: int(re.search(r"sheet#(\d+)", name).group(1)),
        )
        for page_index, name in enumerate(sheet_names, start=1):
            root = ET.fromstring(archive.read(name))
            binary_name = name.rsplit("/", 1)[0] + "/BINARY.png"
            page_image = None
            if Image is not None and binary_name in archive.namelist():
                try:
                    page_image = Image.open(io.BytesIO(archive.read(binary_name))).convert("L")
                except (OSError, ValueError):
                    page_image = None
            picture = next((item for item in root.iter() if local_name(item.tag) == "picture"), None)
            page_width = int(picture.attrib.get("width", "2480")) if picture is not None else 2480
            page_height = int(picture.attrib.get("height", "3507")) if picture is not None else 3507
            left_limit = max(170, int(page_width * 0.08))
            for lyric in root.iter():
                if local_name(lyric.tag) != "lyric-item":
                    continue
                bounds = child(lyric, "bounds")
                if bounds is None:
                    continue
                try:
                    y = int(float(bounds.attrib.get("y", "0")))
                except ValueError:
                    continue
                value = (lyric.attrib.get("value") or "").strip()
                if value and y >= int(page_height * 0.94):
                    footer_lyrics.append(value)
            page_systems = []
            for system_index, system in enumerate(
                (item for item in root.iter() if local_name(item.tag) == "system"), start=1
            ):
                line_candidates = []
                numeric_markers = []
                staff = next((item for item in system.iter() if local_name(item.tag) == "staff"), None)
                staff_left = int(float(staff.attrib.get("left", "0"))) if staff is not None else 0
                staff_points = [
                    point for point in staff.iter()
                    if local_name(point.tag) == "point" and point.attrib.get("y")
                ] if staff is not None else []
                staff_top = min(
                    (int(float(point.attrib["y"])) for point in staff_points), default=0
                )
                staff_lines = sorted(set(
                    int(round(float(point.attrib["y"]))) for point in staff_points
                ))[:5]
                line_limit = staff_left + max(48, int(page_width * 0.025))
                for word in system.iter():
                    if local_name(word.tag) != "word":
                        continue
                    raw_value = (word.attrib.get("value") or "").strip()
                    number = parse_measure_number_value(raw_value)
                    bounds = child(word, "bounds")
                    if number is None or bounds is None:
                        continue
                    try:
                        x = int(float(bounds.attrib.get("x", "99999")))
                        y = int(float(bounds.attrib.get("y", "99999")))
                        width = int(float(bounds.attrib.get("w", bounds.attrib.get("width", "0"))))
                        height = int(float(bounds.attrib.get("h", bounds.attrib.get("height", "0"))))
                    except ValueError:
                        continue
                    if staff_top and not (staff_top - 140 <= y <= staff_top + 30):
                        continue
                    marker = {
                        "value": number,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "kind": "word",
                    }
                    if x <= max(left_limit, line_limit):
                        line_candidates.append((x, number))
                    elif re.fullmatch(r"[0-9'`., ]+", raw_value):
                        numeric_markers.append(marker)
                for measure_count in system.iter():
                    if local_name(measure_count.tag) == "measure-count":
                        number = parse_measure_number_value(measure_count.attrib.get("value"))
                        bounds = child(measure_count, "bounds")
                        if number is None or bounds is None:
                            continue
                        try:
                            numeric_markers.append({
                                "value": number,
                                "x": int(float(bounds.attrib.get("x", "0"))),
                                "y": int(float(bounds.attrib.get("y", "0"))),
                                "width": int(float(bounds.attrib.get("w", bounds.attrib.get("width", "0")))),
                                "height": int(float(bounds.attrib.get("h", bounds.attrib.get("height", "0")))),
                                "kind": "measure-count",
                            })
                        except ValueError:
                            continue
                line_start = min(line_candidates)[1] if line_candidates else None
                stacks = [item for item in list(system) if local_name(item.tag) == "stack"]
                stack_details = []
                for stack in stacks:
                    try:
                        left = int(float(stack.attrib.get("left", "0")))
                        right = int(float(stack.attrib.get("right", str(left))))
                    except ValueError:
                        left, right = 0, 0
                    stack_details.append({
                        "left": left,
                        "right": right,
                        "width": max(0, right - left),
                        "duration": stack.attrib.get("duration", ""),
                        "special": stack.attrib.get("special", ""),
                        "multirestBar": detect_multirest_visual_bar(
                            page_image, left, right, staff_lines),
                    })
                page_systems.append({
                    "page": page_index,
                    "system": system_index,
                    "lineStart": line_start,
                    "lineStartRaw": line_start,
                    "staffLeft": staff_left,
                    "staffTop": staff_top,
                    "staffSpacing": (
                        sorted([b - a for a, b in zip(staff_lines, staff_lines[1:])
                                if b > a])[len(staff_lines) // 2 - 1]
                        if len(staff_lines) >= 2 else 0
                    ),
                    "imageWidth": page_width,
                    "imageHeight": page_height,
                    "staffCount": sum(1 for item in system.iter() if local_name(item.tag) == "staff"),
                    "rawMeasures": len([item for item in stacks if item.attrib.get("special") != "CAUTIONARY"]),
                    "specialMultirests": sum(item.attrib.get("special") == "MULTI_REST" for item in stacks),
                    "interiorNumbers": [item["value"] for item in numeric_markers],
                    "numberMarkers": numeric_markers,
                    "stacks": stack_details,
                })

            reliable_raw = increasing_indexes(page_systems)
            for index, item in enumerate(page_systems):
                if item.get("lineStartRaw") is not None and index in reliable_raw:
                    continue
                staff_left = item.get("staffLeft", 0)
                staff_top = item.get("staffTop", 0)
                if page_image is None or not staff_left or not staff_top:
                    continue
                values = []
                for psm in ("7", "11"):
                    value = crop_number(
                        page_image,
                        (staff_left - 85, staff_top - 110, staff_left + 70, staff_top - 6),
                        9999,
                        allow_multiple=True,
                        psm=psm,
                    )
                    if value is not None and value not in values:
                        values.append(value)
                if values:
                    item["lineStartOcr"] = values[0]
                    item["lineStartOcrCandidates"] = values

            for item in page_systems:
                rest_counts = []
                stacks = item.get("stacks") or []
                markers = item.get("numberMarkers") or []
                def near_staff_marker(marker):
                    return (
                        type(marker.get("value")) is int
                        and 1 < marker.get("value") <= 64
                        and (
                            marker.get("kind") == "measure-count"
                            or 0 <= item.get("staffTop", 0) - (
                                marker.get("y", 0) + marker.get("height", 0)
                            ) <= 60
                        )
                    )
                candidate_indexes = [
                    index for index, stack in enumerate(stacks)
                    if stack.get("special") == "MULTI_REST"
                    or (
                        (
                            stack.get("multirestBar")
                            or str(stack.get("duration", "")).strip() in ("0", "0/1")
                        )
                        and any(
                            stack.get("left", 0) - 8 <= marker.get("x", -1)
                            <= stack.get("right", 0) + 8
                            and near_staff_marker(marker)
                            for marker in markers
                        )
                    )
                ]
                for stack_index in candidate_indexes:
                    stack = stacks[stack_index]
                    marker = next((
                        candidate for candidate in markers
                        if stack.get("left", 0) - 8 <= candidate.get("x", -1)
                        <= stack.get("right", 0) + 8
                        and near_staff_marker(candidate)
                    ), None)
                    raw_value = marker.get("value") if marker else None
                    ocr_values = []
                    if page_image is not None and raw_value is None:
                        if marker:
                            x = marker.get("x", 0)
                            y = marker.get("y", 0)
                            width = marker.get("width", 0)
                            height = marker.get("height", 0)
                            ocr_bounds = (
                                x - 55,
                                y - 40,
                                x + width + 35,
                                min(item.get("staffTop", y + height + 10) - 4, y + height + 10),
                            )
                        elif stack.get("special") == "MULTI_REST":
                            center = (stack.get("left", 0) + stack.get("right", 0)) // 2
                            ocr_bounds = (
                                center - 75, item.get("staffTop", 0) - 135,
                                center + 75, item.get("staffTop", 0) - 5,
                            )
                        else:
                            ocr_bounds = (
                                stack.get("left", 0) - 12, item.get("staffTop", 0) - 140,
                                stack.get("right", 0) + 12, item.get("staffTop", 0) - 5,
                            )
                        # Music-font digits react differently to Tesseract page
                        # segmentation modes. A unique majority is stronger than
                        # requiring every successful mode to agree.
                        for psm in ("6", "7", "10", "11"):
                            candidate = crop_number(page_image, ocr_bounds, 64, psm=psm)
                            if candidate is not None:
                                ocr_values.append(candidate)
                    ocr_value, ocr_consensus = integer_ocr_consensus(ocr_values)
                    if ocr_value is None and ocr_values:
                        ocr_value = ocr_values[0]
                    value = raw_value
                    if ocr_consensus and ocr_value is not None and ocr_value >= 2 and (
                        raw_value is None
                        or len(str(ocr_value)) <= len(str(raw_value)) + 1
                    ):
                        value = ocr_value
                    if value is not None and 1 < value <= 64:
                        rest_counts.append({
                            "stackIndex": stack_index,
                            "value": value,
                            "rawValue": raw_value,
                            "ocrValue": ocr_value,
                            "ocrCandidates": ocr_values,
                            "ocrConsensus": ocr_consensus,
                            "geometry": (
                                "audiveris-multirest" if stack.get("special") == "MULTI_REST" else
                                "raster-multirest-bar" if stack.get("multirestBar") else
                                "printed-count-on-zero-duration-stack"
                            ),
                        })
                item["restCounts"] = rest_counts
                rest_span = {
                    int(row.get("stackIndex")): int(row.get("value"))
                    for row in rest_counts
                    if type(row.get("stackIndex")) is int
                    and type(row.get("value")) is int
                }
                boxed_anchors = []
                stacks = item.get("stacks") or []
                tolerance = max(8, int((item.get("staffSpacing") or 0) * 0.8))
                for marker in markers:
                    if marker.get("kind") not in ("word", "pdf-text"):
                        continue
                    if not detect_boxed_number(
                            page_image, marker, item.get("staffSpacing") or 0):
                        continue
                    marker_center = marker.get("x", 0) + marker.get("width", 0) / 2.0
                    candidates = [
                        (abs(marker_center - stack.get("left", 0)), position)
                        for position, stack in enumerate(stacks)
                    ]
                    if not candidates:
                        continue
                    distance, stack_index = min(candidates)
                    if distance > tolerance:
                        continue
                    prefix = sum(rest_span.get(position, 1)
                                 for position in range(stack_index))
                    line_start = int(marker["value"]) - prefix
                    if line_start <= 0:
                        continue
                    boxed_anchors.append({
                        "value": int(marker["value"]),
                        "stackIndex": stack_index,
                        "derivedLineStart": line_start,
                        "distanceToBoundary": distance,
                        "basis": "boxed-number-at-stack-boundary",
                    })
                item["boxedMeasureAnchors"] = boxed_anchors
                derived = sorted(set(row["derivedLineStart"] for row in boxed_anchors))
                if len(derived) == 1:
                    item["lineStartInterior"] = derived[0]
            systems.extend(page_systems)

    options = []
    for index, item in enumerate(systems):
        values = []
        if item.get("lineStartRaw") is not None:
            values.append((item["lineStartRaw"], 0))
        if item.get("lineStartInterior") is not None:
            values.append((item["lineStartInterior"], 1))
        ocr_values = list(item.get("lineStartOcrCandidates") or [])
        previous_raw = next((
            candidate.get("lineStartRaw") for candidate in reversed(systems[:index])
            if candidate.get("lineStartRaw") is not None
        ), None)
        next_raw = next((
            candidate.get("lineStartRaw") for candidate in systems[index + 1:]
            if candidate.get("lineStartRaw") is not None
            and (previous_raw is None or candidate.get("lineStartRaw") > previous_raw)
        ), None)
        for value in list(ocr_values):
            if value >= 10 or previous_raw is None or next_raw is None:
                continue
            candidate = previous_raw + 1
            while candidate < next_raw:
                if candidate % 10 == value and candidate not in ocr_values:
                    ocr_values.append(candidate)
                candidate += 1
        for value in ocr_values:
            values.append((value, 1))
        if index == 0 and item.get("lineStartRaw") is None:
            values.append((1, 0))
        unique_values = {}
        for value, penalty in values:
            unique_values[value] = min(penalty, unique_values.get(value, penalty))
        for value, penalty in unique_values.items():
            options.append((index, value, penalty))
    chains = []
    for position, (system_index, value, penalty) in enumerate(options):
        chain = ([position], 1, penalty, 0)
        for previous in range(position):
            previous_index, previous_value, _ = options[previous]
            if previous_index >= system_index or previous_value >= value:
                continue
            minimum_delta = sum(
                max(1, int(systems[index].get("rawMeasures", 1)) - 2)
                for index in range(previous_index, system_index)
            )
            if value - previous_value < minimum_delta:
                continue
            estimated_delta = 0
            for index in range(previous_index, system_index):
                system = systems[index]
                estimated_span = int(system.get("rawMeasures", 1))
                stacks = system.get("stacks") or []
                for detection in system.get("restCounts") or []:
                    stack_index = detection.get("stackIndex")
                    has_geometry = (
                        stack_index is not None
                        and stack_index < len(stacks)
                        and stacks[stack_index].get("special") == "MULTI_REST"
                    )
                    if detection.get("rawValue") is not None or has_geometry:
                        estimated_span += max(0, int(detection.get("value", 1)) - 1)
                estimated_delta += estimated_span
            deviation = abs((value - previous_value) - estimated_delta)
            previous_chain = chains[previous]
            candidate = (
                previous_chain[0] + [position],
                previous_chain[1] + 1,
                previous_chain[2] + penalty,
                previous_chain[3] + deviation,
            )
            if (candidate[1], -candidate[2], -candidate[3]) > (
                chain[1], -chain[2], -chain[3]
            ):
                chain = candidate
        chains.append(chain)
    if chains:
        selected = max(chains, key=lambda item: (item[1], -item[2], -item[3]))[0]
        selected_values = {options[position][0]: options[position][1] for position in selected}
        for index, item in enumerate(systems):
            item["lineStart"] = selected_values.get(index)
    if systems and systems[0].get("lineStartRaw") is None:
        systems[0]["lineStart"] = 1
    recognized = [item["lineStart"] for item in systems if item.get("lineStart") is not None]
    monotonic = all(after > before for before, after in zip(recognized, recognized[1:]))
    coverage = len(recognized) / max(1, len(systems))
    issue = ""
    has_rest_candidates = any(
        likely_merged_multirest_indexes(item) for item in systems
    )
    if coverage < 0.70 and has_rest_candidates:
        issue = "行首小节号识别覆盖不足"
    elif not monotonic:
        issue = "行首小节号不是严格递增序列"
    return {
        "systems": systems,
        "recognizedLineNumbers": recognized,
        "lineNumberCoverage": round(coverage, 3),
        "footerLyrics": sorted(set(footer_lyrics)),
        "bookIssue": issue,
    }


def recover_rest_counts_from_unresolved_gaps(path, omr_analysis, unresolved_gaps):
    """Run bounded OCR only on systems whose measure arithmetic did not close.

    Audiveris sometimes preserves an old-style multi-rest glyph and its stack
    while omitting the printed count from the project XML. Scanning every stack
    on every page is both slow and noisy, so this second pass is restricted to
    independently detected structural gaps. A count is only returned after a
    unique multi-pass OCR consensus; the repair layer still requires a rest-only
    MusicXML measure and compatible line-start arithmetic before applying it.
    """
    tesseract = shutil.which("tesseract")
    if not path or not zipfile.is_zipfile(path) or not tesseract:
        return []
    try:
        from PIL import Image
    except ImportError:
        return []
    targets = {
        (item.get("page"), item.get("system"))
        for item in (unresolved_gaps or [])
        if item.get("page") is not None and item.get("system") is not None
    }
    systems = {
        (item.get("page"), item.get("system")): item
        for item in (omr_analysis.get("systems") or [])
    }
    recovered = []
    with zipfile.ZipFile(path) as archive:
        images = {}
        for key in sorted(targets):
            system = systems.get(key)
            if not system:
                continue
            page, _ = key
            binary_name = "sheet#%s/BINARY.png" % page
            if binary_name not in archive.namelist():
                continue
            if page not in images:
                try:
                    images[page] = Image.open(io.BytesIO(archive.read(binary_name))).convert("L")
                except (OSError, ValueError):
                    images[page] = None
            image = images[page]
            staff_top = int(system.get("staffTop") or 0)
            if image is None or not staff_top:
                continue
            existing = {
                (item.get("stackIndex"), item.get("value"))
                for item in (system.get("restCounts") or [])
            }
            for stack_index, stack in enumerate(system.get("stacks") or []):
                if stack.get("special") == "CAUTIONARY":
                    continue
                left = max(0, int(stack.get("left", 0)) - 8)
                right = min(image.size[0], int(stack.get("right", left)) + 8)
                top = max(0, staff_top - 110)
                bottom = min(image.size[1], staff_top - 4)
                if right - left < 12 or bottom <= top:
                    continue
                crop = image.crop((left, top, right, bottom))
                crop = crop.resize((max(1, crop.size[0] * 5), max(1, crop.size[1] * 5)))
                payload = io.BytesIO()
                crop.save(payload, format="PNG")
                values = []
                for psm in ("6", "7", "10"):
                    try:
                        completed = subprocess.run(
                            [tesseract, "stdin", "stdout", "--psm", psm, "--dpi", "300",
                             "-c", "tessedit_char_whitelist=0123456789"],
                            input=payload.getvalue(), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=4,
                        )
                    except (OSError, subprocess.SubprocessError):
                        continue
                    matches = re.findall(r"\d+", completed.stdout.decode("utf-8", "ignore"))
                    if len(matches) == 1:
                        value = int(matches[0])
                        if 1 < value <= 64:
                            values.append(value)
                value, consensus = integer_ocr_consensus(values)
                if not consensus or (stack_index, value) in existing:
                    continue
                detection = {
                    "stackIndex": stack_index,
                    "value": value,
                    "rawValue": None,
                    "ocrValue": value,
                    "ocrCandidates": values,
                    "ocrConsensus": True,
                    "geometry": "targeted-rhythm-gap-ocr",
                }
                system.setdefault("restCounts", []).append(detection)
                existing.add((stack_index, value))
                recovered.append(dict(detection, page=page, system=key[1]))
    return recovered


def sanitize_audiveris_book(source_path, output_path):
    """Remove malformed relations that make Audiveris skip whole measures on export.

    A ChordGraceRelation is only valid between a normal chord and a small chord.
    Some dense scores produce small-to-small or normal-to-normal relations; Audiveris
    then raises ClassCastException while exporting and silently omits the measure.
    """
    removed = 0
    with zipfile.ZipFile(source_path) as source, zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", info.filename):
                root = ET.fromstring(payload)
                for parent in root.iter():
                    for node in list(parent):
                        name = local_name(node.tag)
                        has_wedge_relation = name == "relation" and any(
                            local_name(item.tag) == "chord-wedge" for item in node.iter()
                        )
                        if name == "wedge" or has_wedge_relation:
                            parent.remove(node)
                            removed += 1
                for sig in (node for node in root.iter() if local_name(node.tag) == "sig"):
                    inters = next((node for node in list(sig) if local_name(node.tag) == "inters"), None)
                    relations = next((node for node in list(sig) if local_name(node.tag) == "relations"), None)
                    if inters is None or relations is None:
                        continue
                    inter_types = {
                        node.attrib.get("id"): local_name(node.tag)
                        for node in list(inters) if node.attrib.get("id")
                    }
                    contained_by = {}
                    for relation in list(relations):
                        if any(local_name(node.tag) == "containment" for node in relation.iter()):
                            contained_by[relation.attrib.get("target")] = relation.attrib.get("source")
                    for inter in list(inters):
                        shape = inter.attrib.get("shape", "")
                        container_type = inter_types.get(contained_by.get(inter.attrib.get("id")))
                        if (local_name(inter.tag) == "head" and shape.endswith("_SMALL")
                                and container_type == "head-chord"):
                            inter.attrib["shape"] = shape[:-6]
                            removed += 1
                    for relation in list(relations):
                        has_grace_relation = any(
                            local_name(node.tag) == "chord-grace" for node in relation.iter()
                        )
                        if not has_grace_relation:
                            continue
                        endpoint_types = {
                            inter_types.get(relation.attrib.get("source")),
                            inter_types.get(relation.attrib.get("target")),
                        }
                        if endpoint_types != {"head-chord", "small-chord"}:
                            relations.remove(relation)
                            removed += 1
                payload = b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
            target.writestr(info, payload)
    return removed


def first_part_measures(root):
    for part in root.iter():
        if local_name(part.tag) == "part":
            return [item for item in list(part) if local_name(item.tag) == "measure"]
    return []


def score_parts(root):
    return [item for item in root.iter() if local_name(item.tag) == "part"]


def part_measures(part):
    return [item for item in list(part) if local_name(item.tag) == "measure"]


def musicxml_systems(root):
    systems, current = [], None
    for measure_index, measure in enumerate(first_part_measures(root)):
        new_page = False
        new_system = False
        for item in list(measure):
            if local_name(item.tag) != "print":
                continue
            new_page = item.attrib.get("new-page") == "yes"
            new_system = item.attrib.get("new-system") == "yes"
            break
        if current is None or (measure_index > 0 and (new_page or new_system)):
            if current is not None:
                systems.append(current)
            current = {"measureIndexes": [], "measures": []}
        current["measureIndexes"].append(measure_index)
        current["measures"].append(measure)
    if current is not None:
        systems.append(current)
    return systems


def normalize_musicxml_layout(root):
    """Keep every non-empty page credit produced by OMR.

    Credits contain more than the work title: part names, subtitles, composers,
    arrangers, copyright lines, running headers and printed page numbers all use
    the same MusicXML container.  Earlier code retained only a short allow-list
    on page one, which silently discarded valid static score content before
    MuseScore ever saw it.
    """
    for item in list(root):
        if local_name(item.tag) != "credit":
            continue
        words = [node for node in list(item) if local_name(node.tag) == "credit-words"]
        text = " ".join((node.text or "").strip() for node in words).strip()
        if not text:
            root.remove(item)




def remove_footer_ocr_lyrics(root, footer_values):
    normalized_values = {
        re.sub(r"\s+", " ", str(value or "")).strip().casefold()
        for value in (footer_values or []) if str(value or "").strip()
    }
    footer_words = {
        token.casefold()
        for value in normalized_values
        for token in re.findall(r"[A-Za-z0-9]+", value)
    }
    if not normalized_values:
        return 0
    removed = 0
    for note in (item for item in root.iter() if local_name(item.tag) == "note"):
        for lyric in [item for item in list(note) if local_name(item.tag) == "lyric"]:
            text_node = next((item for item in lyric.iter() if local_name(item.tag) == "text"), None)
            value = re.sub(r"\s+", " ", (text_node.text or "")).strip().casefold() if text_node is not None else ""
            try:
                default_y = float(lyric.attrib.get("default-y", "0"))
            except ValueError:
                default_y = 0
            tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", value)]
            footer_match = value in normalized_values or (tokens and all(token in footer_words for token in tokens))
            if default_y <= -100 and footer_match:
                note.remove(lyric)
                removed += 1
    return removed


def repair_final_fermata(root):
    measures = first_part_measures(root)
    if not measures:
        return False
    final_measure = measures[-1]
    terminal_bar = any(
        local_name(item.tag) == "barline"
        and item.attrib.get("location") == "right"
        and child_text(item, "bar-style") in ("light-heavy", "heavy-heavy")
        for item in list(final_measure)
    )
    pitched_notes = [
        item for item in list(final_measure)
        if local_name(item.tag) == "note" and child(item, "pitch") is not None
    ]
    if not terminal_bar or not pitched_notes:
        return False
    note = pitched_notes[-1]
    if child_text(note, "type") not in ("whole", "half"):
        return False
    notations = child(note, "notations")
    if notations is None or any(local_name(item.tag) == "fermata" for item in list(notations)):
        return False
    articulations = child(notations, "articulations")
    staccato = child(articulations, "staccato") if articulations is not None else None
    if staccato is None:
        return False
    articulations.remove(staccato)
    if not list(articulations):
        notations.remove(articulations)
    fermata = ET.SubElement(notations, qname(notations, "fermata"), {"type": "upright"})
    fermata.text = "normal"
    return True


def measure_is_empty(measure):
    meaningful = {"note", "backup", "forward", "harmony", "direction", "barline"}
    return not any(local_name(item.tag) in meaningful for item in list(measure))


def measure_is_barline_separator(measure):
    """Return true for an OMR-created measure that only carries barlines.

    Some recognizers split a double barline into a zero-duration stack and
    export it as its own MusicXML measure.  It is not semantically empty to the
    general XML helpers because the barline must normally be preserved.  The
    caller may remove it only when the OMR stack is zero-duration and adjacent
    printed measure numbers prove that it is a false measure boundary.
    """
    children = list(measure)
    return bool(children) and all(
        local_name(item.tag) in ("barline", "print") for item in children)


def measure_is_rest_only(measure):
    notes = [item for item in list(measure) if local_name(item.tag) == "note"]
    return bool(notes) and all(child(item, "rest") is not None for item in notes)


def measure_has_pitched_notes(measure):
    return any(
        local_name(item.tag) == "note" and child(item, "pitch") is not None
        for item in list(measure)
    )


def effective_measure_span(measure):
    return multiple_rest_value(measure) if measure_is_rest_only(measure) else 1


PROTECTED_ATTRIBUTE_NAMES = {
    "divisions", "key", "time", "clef", "transpose", "staves",
    "staff-details", "instruments", "part-symbol",
}


def protected_measure_attributes(measure):
    attributes = child(measure, "attributes")
    if attributes is None:
        return []
    return [
        item for item in list(attributes)
        if local_name(item.tag) in PROTECTED_ATTRIBUTE_NAMES
    ]


def normalized_rest_duration(measures, measure_index):
    measure = measures[measure_index]
    expected = active_measure_duration(measures, measure_index)
    durations = []
    for note in (item for item in list(measure) if local_name(item.tag) == "note"):
        if child(note, "rest") is None:
            return None
        try:
            durations.append(Fraction(int(float(child_text(note, "duration", "0"))), expected))
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return tuple(durations) if durations else None


def remove_malformed_multiple_rests(root):
    removals = []
    for part in score_parts(root):
        for measure in part_measures(part):
            if not measure_has_pitched_notes(measure):
                continue
            for parent in measure.iter():
                for node in list(parent):
                    if local_name(node.tag) == "multiple-rest":
                        removals.append((parent, node))
    for parent, node in removals:
        parent.remove(node)
    return len(removals)


def remove_measure_indexes(root, indexes):
    indexes = sorted(set(indexes), reverse=True)
    parts = score_parts(root)
    if not parts:
        return False
    for part in parts:
        measures = part_measures(part)
        for index in indexes:
            if index < 0 or index >= len(measures):
                return False
            measure = measures[index]
            if measure_has_pitched_notes(measure) or protected_measure_attributes(measure):
                return False
    for part in parts:
        measures = part_measures(part)
        for index in indexes:
            part.remove(measures[index])
    return True


def merge_measure_indexes(root, indexes):
    indexes = sorted(set(indexes), reverse=True)
    parts = score_parts(root)
    if not parts:
        return False
    for part in parts:
        measures = part_measures(part)
        if any(index <= 0 or index >= len(measures) for index in indexes):
            return False
    for index in indexes:
        for part in parts:
            measures = part_measures(part)
            target = measures[index - 1]
            source = measures[index]
            for node in [item for item in list(target) if local_name(item.tag) == "barline"]:
                if node.attrib.get("location") == "right":
                    target.remove(node)
            for node in list(source):
                name = local_name(node.tag)
                if name == "print":
                    continue
                if name == "barline" and node.attrib.get("location") == "left":
                    continue
                source.remove(node)
                target.append(node)
            part.remove(source)
    return True


def duration_fraction(value):
    try:
        return Fraction(str(value or "0"))
    except (ValueError, ZeroDivisionError):
        return Fraction(0, 1)


def likely_false_split_positions(omr_system):
    stacks = [
        item for item in (omr_system.get("stacks") or [])
        if item.get("special") != "CAUTIONARY"
    ]
    durations = [duration_fraction(item.get("duration")) for item in stacks]
    nonzero = [item for item in durations if item > 0]
    if len(nonzero) < 3:
        return []
    frequency = {}
    for value in nonzero:
        frequency[value] = frequency.get(value, 0) + 1
    nominal = max(frequency, key=lambda item: (frequency[item], item))
    widths = sorted(item.get("width", 0) for item in stacks if item.get("width", 0) > 0)
    if not widths or nominal <= 0:
        return []
    median_width = widths[len(widths) // 2]
    candidates = []
    for index in range(len(stacks) - 1):
        left_duration = durations[index]
        right_duration = durations[index + 1]
        if not (0 < left_duration < nominal and 0 < right_duration < nominal):
            continue
        combined_duration = left_duration + right_duration
        if not nominal * Fraction(4, 5) <= combined_duration <= nominal * Fraction(4, 3):
            continue
        left_width = stacks[index].get("width", 0)
        right_width = stacks[index + 1].get("width", 0)
        if not left_width or not right_width:
            continue
        if min(left_width, right_width) > median_width * 0.78:
            continue
        if left_width + right_width > median_width * 1.75:
            continue
        candidates.append(index + 1)
    return candidates


def collapse_expanded_multirests(root):
    measures = first_part_measures(root)
    remove_indexes = []
    collapsed = []
    index = 0
    while index < len(measures):
        measure = measures[index]
        count = multiple_rest_value(measure)
        if count <= 1 or index + count > len(measures):
            index += 1
            continue
        following = measures[index + 1:index + count]
        if not measure_is_rest_only(measure) or not all(measure_is_rest_only(item) for item in following):
            index += 1
            continue
        first_number = parse_measure_number_value(measure.attrib.get("number"))
        following_numbers = [parse_measure_number_value(item.attrib.get("number")) for item in following]
        if first_number is None or following_numbers != list(range(first_number + 1, first_number + count)):
            index += 1
            continue
        for part in score_parts(root):
            candidates = part_measures(part)
            if index + count > len(candidates):
                raise UnsafeRepairError("多声部多小节休止长度不一致")
            group = candidates[index:index + count]
            if multiple_rest_value(group[0]) != count:
                raise UnsafeRepairError("多声部多小节休止计数不一致")
            if any(measure_has_pitched_notes(item) or not measure_is_rest_only(item) for item in group):
                raise UnsafeRepairError("多声部多小节休止范围内存在音符")
            if any(protected_measure_attributes(item) for item in group[1:]):
                raise UnsafeRepairError("多小节休止占位小节包含受保护 attributes")
            starts_new_system = any(
                any(
                    local_name(item.tag) == "print"
                    and (item.attrib.get("new-system") == "yes" or item.attrib.get("new-page") == "yes")
                    for item in list(candidate)
                )
                for candidate in group[1:]
            )
            if starts_new_system:
                raise UnsafeRepairError("多小节休止跨越了原始系统边界")
            durations = [normalized_rest_duration(candidates, position) for position in range(index, index + count)]
            if not durations[0] or any(value != durations[0] for value in durations[1:]):
                raise UnsafeRepairError("多声部多小节休止时值不一致")
        remove_indexes.extend(range(index + 1, index + count))
        collapsed.append({"measure": first_number, "multipleRest": count, "removedPlaceholders": count - 1})
        index += count
    if remove_indexes and not remove_measure_indexes(root, remove_indexes):
        raise UnsafeRepairError("多小节休止折叠会删除音符或受保护 attributes")
    return collapsed


def ensure_multiple_rest_value(measure, value):
    if set_multiple_rest_value(measure, value):
        return
    attributes = child(measure, "attributes")
    if attributes is None:
        attributes = ET.Element(qname(measure, "attributes"))
        insert_at = 1 if list(measure) and local_name(list(measure)[0].tag) == "print" else 0
        measure.insert(insert_at, attributes)
    measure_style = child(attributes, "measure-style")
    if measure_style is None:
        measure_style = ET.SubElement(attributes, qname(attributes, "measure-style"))
    multiple_rest = ET.SubElement(measure_style, qname(measure_style, "multiple-rest"))
    multiple_rest.text = str(max(1, int(value)))


def active_measure_duration(measures, stop_index):
    divisions, beats, beat_type = 1, 4, 4
    for measure in measures[:stop_index + 1]:
        attributes = child(measure, "attributes")
        if attributes is None:
            continue
        divisions_text = child_text(attributes, "divisions", "")
        if divisions_text:
            try:
                divisions = max(1, int(float(divisions_text)))
            except ValueError:
                pass
        time_node = child(attributes, "time")
        if time_node is not None:
            try:
                beats = max(1, int(float(child_text(time_node, "beats", str(beats)))))
                beat_type = max(1, int(float(child_text(time_node, "beat-type", str(beat_type)))))
            except ValueError:
                pass
    return max(1, int(round(divisions * beats * 4 / beat_type)))


def ensure_measure_rest_note(measure, duration_value):
    if any(local_name(item.tag) == "note" for item in list(measure)):
        return
    note = ET.SubElement(measure, qname(measure, "note"))
    ET.SubElement(note, qname(note, "rest"), {"measure": "yes"})
    duration = ET.SubElement(note, qname(note, "duration"))
    duration.text = str(duration_value)
    voice = ET.SubElement(note, qname(note, "voice"))
    voice.text = "1"


def set_multirest_at_index(root, measure_index, value):
    parts = score_parts(root)
    if not parts:
        return False
    for part in parts:
        measures = part_measures(part)
        if measure_index >= len(measures) or measure_has_pitched_notes(measures[measure_index]):
            return False
    for part in parts:
        measures = part_measures(part)
        duration = active_measure_duration(measures, measure_index)
        ensure_multiple_rest_value(measures[measure_index], value)
        ensure_measure_rest_note(measures[measure_index], duration)
    return True


def insert_rest_measures_after(root, after_measure, count, multiple_rest_count=None):
    inserted = []
    first_measures = first_part_measures(root)
    try:
        measure_index = first_measures.index(after_measure)
    except ValueError:
        return None
    parts = score_parts(root)
    if not parts:
        return None
    for part in parts:
        measures = part_measures(part)
        if measure_index >= len(measures):
            return None
    for part_index, part in enumerate(parts):
        measures = part_measures(part)
        reference = measures[measure_index]
        part_children = list(part)
        insert_at = part_children.index(reference) + 1
        duration_value = active_measure_duration(measures, measure_index)
        for offset in range(max(0, int(count))):
            measure = ET.Element(qname(reference, "measure"), {"number": reference.attrib.get("number", "1")})
            if offset == 0 and multiple_rest_count:
                attributes = ET.SubElement(measure, qname(measure, "attributes"))
                measure_style = ET.SubElement(attributes, qname(attributes, "measure-style"))
                multiple_rest = ET.SubElement(measure_style, qname(measure_style, "multiple-rest"))
                multiple_rest.text = str(max(1, int(multiple_rest_count)))
            ensure_measure_rest_note(measure, duration_value)
            part.insert(insert_at + offset, measure)
            if part_index == 0:
                inserted.append(measure)
    return inserted[0] if inserted else None


def insert_multirest_before(root, before_measure, value):
    first_measures = first_part_measures(root)
    try:
        measure_index = first_measures.index(before_measure)
    except ValueError:
        return None
    parts = score_parts(root)
    if not parts:
        return None
    for part in parts:
        measures = part_measures(part)
        if measure_index >= len(measures):
            return None
    inserted = None
    for part_index, part in enumerate(parts):
        measures = part_measures(part)
        reference = measures[measure_index]
        insert_at = list(part).index(reference)
        duration_value = active_measure_duration(measures, measure_index if measure_index == 0 else measure_index - 1)
        measure = ET.Element(qname(reference, "measure"), {"number": reference.attrib.get("number", "1")})
        for layout_node in [item for item in list(reference) if local_name(item.tag) == "print"]:
            reference.remove(layout_node)
            measure.append(layout_node)
        if measure_index == 0:
            reference_attributes = child(reference, "attributes")
            if reference_attributes is not None:
                measure.append(copy.deepcopy(reference_attributes))
        ensure_multiple_rest_value(measure, value)
        ensure_measure_rest_note(measure, duration_value)
        part.insert(insert_at, measure)
        if part_index == 0:
            inserted = measure
    return inserted


def remove_multiple_rest_nodes(measure):
    removed = 0
    for parent in measure.iter():
        for node in list(parent):
            if local_name(node.tag) == "multiple-rest":
                parent.remove(node)
                removed += 1
    return removed


def expand_multirests_for_rendering(root):
    expanded = []
    index = 0
    while True:
        measures = first_part_measures(root)
        if index >= len(measures):
            break
        measure = measures[index]
        count = effective_measure_span(measure)
        if count <= 1:
            index += 1
            continue
        for part in score_parts(root):
            candidates = part_measures(part)
            if index < len(candidates):
                remove_multiple_rest_nodes(candidates[index])
        insert_rest_measures_after(root, measure, count - 1)
        expanded.append({
            "measure": measure.attrib.get("number", ""),
            "multipleRest": count,
            "insertedPlaceholders": count - 1,
        })
        index += count
    renumber_musicxml_measures(root)
    return expanded


def estimated_last_system_measures(omr_analysis):
    raw_pages = omr_analysis.get("rawPages") or []
    if raw_pages and raw_pages[-1].get("systems"):
        return max(1, int(raw_pages[-1]["systems"][-1]))
    return 4


def renumber_musicxml_measures(root):
    for part in root.iter():
        if local_name(part.tag) != "part":
            continue
        cursor = 1
        measures = [item for item in list(part) if local_name(item.tag) == "measure"]
        for measure in measures:
            measure.attrib["number"] = str(cursor)
            cursor += effective_measure_span(measure)


def likely_merged_multirest_indexes(omr_system):
    stacks = omr_system.get("stacks") or []
    if not stacks:
        return []
    indexes = [
        index for index, stack in enumerate(stacks)
        if stack.get("special") == "MULTI_REST"
    ]
    indexes.extend(
        index for index, stack in enumerate(stacks)
        if str(stack.get("duration", "")).strip() in ("0", "0/1")
    )
    widths = sorted(stack.get("width", 0) for stack in stacks if stack.get("width", 0) > 0)
    if len(widths) >= 3:
        median = widths[len(widths) // 2]
        widest_index = max(range(len(stacks)), key=lambda index: stacks[index].get("width", 0))
        widest = stacks[widest_index].get("width", 0)
        if median and widest >= median * 1.65:
            indexes.append(widest_index)
    return list(dict.fromkeys(indexes))


def apply_verified_multirest_repairs(input_path, output_path, omr_analysis, unresolved_report=None):
    """Commit only uniquely constrained printed multirest counts.

    This fallback starts from the untouched OMR export. OCR-only counts are
    accepted only when bounded gap OCR, rest geometry, two independent line
    anchors and a unique structure equation all agree. Therefore an ambiguous
    gap elsewhere cannot roll back a proven rest or introduce a guessed rest.
    """
    root = read_musicxml_root(input_path)
    namespace = namespace_of(root.tag)
    if namespace:
        ET.register_namespace("", namespace)
    omr_systems = omr_analysis.get("systems") or []
    try:
        malformed = remove_malformed_multiple_rests(root)
        collapsed = collapse_expanded_multirests(root)
    except UnsafeRepairError:
        return {"changed": False, "safePartialOutput": False}
    xml_systems = musicxml_systems(root)
    if not omr_systems or len(omr_systems) != len(xml_systems):
        return {"changed": False, "safePartialOutput": False}

    selected_repairs = []
    removed_empty_separators = []
    repaired_system_indexes = set()
    for system_index, (omr_system, xml_system) in enumerate(zip(omr_systems, xml_systems)):
        current_start = omr_system.get("lineStart")
        next_start = (omr_systems[system_index + 1].get("lineStart")
                      if system_index + 1 < len(omr_systems) else None)
        if current_start is None or next_start is None or next_start <= current_start:
            continue
        next_system = omr_systems[system_index + 1]
        current_anchor = omr_system.get("lineStartPdf") or omr_system.get("lineStartRaw")
        next_anchor = next_system.get("lineStartPdf") or next_system.get("lineStartRaw")
        inferred_first_measure = (
            system_index == 0 and current_start == 1 and current_anchor is None)
        independent_line_anchors = (
            (current_anchor == current_start or inferred_first_measure)
            and next_anchor == next_start)
        proposals = []
        stacks = omr_system.get("stacks") or []
        for detection in omr_system.get("restCounts") or []:
            position = detection.get("stackIndex")
            value = detection.get("value")
            raw_value = detection.get("rawValue")
            ocr_value = detection.get("ocrValue")
            raw_confirmed = raw_value == value
            ocr_completed_leading_digit = (
                independent_line_anchors and type(ocr_value) is int and ocr_value == value
                and type(raw_value) is int and value >= 10
                and str(value).endswith(str(raw_value))
            )
            if (type(position) is not int or type(value) is not int
                    or not (raw_confirmed or ocr_completed_leading_digit)
                    or value < 2 or value > 64 or position >= len(xml_system["measures"])
                    or position >= len(stacks)
                    or stacks[position].get("special") != "MULTI_REST"):
                continue
            measure = xml_system["measures"][position]
            if not measure_is_rest_only(measure):
                continue
            delta = value - effective_measure_span(measure)
            if delta <= 0:
                # A count already present in MusicXML is supporting evidence,
                # not a separate repair choice. Including zero-delta choices
                # would make an otherwise unique subset appear ambiguous.
                continue
            proposals.append({
                "position": position, "value": value, "measure": measure,
                "delta": delta,
                "detection": detection,
                "evidence": ("printed-count+multirest-geometry+line-start-span"
                             if raw_confirmed else
                             "raster-count+printed-suffix+multirest-geometry+line-start-span"),
            })
        expected_span = next_start - current_start
        base_span = sum(effective_measure_span(measure) for measure in xml_system["measures"])
        exact_masks = []
        if len(proposals) <= 8:
            for mask in range(1, 1 << len(proposals)):
                span = base_span + sum(
                    proposal["delta"] for index, proposal in enumerate(proposals)
                    if mask & (1 << index)
                )
                if span == expected_span:
                    exact_masks.append(mask)
        chosen = ([
            proposal for index, proposal in enumerate(proposals)
            if exact_masks[0] & (1 << index)
        ] if len(exact_masks) == 1 else [])
        for proposal in chosen:
            measure_index = first_part_measures(root).index(proposal["measure"])
            if not set_multirest_at_index(root, measure_index, proposal["value"]):
                return {"changed": False, "safePartialOutput": False}
        for proposal in chosen:
            selected_repairs.append({
                "page": omr_system.get("page"), "system": omr_system.get("system"),
                "stackIndex": proposal["position"],
                "measure": proposal["measure"].attrib.get("number", ""),
                "multipleRest": proposal["value"],
                "rawValue": proposal["detection"].get("rawValue"),
                "ocrValue": proposal["detection"].get("ocrValue"),
                "reason": "休止数字、MULTI_REST 几何与前后行首小节号形成唯一解",
                "evidence": proposal["evidence"],
                "confidence": "high",
            })
        if chosen:
            repaired_system_indexes.add(system_index)

        # Audiveris sometimes merges a printed multi-rest and the following
        # notes into one ordinary stack. In that case replacing the populated
        # measure would destroy music; the rest must be inserted before it.
        # A double barline can simultaneously become an empty XML measure, so
        # insertion and removal are solved together against the printed line
        # starts. Nothing is committed unless that operation set is unique.
        current_xml_system = musicxml_systems(root)[system_index]
        merged_operations = []
        for detection in omr_system.get("restCounts") or []:
            position = detection.get("stackIndex")
            value = detection.get("value")
            if (type(position) is not int or type(value) is not int
                    or value < 2 or value > 64 or position >= len(stacks)):
                continue
            stack = stacks[position]
            if (stack.get("special") == "MULTI_REST"
                    or detection.get("geometry") not in (
                        "raster-multirest-bar", "targeted-rhythm-gap-ocr")
                    or not stack.get("multirestBar")):
                continue
            raw_confirmed = detection.get("rawValue") == value
            ocr_confirmed = (
                detection.get("ocrConsensus") is True
                and detection.get("ocrValue") == value)
            if not (raw_confirmed or ocr_confirmed):
                continue
            measures = current_xml_system["measures"]
            if not measures or position > len(measures):
                continue
            if position == len(measures):
                # A page-end multirest can survive in the OMR graph as a
                # cautionary stack while its MusicXML measure is omitted.
                measure = measures[-1]
                delta = value
                operation = "append"
            elif measure_is_rest_only(measures[position]):
                measure = measures[position]
                delta = value - effective_measure_span(measure)
                operation = "set"
            else:
                measure = measures[position]
                delta = value
                operation = "insert"
            if delta <= 0:
                continue
            merged_operations.append({
                "kind": operation, "position": position, "measure": measure,
                "value": value, "delta": delta, "detection": detection,
            })

        for position, stack in enumerate(stacks):
            if (position >= len(current_xml_system["measures"])
                    or stack.get("special") in ("MULTI_REST", "CAUTIONARY")
                    or str(stack.get("duration", "")).strip() not in ("0", "0/1")):
                continue
            measure = current_xml_system["measures"][position]
            if ((measure_is_empty(measure) or measure_is_barline_separator(measure))
                    and not protected_measure_attributes(measure)):
                merged_operations.append({
                    "kind": "remove", "position": position, "measure": measure,
                    "value": None, "delta": -1, "detection": None,
                })

        merged_masks = []
        if independent_line_anchors and 0 < len(merged_operations) <= 10:
            current_span = sum(
                effective_measure_span(measure)
                for measure in current_xml_system["measures"])
            for mask in range(1, 1 << len(merged_operations)):
                selected = [
                    operation for index, operation in enumerate(merged_operations)
                    if mask & (1 << index)
                ]
                if not any(operation["kind"] in ("append", "insert", "set")
                           for operation in selected):
                    continue
                if current_span + sum(operation["delta"] for operation in selected) == expected_span:
                    merged_masks.append(mask)
        if len(merged_masks) == 1:
            merged_selected = [
                operation for index, operation in enumerate(merged_operations)
                if merged_masks[0] & (1 << index)
            ]
            # Keep every reference alive until insert/set operations finish.
            # A zero-duration separator can also be the visual anchor for a
            # multi-rest count; deleting it first would invalidate that anchor.
            for operation in sorted(
                    (item for item in merged_selected if item["kind"] != "remove"),
                    key=lambda item: item["position"], reverse=True):
                if operation["kind"] == "set":
                    measure_index = first_part_measures(root).index(operation["measure"])
                    changed = set_multirest_at_index(root, measure_index, operation["value"])
                    inserted = operation["measure"] if changed else None
                elif operation["kind"] == "append":
                    inserted = insert_rest_measures_after(
                        root, operation["measure"], 1,
                        multiple_rest_count=operation["value"])
                else:
                    inserted = insert_multirest_before(
                        root, operation["measure"], operation["value"])
                if inserted is None:
                    return {"changed": False, "safePartialOutput": False}
                detection = operation["detection"]
                selected_repairs.append({
                    "page": omr_system.get("page"), "system": omr_system.get("system"),
                    "stackIndex": operation["position"],
                    "measure": inserted.attrib.get("number", ""),
                    "multipleRest": operation["value"],
                    "rawValue": detection.get("rawValue"),
                    "ocrValue": detection.get("ocrValue"),
                    "inserted": operation["kind"] in ("append", "insert"),
                    "reason": "休止横杠、计数与前后行首小节跨度形成唯一结构解",
                    "evidence": ("printed-count" if detection.get("rawValue") == operation["value"]
                                 else "two-pass-raster-count")
                                + "+raster-multirest-bar+line-start-span",
                    "confidence": "high",
                })
            try:
                remove_indexes = sorted((
                    first_part_measures(root).index(operation["measure"])
                    for operation in merged_selected if operation["kind"] == "remove"
                ), reverse=True)
            except ValueError:
                return {"changed": False, "safePartialOutput": False}
            if remove_indexes and not remove_measure_indexes(root, remove_indexes):
                return {"changed": False, "safePartialOutput": False}
            for operation in merged_selected:
                if operation["kind"] == "remove":
                    removed_empty_separators.append({
                        "page": omr_system.get("page"),
                        "system": omr_system.get("system"),
                        "stackIndex": operation["position"],
                        "reason": "无音符的零时值谱格仅表示分隔线，并由行首跨度唯一确认",
                    })
            repaired_system_indexes.add(system_index)

        current_xml_system = musicxml_systems(root)[system_index]
        current_span = sum(
            effective_measure_span(measure)
            for measure in current_xml_system["measures"])
        missing = expected_span - current_span

        # A MULTI_REST object is already a semantic classification, even when
        # its printed number is absent from the OMR graph and every OCR pass
        # fails. With two independent line-start anchors and exactly one
        # unresolved rest-only MULTI_REST stack, the count has one equation:
        #
        # count = printed system span - span of all other measures.
        #
        # This recovers any 2..64 count without memorising a score or trusting
        # OCR alone. Multiple unknown multirests remain unresolved.
        structural_counts = []
        if missing > 0 and independent_line_anchors:
            for position, stack in enumerate(stacks):
                if (stack.get("special") != "MULTI_REST"
                        or position >= len(current_xml_system["measures"])):
                    continue
                measure = current_xml_system["measures"][position]
                existing_span = effective_measure_span(measure)
                inferred = expected_span - (current_span - existing_span)
                if (measure_is_rest_only(measure) and existing_span == 1
                        and 2 <= inferred <= 64 and inferred > existing_span):
                    structural_counts.append((position, measure, inferred))
        if len(structural_counts) == 1:
            position, measure, inferred = structural_counts[0]
            measure_index = first_part_measures(root).index(measure)
            if not set_multirest_at_index(root, measure_index, inferred):
                return {"changed": False, "safePartialOutput": False}
            selected_repairs.append({
                "page": omr_system.get("page"), "system": omr_system.get("system"),
                "stackIndex": position,
                "measure": measure.attrib.get("number", ""),
                "multipleRest": inferred,
                "rawValue": None, "ocrValue": None,
                "reason": "唯一 MULTI_REST 位置与前后行首小节号形成唯一结构解",
                "evidence": "audiveris-multirest+independent-line-start-span+unique-structural-equation",
                "confidence": "high",
            })
            repaired_system_indexes.add(system_index)
            current_xml_system = musicxml_systems(root)[system_index]
            current_span = sum(
                effective_measure_span(item)
                for item in current_xml_system["measures"])
            missing = expected_span - current_span

        merged_indexes = likely_merged_multirest_indexes(omr_system)
        printed_counts = [
            value for value in (omr_system.get("interiorNumbers") or [])
            if type(value) is int and 1 < value <= 64
        ]
        if (missing >= 2 and independent_line_anchors and printed_counts.count(missing) == 1
                and len(merged_indexes) == 1):
            merged_index = merged_indexes[0]
            reference = (current_xml_system["measures"][merged_index]
                         if merged_index < len(current_xml_system["measures"])
                         else current_xml_system["measures"][-1])
            inserted = (insert_multirest_before(root, reference, missing)
                        if merged_index < len(current_xml_system["measures"])
                        else insert_rest_measures_after(root, reference, 1, multiple_rest_count=missing))
            if inserted is None:
                return {"changed": False, "safePartialOutput": False}
            selected_repairs.append({
                "page": omr_system.get("page"), "system": omr_system.get("system"),
                "stackIndex": merged_index,
                "measure": inserted.attrib.get("number", ""),
                "multipleRest": missing,
                "rawValue": missing, "ocrValue": None, "inserted": True,
                "reason": "印刷休止数字、唯一宽谱表区域与前后行首小节号形成唯一解",
                "evidence": "printed-count+unique-wide-stack+independent-line-start-span",
                "confidence": "high",
            })
            repaired_system_indexes.add(system_index)
    if not selected_repairs:
        return {"changed": False, "safePartialOutput": False}

    verified_systems = musicxml_systems(root)
    if len(verified_systems) != len(omr_systems):
        return {"changed": False, "safePartialOutput": False}
    for system_index in repaired_system_indexes:
        current_start = omr_systems[system_index].get("lineStart")
        next_start = omr_systems[system_index + 1].get("lineStart")
        actual_span = sum(
            effective_measure_span(measure)
            for measure in verified_systems[system_index]["measures"]
        )
        if actual_span != next_start - current_start:
            return {"changed": False, "safePartialOutput": False}

    expanded = expand_multirests_for_rendering(root)
    normalize_musicxml_layout(root)
    removed_footer = remove_footer_ocr_lyrics(root, omr_analysis.get("footerLyrics"))
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    signature = score_signature(output_path)
    unresolved_report = unresolved_report or {}
    return {
        "changed": True,
        "valid": False,
        "fatal": False,
        "repairApplied": True,
        "safePartialOutput": True,
        "candidateContinued": True,
        "repairValidationStatus": "PARTIAL",
        "reason": unresolved_report.get("reason", "部分休止结构仍需人工确认"),
        "targetSpan": signature.get("measureCount"),
        "collapsed": collapsed,
        "removedMalformedMultirests": malformed,
        "expandedForRendering": expanded,
        "detectedRestCounts": selected_repairs,
        "partialRepairs": selected_repairs,
        "removedEmptySeparators": removed_empty_separators,
        "unresolvedGaps": unresolved_report.get("unresolvedGaps", []),
        "removedFooterLyrics": removed_footer,
    }


def repair_musicxml_structure(input_path, output_path, omr_analysis):
    root = read_musicxml_root(input_path)
    namespace = namespace_of(root.tag)
    if namespace:
        ET.register_namespace("", namespace)

    # Keep stable references to the untouched OMR export. Failed repair
    # attempts deliberately fall back to that file, so editor suggestions must
    # never point at indexes created by a partially mutated in-memory tree.
    original_measure_ids = {
        id(measure): "p1-m%s" % (index + 1)
        for index, measure in enumerate(first_part_measures(root))
    }

    def unresolved_gap(omr_system, xml_system, missing, reason, candidates=None):
        candidates = candidates or []
        candidate_rows = []
        for position, measure in candidates:
            measure_id = original_measure_ids.get(id(measure))
            if not measure_id:
                continue
            candidate_rows.append({
                "measureId": measure_id,
                "measureNumber": measure.attrib.get("number", ""),
                "positionInSystem": position + 1,
                "isRest": not measure_has_pitched_notes(measure),
            })
        system_rows = []
        for position, measure in enumerate(xml_system.get("measures", [])):
            measure_id = original_measure_ids.get(id(measure))
            if measure_id:
                system_rows.append({
                    "measureId": measure_id,
                    "measureNumber": measure.attrib.get("number", ""),
                    "positionInSystem": position + 1,
                })
        current_start = omr_system.get("lineStart")
        next_start = omr_system.get("nextLineStart")
        return {
            "id": "p%s-s%s" % (omr_system.get("page"), omr_system.get("system")),
            "status": "requires_human_confirmation",
            "page": omr_system.get("page"),
            "system": omr_system.get("system"),
            "lineStart": current_start,
            "nextLineStart": next_start,
            "expectedSpan": (next_start - current_start) if current_start is not None and next_start is not None else None,
            "recognizedSpan": sum(effective_measure_span(item) for item in xml_system.get("measures", [])),
            "missingMeasures": missing,
            "reason": reason,
            "contentKnown": False,
            "candidateMeasures": candidate_rows,
            "systemMeasures": system_rows,
            "allowedAction": "confirm_and_insert_whole_bar_rests",
        }

    omr_systems = omr_analysis.get("systems") or []
    try:
        malformed_multirests = remove_malformed_multiple_rests(root)
        collapsed = collapse_expanded_multirests(root)
    except UnsafeRepairError as exc:
        return {
            "changed": False,
            "valid": False,
            "fatal": True,
            "reason": str(exc),
            "repairValidationStatus": "FAILED",
        }
    xml_systems = musicxml_systems(root)
    if omr_analysis.get("bookIssue") or len(omr_systems) != len(xml_systems):
        return {
            "changed": False,
            "valid": False,
            "reason": omr_analysis.get("bookIssue") or "OMR 系统数量与 MusicXML 不一致",
            "systems": len(xml_systems),
            "omrSystems": len(omr_systems),
        }

    detected_rests = []
    ignored_rest_counts = []
    for system_index, (omr_system, xml_system) in enumerate(zip(omr_systems, xml_systems)):
        proposals = []
        for detection in omr_system.get("restCounts") or []:
            position = detection.get("stackIndex")
            value = detection.get("value")
            if position is None or value is None or position >= len(xml_system["measures"]):
                continue
            measure = xml_system["measures"][position]
            if measure_has_pitched_notes(measure):
                continue
            proposals.append({
                "detection": detection,
                "measure": measure,
                "value": value,
                "delta": value - effective_measure_span(measure),
            })

        current_start = omr_system.get("lineStart")
        next_start = (
            omr_systems[system_index + 1].get("lineStart")
            if system_index + 1 < len(omr_systems) else None
        )
        selected_indexes = set()
        if current_start is not None and next_start is not None and proposals:
            expected_span = next_start - current_start
            base_span = sum(effective_measure_span(measure) for measure in xml_system["measures"])
            best = (abs(base_span - expected_span), 0, 0)
            for mask in range(1, 1 << len(proposals)):
                span = base_span + sum(
                    proposal["delta"] for index, proposal in enumerate(proposals)
                    if mask & (1 << index)
                )
                evidence = sum(
                    2 if proposal["detection"].get("rawValue") is not None else 1
                    for index, proposal in enumerate(proposals)
                    if mask & (1 << index)
                )
                candidate = (abs(span - expected_span), -evidence, mask)
                if candidate[:2] < best[:2]:
                    best = candidate
            selected_indexes = {
                index for index in range(len(proposals)) if best[2] & (1 << index)
            }

        for proposal_index, proposal in enumerate(proposals):
            detection = proposal["detection"]
            measure = proposal["measure"]
            value = proposal["value"]
            if proposal_index not in selected_indexes:
                ignored_rest_counts.append({
                    "page": omr_system.get("page"),
                    "system": omr_system.get("system"),
                    "stackIndex": detection.get("stackIndex"),
                    "value": value,
                })
                continue
            measure_index = first_part_measures(root).index(measure)
            if not set_multirest_at_index(root, measure_index, value):
                return {
                    "changed": False,
                    "valid": False,
                    "fatal": True,
                    "reason": "多声部对应小节包含音符或索引不一致，不能安全设置多小节休止",
                    "repairValidationStatus": "FAILED",
                    "collapsed": collapsed,
                }
            detected_rests.append({
                "page": omr_system.get("page"),
                "system": omr_system.get("system"),
                "measure": measure.attrib.get("number", ""),
                "multipleRest": value,
                "rawValue": detection.get("rawValue"),
                "ocrValue": detection.get("ocrValue"),
                "reason": "原谱休止计数与行首小节跨度共同约束",
                "evidence": "printed-count" if detection.get("rawValue") is not None else "tesseract-ocr",
                "confidence": "high" if detection.get("rawValue") is not None else "medium",
            })
    xml_systems = musicxml_systems(root)

    removed_empty = []
    merged_false_splits = []
    for index, (omr_system, xml_system) in enumerate(zip(omr_systems, xml_systems)):
        current_start = omr_system.get("lineStart")
        next_start = omr_systems[index + 1].get("lineStart") if index + 1 < len(omr_systems) else None
        omr_system["nextLineStart"] = next_start
        if current_start is None or next_start is None:
            continue
        expected_span = next_start - current_start
        current_span = sum(effective_measure_span(measure) for measure in xml_system["measures"])
        excess = current_span - expected_span
        if excess <= 0:
            continue
        empty_indexes = [
            measure_index for measure_index, measure in zip(
                xml_system["measureIndexes"], xml_system["measures"]
            ) if measure_is_empty(measure)
        ]
        merge_indexes = []
        for position in likely_false_split_positions(omr_system):
            if position >= len(xml_system["measures"]):
                continue
            left_measure = xml_system["measures"][position - 1]
            right_measure = xml_system["measures"][position]
            if not (measure_has_pitched_notes(left_measure) and measure_has_pitched_notes(right_measure)):
                continue
            merge_indexes.append(xml_system["measureIndexes"][position])
        if len(empty_indexes) + len(merge_indexes) < excess:
            return {
                "changed": False,
                "valid": False,
                "reason": "第 %s 页第 %s 行比原谱多出 %s 个含内容小节" % (
                    omr_system.get("page"), omr_system.get("system"),
                    excess - len(empty_indexes) - len(merge_indexes)
                ),
                "collapsed": collapsed,
            }
        remove_count = min(excess, len(empty_indexes))
        removed_empty.extend(empty_indexes[:remove_count])
        remaining = excess - remove_count
        merged_false_splits.extend(merge_indexes[:remaining])
    operations = [
        (index, "remove") for index in removed_empty
    ] + [
        (index, "merge") for index in merged_false_splits
    ]
    for measure_index, operation in sorted(operations, reverse=True):
        if operation == "remove":
            operation_ok = remove_measure_indexes(root, [measure_index])
        else:
            operation_ok = merge_measure_indexes(root, [measure_index])
        if not operation_ok:
            return {
                "changed": False,
                "valid": False,
                "fatal": True,
                "reason": "结构修复会删除音符、受保护 attributes，或造成多声部不一致",
                "repairValidationStatus": "FAILED",
                "collapsed": collapsed,
            }
    if operations:
        xml_systems = musicxml_systems(root)

    repaired = []
    for index, (omr_system, xml_system) in enumerate(zip(omr_systems, xml_systems)):
        current_start = omr_system.get("lineStart")
        next_start = omr_systems[index + 1].get("lineStart") if index + 1 < len(omr_systems) else None
        if current_start is None or next_start is None:
            continue
        expected_span = next_start - current_start
        current_span = sum(effective_measure_span(measure) for measure in xml_system["measures"])
        if expected_span <= 0:
            return {
                "changed": False,
                "valid": False,
                "reason": "第 %s 页第 %s 行的小节号不是递增序列" % (
                    omr_system.get("page"), omr_system.get("system")
                ),
                "collapsed": collapsed,
            }
        missing = expected_span - current_span
        if missing < 0:
            return {
                "changed": False,
                "valid": False,
                "reason": "第 %s 页第 %s 行比原谱行首序号多出 %s 小节" % (
                    omr_system.get("page"), omr_system.get("system"), -missing
                ),
                "collapsed": collapsed,
            }
        if missing == 0:
            continue
        merged_indexes = likely_merged_multirest_indexes(omr_system)
        candidates = [
            (position, measure) for position, measure in enumerate(xml_system["measures"])
            if not measure_has_pitched_notes(measure)
        ]
        geometry_candidates = [
            item for item in candidates if item[0] in merged_indexes
        ]
        unresolved_geometry = [
            item for item in geometry_candidates if effective_measure_span(item[1]) == 1
        ]
        if len(unresolved_geometry) == 1:
            selected = unresolved_geometry[0]
        elif not unresolved_geometry and len(geometry_candidates) == 1:
            selected = geometry_candidates[0]
        else:
            selected = None
        if selected is None and (
            len(unresolved_geometry) > 1
            or (not unresolved_geometry and len(geometry_candidates) > 1)
        ):
            reason = "第 %s 页第 %s 行有多个未识别休止，无法唯一分配缺少的 %s 小节" % (
                omr_system.get("page"), omr_system.get("system"), missing
            )
            return {
                "changed": False,
                "valid": False,
                "reason": reason,
                "collapsed": collapsed,
                "detectedRestCounts": detected_rests,
                "unresolvedGaps": [unresolved_gap(
                    omr_system, xml_system, missing, reason,
                    unresolved_geometry or geometry_candidates,
                )],
            }
        if selected is not None:
            _, candidate = selected
            inferred = effective_measure_span(candidate) + missing
            old_number = candidate.attrib.get("number", "")
            measure_index = first_part_measures(root).index(candidate)
            if not set_multirest_at_index(root, measure_index, inferred):
                return {
                    "changed": False,
                    "valid": False,
                    "fatal": True,
                    "reason": "无法在所有声部原子应用推断出的多小节休止",
                    "repairValidationStatus": "FAILED",
                    "collapsed": collapsed,
                }
            repaired.append({
                "page": omr_system.get("page"),
                "system": omr_system.get("system"),
                "measure": old_number,
                "multipleRest": inferred,
                "addedMeasures": missing,
                "reason": "行首小节号跨度大于 MusicXML 当前跨度",
                "evidence": "line-start-and-rest-geometry",
                "confidence": "medium",
            })
            continue

        merged_index = next((
            position for position in merged_indexes
            if position >= len(xml_system["measures"])
            or effective_measure_span(xml_system["measures"][position]) == 1
        ), merged_indexes[0] if merged_indexes else None)
        printed_counts = omr_system.get("interiorNumbers") or []
        if missing in printed_counts and merged_index is not None:
            if merged_index >= len(xml_system["measures"]):
                inserted = insert_rest_measures_after(
                    root, xml_system["measures"][-1], 1, multiple_rest_count=missing
                )
            else:
                inserted = insert_multirest_before(
                    root, xml_system["measures"][merged_index], missing
                )
            if inserted is not None:
                repaired.append({
                    "page": omr_system.get("page"),
                    "system": omr_system.get("system"),
                    "measure": inserted.attrib.get("number", ""),
                    "multipleRest": missing,
                    "addedMeasures": missing,
                    "inserted": True,
                    "evidence": "printed-count",
                    "reason": "谱面印刷休止计数与缺失跨度一致",
                    "confidence": "high",
                    "attributesPolicy": "COPY_INITIAL" if first_part_measures(root).index(inserted) == 0 else "KEEP_ON_REFERENCE",
                })
                continue

        strong_leading_merge = merged_index == 0 and missing >= 2
        if strong_leading_merge:
            inserted = insert_multirest_before(root, xml_system["measures"][0], missing)
            if inserted is not None:
                repaired.append({
                    "page": omr_system.get("page"),
                    "system": omr_system.get("system"),
                    "measure": inserted.attrib.get("number", ""),
                    "multipleRest": missing,
                    "addedMeasures": missing,
                    "inserted": True,
                    "reason": "行首位置存在唯一的合并休止几何证据",
                    "evidence": "leading-rest-geometry",
                    "confidence": "medium",
                    "attributesPolicy": "COPY_INITIAL" if first_part_measures(root).index(inserted) == 0 else "KEEP_ON_REFERENCE",
                })
                continue

        reason = "第 %s 页第 %s 行缺少 %s 小节，但无法可靠定位休止位置" % (
            omr_system.get("page"), omr_system.get("system"), missing
        )
        return {
            "changed": False,
            "valid": False,
            "reason": reason,
            "collapsed": collapsed,
            "unresolvedGaps": [unresolved_gap(
                omr_system, xml_system, missing, reason,
                geometry_candidates or candidates,
            )],
        }

    renumber_musicxml_measures(root)
    numbered_systems = musicxml_systems(root)
    line_starts = [
        measure_number_value(system["measures"][0], 0)
        for system in numbered_systems
        if system.get("measures")
    ]
    expected_line_starts = [item.get("lineStart") for item in omr_systems]
    mismatched_line_starts = [
        (index, expected, line_starts[index] if index < len(line_starts) else None)
        for index, expected in enumerate(expected_line_starts)
        if expected is not None
        and (index >= len(line_starts) or line_starts[index] != expected)
    ]
    if mismatched_line_starts:
        return {
            "changed": False,
            "valid": False,
            "reason": "结构修复后行首序号仍不一致",
            "lineStartNumbers": line_starts,
            "expectedLineStartNumbers": expected_line_starts,
            "lineStartMismatches": mismatched_line_starts,
            "collapsed": collapsed,
            "detectedRestCounts": detected_rests,
            "repaired": repaired,
        }

    expanded_multirests = expand_multirests_for_rendering(root)
    normalize_musicxml_layout(root)
    removed_footer_lyrics = remove_footer_ocr_lyrics(root, omr_analysis.get("footerLyrics"))
    repaired_final_fermata = repair_final_fermata(root)
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    final_signature = score_signature(output_path)
    heuristic_repairs = []
    if repaired_final_fermata:
        heuristic_repairs.append({
            "repairType": "final_fermata_heuristic",
            "reason": "末小节终止线和末音形态符合现有启发式规则",
            "evidence": "musicxml-heuristic-only",
            "confidence": "low",
        })
    repair_applied = bool(
        collapsed or malformed_multirests or repaired or detected_rests
        or merged_false_splits or removed_empty or removed_footer_lyrics
        or repaired_final_fermata
    )
    return {
        "changed": bool(
            collapsed or expanded_multirests or malformed_multirests or repaired
            or detected_rests or merged_false_splits
            or removed_footer_lyrics or repaired_final_fermata
        ),
        "valid": True,
        "fatal": False,
        "repairApplied": repair_applied,
        "repairValidationStatus": "PASSED" if repair_applied else "NOT_NEEDED",
        "targetSpan": final_signature.get("measureCount"),
        "lineStartNumbers": line_starts,
        "collapsed": collapsed,
        "expandedForRendering": expanded_multirests,
        "removedMalformedMultirests": malformed_multirests,
        "removedEmptyMeasures": len(removed_empty),
        "mergedFalseSplitMeasures": len(merged_false_splits),
        "detectedRestCounts": detected_rests,
        "ignoredRestCounts": ignored_rest_counts,
        "removedFooterLyrics": removed_footer_lyrics,
        "repairedFinalFermata": repaired_final_fermata,
        "heuristicRepairs": heuristic_repairs,
        "repaired": repaired,
    }


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def score_artifact_descriptor(path, role):
    if not path or not os.path.exists(path):
        return {"role": role, "available": False}
    signature = score_signature(path)
    return {
        "role": role,
        "available": True,
        "fileName": os.path.basename(path),
        "sha256": file_sha256(path),
        "measures": signature.get("measureCount", 0),
        "noteEvents": signature.get("noteCount", 0),
        "timelineContinuous": signature.get("timelineContinuous", False),
    }


def pdf_artifact_descriptor(path, role="output"):
    if not path or not os.path.exists(path):
        return {"role": role, "available": False}
    return {
        "role": role,
        "available": True,
        "fileName": os.path.basename(path),
        "sha256": file_sha256(path),
        "size": os.path.getsize(path),
        "pages": get_pdf_page_count(path),
    }


def repair_was_applied(repair_report):
    if not repair_report or not (
            repair_report.get("valid") or repair_report.get("safePartialOutput")):
        return False
    if "repairApplied" in repair_report:
        return bool(repair_report.get("repairApplied"))
    return bool(
        repair_report.get("collapsed")
        or repair_report.get("removedMalformedMultirests")
        or repair_report.get("removedEmptyMeasures")
        or repair_report.get("mergedFalseSplitMeasures")
        or repair_report.get("detectedRestCounts")
        or repair_report.get("repaired")
        or repair_report.get("removedFooterLyrics")
        or repair_report.get("repairedFinalFermata")
    )


def build_pipeline_status(verification, repair_report=None):
    repair_report = repair_report or {}
    if repair_report and not repair_report.get("valid", False):
        reason = repair_report.get("reason") or "结构修复未通过"
        return PipelineStatus(
            stage="structure_repair",
            overall_status=PIPELINE_NEEDS_REVIEW if repair_report.get("candidateContinued") else PIPELINE_REJECTED,
            fatal=not repair_report.get("candidateContinued", False),
            warnings=[reason],
            output_allowed=False,
        )
    if verification.get("status") != "passed":
        return PipelineStatus(
            stage="final_validation",
            overall_status=PIPELINE_NEEDS_REVIEW,
            fatal=False,
            warnings=verification_warnings(verification),
            output_allowed=False,
        )
    warnings = []
    if repair_was_applied(repair_report):
        warnings.append("自动修复已通过结构约束，但尚未证明与原谱视觉内容完全一致")
    if repair_report.get("heuristicRepairs"):
        warnings.append("结果包含低置信度启发式修复")
    status = PIPELINE_VERIFIED_WITH_WARNINGS if warnings else PIPELINE_VERIFIED
    return PipelineStatus(
        stage="completed",
        overall_status=status,
        fatal=False,
        warnings=warnings,
        output_allowed=True,
    )


def verify_score_transposition(
    source_musicxml, transposed_musicxml, semitones, source_pages, output_pages,
    omr_analysis=None, layout_info=None,
    original_musicxml=None, repair_report=None,
):
    source = score_signature(source_musicxml)
    target = score_signature(transposed_musicxml)
    original = score_signature(original_musicxml or source_musicxml)
    omr_analysis = omr_analysis or {}
    layout_info = layout_info or {}
    pitch_mismatches = []
    for index, (before, after) in enumerate(zip(source["noteEvents"], target["noteEvents"])):
        actual = after["midi"] - before["midi"]
        if actual != semitones:
            pitch_mismatches.append({
                "index": index + 1,
                "measure": before["measureNumber"],
                "expected": semitones,
                "actual": actual,
            })
            if len(pitch_mismatches) >= 8:
                break
    note_count_match = source["noteCount"] == target["noteCount"]
    pitch_shift_ok = note_count_match and not pitch_mismatches
    measure_count_match = source["measureCount"] == target["measureCount"]
    measure_sequence_match = source["measureNumbers"] == target["measureNumbers"]
    timeline_match = (
        source.get("timelineContinuous")
        and target.get("timelineContinuous")
        and source.get("expandedMeasureValues") == target.get("expandedMeasureValues")
    )
    line_start_match = source["lineStartNumbers"] == target["lineStartNumbers"]
    if layout_info.get("outputSystemStarts") is not None:
        source_breaks = exported_layout(read_musicxml_root(source_musicxml))["pageSystemStarts"]
        line_start_match = source_breaks == layout_info["outputSystemStarts"]
    page_count_match = bool(source_pages and output_pages and source_pages == output_pages)
    expected_layout_systems = layout_info.get("expectedSystemsPerPage") or []
    output_layout_systems = layout_info.get("outputSystemsPerPage") or []
    system_layout_match = bool(
        layout_info.get("systemCountValidated")
        and expected_layout_systems
        and expected_layout_systems == output_layout_systems
    )
    source_measure_values = set(source.get("expandedMeasureValues") or [])
    output_measure_values = set(target.get("expandedMeasureValues") or [])
    recognized_line_numbers = omr_analysis.get("recognizedLineNumbers") or []
    missing_line_numbers = [
        number for number in recognized_line_numbers
        if number >= 5 and (number not in source_measure_values or number not in output_measure_values)
    ]
    multirests = omr_analysis.get("multirestMissing") or []
    export_errors = omr_analysis.get("exportErrors") or []
    structure_repair = repair_report or omr_analysis.get("multirestRepair") or {}
    structure_valid = structure_repair.get("valid", True)
    omr_structure_ok = (
        (not omr_analysis.get("ocrIssue"))
        and (not omr_analysis.get("bookIssue"))
        and (not multirests)
        and (not missing_line_numbers)
        and structure_valid
    )
    checks = [
        {
            "id": "pitch_shift",
            "label": "调性 / 音高转调",
            "passed": pitch_shift_ok,
            "detail": "已核对 %s 个音符事件，目标移动 %s 半音" % (min(source["noteCount"], target["noteCount"]), semitones)
            if pitch_shift_ok else
            "发现音符数量或半音移动不一致，前 %s 处异常需要人工复核" % len(pitch_mismatches),
        },
        {
            "id": "measure_count",
            "label": "识谱小节数量",
            "passed": measure_count_match,
            "detail": "OMR 识谱结果 %s 个小节，输出 %s 个小节" % (source["measureCount"], target["measureCount"]),
        },
        {
            "id": "measure_sequence",
            "label": "MusicXML 小节序号",
            "passed": measure_sequence_match,
            "detail": "小节序号序列一致" if measure_sequence_match else "小节序号序列不一致，需要检查漏小节、重排或 OMR 识别错误",
        },
        {
            "id": "measure_timeline",
            "label": "小节时间轴 / 空小节",
            "passed": timeline_match,
            "detail": "小节时间轴连续，空小节和多小节休止均已计入" if timeline_match else
            "小节时间轴存在断号、重复或多小节休止展开不一致",
        },
        {
            "id": "omr_export",
            "label": "OMR 音符导出完整性",
            "passed": not export_errors,
            "detail": (
                "Audiveris 没有跳过含音符的小节"
                if not export_errors else
                "Audiveris 导出时跳过了小节：%s" % ", ".join(map(str, export_errors[:12]))
            ),
        },
        {
            "id": "omr_structure",
            "label": "原谱行首小节号 / 多小节休止",
            "passed": omr_structure_ok,
            "detail": (
                "原谱行首小节号与多小节休止未发现结构风险"
                if omr_structure_ok else
                "发现结构风险：%s%s%s%s" % (
                    ("OCR 未正常工作；" if omr_analysis.get("ocrIssue") else ""),
                    ("多小节休止缺少计数 %s 处；" % len(multirests) if multirests else ""),
                    ("OCR 读到但时间轴缺少的行首小节号：%s；" % ", ".join(map(str, missing_line_numbers[:10])) if missing_line_numbers else ""),
                    ((structure_repair.get("reason") or "结构修复未通过") if not structure_valid else ""),
                )
            ),
        },
    ]
    render_audit = layout_info.get("renderAudit")
    if render_audit is not None:
        checks.extend(render_audit["checks"])
    source_audit = omr_analysis.get("pdfSourceAudit", {})
    if source_audit.get("matchedSystems"):
        conflicts = source_audit.get("measureConflicts", [])
        checks.append({"id": "pdf_barlines", "label": "原 PDF 小节线与识谱结果",
                       "passed": not conflicts,
                       "detail": "已对照原 PDF 的矢量小节线，未发现漏小节" if not conflicts else
                       "原 PDF 与识谱小节数不同：" + "；".join(
                           "第 %s 页第 %s 行 %s → %s" % (item["page"], item["system"], item["pdfMeasures"], item["recognizedMeasures"])
                           for item in conflicts[:8])})
    checks.extend([
        {
            "id": "line_start_numbers",
            "label": "每行左侧小节号",
            "passed": line_start_match,
            "detail": "转调前后行首小节号序列一致" if line_start_match else
            "转调前后行首小节号序列不一致",
        },
        {
            "id": "page_count",
            "label": "页码 / 页数一致",
            "passed": page_count_match,
            "detail": "源谱 %s 页，输出 %s 页" % (source_pages or "-", output_pages or "-"),
        },
        {
            "id": "system_layout",
            "label": "每页系统数 / 自动换行",
            "passed": system_layout_match,
            "detail": "每页系统数保持一致" if system_layout_match else
            "最终排版谱的实际系统分布与原谱不一致，或无法完成分页核验",
        },
    ])
    passed = all(item["passed"] for item in checks)
    repair_applied = repair_was_applied(structure_repair)
    repair_validation_status = (
        "FAILED" if structure_repair and not structure_repair.get("valid", False) else
        "PASSED" if repair_applied else "NOT_NEEDED"
    )
    source_integrity_status = (
        "FAILED" if repair_validation_status == "FAILED" else
        "PARTIALLY_VALIDATED" if repair_applied else
        "OMR_EXPORT_UNCHANGED"
    )
    transpose_consistency_status = "PASSED" if all(
        item["passed"] for item in checks
        if item["id"] in {"pitch_shift", "measure_count", "measure_sequence", "measure_timeline"}
    ) else "FAILED"
    return {
        "status": "passed" if passed else "failed",
        "strict": True,
        "checks": checks,
        "pitchMismatches": pitch_mismatches,
        "source": {
            "measures": source["measureCount"],
            "noteEvents": source["noteCount"],
            "pages": source_pages,
            "lineStartNumbers": source["lineStartNumbers"],
        },
        "output": {
            "measures": target["measureCount"],
            "noteEvents": target["noteCount"],
            "pages": output_pages,
            "lineStartNumbers": target["lineStartNumbers"],
        },
        "sources": {
            "original": score_artifact_descriptor(original_musicxml or source_musicxml, "original"),
            "repaired": score_artifact_descriptor(source_musicxml, "repaired"),
            "transposed": score_artifact_descriptor(transposed_musicxml, "transposed"),
        },
        "original": {
            "measures": original["measureCount"],
            "noteEvents": original["noteCount"],
            "timelineContinuous": original["timelineContinuous"],
        },
        "repair_validation_status": repair_validation_status,
        "source_integrity_status": source_integrity_status,
        "transpose_consistency_status": transpose_consistency_status,
        "omr": omr_analysis,
        "layout": layout_info,
        "summary": (
            "移调一致性验证通过，但不代表自动修复与原谱视觉内容一致。"
            if passed and repair_applied else
            "核实通过：调性、小节和页数均一致"
            if passed else "核实未通过：请重点检查未通过项目"
        ),
    }


def call_deepseek(messages, temperature=0.25, max_tokens=500, timeout=20):
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("AI 服务暂不可用")
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode()
    request = Request(
        DEEPSEEK_API_URL,
        data=payload,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode())
    return result["choices"][0]["message"]["content"]


def ai_score_verification_note(verification, source_instrument, target_instrument, semitones):
    prompt = """你是乐谱转调结果核实助手。你不能声称自己直接看过 PDF 原图，只能基于系统提供的结构化校验数据给结论。

输出要求：
- 用中文，4 到 6 句，直接说明是否通过。
- 必须覆盖：调性是否转对、OMR 是否跳过含音符小节、小节数量与时间轴是否一致。
- 所有任务均要求保留原谱，必须评价页数、分行和每行左侧小节号是否一致。
- 如果存在多小节休止缺少计数、OCR 行首编号缺失或 MusicXML 小节总数不可信，要明确说“小节结构不能视为已匹配原谱”。
- 如果页数不一致，要明确说“不满足页码必须一致的要求”。
- 如果有未通过项，不要安慰式模糊表达，要告诉用户需要回到谱面人工复核。
- 不要输出 Markdown 表格。"""
    user = {
        "sourceInstrument": source_instrument,
        "targetInstrument": target_instrument,
        "semitones": semitones,
        "verification": verification,
    }
    try:
        content = call_deepseek(
            [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
            temperature=0.15,
            max_tokens=420,
            timeout=20,
        )
        return content.strip() or "AI 核实说明暂时为空；请以系统硬校验结果为准。"
    except (RuntimeError, HTTPError, URLError, KeyError, json.JSONDecodeError, TimeoutError):
        logging.exception("score AI verification failed")
        return "AI 核实说明暂时不可用；请以系统硬校验结果为准。"


def split_command(value):
    return shlex.split(value, posix=(os.name != "nt")) if value else []


def find_audiveris_command():
    configured = split_command(os.environ.get("SCORE_AUDIVERIS_CMD", ""))
    if configured:
        return configured
    executable = shutil.which("audiveris") or shutil.which("Audiveris")
    if executable:
        return [executable]
    if os.name == "nt":
        base = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Audiveris")
        java = os.path.join(base, "runtime", "bin", "java.exe")
        app = os.path.join(base, "app", "*")
        if os.path.exists(java):
            return [java, "-cp", app, "Audiveris"]
    for candidate in ("/opt/audiveris/bin/Audiveris", "/usr/local/bin/audiveris"):
        if os.path.exists(candidate):
            return [candidate]
    return []


def find_musescore_command():
    configured = split_command(os.environ.get("SCORE_MUSESCORE_CMD", ""))
    if configured:
        return configured
    for name in ("mscore", "musescore", "MuseScore4", "musescore4"):
        executable = shutil.which(name)
        if executable:
            return [executable]
    if os.name == "nt":
        candidate = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "MuseScore 4", "bin", "MuseScore4.exe")
        if os.path.exists(candidate):
            return [candidate]
    return []


def run_command(command, cwd, timeout, label):
    logging.info("running %s: %s", label, " ".join(command))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s 超时，请换一份更小或更清晰的 PDF" % label)
    if completed.returncode != 0:
        tail = (completed.stdout or "")[-1200:]
        raise RuntimeError("%s 失败：%s" % (label, tail.strip() or "没有错误输出"))
    return completed.stdout or ""


def newest_musicxml_file(root_dir):
    candidates = []
    for current, _, files in os.walk(root_dir):
        for filename in files:
            if filename.lower().endswith((".mxl", ".musicxml", ".xml")):
                candidates.append(os.path.join(current, filename))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: os.path.getmtime(item))


def newest_omr_file(root_dir):
    candidates = []
    for current, _, files in os.walk(root_dir):
        for filename in files:
            if filename.lower().endswith(".omr"):
                candidates.append(os.path.join(current, filename))
    return max(candidates, key=lambda item: os.path.getmtime(item)) if candidates else ""


def retry_audiveris_export(audiveris, omr_book, job_dir, timeout,
                           directory_name="omr-export-retry",
                           label="Audiveris 安全二次导出"):
    retry_dir = os.path.join(job_dir, directory_name)
    os.makedirs(retry_dir, exist_ok=True)
    sanitized_book = os.path.join(retry_dir, "sanitized.omr")
    removed_relations = sanitize_audiveris_book(omr_book, sanitized_book)
    if removed_relations <= 0:
        raise RuntimeError("Audiveris 跳过了含音符小节，且没有找到可安全清理的异常关系")
    output = run_command(
        list(audiveris) + ["-batch", "-export", "-output", retry_dir, sanitized_book],
        job_dir,
        timeout,
        label,
    )
    analysis = analyze_audiveris_output(output)
    musicxml = newest_musicxml_file(retry_dir)
    if not musicxml or analysis.get("exportErrors"):
        raise RuntimeError("Audiveris 二次导出仍跳过含音符小节，已阻止生成不完整乐谱")
    return musicxml, removed_relations, analysis


def get_pdf_page_count(path):
    vendor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
    if os.path.isdir(vendor_path) and vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    try:
        from PyPDF2 import PdfFileReader
        with open(path, "rb") as file:
            reader = PdfFileReader(file, strict=False)
            return max(1, int(reader.getNumPages()))
    except (ImportError, OSError, ValueError, TypeError, Exception) as exc:
        logging.warning("reliable PDF page parser unavailable for %s: %s", path, exc)
    try:
        with open(path, "rb") as file:
            data = file.read()
        count = len(re.findall(rb"/Type\s*/Page\b", data))
        return max(1, count) if count else 0
    except OSError:
        return 0


def count_pdf_pages(path):
    """Compatibility alias. New code should use get_pdf_page_count()."""
    return get_pdf_page_count(path)


def pdf_page_size(path):
    try:
        with open(path, "rb") as file:
            data = file.read(256 * 1024)
        match = re.search(
            rb"/MediaBox\s*\[\s*[-0-9.]+\s+[-0-9.]+\s+([-0-9.]+)\s+([-0-9.]+)\s*\]",
            data,
        )
        if match:
            return float(match.group(1)), float(match.group(2))
    except (OSError, ValueError):
        pass
    return 595.28, 841.89


def render_score_pdf(musescore, musicxml_path, output_pdf, job_dir, timeout, label, style_path=None):
    command = list(musescore)
    if style_path:
        command += ["-S", style_path]
    command += ["-f", "-o", output_pdf, musicxml_path]
    run_command(command, job_dir, timeout, label)
    if not os.path.exists(output_pdf) or os.path.getsize(output_pdf) <= 0:
        raise RuntimeError("%s 失败，结果文件为空" % label)
    return get_pdf_page_count(output_pdf)


def musescore_style_number(path, name, default):
    try:
        tree = ET.parse(path)
        score = next((item for item in tree.getroot().iter() if local_name(item.tag) == "Score"), None)
        style = child(score, "Style") if score is not None else None
        node = child(style, name) if style is not None else None
        return float(node.text) if node is not None and node.text else default
    except (OSError, ET.ParseError, TypeError, ValueError):
        return default


def patch_musescore_layout(input_path, output_path, page_width, page_height, spatium):
    tree = ET.parse(input_path)
    root = tree.getroot()
    score = next((item for item in root.iter() if local_name(item.tag) == "Score"), None)
    if score is None:
        raise RuntimeError("MuseScore 文件缺少 Score 节点")
    style = child(score, "Style")
    if style is None:
        style = ET.Element(qname(score, "Style"))
        score.insert(0, style)

    # OMR imports can place two title-block texts at the exact same anchor.
    # Keep the composer on the conventional right side and move the paired
    # instrument/credit text to the left so neither label is obscured.
    for frame in (node for node in root.iter() if local_name(node.tag) == "VBox"):
        anchored_texts = {}
        for text_node in (node for node in list(frame) if local_name(node.tag) == "Text"):
            align_node = child(text_node, "align")
            offset_node = child(text_node, "offset")
            align = (align_node.text or "") if align_node is not None else ""
            if "right" not in align.lower():
                continue
            try:
                offset_x = float(offset_node.get("x", "0")) if offset_node is not None else 0.0
                offset_y = float(offset_node.get("y", "0")) if offset_node is not None else 0.0
            except (TypeError, ValueError):
                continue
            key = (round(offset_x, 3), round(offset_y, 3), align.lower())
            anchored_texts.setdefault(key, []).append(text_node)

        for (_, offset_y, _), text_nodes in anchored_texts.items():
            if len(text_nodes) < 2:
                continue
            composer_nodes = []
            for text_node in text_nodes:
                style_node = child(text_node, "style")
                style_name = (style_node.text or "") if style_node is not None else ""
                if style_name.strip().lower() == "composer":
                    composer_nodes.append(text_node)
            right_node = composer_nodes[-1] if composer_nodes else text_nodes[-1]
            left_nodes = [node for node in text_nodes if node is not right_node]
            for index, text_node in enumerate(left_nodes):
                align_node = child(text_node, "align")
                if align_node is None:
                    align_node = ET.SubElement(text_node, qname(text_node, "align"))
                align_node.text = "left,top"
                offset_node = child(text_node, "offset")
                if offset_node is None:
                    offset_node = ET.SubElement(text_node, qname(text_node, "offset"))
                offset_node.set("x", "0")
                if index:
                    offset_node.set("y", "%.3f" % (offset_y + 5.5 * index))
    values = {
        "pageWidth": "%.4f" % page_width,
        "pageHeight": "%.4f" % page_height,
        "pagePrintableWidth": "%.4f" % max(1.0, page_width - 0.5),
        "Spatium": "%.3f" % spatium,
        "pageEvenTopMargin": "0.12",
        "pageEvenBottomMargin": "0.12",
        "pageEvenLeftMargin": "0.25",
        "pageOddTopMargin": "0.12",
        "pageOddBottomMargin": "0.12",
        "pageOddLeftMargin": "0.25",
        "createMultiMeasureRests": "1",
        "showHeader": "0",
        "showFooter": "0",
        "staffUpperBorder": "0",
        "staffLowerBorder": "0",
        "minSystemDistance": "0",
        "maxSystemDistance": "12",
        "enableVerticalSpread": "1",
        "systemFrameDistance": "1",
        "frameSystemDistance": "1",
        "minMeasureWidth": "2",
        "minNoteDistance": "0.12",
        "barNoteDistance": "0.45",
        "measureSpacing": "0.60",
        # MusicXML imports retain printed/system-start numbers as explicit
        # overrides. Enabling MuseScore's automatic counter at the same time
        # creates duplicate, often off-by-one labels after pickup measures.
        "showMeasureNumber": "0",
        "measureNumberSystem": "1",
        "measureNumberAllStaffs": "0",
    }
    for name, value in values.items():
        node = child(style, name)
        if node is None:
            node = ET.SubElement(style, qname(style, name))
        node.text = value
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def expected_system_counts(omr_analysis):
    counts = {}
    for system in (omr_analysis or {}).get("systems", []):
        page = int(system.get("page") or 0)
        if page > 0:
            counts[page] = counts.get(page, 0) + 1
    return [counts[index] for index in sorted(counts)]


def expected_staff_counts(omr_analysis):
    """Total printed staves per page, comparable with MuseScore SVG output."""
    counts = {}
    for system in (omr_analysis or {}).get("systems", []):
        page = int(system.get("page") or 0)
        if page > 0:
            counts[page] = counts.get(page, 0) + max(1, int(system.get("staffCount") or 1))
    return [counts[index] for index in sorted(counts)]


def layout_count_distance(actual, expected, expected_pages=0):
    if expected:
        width = max(len(actual), len(expected))
        values = sum(abs((actual[index] if index < len(actual) else 0) -
                         (expected[index] if index < len(expected) else 0))
                     for index in range(width))
        return values + abs(len(actual) - len(expected)) * 100
    return abs(len(actual) - expected_pages) if expected_pages else 0


def svg_staff_counts(job_dir, output_stem):
    candidates = []
    exact = os.path.join(job_dir, output_stem + ".svg")
    if os.path.exists(exact):
        candidates.append(exact)
    pattern = re.compile(r"^%s-(\d+)\.svg$" % re.escape(output_stem))
    numbered = []
    for filename in os.listdir(job_dir):
        match = pattern.match(filename)
        if match:
            numbered.append((int(match.group(1)), os.path.join(job_dir, filename)))
    candidates.extend(path for _, path in sorted(numbered))
    counts = []
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
        except OSError:
            continue
        staff_lines = len(re.findall(r'class="StaffLines"', content))
        counts.append(staff_lines // 5)
    return counts


def svg_system_counts(job_dir, output_stem):
    """Compatibility alias; the legacy implementation counts staves, not systems."""
    return svg_staff_counts(job_dir, output_stem)


def scale_pdf_to_page(input_path, output_path, target_width, target_height):
    vendor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    try:
        from PyPDF2 import PdfFileReader, PdfFileWriter
    except ImportError:
        raise RuntimeError("服务器缺少 PyPDF2，无法把保版式结果缩放回原 PDF 页面")
    with open(input_path, "rb") as source_file, open(output_path, "wb") as output_file:
        reader = PdfFileReader(source_file)
        writer = PdfFileWriter()
        for index in range(reader.getNumPages()):
            page = reader.getPage(index)
            width = float(page.mediaBox.getWidth())
            height = float(page.mediaBox.getHeight())
            scale = min(target_width / width, target_height / height)
            page.scaleBy(scale)
            page.mediaBox.lowerLeft = (0, 0)
            page.mediaBox.upperRight = (target_width, target_height)
            page.cropBox.lowerLeft = (0, 0)
            page.cropBox.upperRight = (target_width, target_height)
            writer.addPage(page)
        writer.write(output_file)


def add_multirest_render_boundaries(input_path, output_path, omr_analysis):
    """Annotate expanded rest runs so MuseScore cannot merge across them.

    The repair layer expands a confirmed multi-rest into ordinary measures for
    stable numbering and editing. MusicXML's multiple-rest marker is restored
    only in the renderer input; MuseScore uses it to place break boundaries at
    both ends of the run. MuseScore 3 interprets the MusicXML value as the end
    boundary after the containing measure, so the importer value is one larger
    than the number of measures that must remain grouped.
    """
    repair = (omr_analysis or {}).get("multirestRepair") or {}
    boundaries = repair.get("expandedForRendering") or []
    if not boundaries:
        return input_path, []
    root = read_musicxml_root(input_path)
    applied = []
    for boundary in boundaries:
        number = str(boundary.get("measure", ""))
        count = boundary.get("multipleRest")
        if type(count) is not int or count < 2 or not number:
            continue
        matched = 0
        for part in (item for item in root if local_name(item.tag) == "part"):
            measure = next((
                item for item in part if local_name(item.tag) == "measure"
                and item.attrib.get("number") == number
            ), None)
            if measure is None:
                continue
            attributes = next((
                item for item in measure if local_name(item.tag) == "attributes"
            ), None)
            if attributes is None:
                attributes = ET.Element(qname(measure, "attributes"))
                measure.insert(0, attributes)
            style = next((
                item for item in attributes if local_name(item.tag) == "measure-style"
            ), None)
            if style is None:
                style = ET.SubElement(attributes, qname(attributes, "measure-style"))
            multiple = next((
                item for item in style if local_name(item.tag) == "multiple-rest"
            ), None)
            if multiple is None:
                multiple = ET.SubElement(style, qname(style, "multiple-rest"))
            importer_count = count + 1
            multiple.text = str(importer_count)
            matched += 1
        if matched:
            applied.append({
                "measure": number, "multipleRest": count,
                "museScoreImporterBoundary": importer_count, "parts": matched,
            })
    if not applied:
        return input_path, []
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path, applied


def render_preserved_score_pdf(
    musescore, musicxml_path, output_pdf, source_pdf, job_dir, timeout, label, omr_analysis=None
):
    source_width, source_height = pdf_page_size(source_pdf)
    page_width = source_width / 72.0
    page_height = source_height / 72.0
    source_pages = get_pdf_page_count(source_pdf)
    expected_systems = expected_system_counts(omr_analysis)
    expected_staffs = expected_staff_counts(omr_analysis)
    render_input, render_boundaries = add_multirest_render_boundaries(
        musicxml_path, os.path.join(job_dir, "render-input.musicxml"), omr_analysis
    )
    base_mscx = os.path.join(job_dir, "layout-base.mscx")
    run_command(list(musescore) + ["-f", "-o", base_mscx, render_input], job_dir, timeout, label + "（导入）")
    source_spatium = musescore_style_number(base_mscx, "Spatium", 1.60)
    best = None
    probes = []
    for index, ratio in enumerate((1.00, 0.96, 0.92, 0.88, 0.84, 0.80, 0.76, 0.72, 0.68, 0.64, 0.60), start=1):
        spatium = max(0.80, source_spatium * ratio)
        styled_mscx = os.path.join(job_dir, "layout-candidate-%02d.mscx" % index)
        svg_stem = "layout-probe-%02d" % index
        svg_path = os.path.join(job_dir, svg_stem + ".svg")
        patch_musescore_layout(base_mscx, styled_mscx, page_width, page_height, spatium)
        run_command(
            list(musescore) + ["-f", "-o", svg_path, styled_mscx],
            job_dir,
            timeout,
            label + "（版式探针 %s）" % index,
        )
        output_staff_counts = svg_staff_counts(job_dir, svg_stem)
        page_match = bool(output_staff_counts) and (not source_pages or len(output_staff_counts) == source_pages)
        count_match = bool(output_staff_counts) and (output_staff_counts == expected_staffs) if expected_staffs else page_match
        distance = layout_count_distance(output_staff_counts, expected_staffs, source_pages)
        candidate = {
            "path": styled_mscx,
            "spatium": round(spatium, 3),
            "staffCounts": output_staff_counts,
            "distance": distance,
            "pageMatched": page_match,
            "matched": count_match,
        }
        probes.append({key: value for key, value in candidate.items() if key != "path"})
        if best is None or candidate["distance"] < best["distance"]:
            best = candidate
        if candidate["matched"]:
            best = candidate
            break
    if best is None:
        raise RuntimeError("MuseScore 自适应排版没有生成可用候选")
    run_command(
        list(musescore) + ["-f", "-o", output_pdf, best["path"]],
        job_dir,
        timeout,
        label + "（最终导出）",
    )
    output_pages = get_pdf_page_count(output_pdf)
    audit_path = os.path.join(job_dir, "rendered.musicxml")
    run_command(list(musescore) + ["-f", "-o", audit_path, best["path"]], job_dir, timeout, label + "（回读核对）")
    rendered_root = read_musicxml_root(audit_path)
    actual_layout = exported_layout(rendered_root)
    if render_boundaries:
        remove_multiple_rest_nodes(rendered_root)
        ET.ElementTree(rendered_root).write(
            audit_path, encoding="utf-8", xml_declaration=True)
    return output_pages, {
        "sourceSpatium": round(source_spatium, 3),
        "outputSpatium": best["spatium"],
        "expectedSystemsPerPage": expected_systems,
        "expectedStaffsPerPage": expected_staffs,
        "outputStaffsPerPage": best["staffCounts"],
        "outputSystemsPerPage": actual_layout["systemsPerPage"],
        "outputSystemStarts": actual_layout["pageSystemStarts"],
        "systemCountValidated": actual_layout["breaksDeclared"] and len(actual_layout["systemsPerPage"]) == output_pages,
        "renderAudit": compare_rendered_score(read_musicxml_root(musicxml_path), rendered_root),
        "renderedMusicxml": audit_path,
        "multirestRenderBoundaries": render_boundaries,
        "matched": best["matched"],
        "layoutProbes": probes,
    }




def write_musescore_style(path, spatium, page_width=8.2677, page_height=11.6929):
    content = """<?xml version="1.0" encoding="UTF-8"?>
<museScore version="3.02">
  <Style>
    <pageWidth>%.4f</pageWidth>
    <pageHeight>%.4f</pageHeight>
    <pagePrintableWidth>%.4f</pagePrintableWidth>
    <pageEvenTopMargin>0.12</pageEvenTopMargin>
    <pageEvenBottomMargin>0.12</pageEvenBottomMargin>
    <pageEvenLeftMargin>0.20</pageEvenLeftMargin>
    <pageOddTopMargin>0.12</pageOddTopMargin>
    <pageOddBottomMargin>0.12</pageOddBottomMargin>
    <pageOddLeftMargin>0.20</pageOddLeftMargin>
    <Spatium>%.3f</Spatium>
    <createMultiMeasureRests>1</createMultiMeasureRests>
    <showHeader>0</showHeader>
    <showFooter>0</showFooter>
    <staffUpperBorder>0</staffUpperBorder>
    <staffLowerBorder>0</staffLowerBorder>
    <staffDistance>2</staffDistance>
    <akkoladeDistance>2</akkoladeDistance>
    <minSystemDistance>0</minSystemDistance>
    <maxSystemDistance>1</maxSystemDistance>
    <systemFrameDistance>1</systemFrameDistance>
    <frameSystemDistance>1</frameSystemDistance>
    <minMeasureWidth>3</minMeasureWidth>
    <minNoteDistance>0.18</minNoteDistance>
    <barNoteDistance>0.55</barNoteDistance>
    <measureSpacing>0.78</measureSpacing>
    <showMeasureNumber>0</showMeasureNumber>
    <measureNumberSystem>1</measureNumberSystem>
    <measureNumberAllStaffs>0</measureNumberAllStaffs>
  </Style>
</museScore>
""" % (page_width, page_height, page_width - 0.4, spatium)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def failed_check_ids(verification):
    return {item.get("id") for item in verification.get("checks", []) if not item.get("passed")}


def verification_warnings(verification):
    warnings = []
    labels = {
        "pitch_shift": "调性/音高转调核实未通过，请人工检查异常音符",
        "measure_count": "转调前后的 OMR 小节数量不一致，可能存在识谱结构错误",
        "measure_sequence": "MusicXML 小节序号不一致，请检查漏小节、重排或编号识别错误",
        "measure_timeline": "小节时间轴存在断号、重复或空小节遗漏",
        "omr_export": "OMR 导出时跳过了含音符的小节，结果不能交付",
        "line_start_numbers": "每行左侧小节号序列与转调前不一致，不能保证行首编号对应原谱",
        "omr_structure": "原谱行首小节号或多小节休止未正确进入 MusicXML，小节总数不能视为可信",
        "rhythm_gaps": "识谱声部时间轴存在缺拍或超出拍号容量的位置，请按小节复核休止符、音符时值和声部",
        "page_count": "页数不一致，未满足输出页码必须与原谱一致的要求",
        "system_layout": "尚不能确认每页分行与原谱一致，需要复核版式",
    }
    for check_id in failed_check_ids(verification):
        warning = labels.get(check_id)
        if warning:
            warnings.append(warning)
    return warnings


def public_score_verification(verification):
    """Keep polling responses small while full evidence stays in the job workspace."""
    value = copy.deepcopy(verification or {})
    value["issues"] = value.get("issues", [])[:50]
    omr = value.get("omr")
    if isinstance(omr, dict):
        systems = omr.get("systems", [])
        repair = omr.get("multirestRepair", {})
        value["omr"] = {
            "ocrIssue": omr.get("ocrIssue"),
            "bookIssue": omr.get("bookIssue"),
            "repairState": omr.get("repairState"),
            "systemCount": len(systems),
            "systemsPerPage": [item.get("systems", []) for item in omr.get("rawPages", [])],
            "multirestMissing": omr.get("multirestMissing", []),
            "exportErrors": omr.get("exportErrors", []),
            "recognitionAttempts": omr.get("recognitionAttempts", []),
            "recognitionDecision": omr.get("recognitionDecision", {}),
            "multirestRepair": {
                "valid": repair.get("valid"), "changed": repair.get("changed"),
                "reason": repair.get("reason"),
                "detectedRestCount": len(repair.get("detectedRestCounts", [])),
                "unresolvedGaps": repair.get("unresolvedGaps", []),
            },
        }
    preflight = value.get("preflight")
    if isinstance(preflight, dict):
        value["preflight"] = {
            "changed": preflight.get("changed"), "pages": preflight.get("pages"),
            "musicFamily": preflight.get("musicFamily"),
            "repairs": preflight.get("repairs", []), "issues": preflight.get("issues", []),
        }
    layout = value.get("layout")
    if isinstance(layout, dict):
        audit = layout.get("renderAudit", {})
        semantic = audit.get("semanticAudit", {})
        value["layout"] = {
            "sourceSpatium": layout.get("sourceSpatium"),
            "outputSpatium": layout.get("outputSpatium"),
            "expectedSystemsPerPage": layout.get("expectedSystemsPerPage"),
            "expectedStaffsPerPage": layout.get("expectedStaffsPerPage"),
            "outputStaffsPerPage": layout.get("outputStaffsPerPage"),
            "outputSystemsPerPage": layout.get("outputSystemsPerPage"),
            "outputSystemStarts": layout.get("outputSystemStarts"),
            "systemCountValidated": layout.get("systemCountValidated"),
            "renderPlan": {
                "selectedMode": (layout.get("renderPlan") or {}).get("selectedMode"),
                "reason": (layout.get("renderPlan") or {}).get("reason"),
                "outputTrust": (layout.get("renderPlan") or {}).get("outputTrust"),
            },
            "renderAudit": {
                "eventsMatch": audit.get("eventsMatch"), "marksMatch": audit.get("marksMatch"),
                "differences": audit.get("differences", [])[:20],
                "semanticAudit": {"passed": semantic.get("passed"),
                                  "issueCount": semantic.get("issueCount"),
                                  "truncated": semantic.get("truncated")},
                "checks": audit.get("checks", []),
            },
        }
    composition = value.get("systemComposition")
    if isinstance(composition, dict):
        value["systemComposition"] = {
            "status": composition.get("status"),
            "reason": composition.get("reason"),
            "pages": composition.get("pages"),
            "systems": composition.get("systems"),
            "preservedOutsideSystemRegions": composition.get("preservedOutsideSystemRegions"),
            "semanticVerification": False,
            "postCompositionLayoutStatus": (
                composition.get("postCompositionLayoutAudit") or {}).get("status"),
        }
    output_omr = value.get("outputPdfOmrAudit")
    if isinstance(output_omr, dict):
        comparison = output_omr.get("comparison") or {}
        semantic = comparison.get("semanticAudit") or {}
        value["outputPdfOmrAudit"] = {
            "status": output_omr.get("status"),
            "reason": output_omr.get("reason"),
            "evidenceLevel": output_omr.get("evidenceLevel"),
            "checks": comparison.get("checks", []),
            "differences": comparison.get("differences", [])[:20],
            "semanticAudit": {
                "passed": semantic.get("passed"),
                "issueCount": semantic.get("issueCount"),
                "truncated": semantic.get("truncated"),
            },
            "outputAllowed": False,
            "verificationAuthority": "none",
        }
    return value


def process_score_pdf(input_pdf, job_dir, semitones, accidental_preference, progress=None,
                      source_instrument=None, target_instrument=None, preflight=None,
                      intent=None, inspection=None, omr_variant=None):
    progress = progress or (lambda *args: None)
    audiveris = find_audiveris_command()
    musescore = find_musescore_command()
    if not audiveris:
        raise RuntimeError("服务器还没有配置 Audiveris 识谱引擎，暂时不能处理任意 PDF")
    if not musescore:
        raise RuntimeError("服务器还没有配置 MuseScore PDF 渲染引擎，暂时不能导出结果 PDF")

    timeout = int(os.environ.get("SCORE_PROCESS_TIMEOUT", str(min(1200, 120 + 90 * get_pdf_page_count(input_pdf)))))
    omr_dir = os.path.join(job_dir, "omr")
    os.makedirs(omr_dir, exist_ok=True)
    progress("recognizing", "正在识别乐谱中的音符、小节和演奏标记", 22)
    family = (preflight or {}).get("musicFamily")
    font_options = ["-constant", "org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=" + family] if family else []
    audiveris_output = run_command(
        audiveris + font_options + [
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true",
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.multiWholeHeadChords=true",
            "-batch", "-export", "-output", omr_dir, input_pdf,
        ],
        job_dir,
        timeout,
        "Audiveris 识谱",
    )
    omr_analysis = analyze_audiveris_output(audiveris_output)
    omr_book = newest_omr_file(omr_dir)
    musicxml = newest_musicxml_file(omr_dir)
    if not musicxml:
        raise RuntimeError("识谱完成但没有找到 MusicXML/MXL 结果，可能是 PDF 清晰度不足")
    if omr_analysis.get("exportErrors"):
        original_errors = list(omr_analysis["exportErrors"])
        musicxml, removed_wedges, retry_analysis = retry_audiveris_export(
            audiveris, omr_book, job_dir, timeout
        )
        omr_analysis["exportErrorsOriginal"] = original_errors
        omr_analysis["exportErrors"] = retry_analysis.get("exportErrors") or []
        omr_analysis["exportRecovery"] = {
            "recoveredMeasures": original_errors,
            "removedWedgeRelations": removed_wedges,
        }
    omr_book_analysis = analyze_audiveris_book(omr_book)
    omr_analysis.update(omr_book_analysis)
    if preflight:
        apply_pdf_anchors(omr_analysis, preflight)

    omr_analysis["timelineRisk"] = musicxml_timeline_risk(musicxml)
    initial_notes = len(score_signature(musicxml)["noteEvents"])
    attempt_signatures = [{"attemptId": "audiveris-primary", "signature": score_signature(musicxml)}]
    attempts = [recognition_attempt(
        "audiveris-primary", family or "Bravura", omr_analysis, initial_notes,
        os.path.relpath(input_pdf, job_dir).replace("\\", "/"),
    )]
    families = recognition_families(preflight)
    alternate_reason = None
    timeline_risk = omr_analysis.get("timelineRisk") or {}
    timeline_total = int(timeline_risk.get("gapCount") or 0) + int(
        timeline_risk.get("overflowCount") or 0)
    if timeline_total:
        alternate_reason = "musicxml_timeline_gaps"
    if not omr_variant and timeline_total:
        # A vector PDF can still contain a music font or drawing construction
        # that the OMR importer handles poorly. A high-resolution raster is an
        # independent representation of the same page and often exposes note
        # heads/stems that disappeared during direct PDF ingestion.
        try:
            omr_variant, variant_report = prepare_omr_variant(input_pdf, job_dir, 400)
            alternate_reason = "timeline_gaps_high_resolution_raster"
        except RuntimeError:
            omr_variant = None
    alternate_family = (family or families[0]) if omr_variant else (
        families[1] if len(families) > 1 else None)
    alternate_input = omr_variant or input_pdf
    if alternate_family and needs_alternative(omr_analysis, initial_notes):
        progress("recognizing", "发现识谱疑点，正在用另一组输入与参数重新识别", 42)
        alternative_dir = os.path.join(job_dir, "omr-alternative")
        os.makedirs(alternative_dir, exist_ok=True)
        try:
            log = run_command(audiveris + [
                "-constant", "org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=" + alternate_family,
                "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
                "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true",
                "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.multiWholeHeadChords=true",
                "-batch", "-export", "-output", alternative_dir, alternate_input,
            ], job_dir, timeout, "Audiveris 第二次识谱")
            alternate_xml = newest_musicxml_file(alternative_dir)
            alternate_book = newest_omr_file(alternative_dir)
            if alternate_xml and alternate_book:
                alternate = analyze_audiveris_output(log)
                if alternate.get("exportErrors"):
                    original_errors = list(alternate["exportErrors"])
                    try:
                        alternate_xml, removed_wedges, retry_analysis = retry_audiveris_export(
                            audiveris, alternate_book, job_dir, timeout,
                            "omr-alternative-export-retry",
                            "Audiveris 高清候选安全二次导出",
                        )
                        alternate["exportErrorsOriginal"] = original_errors
                        alternate["exportErrors"] = retry_analysis.get("exportErrors") or []
                        alternate["exportRecovery"] = {
                            "recoveredMeasures": original_errors,
                            "removedWedgeRelations": removed_wedges,
                        }
                    except RuntimeError as exc:
                        alternate["exportRecovery"] = {
                            "recoveredMeasures": [],
                            "failedMeasures": original_errors,
                            "error": str(exc),
                        }
                alternate.update(analyze_audiveris_book(alternate_book))
                if preflight:
                    apply_pdf_anchors(alternate, preflight)
                alternate["timelineRisk"] = musicxml_timeline_risk(alternate_xml)
                notes = len(score_signature(alternate_xml)["noteEvents"])
                risk = recognition_risk(alternate, notes)
                attempts.append(recognition_attempt(
                    "audiveris-alternative", alternate_family, alternate, notes,
                    os.path.relpath(alternate_input, job_dir).replace("\\", "/"),
                    "grayscale_autocontrast_raster_pdf" if omr_variant else "pdf",
                ))
                attempts[-1]["trigger"] = alternate_reason
                attempt_signatures.append({"attemptId": "audiveris-alternative",
                                           "signature": score_signature(alternate_xml)})
                if risk < recognition_risk(omr_analysis, initial_notes):
                    omr_analysis, musicxml, omr_book = alternate, alternate_xml, alternate_book
        except RuntimeError as exc:
            attempts.append({
                "schemaVersion": 1, "attemptId": "audiveris-alternative",
                "engine": {"name": "Audiveris", "family": alternate_family},
                "status": "failed", "error": str(exc),
            })
    comparable_attempts = [item for item in attempts if item.get("riskTuple") is not None]
    decision = recognition_decision(comparable_attempts)
    decision["candidateConsensus"] = recognition_consensus(
        attempt_signatures, decision["selectedAttemptId"])
    if len(comparable_attempts) != len(attempts):
        decision["failedAttempts"] = [item for item in attempts if item.get("riskTuple") is None]
    omr_analysis["recognitionAttempts"] = decision["attempts"] + decision.get("failedAttempts", [])
    omr_analysis["recognitionDecision"] = {
        key: value for key, value in decision.items() if key != "attempts"
    }
    decision_path = os.path.join(job_dir, "review", "recognition-decision.json")
    os.makedirs(os.path.dirname(decision_path), exist_ok=True)
    with open(decision_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(decision, stream, ensure_ascii=False, indent=2)
    os.replace(decision_path + ".tmp", decision_path)
    workspace = ScoreWorkspace(job_dir)
    if os.path.isfile(workspace.manifest_path):
        workspace.register_artifact("recognition-decision", decision_path)
        workspace.record_runtime(
            engines={"musicRecognition": {"name": "Audiveris", "mode": "parameter-ensemble"}},
            parameters={"recognitionAttempts": len(comparable_attempts)},
        )

    source_pages = get_pdf_page_count(input_pdf)
    repairs = []
    original_musicxml = musicxml
    structure_repair = {
        "valid": True,
        "fatal": False,
        "repairApplied": False,
        "repairValidationStatus": "NOT_NEEDED",
    }
    repair_state = "repair_not_needed"
    auto_repair = os.environ.get("SCORE_AUTO_REPAIR_RESTS", "1") == "1"
    if omr_analysis.get("ocrIssue") or omr_analysis.get("bookIssue") or not omr_analysis.get("systems"):
        reason = (
            omr_analysis.get("bookIssue")
            or ("OMR 数字识别不可用" if omr_analysis.get("ocrIssue") else "OMR 工程缺少可验证的系统结构")
        )
        structure_repair = {
            "valid": False,
            "fatal": True,
            "reason": reason,
            "repairValidationStatus": "FAILED",
        }
        repair_state = "repair_failed"
    elif auto_repair:
        repaired_musicxml = os.path.join(job_dir, "structure-repaired.musicxml")
        structure_repair = repair_musicxml_structure(
            musicxml, repaired_musicxml, omr_analysis
        )
        targeted_counts = []
        for _ in range(4):
            if structure_repair.get("valid") or not structure_repair.get("unresolvedGaps"):
                break
            progress("recognizing", "正在放大结构缺口并复查多小节休止数字", 52)
            recovered_counts = recover_rest_counts_from_unresolved_gaps(
                omr_book, omr_analysis, structure_repair.get("unresolvedGaps")
            )
            if not recovered_counts:
                break
            targeted_counts.extend(recovered_counts)
            structure_repair = repair_musicxml_structure(
                musicxml, repaired_musicxml, omr_analysis
            )
        if targeted_counts:
            structure_repair["targetedVisualRestCounts"] = targeted_counts
        if structure_repair.get("valid"):
            repair_state = "repair_success"
            omr_analysis["multirestMissingOriginal"] = omr_analysis.get("multirestMissing", [])
            omr_analysis["multirestMissing"] = []
            musicxml = repaired_musicxml
        else:
            partial_repair = apply_verified_multirest_repairs(
                musicxml, repaired_musicxml, omr_analysis, structure_repair)
            if partial_repair.get("safePartialOutput"):
                structure_repair = partial_repair
                repair_state = "repair_partial"
                musicxml = repaired_musicxml
            else:
                repair_state = "repair_failed"
        repairs.append({
            "id": "repair_multimeasure_rests",
            "label": "恢复小节边界与序列 / 多小节休止计数",
            "status": (
                "needs_review" if structure_repair.get("safePartialOutput") else
                "fixed" if repair_was_applied(structure_repair) else
                "skipped" if structure_repair.get("valid") else "failed"
            ),
            "detail": (
                "已提交 %s 处三重证据一致的多小节休止；其余结构疑点仍需人工确认：%s"
                % (len(structure_repair.get("partialRepairs", [])), structure_repair.get("reason", ""))
                if structure_repair.get("safePartialOutput") else
                "已根据每页行首编号恢复 %s 处休止结构，时间轴共 %s 小节"
                % (len(structure_repair.get("repaired", [])), structure_repair.get("targetSpan", 0))
                if repair_was_applied(structure_repair) else
                structure_repair.get("reason", "结构检查通过，没有需要自动修复的内容")
            ),
        })
        omr_analysis["multirestRepair"] = structure_repair
    omr_analysis["repairState"] = repair_state
    omr_analysis["multirestRepair"] = structure_repair
    if repair_state == "repair_failed":
        # A failed structural inference must not alter the recognized source.
        # Continue only as an explicitly unverified candidate, without guessing
        # where missing notes or rests belong. Keep the failure report even if
        # later transposition or rendering cannot finish.
        musicxml = original_musicxml
        structure_repair["candidateContinued"] = True
        pipeline_status = build_pipeline_status({}, structure_repair)
        write_pipeline_report(
            job_dir,
            pipeline_status,
            verification={
                "status": "failed",
                "checks": [{"id": "source_structure", "label": "原谱结构与识谱结果",
                            "passed": False, "detail": structure_repair.get("reason", "结构修复失败")}],
                "repair_validation_status": "FAILED",
                "source_integrity_status": "FAILED",
                "transpose_consistency_status": "NOT_RUN",
                "reason": structure_repair.get("reason", "结构修复失败"),
                "omr": omr_analysis,
                "preflight": preflight,
            },
            artifacts={
                "original": score_artifact_descriptor(original_musicxml, "original"),
                "repaired": {"role": "repaired", "available": False},
                "transposed": {"role": "transposed", "available": False},
                "output": {"role": "output", "available": False},
            },
        )
        progress("recognizing", "小节边界与序列存在疑点，将保留识别内容生成待校对候选", 55)

    # Source repair belongs to source reconstruction.  It must finish before
    # deterministic transposition, otherwise a recognition error is copied into
    # the target and only discovered after rendering.
    source_before_rhythm_repair = musicxml
    source_repair_before_gaps = {"gaps": [], "overflows": []}
    source_evidence = None
    auto_repair_report = {
        "schemaVersion": 1, "status": "disabled", "appliedCount": 0,
        "reason": "SCORE_AUTO_REPAIR_RHYTHM_GAPS is disabled",
    }
    if os.environ.get("SCORE_AUTO_REPAIR_RHYTHM_GAPS", "1") == "1":
        progress("source_repair", "正在建立小节与声部时间轴，并回看原谱中的休止符", 56)
        try:
            source_evidence = build_source_repair_evidence(
                job_dir, input_pdf, musicxml, read_musicxml_root,
                omr_analysis=omr_analysis, preflight=preflight, omr_book=omr_book)
            source_repair_before_gaps = source_evidence.get("rhythmGapDetection") or {
                "gaps": [], "overflows": []}
            source_root = read_musicxml_root(musicxml)
            try:
                omr_threshold = float(os.environ.get("SCORE_AUTO_REPAIR_OMR_GRADE", "0.75"))
                visual_threshold = float(os.environ.get("SCORE_AUTO_REPAIR_VISUAL_SCORE", "0.94"))
            except ValueError:
                omr_threshold, visual_threshold = 0.75, 0.94
            auto_repair_report = apply_safe_rhythm_repairs(
                source_root, source_repair_before_gaps,
                source_evidence.get("restClassification") or {},
                max(0.70, min(0.95, omr_threshold)),
                max(0.85, min(0.995, visual_threshold)),
            )
            auto_repair_report["schemaVersion"] = 1
            if auto_repair_report.get("appliedCount"):
                auto_source = os.path.join(job_dir, "auto-repaired-source.musicxml")
                ET.ElementTree(source_root).write(
                    auto_source, encoding="utf-8", xml_declaration=True)
                after_ir = score_ir(
                    read_musicxml_root(auto_source), "canonical-source-repaired",
                    artifact_sha256=file_sha256(auto_source))
                after_gaps = detect_rhythm_gaps(after_ir)
                accepted, source_validation = validate_source_repair_result(
                    source_repair_before_gaps, after_gaps,
                    auto_repair_report.get("applied") or [],
                    source_evidence.get("sourceIndex") or {}, after_ir)
                auto_repair_report["sourceValidation"] = source_validation
                if accepted:
                    musicxml = auto_source
                    auto_repair_report["status"] = "source_accepted_pending_output_validation"
                    auto_repair_report["reason"] = source_validation["reason"]
                else:
                    auto_repair_report["status"] = "source_reverted"
                    auto_repair_report["reason"] = source_validation["reason"]
            else:
                auto_repair_report["reason"] = "没有同时满足缺拍、原谱坐标、视觉类别、谱表几何和风险规则的候选"
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            auto_repair_report = {
                "schemaVersion": 1, "status": "failed", "appliedCount": 0,
                "reason": str(exc),
            }
            musicxml = source_before_rhythm_repair

    auto_repair_path = os.path.join(job_dir, "review", "auto-repair.json")
    os.makedirs(os.path.dirname(auto_repair_path), exist_ok=True)
    with open(auto_repair_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(auto_repair_report, stream, ensure_ascii=False, indent=2)
    os.replace(auto_repair_path + ".tmp", auto_repair_path)
    if os.path.isfile(workspace.manifest_path):
        workspace.register_artifact("source-draft-ir", os.path.join(job_dir, "source-draft-score-ir.json"))
        workspace.register_artifact("source-rhythm-gaps", os.path.join(job_dir, "review", "rhythm-gaps.json"))
        workspace.register_artifact("source-rest-evidence", os.path.join(job_dir, "review", "rest-classification.json"))
        workspace.register_artifact("source-auto-repair", auto_repair_path)
        if musicxml != source_before_rhythm_repair:
            workspace.register_artifact("canonical-source-repaired", musicxml)

    # Persist the exact source MusicXML used for deterministic transposition.
    # Canonical JSON remains the semantic contract; this lossless XML version is
    # the editable source for later human corrections and target regeneration.
    canonical_source_xml = os.path.join(
        job_dir, "scores", "source", "canonical-source.musicxml")
    os.makedirs(os.path.dirname(canonical_source_xml), exist_ok=True)
    shutil.copyfile(musicxml, canonical_source_xml)
    musicxml = canonical_source_xml
    if os.path.isfile(workspace.manifest_path):
        workspace.register_artifact("canonical-source-musicxml", musicxml)

    progress("transposing", "正在计算目标音高并处理临时变音", 58)
    transposed = os.path.join(job_dir, "transposed.musicxml")
    summary = transpose_musicxml(musicxml, transposed, semitones, accidental_preference, source_instrument, target_instrument)
    render_plan = build_render_plan(
        inspection, omr_analysis, intent,
        {"fullScoreRenderer": True, "systemRenderer": False,
         "eventObjectMapping": False, "renderDependencyGraph": False,
         "vectorPatchEngine": False},
    )
    render_plan_path = os.path.join(job_dir, "review", "render-plan.json")
    os.makedirs(os.path.dirname(render_plan_path), exist_ok=True)
    with open(render_plan_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(render_plan, stream, ensure_ascii=False, indent=2)
    os.replace(render_plan_path + ".tmp", render_plan_path)
    workspace = ScoreWorkspace(job_dir)
    if os.path.isfile(workspace.manifest_path):
        workspace.register_artifact("render-plan", render_plan_path)
    output_pdf = os.path.join(job_dir, "output.pdf")
    progress("rendering", "正在生成转调 PDF", 72)
    output_pages, layout_info = render_preserved_score_pdf(
        musescore, transposed, output_pdf, input_pdf, job_dir, timeout,
        "MuseScore 保版式导出 PDF", omr_analysis=omr_analysis
    )
    progress("verifying", "正在检查音高、小节编号和分页", 90)
    verification = verify_score_transposition(
        musicxml, transposed, semitones, source_pages, output_pages,
        omr_analysis, layout_info,
        original_musicxml=original_musicxml, repair_report=structure_repair,
    )

    failed_ids = failed_check_ids(verification)
    if "pitch_shift" in failed_ids:
        repairs.append({
            "id": "retry_pitch_transpose",
            "label": "重新生成转调 MusicXML",
            "status": "running",
            "detail": "检测到音高移动异常，已尝试从原始 MusicXML 重新转调",
        })
        transposed_retry = os.path.join(job_dir, "transposed-retry.musicxml")
        summary = transpose_musicxml(musicxml, transposed_retry, semitones, accidental_preference, source_instrument, target_instrument)
        output_retry = os.path.join(job_dir, "output-retry.pdf")
        output_pages, layout_info = render_preserved_score_pdf(
            musescore, transposed_retry, output_retry, input_pdf, job_dir, timeout,
            "MuseScore 重新导出 PDF", omr_analysis=omr_analysis
        )
        verification = verify_score_transposition(
            musicxml, transposed_retry, semitones, source_pages, output_pages,
            omr_analysis, layout_info,
            original_musicxml=original_musicxml, repair_report=structure_repair,
        )
        os.replace(transposed_retry, transposed)
        os.replace(output_retry, output_pdf)
        if verification["status"] == "passed" or "pitch_shift" not in failed_check_ids(verification):
            repairs[-1]["status"] = "fixed"
            repairs[-1]["detail"] = "重新生成后音高核实已通过"
        else:
            repairs[-1]["status"] = "failed"
            repairs[-1]["detail"] = "重新生成后仍发现音高异常，需要人工校谱"

    verification["repairs"] = repairs
    review = write_score_review(
        job_dir, os.path.join(job_dir, "input.pdf") if os.path.isfile(os.path.join(job_dir, "input.pdf")) else input_pdf,
        musicxml, transposed, layout_info.get("renderedMusicxml"), read_musicxml_root,
        semitones, accidental_preference, source_instrument, target_instrument,
        output_pdf=output_pdf, original_xml=original_musicxml,
        omr_analysis=omr_analysis, preflight=preflight, intent=intent, omr_book=omr_book,
        source_repair_evidence=source_evidence,
    )
    if auto_repair_report.get("status") == "source_accepted_pending_output_validation":
        accepted, output_validation = validate_repair_result(
            source_repair_before_gaps,
            review.get("rhythmGapDetection") or {},
            auto_repair_report.get("applied") or [], verification)
        auto_repair_report["outputValidation"] = output_validation
        if accepted:
            auto_repair_report["status"] = "accepted"
            auto_repair_report["reason"] = output_validation["reason"]
        else:
            # The source-only gate passed, but the transformed/rendered result did
            # not.  Revert the source patch and rebuild the candidate from the
            # unmodified canonical draft.
            progress("source_repair", "自动修复未通过最终验证，正在回退并重新生成候选", 91)
            musicxml = source_before_rhythm_repair
            summary = transpose_musicxml(
                musicxml, transposed, semitones, accidental_preference,
                source_instrument, target_instrument)
            output_pages, layout_info = render_preserved_score_pdf(
                musescore, transposed, output_pdf, input_pdf, job_dir, timeout,
                "MuseScore 回退源谱后重新导出 PDF", omr_analysis=omr_analysis)
            verification = verify_score_transposition(
                musicxml, transposed, semitones, source_pages, output_pages,
                omr_analysis, layout_info, original_musicxml=original_musicxml,
                repair_report=structure_repair)
            review = write_score_review(
                job_dir,
                os.path.join(job_dir, "input.pdf") if os.path.isfile(os.path.join(job_dir, "input.pdf")) else input_pdf,
                musicxml, transposed, layout_info.get("renderedMusicxml"),
                read_musicxml_root, semitones, accidental_preference,
                source_instrument, target_instrument, output_pdf=output_pdf,
                original_xml=original_musicxml, omr_analysis=omr_analysis,
                preflight=preflight, intent=intent, omr_book=omr_book,
                source_repair_evidence=source_evidence)
            auto_repair_report["status"] = "reverted"
            auto_repair_report["reason"] = output_validation["reason"]

    with open(auto_repair_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(auto_repair_report, stream, ensure_ascii=False, indent=2)
    os.replace(auto_repair_path + ".tmp", auto_repair_path)
    repairs.append({
        "id": "repair_evidence_backed_rhythm_gaps",
        "label": "原谱节奏缺口安全修复",
        "status": ("fixed" if auto_repair_report.get("status") == "accepted" else
                   "skipped" if auto_repair_report.get("status") in
                   ("no_safe_candidate", "disabled") else "needs_review"),
        "detail": auto_repair_report.get("reason", "未执行自动节奏修复"),
    })
    verification["repairs"] = repairs
    verification["autoRepair"] = auto_repair_report
    layout_info["renderPlan"] = render_plan
    attach_review(verification, review)
    if auto_repair_report.get("status") == "accepted":
        verification["rhythmGapDetection"]["autoRepairApplied"] = True
        verification["restClassification"]["autoRepairApplied"] = True
    pipeline_status = build_pipeline_status(verification, structure_repair)
    verification["pipeline"] = pipeline_status.to_dict()
    write_pipeline_report(
        job_dir,
        pipeline_status,
        verification=verification,
        artifacts={
            **verification.get("sources", {}),
            "output": pdf_artifact_descriptor(output_pdf),
        },
    )
    summary["sourcePages"] = source_pages
    summary["outputPages"] = output_pages
    summary["measures"] = verification.get("source", {}).get("measures", summary.get("measures", 0))
    return output_pdf, summary, verification


def inspect_candidate_layout(output_pdf, job_dir, expected_pages, workspace, verification):
    """Refresh target-side evidence after each concrete PDF candidate change."""
    target_inspection = inspect_rendered_score_pdf(output_pdf, job_dir, expected_pages)
    verification["targetInspection"] = target_inspection
    checks = [item for item in verification.setdefault("checks", [])
              if item.get("id") != "target_pdf_render"]
    checks.append({
        "id": "target_pdf_render",
        "label": "候选 PDF 可视化与对象层",
        "passed": target_inspection.get("pageCount") == expected_pages,
        "detail": "已从候选 PDF 独立生成 150/400 DPI 页面、对象证据与坐标映射",
    })
    verification["checks"] = checks
    target_inspection_artifacts = {
        "target-render-evidence": ("evidence/target-render-evidence.json", None),
        "target-coordinate-map": ("layout/target/coordinate-map.json", "targetLayoutMap"),
        "target-score-profile": ("inspection/target-score-profile.json", None),
        "target-structure-candidates": ("inspection/target-structure-candidates.json", None),
        "target-inspection-report": ("inspection/target-inspection.json", None),
    }
    for role, (relative, contract) in target_inspection_artifacts.items():
        workspace.register_artifact(role, os.path.join(job_dir, *relative.split("/")), contract)
    visual_audit = compare_visual_layout(job_dir)
    verification["visualLayoutAudit"] = visual_audit
    visual_audit_path = os.path.join(job_dir, "review", "visual-layout-audit.json")
    with open(visual_audit_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(visual_audit, stream, ensure_ascii=False, indent=2)
    os.replace(visual_audit_path + ".tmp", visual_audit_path)
    workspace.register_artifact("visual-layout-audit", visual_audit_path)
    return target_inspection, visual_audit


def system_composition_eligibility(target_inspection, visual_audit):
    if (target_inspection.get("scoreProfile") or {}).get("documentType") not in ("vector", "mixed"):
        return False, "候选 PDF 不是可稳定裁切的矢量谱"
    if visual_audit.get("status") != "passed":
        return False, "源谱与候选谱的页面或谱表系统尚未对齐"
    checks = {item.get("id"): item for item in visual_audit.get("checks", [])}
    required = ("visual_page_count", "visual_system_count", "visual_system_positions",
                "visual_measure_candidates")
    failed = [name for name in required if not checks.get(name, {}).get("passed")]
    if failed:
        return False, "贴回所需的版式检查未全部通过：%s" % "、".join(failed)
    return True, "源谱与候选谱的系统级坐标已建立对应"


def update_score_review_pdf_digest(job_dir, output_pdf):
    path = os.path.join(job_dir, "score-review.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as stream:
        report = json.load(stream)
    report["candidatePdfSha256"] = file_sha256(output_pdf)
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)


def audit_output_pdf_with_omr(output_pdf, target_xml, job_dir, timeout=300):
    """Read the concrete PDF through OMR and compare it with the target model.

    This is independent from MuseScore's own import/export round trip, but it
    remains correlated with source recognition when both use Audiveris.
    """
    audiveris = find_audiveris_command()
    if not audiveris:
        raise RuntimeError("输出 PDF 回读需要 Audiveris")
    output_dir = os.path.join(job_dir, "output-pdf-omr")
    os.makedirs(output_dir, exist_ok=True)
    log = run_command(
        list(audiveris) + [
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true",
            "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.multiWholeHeadChords=true",
            "-batch", "-export", "-output", output_dir, output_pdf,
        ],
        job_dir, timeout, "输出 PDF 独立 OMR 回读",
    )
    recognized = newest_musicxml_file(output_dir)
    analysis = analyze_audiveris_output(log)
    if not recognized:
        raise RuntimeError("输出 PDF 回读没有生成 MusicXML")
    expected_root = read_musicxml_root(target_xml)
    recognized_root = read_musicxml_root(recognized)
    comparison = compare_rendered_score(expected_root, recognized_root)
    semantic = comparison.get("semanticAudit") or {}
    if len(semantic.get("issues", [])) > 100:
        semantic["issues"] = semantic["issues"][:100]
        semantic["truncated"] = True
    passed = bool(comparison.get("eventsMatch") and comparison.get("marksMatch")
                  and semantic.get("passed") and not analysis.get("exportErrors"))
    reason = ("从最终 PDF 重新识别的音符、节奏和标记与目标数据一致"
              if passed else "从最终 PDF 重新识别后发现音符、节奏或标记冲突")
    report = {
        "schemaVersion": 1,
        "status": "observed_match" if passed else "conflict",
        "reason": reason,
        "evidenceLevel": "pdf_rerecognition_same_omr_family",
        "sourcePdfSha256": file_sha256(output_pdf),
        "targetMusicxmlSha256": file_sha256(target_xml),
        "recognizedMusicxmlSha256": file_sha256(recognized),
        "recognizedMusicxml": os.path.relpath(recognized, job_dir).replace("\\", "/"),
        "comparison": comparison,
        "exportErrors": analysis.get("exportErrors", []),
        "outputAllowed": False,
        "verificationAuthority": "none",
        "limits": "回读可发现渲染丢失和结构冲突；与源谱识别使用同类 OMR，不能独立证明原谱识别正确",
    }
    report_path = os.path.join(job_dir, "review", "output-pdf-omr-audit.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    os.replace(report_path + ".tmp", report_path)
    return report, recognized, report_path


def attach_output_pdf_omr_observation(job_dir, verification, report):
    matched = report.get("status") == "observed_match"
    status = "OBSERVED_MATCH" if matched else "CONFLICT"
    reason = ("从最终 PDF 重新识别的音符、节奏和标记与目标数据一致"
              if matched else "从最终 PDF 重新识别后发现音符、节奏或标记冲突")
    verification["outputPdfOmrAudit"] = report
    verification.setdefault("reviewCoverage", {})["outputPdfRecognition"] = status
    existing_checks = []
    for check in verification.setdefault("checks", []):
        if check.get("id") == "output_pdf_evidence":
            existing_checks.append({
                "id": "output_pdf_evidence", "label": check.get("label", "输出 PDF 的独立核验"),
                "passed": matched,
                "detail": reason + "；本检查与源谱识别使用同类 OMR，不证明原谱识别正确",
            })
        else:
            existing_checks.append(check)
    verification["checks"] = existing_checks
    comparison = report.get("comparison") or {}
    for check in comparison.get("checks", []):
        item = dict(check)
        item["id"] = "output_pdf_omr_" + str(item.get("id") or "check")
        item["label"] = "PDF 回读：" + str(item.get("label") or "输出乐谱")
        verification.setdefault("checks", []).append(item)
    review_path = os.path.join(job_dir, "score-review.json")
    if os.path.isfile(review_path):
        with open(review_path, encoding="utf-8") as stream:
            review = json.load(stream)
        review["outputPdfRecognition"] = {
            "status": status, "reason": reason,
            "evidenceLevel": report.get("evidenceLevel"),
            "verificationAuthority": "none",
        }
        with open(review_path + ".tmp", "w", encoding="utf-8") as stream:
            json.dump(review, stream, ensure_ascii=False, indent=2)
        os.replace(review_path + ".tmp", review_path)



def process_score_job(job_id, request, progress):
    job_dir = os.path.join(SCORE_DIR, job_id)
    input_pdf = os.path.join(job_dir, "input.pdf")
    workspace = ScoreWorkspace(job_dir)
    warnings = []
    try:
        intent = request.get("intent") or build_transposition_intent(request)
        request["intent"] = intent
        if not os.path.isfile(workspace.manifest_path):
            workspace.initialize(job_id, input_pdf, request, intent)
        queue_progress = progress

        def tracked_progress(stage, message, percent):
            workspace.update_stage(stage, message, percent)
            queue_progress(stage, message, percent)

        progress = tracked_progress
        if request.get("manualEdit"):
            return process_score_edit(job_id, request, progress)
        progress("inspecting", "正在检查 PDF 和原谱结构", 12)
        source_pages = get_pdf_page_count(input_pdf)
        if not source_pages or source_pages > 20:
            raise RuntimeError("请上传 1 至 20 页的有效乐谱 PDF")
        engine = os.environ.get("SCORE_ENGINE", "omr")
        if engine not in ("omr", "deepseek-agent"):
            raise RuntimeError("转谱引擎配置无效")
        prepared_pdf, preflight = preflight_pdf(input_pdf, job_dir)
        inspection = None
        try:
            workspace.update_stage("inspecting", "正在建立多尺度 PDF 视觉工作区", 18)
            inspection = inspect_score_pdf(input_pdf, job_dir, preflight)
            workspace.record_runtime(
                engines={"pdfInspection": inspection.get("engine", {})},
                parameters={
                    "previewDpi": inspection.get("scoreProfile", {}).get("recognitionPlan", {}).get("previewDpi"),
                    "analysisDpi": inspection.get("scoreProfile", {}).get("recognitionPlan", {}).get("analysisDpi"),
                    "detailDpi": inspection.get("scoreProfile", {}).get("recognitionPlan", {}).get("detailDpi"),
                },
            )
            inspection_artifacts = {
                "source-evidence": ("evidence/source-evidence.json", "sourceEvidence"),
                "source-coordinate-map": ("layout/source/coordinate-map.json", "sourceLayoutMap"),
                "score-profile": ("inspection/score-profile.json", None),
                "structure-candidates": ("inspection/structure-candidates.json", None),
                "inspection-report": ("inspection/inspection.json", None),
            }
            for role, (relative, contract) in inspection_artifacts.items():
                workspace.register_artifact(
                    role, os.path.join(job_dir, *relative.split("/")), contract)
        except RuntimeError as exc:
            inspection = {"status": "unavailable", "reason": str(exc)}
            warnings.append("PDF 多尺度视觉检查暂时不可用，已继续使用原有识谱流程")
        if preflight["changed"]:
            warnings.append("已修复 PDF 内嵌字体的编码或索引错误，再进行识谱；原始文件已保留")
        if preflight.get("issues"):
            issue_pages = sorted({str(item.get("page")) for item in preflight["issues"] if item.get("page")})
            warnings.append("第 %s 页存在无法修复的内嵌字体问题；已从渲染图继续识别，结果必须人工复核" %
                            "、".join(issue_pages))

        omr_variant = None
        if inspection and inspection.get("scoreProfile", {}).get("documentType") in ("scan", "mixed"):
            try:
                workspace.update_stage("inspecting", "正在为扫描谱建立增强识谱输入", 20)
                omr_variant, variant_report = prepare_omr_variant(input_pdf, job_dir, 300)
                workspace.register_artifact("omr-normalized-input", omr_variant,
                                            metadata={"representation": variant_report.get("representation")})
            except RuntimeError as exc:
                warnings.append("扫描谱增强识谱输入暂时不可用，已保留原 PDF 继续处理")

        generic_omr = False
        # Reviewed gold-set files are regression fixtures only.  Production
        # requests always use the general reconstruction pipeline and can never
        # branch on a known PDF digest, file name, page count or coordinates.
        processed = (process_agent_score(job_dir, request, progress)
                     if engine == "deepseek-agent" else None)
        if processed is None:
            generic_omr = True
            instrument_mode = request.get("transposeMode") == "instrument"
            processed = process_score_pdf(
                prepared_pdf, job_dir, request["semitones"], request["accidentalPreference"],
                progress=progress,
                source_instrument=request["sourceInstrument"] if instrument_mode else None,
                target_instrument=request["targetInstrument"] if instrument_mode else None,
                preflight=preflight, intent=intent, inspection=inspection,
                omr_variant=omr_variant,
            )
            warnings.append("本次使用自动识谱；识别得到的音符已检查移调一致性，原谱中的复杂符号仍需复核")
        output_pdf, summary, verification = processed
        try:
            workspace.update_stage("verifying", "正在独立检查候选 PDF 的页面和坐标", 94)
            expected_pages = summary.get("outputPages") or source_pages
            target_inspection, visual_audit = inspect_candidate_layout(
                output_pdf, job_dir, expected_pages, workspace, verification)
            if generic_omr:
                try:
                    workspace.update_stage("rendering", "正在保留原谱标题、页眉和页码", 95)
                    preserved_pdf, static_content = preserve_score_headers(
                        job_dir, input_pdf, output_pdf)
                    shutil.copy2(preserved_pdf, output_pdf)
                    static_content["status"] = "applied"
                    verification["staticContentPreservation"] = static_content
                    static_report = os.path.join(
                        job_dir, "review", "static-content-preservation.json")
                    update_score_review_pdf_digest(job_dir, output_pdf)
                    workspace.register_artifact("header-preserved-pdf", preserved_pdf)
                    workspace.register_artifact("static-content-preservation", static_report)
                except (RuntimeError, OSError, ValueError) as exc:
                    verification["staticContentPreservation"] = {
                        "status": "skipped", "reason": str(exc),
                        "semanticVerification": False,
                    }
                    warnings.append("原谱标题区无法安全贴回，已保留识谱得到的标题文字供复核")
            if generic_omr and os.environ.get("SCORE_SYSTEM_COMPOSITOR", "0") == "1":
                eligible, reason = system_composition_eligibility(target_inspection, visual_audit)
                verification["systemComposition"] = {
                    "status": "eligible" if eligible else "skipped",
                    "reason": reason,
                    "semanticVerification": False,
                }
                if eligible:
                    full_candidate = os.path.join(job_dir, "candidates", "full-reengraved.pdf")
                    try:
                        workspace.update_stage(
                            "rendering", "正在保留原页外围内容并按谱表系统贴回", 95)
                        os.makedirs(os.path.dirname(full_candidate), exist_ok=True)
                        shutil.copy2(output_pdf, full_candidate)
                        composed_pdf, composition = compose_score_systems(
                            job_dir, input_pdf, full_candidate)
                        shutil.copy2(composed_pdf, output_pdf)
                        composition["status"] = "applied"
                        composition["reason"] = reason
                        composition_plan = build_render_plan(
                            inspection, verification.get("omr", {}), intent,
                            {"fullScoreRenderer": True, "systemRenderer": True,
                             "systemCorrespondence": True, "eventObjectMapping": False,
                             "renderDependencyGraph": False, "vectorPatchEngine": False},
                        )
                        verification.setdefault("layout", {})["renderPlan"] = composition_plan
                        target_inspection, post_audit = inspect_candidate_layout(
                            output_pdf, job_dir, expected_pages, workspace, verification)
                        post_eligible, post_reason = system_composition_eligibility(
                            target_inspection, post_audit)
                        if not post_eligible:
                            raise RuntimeError("按系统贴回后的版式检查未通过：" + post_reason)
                        composition["postCompositionLayoutAudit"] = {
                            "status": post_audit.get("status"),
                            "checks": post_audit.get("checks", []),
                            "semanticVerification": False,
                        }
                        verification["systemComposition"] = composition
                        composition_path = os.path.join(job_dir, "review", "system-composition.json")
                        with open(composition_path + ".tmp", "w", encoding="utf-8") as stream:
                            json.dump(composition, stream, ensure_ascii=False, indent=2)
                        os.replace(composition_path + ".tmp", composition_path)
                        update_score_review_pdf_digest(job_dir, output_pdf)
                        workspace.register_artifact("full-reengraved-pdf", full_candidate)
                        workspace.register_artifact("system-composed-pdf", composed_pdf)
                        workspace.register_artifact("system-composition", composition_path)
                    except (RuntimeError, OSError, ValueError) as exc:
                        if os.path.isfile(full_candidate):
                            shutil.copy2(full_candidate, output_pdf)
                            try:
                                inspect_candidate_layout(
                                    output_pdf, job_dir, expected_pages, workspace, verification)
                            except (RuntimeError, OSError, ValueError):
                                pass
                        update_score_review_pdf_digest(job_dir, output_pdf)
                        verification["systemComposition"] = {
                            "status": "fallback_full_reengrave", "reason": str(exc),
                            "semanticVerification": False,
                        }
                        warnings.append("按谱表保留原版式未通过安全门槛，已保留完整重排的候选 PDF")
        except (RuntimeError, OSError, ValueError) as exc:
            verification["targetInspection"] = {"status": "unavailable", "reason": str(exc)}
            warnings.append("候选 PDF 的独立视觉检查暂时不可用，结果必须人工复核")
        try:
            output_omr_max_pages = max(1, min(20, int(
                os.environ.get("SCORE_OUTPUT_OMR_AUDIT_MAX_PAGES", "8"))))
        except ValueError:
            output_omr_max_pages = 8
        output_page_count = int(summary.get("outputPages") or source_pages)
        if (generic_omr and os.environ.get("SCORE_OUTPUT_OMR_AUDIT", "0") == "1"
                and output_page_count <= output_omr_max_pages):
            try:
                workspace.update_stage("verifying", "正在从最终 PDF 重新识别并比较目标乐谱", 96)
                output_omr, recognized_xml, output_omr_path = audit_output_pdf_with_omr(
                    output_pdf, os.path.join(job_dir, "transposed.musicxml"), job_dir,
                    min(900, 180 + 45 * output_page_count),
                )
                attach_output_pdf_omr_observation(job_dir, verification, output_omr)
                workspace.register_artifact("output-pdf-omr-musicxml", recognized_xml)
                workspace.register_artifact("output-pdf-omr-audit", output_omr_path)
                workspace.record_runtime(engines={"outputPdfRecognition": "Audiveris PDF rerecognition"})
            except (RuntimeError, OSError, ValueError) as exc:
                verification["outputPdfOmrAudit"] = {
                    "status": "unavailable", "reason": str(exc),
                    "outputAllowed": False, "verificationAuthority": "none",
                }
                warnings.append("最终 PDF 的独立 OMR 回读暂时不可用，已保留候选 PDF 供人工校对")
        elif (generic_omr and os.environ.get("SCORE_OUTPUT_OMR_AUDIT", "0") == "1"
              and output_page_count > output_omr_max_pages):
            verification["outputPdfOmrAudit"] = {
                "status": "skipped", "reason": "候选 PDF 超过本轮 OMR 回读的 %s 页上限" % output_omr_max_pages,
                "outputAllowed": False, "verificationAuthority": "none",
            }
        if (verification.get("status") != "passed" and
                os.environ.get("SCORE_AI_VISUAL_REVIEW", "0") == "1"):
            try:
                workspace.update_stage("ai_review", "AI 正在查看已定位的疑点区域", 96)
                ai_review = run_ai_visual_review(job_dir)
                if ai_review:
                    verification["aiVisualReview"] = ai_review
                    verification["aiNote"] = (ai_review.get("modelOutput") or {}).get("summary")
                    workspace.register_artifact(
                        "ai-visual-review", os.path.join(job_dir, "review", "ai-visual-review.json"))
                    workspace.record_runtime(models={"visualReview": ai_review.get("model")})
            except RuntimeError as exc:
                warnings.append("AI 局部视觉复核暂时不可用；候选 PDF 和人工校对清单仍可使用")
        workspace.record_runtime(
            engines={"recognition": verification.get("engine", engine),
                     "transposition": "deterministic-musicxml-v1"},
            models={"agent": os.environ.get("SCORE_AGENT_MODEL", "") if engine == "deepseek-agent" else ""},
        )
        verification["preflight"] = preflight
        verification["inspection"] = inspection
        pipeline = verification.get("pipeline")
        if pipeline is None:
            pipeline = build_pipeline_status(verification).to_dict()
        if warnings and pipeline.get("overallStatus") == PIPELINE_VERIFIED:
            pipeline["overallStatus"] = PIPELINE_VERIFIED_WITH_WARNINGS
        warnings.extend(item for item in verification_warnings(verification) if item not in warnings)
        warnings.extend(item for item in pipeline.get("warnings", []) if item not in warnings)
        pipeline["warnings"] = warnings
        verification["pipeline"] = pipeline
        write_pipeline_report(job_dir, pipeline, verification, {
            "originalPdf": pdf_artifact_descriptor(input_pdf, "original"),
            "output": pdf_artifact_descriptor(output_pdf),
        })
        contract_artifacts = {
            "evidence-graph": ("evidence/evidence-graph.json", "evidenceGraph"),
            "canonical-source-score": ("scores/source/canonical-score.json", "canonicalSourceScore"),
            "canonical-source-musicxml": ("scores/source/canonical-source.musicxml", None),
            "target-score": ("scores/target/target-score.json", "targetScore"),
            "source-layout-map": ("layout/source/source-layout-map.json", "sourceLayoutMap"),
            "target-layout-map": ("layout/target/target-layout-map.json", "targetLayoutMap"),
            "transformation-proof": ("review/transformation-proof.json", "transformationProof"),
            "rhythm-gap-report": ("review/rhythm-gaps.json", None),
            "rest-classification": ("review/rest-classification.json", None),
            "auto-repair": ("review/auto-repair.json", None),
            "candidate-pdf": ("output.pdf", None),
            "candidate-musicxml": ("transposed.musicxml", None),
        }
        for role, (relative, contract) in contract_artifacts.items():
            workspace.register_artifact(
                role, os.path.join(job_dir, *relative.split("/")), contract)
        source_version = workspace.register_score_version(
            "canonical_source_musicxml",
            os.path.join(job_dir, "scores", "source", "canonical-source.musicxml"))
        workspace.register_score_version(
            "canonical_source_contract",
            os.path.join(job_dir, "scores", "source", "canonical-score.json"),
            source_version.get("versionId") if source_version else None)
        workspace.register_score_version(
            "target_transposed", os.path.join(job_dir, "scores", "target", "target-score.json"),
            source_version.get("versionId") if source_version else None,
            {"intentId": intent.get("intentId")},
        )
        allowed = bool(pipeline.get("outputAllowed")) and pipeline.get("overallStatus") in DOWNLOADABLE_PIPELINE_STATUSES
        workspace.update_stage(
            "completed" if allowed else "needs_review",
            "转调完成，PDF 已可下载" if allowed else "已生成候选 PDF，等待人工校对",
            100,
        )
        return {
            "status": "completed" if allowed else "needs_review", "stage": "completed" if allowed else "needs_review",
            "progress": 100, "message": "转调完成，PDF 已可下载" if allowed else "结果未通过全部检查，请查看具体问题",
            "pipelineStatus": pipeline.get("overallStatus", PIPELINE_NEEDS_REVIEW), "outputAllowed": allowed,
            "outputUrl": "/api/score/transpositions/%s/output" % job_id if allowed else "",
            "fileName": "转调-" + request["name"], "warnings": warnings, "verification": verification,
            "summary": {
                "transposeMode": request.get("transposeMode", "instrument"),
                "sourceInstrument": request["sourceInstrument"], "targetInstrument": request["targetInstrument"],
                "semitones": request["semitones"],
                "sourcePages": summary.get("sourcePages", 0), "outputPages": summary.get("outputPages", 0),
                "sourceDocumentPages": request.get("sourcePageCount", summary.get("sourcePages", 0)),
                "selectedPages": request.get("selectedPages", []),
                "noteEvents": summary.get("noteEvents", 0), "measures": summary.get("measures", 0),
                "outputSize": os.path.getsize(output_pdf), "engine": verification.get("engine", "omr"),
            },
        }
    except (PipelineRejected, RuntimeError) as exc:
        logging.warning("score processing stopped for %s: %s", job_id, exc)
        existing = read_pipeline_report(job_dir)
        verification = existing.get("verification") or {}
        verification.setdefault("status", "failed")
        verification.setdefault("checks", [])
        verification.setdefault("summary", str(exc))
        pipeline = PipelineStatus("failed", PIPELINE_REJECTED, fatal=True, warnings=[str(exc)], output_allowed=False)
        write_pipeline_report(job_dir, pipeline, verification)
        workspace.update_stage("failed", str(exc), 100)
        return {"status": "failed", "stage": "failed", "progress": 100, "message": str(exc),
                "pipelineStatus": PIPELINE_REJECTED, "outputAllowed": False, "outputUrl": "",
                "warnings": [str(exc)], "verification": verification}


def process_score_edit(job_id, request, progress):
    job_dir = os.path.join(SCORE_DIR, job_id)
    workspace = ScoreWorkspace(job_dir)
    parent_dir = os.path.join(SCORE_DIR, request["parentJobId"])
    parent = read_pipeline_report(parent_dir).get("verification", {})
    source_pdf = os.path.join(job_dir, "input.pdf")
    xml_path = os.path.join(job_dir, "transposed.musicxml")
    source_xml = canonical_source_musicxml(job_dir)
    output = os.path.join(job_dir, "output.pdf")
    progress("rendering", ("正在使用校正版源谱生成新的目标乐器谱"
                           if request.get("retarget") else "正在生成修改后的 PDF"), 65)
    count, layout = render_preserved_score_pdf(find_musescore_command(), xml_path, output, source_pdf,
                                              job_dir, 180, "人工校谱导出", omr_analysis=parent.get("omr", {}))
    audit = layout["renderAudit"]
    details = audit.get("semanticAudit", {})
    source_pages = get_pdf_page_count(source_pdf)
    inherited = [dict(check, detail="上一版本遗留，尚未重新核验：" + str(check.get("detail", "")))
                 for check in parent.get("checks", [])
                 if not check.get("passed") and check.get("id") in ("source_structure", "measure_count", "line_start_numbers", "omr_structure", "omr_export", "pdf_barlines")]
    checks = audit["checks"] + inherited + [
        {"id": "page_count", "label": "原谱页数", "passed": count == source_pages,
         "detail": "原谱 %s 页，修改后 %s 页" % (source_pages, count)},
        {"id": "system_layout", "label": "原谱分行", "passed": bool(layout.get("systemCountValidated")) and
         layout.get("outputSystemsPerPage") == layout.get("expectedSystemsPerPage"),
         "detail": "修改后仍需对照每行小节号与原谱位置"},
        {"id": "source_music_evidence", "label": "原谱逐音核对", "passed": False,
         "detail": "本版包含人工修改，仍需对照原谱核对全部内容"}]
    verification = {"status": "failed", "strict": False, "checks": checks,
                    "summary": ("已使用校正版源谱生成新的目标乐器谱，请核对候选 PDF。"
                                if request.get("retarget") else
                                "人工修改已生成候选 PDF，请核对修改位置及其相邻音符。"),
                    "issues": details.get("issues", []), "issueCount": details.get("issueCount", 0),
                    "manualEdits": request["changes"], "parentJobId": request["parentJobId"],
                    "omr": parent.get("omr", {}), "layout": layout}
    if request.get("sourceBasedEdit") and source_xml:
        interval = (request.get("intent") or {}).get("interval") or {}
        instrument_mode = (request.get("intent") or {}).get("mode") == "instrument_rewrite"
        review = write_score_review(
            job_dir, source_pdf, source_xml, xml_path,
            layout.get("renderedMusicxml"), read_musicxml_root,
            interval.get("chromaticSemitones", 0),
            ((request.get("intent") or {}).get("spellingPolicy") or {}).get(
                "accidentalPreference", "auto"),
            (request.get("intent") or {}).get("sourceInstrument") if instrument_mode else None,
            (request.get("intent") or {}).get("targetInstrument") if instrument_mode else None,
            output_pdf=output, original_xml=source_xml,
            omr_analysis=parent.get("omr", {}), preflight=parent.get("preflight", {}),
            intent=request.get("intent"),
            omr_book=newest_omr_file(os.path.join(parent_dir, "omr")))
        attach_review(verification, review)
        verification["sourceEdit"] = {
            "basis": "canonical_source_musicxml",
            "sourceRegenerated": True,
            "targetRegenerated": True,
            "reusableForNewTargets": True,
        }
        verification["summary"] = ("已复用校正版源谱并重新转调生成候选 PDF，请核对目标乐器和谱面。"
                                   if request.get("retarget") else
                                   "源谱修正已写入并重新转调生成候选 PDF，请核对修改位置及相邻内容。")
    pipeline = PipelineStatus("needs_review", PIPELINE_NEEDS_REVIEW, warnings=[verification["summary"]], output_allowed=False)
    verification["pipeline"] = pipeline.to_dict()
    write_pipeline_report(job_dir, pipeline, verification, {"output": pdf_artifact_descriptor(output)})
    workspace.register_artifact("candidate-pdf", output)
    workspace.register_artifact("candidate-musicxml", xml_path)
    if source_xml:
        workspace.register_artifact("canonical-source-musicxml", source_xml)
    for role, relative, contract in (
            ("canonical-source-score", "scores/source/canonical-score.json", "canonicalSourceScore"),
            ("target-score", "scores/target/target-score.json", "targetScore"),
            ("evidence-graph", "evidence/evidence-graph.json", "evidenceGraph"),
            ("source-layout-map", "layout/source/source-layout-map.json", "sourceLayoutMap"),
            ("target-layout-map", "layout/target/target-layout-map.json", "targetLayoutMap"),
            ("transformation-proof", "review/transformation-proof.json", "transformationProof")):
        workspace.register_artifact(
            role, os.path.join(job_dir, *relative.split("/")), contract)
    workspace.update_stage("needs_review", verification["summary"], 100)
    signature = score_signature(xml_path)
    return {"jobId": job_id, "status": "needs_review", "stage": "needs_review", "progress": 100,
            "outputAllowed": False, "outputUrl": "", "pipelineStatus": PIPELINE_NEEDS_REVIEW,
            "fileName": (("重新转调-" if request.get("retarget") else "人工修改-") +
                         request.get("name", "score.pdf")), "verification": verification,
            "message": verification["summary"], "warnings": [verification["summary"]],
            "summary": dict(request.get("summary", {}), noteEvents=signature["noteCount"],
                            measures=signature["measureCount"], sourcePages=source_pages,
                            outputPages=count, outputSize=os.path.getsize(output))}


SCORE_JOBS = ScoreJobs(SCORE_DIR, process_score_job)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "ZHMApi/3.0"

    def log_message(self, fmt, *args):
        logging.info("%s %s", self.address_string(), fmt % args)

    def json_response(self, status, payload, headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def body(self, max_bytes=1024 * 1024):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("请求大小无效")
        if length <= 0 or length > max_bytes:
            raise ValueError("请求内容为空或过大")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求格式无效")

    def client_hash(self):
        raw = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        return hash_value(raw)

    def visitor_hash(self, data=None):
        value = self.headers.get("X-Visitor-ID", "") or ((data or {}).get("visitorId", ""))
        return hash_value((value[:128] if value else self.client_hash()))

    def admin_token(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        item = jar.get(ADMIN_COOKIE)
        return item.value if item else ""

    def is_admin(self):
        token = self.admin_token()
        if not token:
            return False
        with connect() as db:
            row = db.execute("SELECT expires_at FROM admin_sessions WHERE token_hash=?", (hash_value(token),)).fetchone()
            return bool(row and row["expires_at"] > utcnow())

    def require_admin(self):
        if self.is_admin():
            return True
        self.json_response(401, {"success": False, "message": "请先登录管理后台"})
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self.json_response(200, {"success": True})
        if parsed.path == "/api/content":
            return self.get_content()
        if parsed.path == "/api/stars":
            return self.get_stars()
        if parsed.path == "/api/messages":
            return self.get_messages(parse_qs(parsed.query))
        if parsed.path == "/api/identity":
            return self.get_identity(parse_qs(parsed.query))
        if parsed.path == "/api/admin/session":
            return self.json_response(200, {"success": True, "authenticated": self.is_admin()})
        if parsed.path == "/api/admin/analytics":
            if self.require_admin(): return self.get_analytics(parse_qs(parsed.query))
            return
        if parsed.path == "/api/admin/messages":
            if self.require_admin(): return self.get_admin_messages(parse_qs(parsed.query))
            return
        if parsed.path == "/api/admin/rest-annotations":
            if self.require_admin(): return self.get_rest_annotations(parse_qs(parsed.query))
            return
        if parsed.path == "/api/admin/rest-annotations/export":
            if self.require_admin(): return self.export_rest_annotations()
            return
        match = ADMIN_REST_IMAGE_RE.match(parsed.path)
        if match:
            if self.require_admin(): return self.get_rest_annotation_image(match.group(1))
            return
        match = SCORE_STATUS_RE.match(parsed.path)
        if match:
            return self.get_score_status(match.group(1))
        match = SCORE_OUTPUT_RE.match(parsed.path)
        if match:
            return self.get_score_output(match.group(1))
        match = SCORE_REVIEW_RE.match(parsed.path)
        if match and match.group(2) not in ("edits", "retarget"):
            return self.get_score_review_asset(match.group(1), match.group(2), parse_qs(parsed.query))
        return self.json_response(404, {"success": False, "message": "接口不存在"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/admin/login": return self.admin_login()
            if path == "/api/admin/logout": return self.admin_logout()
            if path == "/api/analytics": return self.track_view()
            if path == "/api/stars": return self.toggle_site_star()
            if path == "/api/identity/email-code": return self.request_email_code()
            if path == "/api/identity/verify-email": return self.verify_email_code()
            if path == "/api/messages": return self.create_message()
            if path == "/api/chat": return self.chat()
            if path == "/api/score/transpositions": return self.create_score_transposition()
            match = SCORE_REVIEW_RE.match(path)
            if match and match.group(2) == "edits": return self.create_score_edits(match.group(1))
            if match and match.group(2) == "retarget": return self.create_score_retarget(match.group(1))
            if path == "/api/admin/upload":
                if self.require_admin(): return self.upload()
                return
            if path == "/api/admin/rest-annotations/refresh":
                if self.require_admin(): return self.refresh_rest_annotations()
                return
            match = REPLY_RE.match(path)
            if match: return self.create_reply(match.group(1))
            match = ENTITY_RE.match(path)
            if match:
                entity_type = match.group(1).lower()[:-1]
                return self.toggle_like(entity_type, match.group(2)) if match.group(3).lower() == "likes" else self.report(entity_type, match.group(2))
            return self.json_response(404, {"success": False, "message": "接口不存在"})
        except ValueError as exc:
            return self.json_response(400, {"success": False, "message": str(exc)})

    def do_PUT(self):
        match = ADMIN_REST_SAMPLE_RE.match(urlparse(self.path).path)
        if match:
            if not self.require_admin(): return
            try:
                payload = self.body(128 * 1024)
                item = update_sample(REST_ANNOTATION_DIR, match.group(1), payload)
                return self.json_response(200, {"success": True, "data": item,
                                                "message": "训练标注已保存"})
            except (ValueError, OSError) as exc:
                return self.json_response(409, {"success": False, "message": str(exc)})
        if urlparse(self.path).path == "/api/admin/content" and self.require_admin():
            try:
                payload = self.body(2 * 1024 * 1024)
                if not isinstance(payload, dict): raise ValueError("内容格式无效")
                temp = CONTENT_PATH + ".tmp"
                with open(temp, "w", encoding="utf-8") as file: json.dump(payload, file, ensure_ascii=False, indent=2)
                os.replace(temp, CONTENT_PATH)
                return self.json_response(200, {"success": True, "message": "网站内容已保存并立即生效"})
            except ValueError as exc:
                return self.json_response(400, {"success": False, "message": str(exc)})
        return self.json_response(404, {"success": False, "message": "接口不存在"})

    def do_PATCH(self):
        match = ADMIN_ENTITY_RE.match(urlparse(self.path).path)
        if not match or not self.require_admin(): return
        try:
            data = self.body()
            table, entity_id = match.group(1).lower(), match.group(2)
            fields, values = [], []
            if "status" in data and data["status"] in ("approved", "pending", "hidden"):
                fields.append("status=?"); values.append(data["status"])
            if table == "messages" and "pinned" in data:
                fields.append("pinned=?"); values.append(1 if data["pinned"] else 0)
            if not fields: raise ValueError("没有可更新的字段")
            values.append(entity_id)
            with connect() as db: db.execute(f"UPDATE {table} SET {','.join(fields)} WHERE id=?", values)
            return self.json_response(200, {"success": True, "message": "状态已更新"})
        except ValueError as exc:
            return self.json_response(400, {"success": False, "message": str(exc)})

    def do_DELETE(self):
        match = ADMIN_ENTITY_RE.match(urlparse(self.path).path)
        if not match or not self.require_admin(): return
        table, entity_id = match.group(1).lower(), match.group(2)
        with connect() as db:
            if table == "messages":
                reply_ids = [row[0] for row in db.execute("SELECT id FROM replies WHERE message_id=?", (entity_id,))]
                db.execute("DELETE FROM likes WHERE entity_type='message' AND entity_id=?", (entity_id,))
                for rid in reply_ids: db.execute("DELETE FROM likes WHERE entity_type='reply' AND entity_id=?", (rid,))
            else: db.execute("DELETE FROM likes WHERE entity_type='reply' AND entity_id=?", (entity_id,))
            db.execute(f"DELETE FROM {table} WHERE id=?", (entity_id,))
        return self.json_response(200, {"success": True, "message": "内容已删除"})

    def get_content(self):
        if not os.path.exists(CONTENT_PATH): return self.json_response(200, {"success": True, "data": None})
        try:
            with open(CONTENT_PATH, encoding="utf-8") as file: data = json.load(file)
            return self.json_response(200, {"success": True, "data": data})
        except (OSError, json.JSONDecodeError):
            return self.json_response(500, {"success": False, "message": "内容配置读取失败"})

    def get_messages(self, query):
        page = max(1, min(10000, int(query.get("page", ["1"])[0])))
        size = max(1, min(20, int(query.get("pageSize", ["6"])[0])))
        visitor = self.visitor_hash()
        with connect() as db:
            total = db.execute("SELECT COUNT(*) FROM messages WHERE status='approved'").fetchone()[0]
            rows = db.execute("SELECT * FROM messages WHERE status='approved' ORDER BY pinned DESC, created_at DESC LIMIT ? OFFSET ?", (size, (page - 1) * size)).fetchall()
            items = []
            for row in rows:
                replies = db.execute("SELECT * FROM replies WHERE message_id=? AND status='approved' ORDER BY created_at", (row["id"],)).fetchall()
                def entity_payload(entity, entity_type):
                    count = db.execute("SELECT COUNT(*) FROM likes WHERE entity_type=? AND entity_id=?", (entity_type, entity["id"])).fetchone()[0]
                    liked = db.execute("SELECT 1 FROM likes WHERE entity_type=? AND entity_id=? AND visitor_hash=?", (entity_type, entity["id"], visitor)).fetchone() is not None
                    payload = {"id": entity["id"], "nickname": entity["nickname"], "content": entity["content"], "createdAt": entity["created_at"], "likeCount": count, "liked": liked}
                    if entity_type == "message":
                        payload["emailVerified"] = bool(entity["email_verified"])
                    return payload
                message = entity_payload(row, "message")
                message["pinned"] = bool(row["pinned"])
                message["replies"] = [entity_payload(reply, "reply") for reply in replies]
                items.append(message)
        return self.json_response(200, {"success": True, "data": {"items": items, "page": page, "pageSize": size, "total": total}})

    def get_identity(self, query):
        email = str(query.get("email", [""])[0]).strip().lower()
        if not email:
            return self.json_response(200, {"success": True, "data": {"verified": False}})
        if not EMAIL_RE.match(email):
            raise ValueError("邮箱格式不正确")
        visitor, email_hash = self.visitor_hash(), hash_value(email)
        with connect() as db:
            row = db.execute(
                "SELECT nickname, verified_at FROM verified_identities WHERE visitor_hash=? AND email_hash=?",
                (visitor, email_hash),
            ).fetchone()
        return self.json_response(200, {"success": True, "data": {"verified": bool(row), "nickname": row["nickname"] if row else ""}})

    def request_email_code(self):
        data = self.body()
        email = str(data.get("email", "")).strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("请输入有效邮箱")
        visitor, actor, email_hash = self.visitor_hash(data), self.client_hash(), hash_value(email)
        if not smtp_configured():
            return self.json_response(503, {"success": False, "message": "邮箱验证码服务尚未配置，暂时可以直接留言"})
        code = f"{secrets.randbelow(1000000):06d}"
        now = utcnow()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        with connect() as db:
            if not rate_allowed(db, "email_code", actor, email_hash, 1, 60):
                raise ValueError("验证码发送太频繁，请稍后再试")
            db.execute(
                "INSERT INTO email_verifications(id,visitor_hash,email_hash,code_hash,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), visitor, email_hash, hash_value(code), now, expires),
            )
        try:
            send_verification_email(email, code)
        except (OSError, smtplib.SMTPException, RuntimeError):
            logging.exception("failed to send verification email")
            return self.json_response(503, {"success": False, "message": "验证码邮件发送失败，请稍后再试"})
        return self.json_response(200, {"success": True, "message": "验证码已发送，请查看邮箱"})

    def verify_email_code(self):
        data = self.body()
        email = str(data.get("email", "")).strip().lower()
        code = re.sub(r"\D", "", str(data.get("code", "")))[:6]
        nickname = str(data.get("nickname", "")).strip()[:20]
        if not EMAIL_RE.match(email):
            raise ValueError("请输入有效邮箱")
        if len(code) != 6:
            raise ValueError("请输入 6 位验证码")
        visitor, email_hash = self.visitor_hash(data), hash_value(email)
        with connect() as db:
            row = db.execute(
                "SELECT * FROM email_verifications WHERE visitor_hash=? AND email_hash=? AND verified_at='' ORDER BY created_at DESC LIMIT 1",
                (visitor, email_hash),
            ).fetchone()
            if not row:
                raise ValueError("请先获取验证码")
            if row["expires_at"] < utcnow():
                raise ValueError("验证码已过期，请重新获取")
            if int(row["attempts"]) >= 5:
                raise ValueError("验证码错误次数过多，请重新获取")
            if not hmac.compare_digest(row["code_hash"], hash_value(code)):
                db.execute("UPDATE email_verifications SET attempts=attempts+1 WHERE id=?", (row["id"],))
                raise ValueError("验证码不正确")
            verified_at = utcnow()
            db.execute("UPDATE email_verifications SET verified_at=? WHERE id=?", (verified_at, row["id"]))
            db.execute(
                "INSERT OR REPLACE INTO verified_identities(visitor_hash,email_hash,email,nickname,verified_at) VALUES(?,?,?,?,?)",
                (visitor, email_hash, email, nickname, verified_at),
            )
        return self.json_response(200, {"success": True, "message": "邮箱验证成功", "data": {"verified": True}})

    def get_stars(self):
        visitor = self.visitor_hash()
        with connect() as db:
            count = db.execute("SELECT COUNT(*) FROM site_stars").fetchone()[0]
            starred = db.execute("SELECT 1 FROM site_stars WHERE visitor_hash=?", (visitor,)).fetchone() is not None
        return self.json_response(200, {"success": True, "data": {"starred": starred, "starCount": count}})

    def toggle_site_star(self):
        data = self.body()
        visitor, actor = self.visitor_hash(data), self.client_hash()
        with connect() as db:
            if not rate_allowed(db, "site_star", actor, visitor, 6, 10): raise ValueError("操作太频繁，请稍后再试")
            existing = db.execute("SELECT 1 FROM site_stars WHERE visitor_hash=?", (visitor,)).fetchone()
            if existing:
                db.execute("DELETE FROM site_stars WHERE visitor_hash=?", (visitor,))
                starred = False
            else:
                db.execute("INSERT INTO site_stars(visitor_hash,created_at) VALUES(?,?)", (visitor, utcnow()))
                starred = True
            count = db.execute("SELECT COUNT(*) FROM site_stars").fetchone()[0]
        return self.json_response(200, {"success": True, "data": {"starred": starred, "starCount": count}})

    def validate_text(self, data, reply=False):
        nickname = str(data.get("nickname", "")).strip()
        content = str(data.get("content", "")).strip()
        if len(nickname) < 2 or len(nickname) > 20: raise ValueError("昵称需要 2 至 20 个字符")
        minimum, maximum = (2, 300) if reply else (5, 500)
        if len(content) < minimum or len(content) > maximum: raise ValueError(f"内容需要 {minimum} 至 {maximum} 个字符")
        if data.get("website"): return None
        return nickname, content

    def create_message(self):
        data = self.body()
        validated = self.validate_text(data)
        if validated is None: return self.json_response(200, {"success": True, "message": "留言发布成功"})
        nickname, content = validated
        email = str(data.get("email", "")).strip()
        if email and not EMAIL_RE.match(email): raise ValueError("邮箱格式不正确")
        actor = self.client_hash()
        status = "pending" if contains_sensitive(nickname + content) else "approved"
        with connect() as db:
            if not rate_allowed(db, "message", actor, limit=1, window=30): raise ValueError("提交得有点快，请稍后再试")
            email_verified = 0
            if email:
                row = db.execute(
                    "SELECT 1 FROM verified_identities WHERE visitor_hash=? AND email_hash=?",
                    (self.visitor_hash(data), hash_value(email.lower())),
                ).fetchone()
                email_verified = 1 if row else 0
            db.execute("INSERT INTO messages(id,nickname,email,content,created_at,ip_hash,status,email_verified) VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), nickname, email, content, utcnow(), actor, status, email_verified))
        message = "留言已提交审核" if status == "pending" else "留言发布成功"
        return self.json_response(201, {"success": True, "message": message})

    def create_reply(self, message_id):
        data = self.body()
        validated = self.validate_text(data, True)
        if validated is None: return self.json_response(200, {"success": True, "message": "回复发布成功"})
        nickname, content = validated
        actor = self.client_hash()
        status = "pending" if contains_sensitive(nickname + content) else "approved"
        with connect() as db:
            if not db.execute("SELECT 1 FROM messages WHERE id=? AND status='approved'", (message_id,)).fetchone(): raise ValueError("这条留言不存在")
            if not rate_allowed(db, "reply", actor, message_id, 1, 15): raise ValueError("回复得有点快，请稍后再试")
            db.execute("INSERT INTO replies(id,message_id,nickname,content,created_at,ip_hash,status) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), message_id, nickname, content, utcnow(), actor, status))
        return self.json_response(201, {"success": True, "message": "回复已提交审核" if status == "pending" else "回复发布成功"})

    def toggle_like(self, entity_type, entity_id):
        data = self.body()
        visitor, actor = self.visitor_hash(data), self.client_hash()
        table = "messages" if entity_type == "message" else "replies"
        with connect() as db:
            if not db.execute(f"SELECT 1 FROM {table} WHERE id=? AND status='approved'", (entity_id,)).fetchone(): raise ValueError("内容不存在")
            if not rate_allowed(db, "like", actor, entity_id, 3, 10): raise ValueError("操作太频繁，请稍后再试")
            existing = db.execute("SELECT 1 FROM likes WHERE entity_type=? AND entity_id=? AND visitor_hash=?", (entity_type, entity_id, visitor)).fetchone()
            if existing: db.execute("DELETE FROM likes WHERE entity_type=? AND entity_id=? AND visitor_hash=?", (entity_type, entity_id, visitor)); liked = False
            else: db.execute("INSERT INTO likes VALUES(?,?,?,?)", (entity_type, entity_id, visitor, utcnow())); liked = True
            count = db.execute("SELECT COUNT(*) FROM likes WHERE entity_type=? AND entity_id=?", (entity_type, entity_id)).fetchone()[0]
        return self.json_response(200, {"success": True, "data": {"liked": liked, "likeCount": count}})

    def report(self, entity_type, entity_id):
        data = self.body()
        reason = str(data.get("reason", "不当内容")).strip()[:100]
        visitor, actor = self.visitor_hash(data), self.client_hash()
        table = "messages" if entity_type == "message" else "replies"
        with connect() as db:
            if not db.execute(f"SELECT 1 FROM {table} WHERE id=? AND status='approved'", (entity_id,)).fetchone(): raise ValueError("内容不存在")
            if not rate_allowed(db, "report", actor, entity_id, 1, 3600): raise ValueError("你已经举报过这条内容")
            try: db.execute("INSERT INTO reports(entity_type,entity_id,visitor_hash,reason,created_at) VALUES(?,?,?,?,?)", (entity_type, entity_id, visitor, reason, utcnow()))
            except sqlite3.IntegrityError: raise ValueError("你已经举报过这条内容")
            db.execute(f"UPDATE {table} SET report_count=report_count+1 WHERE id=?", (entity_id,))
        return self.json_response(200, {"success": True, "message": "举报已提交，站长会尽快处理"})

    def track_view(self):
        data = self.body(16384)
        path = str(data.get("path", "/"))[:300]
        if not path.startswith("/") or path.startswith("/admin"): return self.json_response(200, {"success": True})
        session = str(data.get("sessionId", ""))[:128]
        visitor = self.visitor_hash(data)
        device, browser, os_name = parse_user_agent(self.headers.get("User-Agent", ""))
        if device == "bot": return self.json_response(200, {"success": True})
        referrer = str(data.get("referrerHost", ""))[:200]
        with connect() as db:
            if rate_allowed(db, "pageview", hash_value(session or visitor), path, 1, 8):
                db.execute("INSERT INTO page_views(occurred_at,occurred_ts,visitor_hash,session_hash,path,referrer_host,device_type,browser,os) VALUES(?,?,?,?,?,?,?,?,?)", (utcnow(), time.time(), visitor, hash_value(session or visitor), path, referrer, device, browser, os_name))
        return self.json_response(200, {"success": True})

    def admin_login(self):
        data = self.body(4096)
        actor = self.client_hash()
        with connect() as db:
            cutoff = time.time() - 900
            failures = db.execute(
                "SELECT COUNT(*) FROM rate_events WHERE action='admin_login_fail' AND actor_hash=? AND created_at>=?",
                (actor, cutoff),
            ).fetchone()[0]
            if failures >= 5:
                return self.json_response(429, {"success": False, "message": "登录失败次数过多，请 15 分钟后再试"})
        if not verify_password(str(data.get("password", ""))):
            with connect() as db:
                db.execute(
                    "INSERT INTO rate_events(action,actor_hash,entity_key,created_at) VALUES(?,?,?,?)",
                    ("admin_login_fail", actor, "", time.time()),
                )
            return self.json_response(401, {"success": False, "message": "密码不正确"})
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        with connect() as db:
            db.execute("DELETE FROM rate_events WHERE action='admin_login_fail' AND actor_hash=?", (actor,))
            db.execute("INSERT INTO admin_sessions VALUES(?,?,?)", (hash_value(token), utcnow(), expires))
        header = f"{ADMIN_COOKIE}={token}; Path=/; Max-Age=604800; HttpOnly; Secure; SameSite=Strict; Priority=High"
        return self.json_response(200, {"success": True, "message": "登录成功"}, {"Set-Cookie": header})

    def admin_logout(self):
        token = self.admin_token()
        if token:
            with connect() as db: db.execute("DELETE FROM admin_sessions WHERE token_hash=?", (hash_value(token),))
        return self.json_response(200, {"success": True}, {"Set-Cookie": f"{ADMIN_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Priority=High"})

    def get_analytics(self, query):
        days = int(query.get("days", ["30"])[0]); days = days if days in (7, 30, 90, 365) else 30
        cutoff = time.time() - days * 86400
        with connect() as db:
            views = db.execute("SELECT COUNT(*) FROM page_views WHERE occurred_ts>=?", (cutoff,)).fetchone()[0]
            visitors = db.execute("SELECT COUNT(DISTINCT visitor_hash) FROM page_views WHERE occurred_ts>=?", (cutoff,)).fetchone()[0]
            sessions = db.execute("SELECT COUNT(DISTINCT session_hash) FROM page_views WHERE occurred_ts>=?", (cutoff,)).fetchone()[0]
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            today_views = db.execute("SELECT COUNT(*) FROM page_views WHERE occurred_ts>=?", (today,)).fetchone()[0]
            def rows(sql): return [dict(row) for row in db.execute(sql, (cutoff,)).fetchall()]
            trend = rows("SELECT substr(occurred_at,1,10) label, COUNT(*) value FROM page_views WHERE occurred_ts>=? GROUP BY label ORDER BY label")
            pages = rows("SELECT path label, COUNT(*) value FROM page_views WHERE occurred_ts>=? GROUP BY path ORDER BY value DESC LIMIT 10")
            refs = rows("SELECT CASE WHEN referrer_host='' THEN '直接访问' ELSE referrer_host END label, COUNT(*) value FROM page_views WHERE occurred_ts>=? GROUP BY label ORDER BY value DESC LIMIT 10")
            devices = rows("SELECT device_type label, COUNT(*) value FROM page_views WHERE occurred_ts>=? GROUP BY device_type ORDER BY value DESC")
        return self.json_response(200, {"success": True, "data": {"days": days, "views": views, "visitors": visitors, "sessions": sessions, "todayViews": today_views, "trend": trend, "pages": pages, "referrers": refs, "devices": devices}})

    def get_admin_messages(self, query):
        status = query.get("status", ["all"])[0]
        where, params = ("", ()) if status == "all" else ("WHERE m.status=?", (status,))
        with connect() as db:
            messages = []
            for row in db.execute(f"SELECT m.*,(SELECT COUNT(*) FROM likes l WHERE l.entity_type='message' AND l.entity_id=m.id) like_count FROM messages m {where} ORDER BY m.pinned DESC,m.created_at DESC LIMIT 200", params):
                item = dict(row); item["replies"] = [dict(r) for r in db.execute("SELECT r.*,(SELECT COUNT(*) FROM likes l WHERE l.entity_type='reply' AND l.entity_id=r.id) like_count FROM replies r WHERE message_id=? ORDER BY created_at", (row["id"],))]; messages.append(item)
        return self.json_response(200, {"success": True, "data": messages})

    def get_rest_annotations(self, query):
        state = (query.get("state") or ["all"])[0]
        try:
            offset = int((query.get("offset") or ["0"])[0])
            limit = int((query.get("limit") or ["40"])[0])
            data = list_samples(REST_ANNOTATION_DIR, state, offset, limit)
            return self.json_response(200, {"success": True, "data": data})
        except (TypeError, ValueError, OSError) as exc:
            return self.json_response(400, {"success": False, "message": str(exc)})

    def refresh_rest_annotations(self):
        try:
            data = refresh_samples(
                REST_ANNOTATION_DIR, SCORE_DIR, REST_ANNOTATION_EXPORTER,
                REST_ANNOTATION_PYTHON, 800)
            return self.json_response(200, {"success": True, "data": data,
                                            "message": "已从乐谱任务刷新待标注样本"})
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            return self.json_response(409, {"success": False, "message": str(exc)})

    def get_rest_annotation_image(self, sample_id):
        try:
            path = sample_image_path(REST_ANNOTATION_DIR, sample_id)
            with open(path, "rb") as stream:
                data = stream.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, OSError) as exc:
            return self.json_response(404, {"success": False, "message": str(exc)})

    def export_rest_annotations(self):
        archive = None
        try:
            excluded = load_excluded_document_hashes(SCORE_EVALUATION_MANIFEST)
            archive = build_training_archive(REST_ANNOTATION_DIR, excluded)
            size = os.path.getsize(archive)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", "attachment; filename=rest-detector-coco.zip")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with open(archive, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    self.wfile.write(chunk)
        except (ValueError, OSError) as exc:
            return self.json_response(409, {"success": False, "message": str(exc)})
        finally:
            if archive:
                try: os.unlink(archive)
                except OSError: pass

    def upload(self):
        data = self.body(8 * 1024 * 1024)
        name = re.sub(r"[^a-zA-Z0-9._-]", "-", str(data.get("name", "image")))[:80]
        mime = str(data.get("type", ""))
        allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
        if mime not in allowed: raise ValueError("只支持 JPG、PNG、WebP 或 GIF 图片")
        try: binary = base64.b64decode(str(data.get("data", "")), validate=True)
        except ValueError: raise ValueError("图片数据无效")
        if not binary or len(binary) > 6 * 1024 * 1024: raise ValueError("图片不能为空且不能超过 6MB")
        filename = f"{int(time.time())}-{secrets.token_hex(4)}-{os.path.splitext(name)[0]}{allowed[mime]}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as file: file.write(binary)
        return self.json_response(201, {"success": True, "data": {"url": f"/uploads/{filename}"}})

    def get_score_output(self, job_id):
        job_dir = os.path.join(SCORE_DIR, job_id)
        allowed, pipeline_status, reason = score_output_authorization(job_dir)
        if not allowed:
            return self.json_response(409, {
                "success": False,
                "message": reason,
                "data": {
                    "pipelineStatus": pipeline_status,
                    "outputAllowed": False,
                },
            })
        output_path = os.path.join(job_dir, "output.pdf")
        if not os.path.exists(output_path):
            return self.json_response(404, {"success": False, "message": "结果文件不存在或已过期"})
        try:
            with open(output_path, "rb") as file:
                data = file.read()
        except OSError:
            return self.json_response(500, {"success": False, "message": "结果文件读取失败"})
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        job = SCORE_JOBS.read(job_id) or {}
        filename = job.get("fileName") or "transposed-score.pdf"
        disposition = 'inline; filename="transposed-score.pdf"; filename*=UTF-8\'\'' + quote(filename)
        self.send_header("Content-Disposition", disposition)
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def get_score_status(self, job_id):
        result = SCORE_JOBS.read(job_id)
        if result is None:
            return self.json_response(404, {"success": False, "message": "任务不存在或已过期"})
        result = copy.deepcopy(result)
        if result.get("outputAllowed"):
            allowed, status, reason = score_output_authorization(os.path.join(SCORE_DIR, job_id))
            if not allowed:
                result.update(outputAllowed=False, outputUrl="", status="failed", pipelineStatus=status, message=reason)
        directory = os.path.join(SCORE_DIR, job_id)
        try:
            with open(os.path.join(directory, "request.json"), encoding="utf8") as stream:
                score_request = json.load(stream)
            mode = score_request.get("transposeMode", "instrument")
            if mode in ("instrument", "custom"):
                result["transposition"] = {
                    "mode": mode,
                    "sourceInstrument": score_request.get("sourceInstrument", "concert_c"),
                    "targetInstrument": score_request.get("targetInstrument", "concert_c"),
                    "semitones": score_request.get("semitones", 0),
                }
        except (OSError, ValueError, TypeError):
            pass
        candidate = candidate_info(directory, result.get("status"), get_pdf_page_count)
        base = "/api/score/transpositions/" + job_id
        result.update(candidateAvailable=bool(candidate), candidateUrl=base + "/candidate" if candidate else "",
                      reportUrl=base + "/review-report", originalUrl=base + "/original",
                      inspectionAvailable=bool(regular_file(directory, "inspection/inspection.json")),
                      inspectionUrl=base + "/inspection",
                      targetInspectionAvailable=bool(regular_file(directory, "inspection/target-inspection.json")),
                      targetInspectionUrl=base + "/inspection?role=target",
                      editorAvailable=bool(regular_file(directory, "transposed.musicxml")) and
                      result.get("status") not in ("queued", "processing"))
        if result.get("verification"):
            result["verification"] = public_score_verification(result["verification"])
        return self.json_response(200, {"success": True, "data": result}, {"Cache-Control": "no-store"})

    def get_score_review_asset(self, job_id, kind, query=None):
        job = SCORE_JOBS.read(job_id)
        if not job:
            return self.json_response(404, {"success": False, "message": "任务不存在"})
        directory = os.path.join(SCORE_DIR, job_id)
        query = query or {}
        try:
            if kind == "editor":
                if job.get("status") in ("queued", "processing"):
                    raise ValueError("请等待当前处理完成")
                return self.json_response(200, {"success": True, "data": editor_data(directory, read_musicxml_root)})
            if kind == "inspection":
                role = (query.get("role") or ["source"])[0]
                if role not in ("source", "target"):
                    raise ValueError("PDF 视觉检查角色无效")
                filename = "inspection.json" if role == "source" else "target-inspection.json"
                path = regular_file(directory, "inspection/" + filename)
                if not path:
                    raise ValueError("PDF 视觉检查尚未生成")
                with open(path, encoding="utf-8") as stream:
                    payload = json.load(stream)
                return self.json_response(200, {"success": True, "data": payload}, {"Cache-Control": "private, no-store"})
            if kind == "page-image":
                raw_page = (query.get("page") or [""])[0]
                layer = (query.get("layer") or ["analysis"])[0]
                layers = {
                    "preview": "preview-150", "analysis": "analysis-400",
                    "target-preview": "target-preview-150",
                    "target-analysis": "target-analysis-400",
                }
                if not re.fullmatch(r"\d{1,2}", raw_page) or layer not in layers:
                    raise ValueError("谱面图片参数无效")
                page = int(raw_page)
                if not 1 <= page <= 20:
                    raise ValueError("谱面页码无效")
                folder = layers[layer]
                relative = "renders/%s/page-%04d.png" % (folder, page)
                path = regular_file(directory, relative)
                if not path:
                    raise ValueError("对应谱面图片尚未生成")
                mime, name = "image/png", "page-%04d-%s.png" % (page, layer)
            if kind == "region-image":
                role = (query.get("role") or ["source"])[0]
                raw_page = (query.get("page") or [""])[0]
                raw_dpi = (query.get("dpi") or ["600"])[0]
                if role not in ("source", "target") or not re.fullmatch(r"\d{1,2}", raw_page) or not re.fullmatch(r"\d{3}", raw_dpi):
                    raise ValueError("局部谱面参数无效")
                try:
                    bbox = [float((query.get(name) or [""])[0]) for name in ("x0", "y0", "x1", "y1")]
                except ValueError:
                    raise ValueError("局部谱面坐标无效")
                page, dpi = int(raw_page), int(raw_dpi)
                if (not all(math.isfinite(value) for value in bbox) or not 1 <= page <= 20 or
                        not 144 <= dpi <= 800 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1] or
                        (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) * (dpi / 72.0) ** 2 > 20000000):
                    raise ValueError("局部谱面范围过大或坐标无效")
                with connect() as db:
                    if not rate_allowed(db, "score_region", self.client_hash(), limit=12, window=300):
                        raise ValueError("局部放大请求过于频繁，请稍后再试")
                source = regular_file(directory, "input.pdf" if role == "source" else "output.pdf")
                if not source:
                    raise ValueError("对应 PDF 尚未生成")
                rendered = render_score_region(source, directory, page, bbox, dpi)
                path = regular_file(directory, rendered["path"])
                if not path:
                    raise ValueError("局部谱面图片尚未生成")
                mime, name = "image/png", "region-page-%04d-%s.png" % (page, role)
            if kind == "candidate":
                if not candidate_info(directory, job.get("status"), get_pdf_page_count):
                    raise ValueError("尚未生成可读取的候选 PDF；不能把原谱当作转调结果")
                path, mime, name = regular_file(directory, "output.pdf"), "application/pdf", "待校对-" + job.get("fileName", "score.pdf")
            elif kind == "original":
                path, mime, name = regular_file(directory, "input.pdf"), "application/pdf", "原谱.pdf"
            elif kind == "musicxml":
                if job.get("status") in ("queued", "processing"):
                    raise ValueError("请等待当前处理完成")
                path, mime, name = regular_file(directory, "transposed.musicxml"), "application/vnd.recordare.musicxml+xml", "待校对.musicxml"
            elif kind == "review-report":
                text = report_text(dict(job, jobId=job_id), job.get("verification") or read_pipeline_report(directory).get("verification", {}))
                data, mime, name = ('\ufeff' + text).encode("utf-8"), "text/plain; charset=utf-8", "人工校对清单.txt"
                path = None
            if kind != "review-report":
                if not path:
                    raise ValueError("对应文件尚未生成")
                with open(path, "rb") as stream:
                    data = stream.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            disposition = "inline" if kind in ("candidate", "original", "page-image", "region-image") else "attachment"
            self.send_header("Content-Disposition", disposition + "; filename*=UTF-8''" + quote(name))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except (ValueError, RuntimeError) as exc:
            return self.json_response(409, {"success": False, "message": str(exc)})

    def create_score_edits(self, parent_id):
        parent = SCORE_JOBS.read(parent_id)
        if not parent or parent.get("status") in ("queued", "processing"):
            raise ValueError("任务不存在或尚未完成")
        data = self.body(128 * 1024)
        if not isinstance(data, dict) or set(data) != {"revision", "changes"}:
            raise ValueError("编辑请求格式无效")
        parent_dir = os.path.join(SCORE_DIR, parent_id)
        xml_path = regular_file(parent_dir, "transposed.musicxml")
        if not xml_path or data["revision"] != file_sha256(xml_path):
            raise ValueError("乐谱版本已变化，请重新打开编辑器")
        target_root = read_musicxml_root(xml_path)
        current_editor = editor_data(parent_dir, read_musicxml_root)
        rest_confirmations = {item.get("gapId"): item
                              for item in current_editor.get("restSuggestions", [])
                              if item.get("gapId")}
        try:
            with open(os.path.join(parent_dir, "request.json"), encoding="utf-8") as stream:
                parent_request = json.load(stream)
        except (OSError, ValueError):
            parent_request = {}
        intent = parent_request.get("intent")
        if not intent:
            inherited_summary = parent.get("summary", {}) if isinstance(parent.get("summary"), dict) else {}
            if not parent_request:
                source_name = inherited_summary.get("sourceInstrument", "concert_c")
                target_name = inherited_summary.get("targetInstrument", "concert_c")
                shift = inherited_summary.get("semitones", 0)
                inferred_mode = ("instrument" if source_name in INSTRUMENT_OFFSETS and
                                 target_name in INSTRUMENT_OFFSETS and
                                 shift == INSTRUMENT_OFFSETS[source_name] - INSTRUMENT_OFFSETS[target_name]
                                 else "custom")
                parent_request = {
                    "transposeMode": inferred_mode,
                    "sourceInstrument": source_name,
                    "targetInstrument": target_name,
                    "semitones": shift,
                    "accidentalPreference": "auto",
                }
            intent = build_transposition_intent(parent_request)

        source_path = canonical_source_musicxml(parent_dir)
        source_root = read_musicxml_root(source_path) if source_path else None
        target_preview = copy.deepcopy(target_root)
        # Validate the user's visible target edit first.  The same server-side
        # rest evidence and tie rules therefore apply to both old and new jobs.
        changes = apply_edits(target_preview, data["changes"], rest_confirmations)
        source_changes = None
        source_based = source_root is not None
        if source_based:
            pitch_only = all(isinstance(item, dict) and
                             set(item) == {"eventId", "pitch"}
                             for item in data["changes"])
            source_changes = (target_pitch_changes_to_source(
                source_root, target_root, data["changes"],
                (intent.get("interval") or {}).get("chromaticSemitones", 0))
                if pitch_only else data["changes"])
            apply_edits(source_root, source_changes, rest_confirmations)

        with connect() as db:
            if not rate_allowed(db, "score_edit", self.client_hash(), limit=6, window=300):
                raise ValueError("保存过于频繁，请稍后再试；可先集中修改多个音符再保存")
        job_id = str(uuid.uuid4())
        directory = os.path.join(SCORE_DIR, job_id)
        os.makedirs(directory)
        shutil.copyfile(os.path.join(parent_dir, "input.pdf"), os.path.join(directory, "input.pdf"))
        target_output = os.path.join(directory, "transposed.musicxml")
        source_output = os.path.join(directory, "scores", "source", "canonical-source.musicxml")
        if source_based:
            os.makedirs(os.path.dirname(source_output), exist_ok=True)
            ET.ElementTree(source_root).write(
                source_output, encoding="utf-8", xml_declaration=True)
            interval = intent.get("interval") or {}
            instrument_mode = intent.get("mode") == "instrument_rewrite"
            try:
                transpose_musicxml(
                    source_output, target_output, interval.get("chromaticSemitones", 0),
                    (intent.get("spellingPolicy") or {}).get("accidentalPreference", "auto"),
                    intent.get("sourceInstrument") if instrument_mode else None,
                    intent.get("targetInstrument") if instrument_mode else None)
            except RuntimeError as exc:
                raise ValueError("源谱修正已验证，但重新生成目标谱失败：%s" % exc)
            assert_target_pitch_changes(read_musicxml_root(target_output), data["changes"])
        else:
            ET.ElementTree(target_preview).write(
                target_output, encoding="utf-8", xml_declaration=True)

        resolved_gap_ids = [item.get("gapId") for item in changes
                            if item.get("type") == "confirmRest"]
        if any(item.get("type") == "insertRests" for item in changes):
            # Structural insertion changes later measure IDs, so old source
            # review coordinates cannot be attached to the child version.
            resolved_gap_ids = list(rest_confirmations)
        carry_rest_review(parent_dir, directory, resolved_gap_ids)
        request = {"manualEdit": True, "sourceBasedEdit": source_based,
                   "parentJobId": parent_id, "changes": changes,
                   "sourceChanges": source_changes if source_based else None,
                   "name": parent.get("fileName", "score.pdf"), "summary": parent.get("summary", {}),
                   "intent": intent}
        workspace = ScoreWorkspace(directory)
        workspace.initialize(job_id, os.path.join(directory, "input.pdf"), request, intent)
        parent_source_version = None
        try:
            parent_manifest = ScoreWorkspace(parent_dir).read()
            parent_source_version = next((item.get("versionId")
                                          for item in reversed(parent_manifest.get("scoreVersions", []))
                                          if item.get("role") == "canonical_source_musicxml"), None)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        if source_based:
            source_version = workspace.register_score_version(
                "canonical_source_musicxml", source_output, parent_source_version,
                {"parentJobId": parent_id, "parentSourceSha256": current_editor.get("sourceRevision")})
            workspace.register_artifact("canonical-source-musicxml", source_output)
            workspace.register_score_version(
                "target_transposed", target_output,
                source_version.get("versionId") if source_version else None,
                {"parentJobId": parent_id, "intentId": intent.get("intentId")})
        else:
            workspace.register_score_version(
                "manual_target_musicxml", target_output, None,
                {"parentJobId": parent_id, "sourceRevision": data["revision"]})
        workspace.register_artifact("candidate-musicxml", target_output)
        workspace.record_patch({"kind": "manual_source_edit" if source_based else "manual_music_edit",
                                "parentJobId": parent_id,
                                "targetRevision": data["revision"],
                                "sourceRevision": current_editor.get("sourceRevision"),
                                "changes": changes, "sourceChanges": source_changes})
        with open(os.path.join(directory, "request.json"), "w", encoding="utf-8") as stream:
            json.dump(request, stream, ensure_ascii=False, indent=2)
        with open(os.path.join(directory, "edit-history.json"), "w", encoding="utf-8") as stream:
            json.dump(dict(request, targetRevision=data["revision"],
                           sourceRevision=current_editor.get("sourceRevision")),
                      stream, ensure_ascii=False, indent=2)
        try:
            result = SCORE_JOBS.submit(job_id, request)
        except QueueFull:
            return self.json_response(429, {"success": False, "message": "当前处理队列已满，请稍后保存"})
        return self.json_response(202, {"success": True, "data": result})

    def create_score_retarget(self, parent_id):
        parent = SCORE_JOBS.read(parent_id)
        if not parent or parent.get("status") in ("queued", "processing"):
            raise ValueError("任务不存在或尚未完成")
        data = self.body(16 * 1024)
        if (not isinstance(data, dict) or
                set(data) not in ({"targetInstrument"},
                                  {"targetInstrument", "accidentalPreference"})):
            raise ValueError("重新转调请求格式无效")
        parent_dir = os.path.join(SCORE_DIR, parent_id)
        source_xml = canonical_source_musicxml(parent_dir)
        if not source_xml:
            raise ValueError("这份旧任务没有可复用的校正版源谱，请重新上传原谱")
        try:
            parent_manifest = ScoreWorkspace(parent_dir).read()
            parent_intent = parent_manifest.get("intent") or {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            parent_intent = {}
        source = parent_intent.get("sourceInstrument")
        target = data.get("targetInstrument")
        if (parent_intent.get("mode") != "instrument_rewrite" or source not in INSTRUMENT_OFFSETS):
            raise ValueError("自定义音程任务暂不能按乐器重新转调")
        if target not in INSTRUMENT_OFFSETS:
            raise ValueError("请选择有效的目标乐器")
        accidental = data.get("accidentalPreference", "auto")
        if accidental not in ("auto", "sharps", "flats"):
            raise ValueError("升降号偏好无效")
        semitones = INSTRUMENT_OFFSETS[source] - INSTRUMENT_OFFSETS[target]
        request = {
            "manualEdit": True, "retarget": True, "sourceBasedEdit": True,
            "parentJobId": parent_id, "changes": [], "sourceChanges": [],
            "name": parent.get("fileName", "score.pdf"),
            "summary": dict(parent.get("summary", {}), sourceInstrument=source,
                            targetInstrument=target, semitones=semitones,
                            transposeMode="instrument"),
            "transposeMode": "instrument", "sourceInstrument": source,
            "targetInstrument": target, "semitones": semitones,
            "accidentalPreference": accidental,
        }
        request["intent"] = build_transposition_intent(request)
        with connect() as db:
            if not rate_allowed(db, "score_edit", self.client_hash(), limit=6, window=300):
                raise ValueError("保存过于频繁，请稍后再试")
        job_id = str(uuid.uuid4())
        directory = os.path.join(SCORE_DIR, job_id)
        os.makedirs(os.path.join(directory, "scores", "source"))
        shutil.copyfile(os.path.join(parent_dir, "input.pdf"), os.path.join(directory, "input.pdf"))
        child_source = os.path.join(directory, "scores", "source", "canonical-source.musicxml")
        child_target = os.path.join(directory, "transposed.musicxml")
        shutil.copyfile(source_xml, child_source)
        try:
            transpose_musicxml(source_xml, child_target, semitones, accidental,
                               source, target)
        except RuntimeError as exc:
            raise ValueError("从校正版源谱生成目标谱失败：%s" % exc)
        carry_rest_review(parent_dir, directory, [])
        workspace = ScoreWorkspace(directory)
        workspace.initialize(job_id, os.path.join(directory, "input.pdf"),
                             request, request["intent"])
        source_version = workspace.register_score_version(
            "canonical_source_musicxml", child_source, None,
            {"parentJobId": parent_id, "reusedWithoutRecognition": True})
        workspace.register_score_version(
            "target_transposed", child_target,
            source_version.get("versionId") if source_version else None,
            {"parentJobId": parent_id, "intentId": request["intent"].get("intentId")})
        workspace.register_artifact("canonical-source-musicxml", child_source)
        workspace.register_artifact("candidate-musicxml", child_target)
        workspace.record_patch({"kind": "retarget_from_canonical_source",
                                "parentJobId": parent_id,
                                "targetInstrument": target,
                                "semitones": semitones})
        for filename in ("request.json", "edit-history.json"):
            with open(os.path.join(directory, filename), "w", encoding="utf-8") as stream:
                json.dump(request, stream, ensure_ascii=False, indent=2)
        try:
            result = SCORE_JOBS.submit(job_id, request)
        except QueueFull:
            return self.json_response(429, {"success": False,
                                            "message": "当前处理队列已满，请稍后重试"})
        return self.json_response(202, {"success": True, "data": result})

    def create_score_transposition(self):
        data = self.body(36 * 1024 * 1024)
        name = str(data.get("name", "score.pdf")).replace("\\", "/").split("/")[-1]
        name = re.sub(r"[^\w. ()-]", "-", name, flags=re.UNICODE).strip(" .")[:100] or "score.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        source = str(data.get("sourceInstrument", "concert_c"))
        target = str(data.get("targetInstrument", "concert_c"))
        if source not in INSTRUMENT_OFFSETS or target not in INSTRUMENT_OFFSETS:
            raise ValueError("请选择有效的原乐器和目标乐器")
        explicit_shift = "semitones" in data and data["semitones"] is not None
        mode = str(data.get("transposeMode", "custom" if explicit_shift else "instrument"))
        if mode not in ("custom", "instrument"):
            raise ValueError("转调模式无效")
        if explicit_shift:
            raw = data["semitones"]
            if isinstance(raw, bool) or not re.fullmatch(r"[+-]?\d+", str(raw)):
                raise ValueError("转调半音数必须为整数")
            semitones = int(raw)
        else:
            semitones = INSTRUMENT_OFFSETS[source] - INSTRUMENT_OFFSETS[target]
        if mode == "custom" and not explicit_shift:
            raise ValueError("请指定转调半音数")
        if mode == "instrument" and semitones != INSTRUMENT_OFFSETS[source] - INSTRUMENT_OFFSETS[target]:
            raise ValueError("乐器与转调音程不一致")
        if not -48 <= semitones <= 48:
            raise ValueError("转调范围为上下 48 个半音")
        accidental = str(data.get("accidentalPreference", "auto"))
        if accidental not in ("auto", "sharps", "flats"):
            raise ValueError("升降号偏好无效")
        encoded = str(data.get("data", ""))
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            binary = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ValueError("PDF 数据无效")
        maximum = int(os.environ.get("SCORE_MAX_BYTES", str(25 * 1024 * 1024)))
        if not binary or len(binary) > maximum:
            raise ValueError("PDF 不能为空，且不能超过 25MB")
        if not binary.startswith(b"%PDF"):
            raise ValueError("只支持标准 PDF 文件")
        page_selection_mode = str(data.get("pageSelectionMode", "all"))
        if page_selection_mode not in ("all", "custom"):
            raise ValueError("转换页码模式无效")
        selected_pages = (validate_requested_pages(data.get("selectedPages"))
                          if page_selection_mode == "custom" else None)
        actor = self.client_hash()
        with connect() as db:
            if not rate_allowed(db, "score_transpose", actor, limit=2, window=300):
                raise ValueError("乐谱处理请求太频繁，请稍后再试")
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(SCORE_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        uploaded_pdf = os.path.join(job_dir, "source-upload.pdf")
        input_pdf = os.path.join(job_dir, "input.pdf")
        with open(uploaded_pdf, "wb") as stream:
            stream.write(binary)
        try:
            page_selection = prepare_selected_pdf(
                uploaded_pdf, input_pdf, selected_pages,
                os.path.join(job_dir, "page-selection.json"))
        except ValueError:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        try:
            os.remove(uploaded_pdf)
        except OSError:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise ValueError("服务器暂时无法准备所选 PDF 页面")
        request = {"name": name, "sourceInstrument": source, "targetInstrument": target,
                   "semitones": semitones, "accidentalPreference": accidental,
                   "transposeMode": mode,
                   "pageSelectionMode": page_selection["mode"],
                   "selectedPages": page_selection["selectedPages"],
                   "sourcePageCount": page_selection["sourcePageCount"]}
        request["intent"] = build_transposition_intent(request)
        workspace = ScoreWorkspace(job_dir)
        workspace.initialize(job_id, input_pdf, request, request["intent"])
        workspace.register_artifact(
            "page-selection", os.path.join(job_dir, "page-selection.json"),
            metadata={"selectedPages": page_selection["selectedPages"]})
        with open(os.path.join(job_dir, "request.json"), "w", encoding="utf8") as stream:
            json.dump(request, stream, ensure_ascii=False)
        try:
            initial = SCORE_JOBS.submit(job_id, request)
        except QueueFull as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            return self.json_response(429, {"success": False, "message": str(exc)})
        # Cached older frontends expect a completed response. They still use the bounded worker.
        if data.get("async") is not True:
            deadline = time.monotonic() + 210
            while time.monotonic() < deadline:
                snapshot = SCORE_JOBS.read(job_id)
                if snapshot and snapshot.get("status") not in ("queued", "processing"):
                    return self.json_response(201, {"success": True, "message": snapshot.get("message", ""), "data": snapshot})
                time.sleep(0.3)
        return self.json_response(202, {"success": True, "message": "任务已接收", "data": initial})

    def chat(self):
        data = self.body(32768)
        question = str(data.get("message", "")).strip()[:1000]
        if not question: raise ValueError("请输入问题")
        if not DEEPSEEK_API_KEY: return self.json_response(503, {"success": False, "message": "AI 服务暂不可用"})
        context = ""
        try:
            with open(PROFILE_CONTEXT_PATH, encoding="utf-8") as file: context = file.read()[:16000]
        except OSError: pass
        prompt = f"""你是张航铭个人网站里的 AI 导览助手，不是通用闲聊机器人。

核心任务：
1. 帮访客快速理解张航铭是谁、做过什么项目、有哪些经历/奖项/技能，以及如何联系他。
2. 解释网站中出现或强相关的概念，以及首页、项目、经历、荣誉、留言、联系方式和工具箱中的公开功能。
3. 把“概念本身”与“张航铭网站资料中的具体关联”讲清楚，而不是只给百科式解释。

回答风格：
- 先直接回答，不要开场寒暄，不要说“根据资料显示”这种套话。
- 默认 2 到 5 句话；信息较多时用 3 到 5 个短要点。
- 语言自然、清楚、像一个懂网站内容的导览员。用户用中文就用中文，用户用英文就用英文。
- 不要每次都机械套用同一个结构；根据问题选择最合适的表达。
- 可以适度给出下一步浏览建议，例如“可以继续看他的 ROBOCON 项目/荣誉/经历部分”，但不要编造真实链接。

事实边界：
- 关于张航铭本人、项目职责、获奖、邮箱、学校、经历等个人事实，只能使用下方网站资料。
- 如果资料没有写清楚，直接说“网站资料里没有明确写”，然后给出合理的追问方向。
- 对通用技术/赛事/机构概念，可以使用常识做简明解释，但不要给出可能过时的精确数据、官方排名、未经证实的结论。
- 不公开或猜测手机号、住址、身份证、服务器、密码、密钥、后台地址等隐私和安全信息。

常见问题处理：
- 问“他是谁/介绍一下”：概括身份 + 方向 + 代表项目/经历。
- 问“项目”：优先讲 2 到 4 个最有代表性的项目，并点出他负责的部分。
- 问“获奖”：按含金量和相关性概括，不要把所有奖项流水账式列完。
- 问“什么是 X”：先解释 X，再说明它为什么出现在张航铭网站里，最后点出和他的经历/项目/技能的关系。
- 问“联系”：只提供网站资料中的公开邮箱。
- 问网站功能：根据资料说明入口、操作步骤、可获得的结果和需要用户复核的边界，不讨论模型、服务器、代码或内部实现。

网站资料：
{context}"""
        messages = [{"role": "system", "content": prompt}]
        for item in data.get("history", [])[-8:]:
            if not isinstance(item, dict): continue
            role = item.get("role")
            content = str(item.get("content", "")).strip()[:800]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        payload = json.dumps({"model": DEEPSEEK_MODEL, "messages": messages, "temperature": 0.35, "max_tokens": 900}, ensure_ascii=False).encode()
        request = Request(DEEPSEEK_API_URL, data=payload, headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}, method="POST")
        for attempt in range(2):
            try:
                with urlopen(request, timeout=30) as response:
                    result = json.loads(response.read().decode())
                answer = result["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("empty assistant answer")
                return self.json_response(200, {"success": True, "data": {"answer": answer.strip()}})
            except (HTTPError, URLError, KeyError, ValueError) as exc:
                logging.warning("AI guide request failed on attempt %s: %s", attempt + 1, type(exc).__name__)
                if attempt == 0:
                    time.sleep(0.45)
        return self.json_response(502, {"success": False, "message": "AI 服务响应异常，请稍后再试"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    initialize_database()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
