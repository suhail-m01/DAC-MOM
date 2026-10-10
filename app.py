from __future__ import annotations

import csv
import hashlib
import hmac
import html
import io
import json
import mimetypes
import os
import re
import secrets
import time as time_module
import uuid
from datetime import datetime, time as time_value, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_file, session
from auth_store import (
    ROLES, add_user as db_add_user, count_active_admins,
    create_upload_record, delete_all_demo_workspaces, get_catalog, get_upload_record,
    get_user_by_email, get_user_by_id, get_workspace, init_db, latest_pending_workspace,
    list_pending_workspaces, list_users, list_workspaces_for_owner, owner_for_workspace,
    save_workspace, update_user as db_update_user, verify_login_code, workspace_access_for_email,
    workspace_for_owner, store_login_code,
)
from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as PDFImage,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTBOX_PATH = DATA_DIR / "demo-outbox.json"
AUDIT_PATH = DATA_DIR / "demo-audit.json"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 250
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".xlsx", ".pptx", ".txt", ".csv"
}
FILE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
COLLEGE_TZ = ZoneInfo("Asia/Kolkata")
NAVY = colors.HexColor("#172b45")
TEAL = colors.HexColor("#187b74")
PALE = colors.HexColor("#edf4f3")
INK = colors.HexColor("#243244")
MUTED = colors.HexColor("#617084")
RULE = colors.HexColor("#d7dee5")

app = Flask(__name__, static_folder=None)
APP_ENV = os.environ.get("APP_ENV", "demo").strip().lower()
if APP_ENV == "production" and not os.environ.get("FLASK_SECRET_KEY"):
    raise RuntimeError("FLASK_SECRET_KEY must be configured for production.")
DEMO_AUTH_SHOW_OTP = APP_ENV != "production" and os.environ.get("DEMO_AUTH_SHOW_OTP", "1").strip().lower() in {"1", "true", "yes"}
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_urlsafe(48),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=APP_ENV == "production" or os.environ.get("SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes"},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
init_db()

ROLE_CHOICES = sorted(ROLES)


def get_current_user():
    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user:
            session.clear()
            return jsonify({"error": "Sign in with an active, allow-listed account."}), 401
        return fn(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user or user["role"] not in roles:
                return jsonify({"error": "Your account does not have permission for this action."}), 403
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def _csrf_exempt_path(path: str) -> bool:
    return path in {"/api/auth/request-code", "/api/auth/verify-code"}


@app.before_request
def enforce_session_csrf():
    if not request.path.startswith("/api/") or request.method in {"GET", "HEAD", "OPTIONS"} or _csrf_exempt_path(request.path):
        return None
    if not session.get("user_id"):
        return None  # The route-level decorator returns the authentication error.
    expected = str(session.get("csrf_token") or "")
    supplied = str(request.headers.get("X-CSRF-Token") or "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return jsonify({"error": "CSRF verification failed. Refresh the application and retry."}), 403
    return None


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "had", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "our",
    "the", "their", "them", "there", "this", "to", "was", "were", "with", "will", "would",
    "committee", "department", "meeting", "members", "member", "regarding", "concerning",
}
ALIASES = {
    "mom": "minutes", "minute": "minutes", "minutes": "minutes", "previously": "previous",
    "last": "previous", "approved": "approve", "approval": "approve", "approving": "approve",
    "ratified": "approve", "ratification": "approve", "accepted": "approve", "acceptance": "approve",
    "examined": "review", "reviewed": "review", "reviewing": "review", "considered": "review",
    "discussed": "discuss", "discussion": "discuss", "discussing": "discuss",
    "recommendation": "recommend", "recommended": "recommend", "recommends": "recommend",
    "actions": "action", "atr": "action", "syllabi": "syllabus", "curricular": "curriculum",
    "deferred": "defer", "postponed": "defer", "rejected": "reject", "declined": "reject",
    "noted": "note", "recorded": "note", "referred": "refer", "referral": "refer",
}


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _append_json(path: Path, value: dict) -> None:
    rows = _read_json(path, [])
    rows.append(value)
    path.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=2), encoding="utf-8")


def get_upload_path(file_id: str) -> Path | None:
    if not FILE_ID_RE.fullmatch(file_id or ""):
        return None
    matches = list(UPLOAD_DIR.glob(f"{file_id}.*"))
    return matches[0] if len(matches) == 1 else None


def read_uploaded_bytes(file_id: str) -> bytes | None:
    path = get_upload_path(file_id)
    if not path or not path.is_file():
        return None
    return path.read_bytes()


def _normalized_terms(text: str) -> set[str]:
    replacements = {
        "&": " and ", "atr": " action taken report ", "mo m": " minutes ",
        "m.o.m.": " minutes ", "mom": " minutes ",
    }
    value = (text or "").lower()
    for old, new in replacements.items():
        value = value.replace(old, new)
    words = re.findall(r"[a-z0-9]+", value)
    result = set()
    for word in words:
        word = ALIASES.get(word, word)
        if word in STOP_WORDS or len(word) < 2:
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("ing") and len(word) > 5:
            word = word[:-3]
        elif word.endswith("ed") and len(word) > 4:
            word = word[:-2]
        elif word.endswith("s") and len(word) > 4:
            word = word[:-1]
        result.add(ALIASES.get(word, word))
    return result


def _coverage(expected: set[str], actual: set[str]) -> float:
    if not expected:
        return 1.0
    return len(expected & actual) / len(expected)


def _outcome(text: str) -> str | None:
    terms = _normalized_terms(text)
    # Prefer defer/reject over approve if a sentence says "not approved".
    if "defer" in terms:
        return "deferred"
    if "reject" in terms:
        return "rejected"
    if "approve" in terms:
        return "approved"
    if "note" in terms:
        return "noted"
    if "refer" in terms:
        return "referred"
    return None


def validate_mom(payload: dict) -> dict:
    """Transparent, deterministic demo check; not a production AI model."""
    items = payload.get("momItems") or []
    results = []
    for index, item in enumerate(items, start=1):
        title = str(item.get("title") or "").strip()
        discussion = str(item.get("discussion") or "").strip()
        recommendation = str(item.get("recommendation") or "").strip()
        no_recommendation = bool(item.get("noRecommendation"))
        agenda_terms = _normalized_terms(title)
        discussion_terms = _normalized_terms(discussion)
        recommendation_terms = _normalized_terms(recommendation)

        ad_score = _coverage(agenda_terms, discussion_terms)
        dr_score = _coverage(recommendation_terms, discussion_terms)
        ar_score = _coverage(agenda_terms, recommendation_terms)
        checks = []

        if not discussion:
            checks.append({
                "name": "Agenda ↔ Discussion", "status": "needs_revision", "score": 0,
                "message": "Discussion is empty. Record what the committee actually deliberated; do not infer it from the agenda.",
                "evidence": "No discussion text was supplied.",
                "suggestion": f"Add the recorded deliberation that addresses “{title or 'this agenda item'}”.",
            })
        elif ad_score < 0.24:
            checks.append({
                "name": "Agenda ↔ Discussion", "status": "needs_revision", "score": round(ad_score * 100),
                "message": "The discussion may not address this agenda clearly based on the submitted text.",
                "evidence": discussion[:240],
                "suggestion": f"Clarify how the recorded discussion relates to “{title}”. Do not add facts that were not recorded.",
            })
        elif ad_score < 0.50:
            checks.append({
                "name": "Agenda ↔ Discussion", "status": "review", "score": round(ad_score * 100),
                "message": "Some agenda terms appear in the discussion, but the relationship may need a human review.",
                "evidence": discussion[:240],
                "suggestion": "Check that the discussion covers the agenda's main question, not just a shared keyword.",
            })
        else:
            checks.append({
                "name": "Agenda ↔ Discussion", "status": "aligned", "score": round(ad_score * 100),
                "message": "The written discussion shares the agenda's key terms.",
                "evidence": discussion[:240],
                "suggestion": "No wording change suggested by the demo check.",
            })

        if no_recommendation and not recommendation:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "aligned", "score": 100,
                "message": "No separate recommendation was recorded; the demo does not force one.",
                "evidence": "Author marked this item as having no separate recommendation.",
                "suggestion": "No recommendation text needed unless the committee recorded one.",
            })
        elif not recommendation:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "review", "score": 0,
                "message": "Recommendation is empty. Confirm whether the committee made a recommendation or decision.",
                "evidence": "No recommendation text was supplied.",
                "suggestion": "Record the actual outcome, or mark that no separate recommendation was made.",
            })
        elif not discussion:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "needs_revision", "score": 0,
                "message": "A recommendation is present, but there is no written discussion to support it.",
                "evidence": recommendation[:240],
                "suggestion": "Add the recorded discussion or revise the recommendation to reflect what was documented.",
            })
        elif dr_score < 0.25:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "needs_revision", "score": round(dr_score * 100),
                "message": "The recommendation contains key terms not found in the discussion; it may be unsupported.",
                "evidence": f"Discussion: {discussion[:150]} | Recommendation: {recommendation[:150]}",
                "suggestion": "Clarify which recorded point supports the recommendation. Do not add a new decision.",
            })
        elif dr_score < 0.55:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "review", "score": round(dr_score * 100),
                "message": "The recommendation has some textual support, but a reviewer should confirm the reasoning.",
                "evidence": f"Discussion: {discussion[:150]} | Recommendation: {recommendation[:150]}",
                "suggestion": "Make the link between the deliberation and recommendation explicit if the record supports it.",
            })
        else:
            checks.append({
                "name": "Discussion ↔ Recommendation", "status": "aligned", "score": round(dr_score * 100),
                "message": "The recommendation's key terms also appear in the discussion.",
                "evidence": f"Discussion: {discussion[:150]} | Recommendation: {recommendation[:150]}",
                "suggestion": "No wording change suggested by the demo check.",
            })

        if recommendation and agenda_terms and ar_score < 0.25:
            checks.append({
                "name": "Agenda ↔ Recommendation", "status": "review", "score": round(ar_score * 100),
                "message": "The recommendation may not answer the agenda item.",
                "evidence": recommendation[:220],
                "suggestion": "Confirm that this outcome resolves or responds to the agenda item.",
            })

        discussion_outcome = _outcome(discussion)
        recommendation_outcome = _outcome(recommendation)
        if discussion_outcome and recommendation_outcome and discussion_outcome != recommendation_outcome:
            checks.append({
                "name": "Outcome consistency", "status": "needs_revision", "score": 0,
                "message": f"Possible outcome conflict: discussion appears {discussion_outcome}, while recommendation appears {recommendation_outcome}.",
                "evidence": f"Discussion: {discussion[:180]} | Recommendation: {recommendation[:180]}",
                "suggestion": "Verify the committee's recorded outcome and correct the text; the demo cannot determine which version is true.",
            })

        status_rank = {"aligned": 0, "review": 1, "needs_revision": 2}
        overall = max((check["status"] for check in checks), key=lambda status: status_rank[status])
        results.append({
            "agendaNo": index,
            "agendaTitle": title or f"Agenda {index}",
            "status": overall,
            "checks": checks,
        })

    return {
        "mode": "demo-rules-not-LLM",
        "summary": {
            "items": len(results),
            "aligned": sum(row["status"] == "aligned" for row in results),
            "review": sum(row["status"] == "review" for row in results),
            "needsRevision": sum(row["status"] == "needs_revision" for row in results),
        },
        "items": results,
        "notice": "This local demo checks internal wording only. It cannot verify what was actually said in the meeting or establish academic truth.",
    }


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True).replace("\n", "<br/>")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("DACtitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.black, alignment=TA_CENTER, spaceAfter=5),
        "subtitle": ParagraphStyle("DACsubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=10, leading=13, textColor=colors.black, alignment=TA_CENTER, spaceAfter=5),
        "h1": ParagraphStyle("DACh1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.black, spaceBefore=5, spaceAfter=6),
        "h2": ParagraphStyle("DACh2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.black, spaceBefore=5, spaceAfter=3),
        "body": ParagraphStyle("DACbody", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.black, spaceAfter=4),
        "small": ParagraphStyle("DACsmall", parent=base["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.black, spaceAfter=3),
        "table": ParagraphStyle("DACtable", parent=base["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.black),
        "table_head": ParagraphStyle("DACtablehead", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
        "table_head_plain": ParagraphStyle("DACtableheadplain", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.black),
        "center": ParagraphStyle("DACcenter", parent=base["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.black, alignment=TA_CENTER),
    }


def _on_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "Departmental Academic Committee · Minutes of Meeting")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _as_pdf_image(file_id: str, max_width: float, max_height: float):
    raw = read_uploaded_bytes(file_id)
    if not raw:
        return None
    image = PILImage.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((int(max_width * 2), int(max_height * 2)))
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=88)
    stream.seek(0)
    flowable = PDFImage(stream, width=max_width, height=max_height, kind="proportional")
    flowable.hAlign = "CENTER"
    return flowable


def _image_to_pdf(raw: bytes, title: str) -> bytes:
    image = PILImage.open(io.BytesIO(raw)).convert("RGB")
    width_px, height_px = image.size
    page = A4 if height_px >= width_px else (A4[1], A4[0])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=20 * mm)
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=90)
    stream.seek(0)
    styles = _styles()
    story = [Paragraph(_escape(title), styles["h1"]), Spacer(1, 6 * mm), PDFImage(stream, width=doc.width, height=doc.height - 15 * mm, kind="proportional")]
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def _office_attachment_pdf(file_path: Path, display_name: str, agenda_title: str, label: str) -> bytes:
    """Convert supported Office files into readable text/table pages for this demo."""
    ext = file_path.suffix.lower()
    styles = _styles()
    story = [
        Paragraph(_escape(f"Annexure {label} · {display_name}"), styles["h1"]),
        Paragraph(_escape(f"Related agenda: {agenda_title}"), styles["small"]),
        Spacer(1, 4 * mm),
    ]

    if ext == ".docx":
        from docx import Document

        docx = Document(str(file_path))
        for paragraph in docx.paragraphs:
            if paragraph.text.strip():
                story.append(Paragraph(_escape(paragraph.text), styles["body"]))
        for table_index, table in enumerate(docx.tables, start=1):
            story.append(Paragraph(f"Table {table_index}", styles["h2"]))
            for row_index, row in enumerate(table.rows, start=1):
                row_text = "  |  ".join(cell.text.strip() for cell in row.cells)
                story.append(Paragraph(_escape(f"Row {row_index}: {row_text}"), styles["small"]))

    elif ext == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(file_path, read_only=True, data_only=True)
        for sheet in workbook.worksheets:
            story.append(Paragraph(_escape(f"Worksheet: {sheet.title}"), styles["h2"]))
            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = ["" if value is None else str(value) for value in row]
                while values and not values[-1]:
                    values.pop()
                if values:
                    story.append(Paragraph(_escape(f"Row {row_index}: " + " | ".join(values)), styles["small"]))
        workbook.close()

    elif ext == ".pptx":
        from pptx import Presentation

        presentation = Presentation(str(file_path))
        for slide_index, slide in enumerate(presentation.slides, start=1):
            story.append(Paragraph(_escape(f"Slide {slide_index}"), styles["h2"]))
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    story.append(Paragraph(_escape(shape.text), styles["body"]))
                if getattr(shape, "has_table", False):
                    for row in shape.table.rows:
                        story.append(Paragraph(_escape(" | ".join(cell.text for cell in row.cells)), styles["small"]))

    elif ext in {".txt", ".csv"}:
        text = file_path.read_text(encoding="utf-8-sig", errors="replace")
        lines = []
        if ext == ".csv":
            lines = [" | ".join(row) for row in csv.reader(io.StringIO(text))]
        else:
            lines = text.splitlines()
        for line in lines:
            story.append(Paragraph(_escape(line) if line.strip() else "&nbsp;", styles["small"]))

    else:
        story.append(Paragraph("This demo cannot render this attachment type.", styles["body"]))

    if len(story) == 3:
        story.append(Paragraph("No extractable text was found in this file.", styles["body"]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=display_name)
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def annexure_entries(mom_items: list[dict]) -> list[dict]:
    entries = []
    seen = set()
    for agenda_no, item in enumerate(mom_items, start=1):
        for file_no, attachment in enumerate(item.get("attachments") or [], start=1):
            file_id = attachment.get("id")
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            entries.append({
                "id": file_id,
                "label": f"{agenda_no}.{file_no}",
                "agendaNo": agenda_no,
                "agendaTitle": item.get("title", ""),
                "name": attachment.get("name", "Attachment"),
            })
    return entries


def _annexure_index_pdf(entries: list[dict]) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=22 * mm)
    story = [Paragraph("Annexure Index", styles["title"]), Paragraph("Supporting documents included after the MoM pages", styles["subtitle"]), Spacer(1, 6 * mm)]
    rows = [[Paragraph("Annexure", styles["table_head"]), Paragraph("Agenda item", styles["table_head"]), Paragraph("File", styles["table_head"])]]
    for entry in entries:
        rows.append([
            Paragraph(_escape(f"{entry['label']}"), styles["table"]),
            Paragraph(_escape(f"Agenda {entry['agendaNo']}: {entry['agendaTitle']}"), styles["table"]),
            Paragraph(_escape(entry["name"]), styles["table"]),
        ])
    table = LongTable(rows, colWidths=[25 * mm, 75 * mm, doc.width - 100 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.45, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(table)
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def _annexure_divider_pdf(entry: dict) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=65 * mm, bottomMargin=25 * mm)
    story = [
        Paragraph(_escape(f"Annexure {entry['label']}"), styles["title"]),
        Spacer(1, 5 * mm),
        Paragraph(_escape(entry["name"]), styles["h1"]),
        Paragraph(_escape(f"Related agenda: {entry['agendaTitle']}"), styles["subtitle"]),
    ]
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def _ordinal(value) -> str:
    text = str(value or "1").strip()
    match = re.search(r"\d+", text)
    if not match:
        return text
    number = int(match.group(0))
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _numeric_meeting_number(value) -> int:
    match = re.search(r"\d+", str(value or "1"))
    return int(match.group(0)) if match else 1


def _format_date_dmy(value) -> str:
    if not value:
        return "Date not recorded"
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _without_name_prefix(value: object, prefix: str) -> str:
    text = str(value or "").strip()
    return re.sub(rf"^{re.escape(prefix)}\s*", "", text, flags=re.IGNORECASE).strip() or "__________"


def _reference_number(meeting: dict) -> str:
    number = _numeric_meeting_number(meeting.get("meetingNo"))
    school_code = (re.sub(r"[^A-Za-z0-9]", "", str(meeting.get("schoolCode") or "School")) or "School").upper()
    department_code = (re.sub(r"[^A-Za-z0-9]", "", str(meeting.get("departmentCode") or "Dept")) or "Dept").upper()
    academic_year = str(meeting.get("academicYear") or "Academic Year")
    semester = str(meeting.get("semester") or "Semester")
    return f"PU/{school_code}-{department_code}/DAC-{number:02d}/{academic_year}/{semester}/MoM-{number:02d}"


def _agenda_document_title(item: dict, meeting: dict) -> str:
    agenda_id = str(item.get("agendaId") or item.get("id") or "")
    title = str(item.get("title") or "").strip()
    current_number = _numeric_meeting_number(meeting.get("meetingNo"))
    fallback_previous = str(max(1, current_number - 1)) if current_number > 1 else "previous"
    previous_number = _ordinal(meeting.get("previousMeetingNo") or fallback_previous)
    previous_date = _format_date_dmy(meeting.get("previousMeetingDate"))
    if agenda_id == "std-mom":
        if title.startswith("To consider the approval of the MoM of the "):
            return title  # Approved wording is frozen in the MoM snapshot.
        return f"To consider the approval of the MoM of the {previous_number} Departmental Academic Committee meeting held on {previous_date}."
    if agenda_id == "std-atr":
        if title.startswith("To consider the approval of the Action Taken Report (ATR) of the "):
            return title  # Approved wording is frozen in the MoM snapshot.
        return f"To consider the approval of the Action Taken Report (ATR) of the {previous_number} Departmental Academic Committee meeting held on {previous_date}."
    return title or "Agenda"


def _meeting_description(meeting: dict) -> str:
    number = _ordinal(meeting.get("meetingNo"))
    department = _without_name_prefix(meeting.get("department"), "Department of")
    school = _without_name_prefix(meeting.get("school"), "School of")
    date_text = _format_date_dmy(meeting.get("date"))
    time_text = str(meeting.get("startTime") or "Time not recorded")
    venue = str(meeting.get("venue") or "Venue not recorded")
    mode = str(meeting.get("mode") or "Offline").strip().lower()
    if mode == "offline":
        mode_text = "The meeting was held in offline mode at the University campus in Bengaluru."
    elif mode == "online":
        mode_text = "The meeting was held in online mode."
    else:
        mode_text = "The meeting was held in hybrid mode at the University campus in Bengaluru."
    meeting_link = str(meeting.get("onlineLink") or "").strip()
    link_text = f" The meeting link is provided below: {meeting_link}" if meeting_link else " The meeting link is provided below."
    return (
        f"The {number} Meeting of the Departmental Academic Committee of the Department of {department}, "
        f"School of {school}, University, was convened on {date_text}, at {time_text} in the {venue}. "
        f"{mode_text}{link_text}"
    )


def _build_main_mom_pdf(data: dict) -> bytes:
    """Render the final MoM in the four-section hierarchy of the supplied DAC form.

    Each major template section starts on its reference page. Long agenda lists,
    photos, or tables are allowed to flow onto additional A4 pages.
    """
    styles = _styles()
    meeting = data.get("meeting") or {}
    all_members = meeting.get("members") or []
    present_members = [member for member in all_members if member.get("present", True)]
    mom_items = data.get("momItems") or []
    photos = data.get("photos") or []
    actions = data.get("actionItems") or []
    annexure_labels = {entry["id"]: entry["label"] for entry in annexure_entries(mom_items)}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title="DAC Minutes of Meeting",
        author="Departmental Academic Committee",
    )
    width = doc.width
    story = []

    # Reference page 1 — template title, school/department, meeting details and attendance.
    story.extend([
        Paragraph("Minutes of Meeting Template", styles["title"]),
        Spacer(1, 3 * mm),
        Paragraph(_escape(f"SCHOOL OF {_without_name_prefix(meeting.get('school'), 'School of')}").upper(), styles["subtitle"]),
        Paragraph(_escape(f"DEPARTMENT OF {_without_name_prefix(meeting.get('department'), 'Department of')}").upper(), styles["subtitle"]),
        Spacer(1, 2 * mm),
    ])
    reference = meeting.get("referenceNo") or _reference_number(meeting)
    ref_row = Table(
        [[Paragraph(_escape(f"Ref No. {reference}"), styles["small"]), Paragraph(_escape(f"Date: {_format_date_dmy(meeting.get('date'))}"), styles["small"])]],
        colWidths=[width * 0.76, width * 0.24],
    )
    ref_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(ref_row)
    story.append(Spacer(1, 3 * mm))
    meeting_title = f"Minutes of the {_ordinal(meeting.get('meetingNo'))} Meeting of Departmental Academic Committee"
    story.append(Paragraph(_escape(meeting_title), ParagraphStyle(
        "DACMeetingTitle", parent=styles["h1"], alignment=TA_CENTER, fontSize=12, leading=15, spaceBefore=2, spaceAfter=9,
    )))
    story.append(Paragraph(_escape(_meeting_description(meeting)), styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>Members Present:</b> (Provide the list of members who are present at the meeting)", styles["body"]))

    member_rows = [[
        Paragraph("Sl. No.", styles["table_head_plain"]),
        Paragraph("Name and Designation", styles["table_head_plain"]),
        Paragraph("Role", styles["table_head_plain"]),
        Paragraph("Signature", styles["table_head_plain"]),
    ]]
    for row_no, member in enumerate(present_members, start=1):
        name = str(member.get("name") or "")
        designation = str(member.get("designation") or "")
        member_rows.append([
            Paragraph(f"{row_no:02d}", styles["center"]),
            Paragraph(_escape(f"{name} {designation}".strip()), styles["table"]),
            Paragraph(_escape(member.get("role") or "Member"), styles["table"]),
            Paragraph("&nbsp;", styles["table"]),
        ])
    if len(member_rows) == 1:
        member_rows.append([
            Paragraph("—", styles["center"]), Paragraph("No attendance marked.", styles["table"]),
            Paragraph("", styles["table"]), Paragraph("", styles["table"]),
        ])
    member_table = Table(member_rows, colWidths=[17 * mm, width * 0.43, width * 0.23, width * 0.20], repeatRows=1, hAlign="LEFT")
    member_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(member_table)

    # Reference page 2 — opening statement and one generated block per approved agenda.
    story.append(PageBreak())
    story.append(Paragraph(
        "The Chairperson welcomed all the members. The member secretary delivered the opening remarks and deliberated on the following agenda points.",
        styles["body"],
    ))
    story.append(Spacer(1, 2 * mm))
    for index, item in enumerate(mom_items, start=1):
        number = int(item.get("agendaNo") or index)
        title = _agenda_document_title(item, meeting)
        agenda_id = str(item.get("agendaId") or item.get("id") or "")
        story.append(Paragraph(_escape(f"Agenda No: {number:02d}  {title}"), styles["body"]))
        story.append(Paragraph("<b>Discussion:</b>", styles["body"]))
        discussion = str(item.get("discussion") or "").strip()
        story.append(Paragraph(_escape(discussion) if discussion else "&nbsp;", styles["body"]))
        story.append(Paragraph("<b>Recommendations:</b>", styles["body"]))
        recommendation = str(item.get("recommendation") or "").strip()
        if item.get("noRecommendation") and not recommendation:
            recommendation = "No separate recommendation recorded."
        story.append(Paragraph(_escape(recommendation) if recommendation else "&nbsp;", styles["body"]))
        attachments = item.get("attachments") or []
        refs = []
        for attachment in attachments:
            file_id = attachment.get("id")
            label = annexure_labels.get(file_id)
            if label:
                refs.append(f"Annexure {label} — {attachment.get('name', 'Attachment')}")
        if not refs:
            refs.append(f"Annexure {number:02d}")
        document_label = "Document:" if agenda_id == "std-mom" else "Ref. Document:"
        story.append(Paragraph(_escape(f"{document_label} " + "; ".join(refs)), styles["small"]))
        story.append(Spacer(1, 3 * mm))

    additional_items = data.get("additionalDiscussions") or []
    story.append(Paragraph("Additional discussion points (if any)", styles["h2"]))
    if not additional_items:
        story.append(Paragraph("&nbsp;", styles["body"]))
    for index, item in enumerate(additional_items, start=1):
        title = str(item.get("title") or "Additional discussion point")
        story.append(Paragraph(_escape(f"Additional discussion {index:02d}: {title}"), styles["body"]))
        story.append(Paragraph("<b>Discussion:</b>", styles["body"]))
        story.append(Paragraph(_escape(item.get("discussion") or "") or "&nbsp;", styles["body"]))
        story.append(Paragraph("<b>Recommendations:</b>", styles["body"]))
        story.append(Paragraph(_escape(item.get("recommendation") or "") or "&nbsp;", styles["body"]))
        story.append(Spacer(1, 2 * mm))

    # Reference page 3 — photos retain their natural aspect ratio, followed by the action table.
    story.append(PageBreak())
    story.append(Paragraph(
        "Geo-Tagged Photos and Online Platform Screenshots – Departmental Academic Committee",
        ParagraphStyle("DACPhotoHeading", parent=styles["h1"], fontSize=11, leading=14, spaceBefore=0, spaceAfter=8),
    ))
    image_photos = [photo for photo in photos if (photo.get("file") or {}).get("id")]
    for photo_index, photo in enumerate(image_photos, start=1):
        file_data = photo.get("file") or {}
        try:
            flowable = _as_pdf_image(file_data.get("id", ""), width - 8 * mm, 64 * mm)
        except Exception:
            flowable = None
        if not flowable:
            continue
        story.append(flowable)
        caption_parts = [str(photo.get("caption") or file_data.get("name") or f"Image {photo_index}")]
        if photo.get("location"):
            caption_parts.append(f"Location: {photo['location']}")
        if photo.get("capturedAt"):
            caption_parts.append(f"Date/time: {photo['capturedAt']}")
        story.append(Paragraph(_escape(f"Image {photo_index}: " + " · ".join(caption_parts)), styles["small"]))
        story.append(Spacer(1, 2 * mm))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Action Items:", styles["h2"]))

    action_rows = [[
        Paragraph("Agenda No", styles["table_head_plain"]),
        Paragraph("Action(s) to be Taken", styles["table_head_plain"]),
        Paragraph("Person(s) Responsible", styles["table_head_plain"]),
        Paragraph("Target Date", styles["table_head_plain"]),
    ]]
    for action in actions:
        action_rows.append([
            Paragraph(_escape(action.get("agendaNo", "")), styles["table"]),
            Paragraph(_escape(action.get("text", "")), styles["table"]),
            Paragraph(_escape(action.get("owner", "")), styles["table"]),
            Paragraph(_escape(_format_date_dmy(action.get("targetDate")) if action.get("targetDate") else ""), styles["table"]),
        ])
    if len(action_rows) == 1:
        action_rows.append([
            Paragraph("—", styles["table"]), Paragraph("", styles["table"]),
            Paragraph("", styles["table"]), Paragraph("", styles["table"]),
        ])
    action_table = LongTable(action_rows, colWidths=[20 * mm, width * 0.42, width * 0.32, width * 0.18], repeatRows=1)
    action_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(action_table)

    # Reference page 4 — closing, signature locations and annexure enclosure note.
    story.append(PageBreak())
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "The Chairperson and the Member Secretary thanked all the members for their contributions and requested their continued support.",
        styles["body"],
    ))
    story.append(Spacer(1, 24 * mm))
    signature_data = [[
        Paragraph("_____________________________<br/><b>Member Secretary</b>", styles["center"]),
        Paragraph("_____________________________<br/><b>Chairperson</b>", styles["center"]),
    ]]
    sign_table = Table(signature_data, colWidths=[width / 2, width / 2])
    sign_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("Encl: Annexures", styles["body"]))

    doc.build(story)
    return buffer.getvalue()
def build_final_pdf(data: dict) -> bytes:
    main_pdf = _build_main_mom_pdf(data)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(main_pdf)))

    meeting = data.get("meeting") or {}
    mom_items = data.get("momItems") or []
    entries = annexure_entries(mom_items)
    if entries:
        writer.append(PdfReader(io.BytesIO(_annexure_index_pdf(entries))))
    for entry in entries:
        path = get_upload_path(entry["id"])
        if not path:
            continue
        extension = path.suffix.lower()
        if extension == ".pdf":
            writer.append(PdfReader(io.BytesIO(_annexure_divider_pdf(entry))))
            writer.append(str(path))
        elif extension in {".jpg", ".jpeg", ".png", ".webp"}:
            annexure_pdf = _image_to_pdf(path.read_bytes(), f"Annexure {entry['label']}: {entry['name']}")
            writer.append(PdfReader(io.BytesIO(annexure_pdf)))
        elif extension in {".docx", ".xlsx", ".pptx", ".txt", ".csv"}:
            annexure_pdf = _office_attachment_pdf(path, entry["name"], entry["agendaTitle"], entry["label"])
            writer.append(PdfReader(io.BytesIO(annexure_pdf)))

    writer.add_metadata({
        "/Title": "DAC Minutes of Meeting",
        "/Subject": f"{meeting.get('school', '')} — {meeting.get('department', '')}",
        "/Creator": "DAC Minutes Demo",
    })
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def meeting_end_passed(meeting: dict, now: datetime | None = None) -> bool:
    """Return whether the scheduled local meeting end has passed, independent of completion."""
    date_text = meeting.get("date")
    end_text = meeting.get("endTime")
    if not date_text or not end_text:
        return False
    try:
        end_at = datetime.combine(
            datetime.fromisoformat(date_text).date(),
            time_value.fromisoformat(end_text),
            tzinfo=COLLEGE_TZ,
        )
    except ValueError:
        return False
    current = now or datetime.now(COLLEGE_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=COLLEGE_TZ)
    return current >= end_at


def meeting_start_passed(meeting: dict, now: datetime | None = None) -> bool:
    date_text, start_text = meeting.get("date"), meeting.get("startTime")
    if not date_text or not start_text:
        return False
    try:
        start_at = datetime.combine(datetime.fromisoformat(date_text).date(), time_value.fromisoformat(start_text), tzinfo=COLLEGE_TZ)
    except ValueError:
        return False
    current = now or datetime.now(COLLEGE_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=COLLEGE_TZ)
    return current >= start_at


def can_edit_minutes(data: dict, now: datetime | None = None) -> bool:
    meeting = data.get("meeting") or {}
    return data.get("status") == "approved" and meeting.get("completed") is True and meeting_end_passed(meeting, now)

def _validate_upload(file_storage) -> tuple[str, bytes]:
    original_name = file_storage.filename or ""
    safe_name = secure_filename(original_name)
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Choose a supported PDF, image, Office document, TXT, or CSV file.")
    raw = file_storage.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Each file must be 15 MB or smaller in this demo.")
    if not raw:
        raise ValueError("The selected file is empty.")

    try:
        if extension == ".pdf":
            pdf = PdfReader(io.BytesIO(raw))
            if pdf.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported in the demo.")
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise ValueError(f"PDFs are limited to {MAX_PDF_PAGES} pages in this demo.")
        elif extension in {".jpg", ".jpeg", ".png", ".webp"}:
            image = PILImage.open(io.BytesIO(raw))
            image.verify()
        elif extension in {".docx", ".xlsx", ".pptx"}:
            if not raw.startswith(b"PK\x03\x04"):
                raise ValueError("This does not look like a valid Office Open XML document.")
        elif b"\x00" in raw:
            raise ValueError("Binary content is not accepted as TXT/CSV.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The file could not be validated. Try exporting it as PDF or a standard image.") from exc
    return safe_name, raw


def _public_user(user: dict) -> dict:
    return {key: user.get(key) for key in ("id", "email", "name", "role", "active", "schoolId", "school", "departmentId", "department")}


def _email_is_valid(email: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email or ""))


def _code_digest(email: str, code: str) -> str:
    secret = str(app.secret_key).encode("utf-8")
    return hmac.new(secret, f"{email.lower()}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _workspace_payload(workspace: dict | None) -> dict:
    if not workspace:
        return {"workspace": None}
    return {"workspaceId": workspace["workspaceId"], "status": workspace["status"],
            "state": workspace["payload"], "updatedAt": workspace["updatedAt"]}


def _external_workspace_payload(workspace: dict | None) -> dict:
    if not workspace:
        return {"workspace": None}
    source = workspace["payload"]
    meeting = source.get("meeting") or {}
    approved = source.get("approvedMeeting") or {}
    safe_meeting = {key: meeting.get(key) for key in ("id", "meetingNo", "academicYear", "semester", "school", "department", "date", "startTime", "endTime", "venue", "mode")}
    safe_agendas = [{key: item.get(key) for key in ("id", "kind", "title")} for item in (approved.get("agendas") or [])]
    safe_state = {"status": "approved", "meeting": safe_meeting, "approvedMeeting": {"agendas": safe_agendas}, "momItems": []}
    return {"workspaceId": workspace["workspaceId"], "status": "approved", "state": safe_state, "updatedAt": workspace["updatedAt"]}


def _meeting_profile_matches(meeting: dict, user: dict) -> bool:
    def clean(value: str, prefix: str) -> str:
        return re.sub(rf"^{re.escape(prefix)}\s*", "", str(value or ""), flags=re.I).strip().casefold()
    school = clean(meeting.get("school", ""), "School of")
    department = clean(meeting.get("department", ""), "Department of")
    allowed_school = str(user.get("school") or "").strip().casefold()
    allowed_department = str(user.get("department") or "").strip().casefold()
    return (str(meeting.get("chairEmail", "")).strip().lower() == user["email"].lower()
            and str(meeting.get("chairName", "")).strip().casefold() == str(user.get("name") or "").strip().casefold()
            and school == allowed_school and department == allowed_department)


def _validate_workspace_proposal(payload: dict, user: dict) -> str | None:
    meeting = payload.get("meeting") or {}
    required = ("meetingNo", "academicYear", "semester", "school", "department", "date", "startTime", "endTime", "venue", "chairName", "chairEmail")
    missing = [field for field in required if not str(meeting.get(field) or "").strip()]
    if missing:
        return "Complete required meeting details: " + ", ".join(missing) + "."
    if not _meeting_profile_matches(meeting, user):
        return "The meeting school, department and organizer must match your provisioned faculty profile. Ask the System Administrator to update your assignment if needed."
    if not (meeting.get("agendas") or []):
        return "Select or add at least one agenda item."
    if meeting.get("startTime", "") >= meeting.get("endTime", ""):
        return "Expected end time must be after start time."
    if any(item.get("id") in {"std-mom", "std-atr"} for item in meeting.get("agendas", [])) and not (meeting.get("previousMeetingNo") and meeting.get("previousMeetingDate")):
        return "Add the previous meeting number and date for the selected MoM / ATR agenda."
    members = meeting.get("members") or []
    chairs = [member for member in members if member.get("role") == "Chairperson"]
    if len(chairs) != 1:
        return "The meeting roster must contain exactly one meeting-specific Chairperson/organizer."
    if str(chairs[0].get("email") or "").strip().lower() != str(meeting.get("chairEmail") or "").strip().lower() or str(chairs[0].get("name") or "").strip().casefold() != str(meeting.get("chairName") or "").strip().casefold():
        return "The Chairperson roster row must identify the signed-in meeting organizer."
    seen = set()
    for member in members:
        email = str(member.get("email") or "").strip().lower()
        if not str(member.get("name") or "").strip() or not _email_is_valid(email):
            return "Every proposed member needs a name and valid email address."
        if email in seen:
            return "The proposed member list contains a duplicate email address."
        seen.add(email)
        allowed = get_user_by_email(email, active_only=True)
        if not allowed:
            return f"{email} is not in the active access directory. Ask the System Administrator to provision this invitee first."
        if (member.get("role") == "External Member") != (allowed.get("role") == "external_member"):
            return f"{email} must be provisioned as an External Member or assigned an internal member role consistently."
    return None


def _attachment_ids(items: list[dict]) -> set[str]:
    result: set[str] = set()
    for item in items or []:
        for attachment in item.get("attachments") or []:
            if attachment.get("id"):
                result.add(str(attachment["id"]))
    return result


def _validate_owned_uploads(user_id: str, state: dict) -> bool:
    ids = _attachment_ids(state.get("momItems") or [])
    ids.update(str((photo.get("file") or {}).get("id")) for photo in state.get("photos") or [] if (photo.get("file") or {}).get("id"))
    return all((record := get_upload_record(file_id)) is not None and record["owner_id"] == user_id for file_id in ids)


def _approved_mom_snapshot(state: dict) -> dict:
    import copy
    meeting = copy.deepcopy(state.get("meeting") or {})
    meeting["completed"] = False
    meeting["attendanceConfirmed"] = False
    meeting["members"] = [{**member, "present": False} for member in (meeting.get("members") or [])]
    previous = {item.get("agendaId"): item for item in (state.get("momItems") or [])}
    mom_items = []
    for index, agenda in enumerate(meeting.get("agendas") or [], start=1):
        existing = previous.get(agenda.get("id"))
        title = _agenda_document_title(agenda, meeting)
        if existing:
            mom_items.append({**existing, "agendaNo": index, "agendaId": agenda.get("id"), "title": title, "kind": agenda.get("kind", "standard")})
        else:
            mom_items.append({"id": uuid.uuid4().hex, "agendaId": agenda.get("id"), "agendaNo": index, "title": title,
                              "kind": agenda.get("kind", "standard"), "discussion": "", "recommendation": "",
                              "noRecommendation": False, "attachments": []})
    state = {**state, "status": "approved", "meeting": meeting,
             "approvedMeeting": {**meeting, "agendas": [{**agenda, "title": _agenda_document_title(agenda, meeting)} for agenda in (meeting.get("agendas") or [])]},
             "momItems": mom_items, "approvalVersion": int(state.get("approvalVersion") or 0) + 1,
             "officeComment": "", "changeRequest": False, "meetingCompletedAt": "", "pdfGenerated": False}
    return state


@app.get("/")
def index():
    return jsonify({"service": "DAC Minutes Studio API", "frontend": "Run the Vite application on port 3000.", "health": "/api/health"})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "mode": APP_ENV, "authentication": "email allow-list + local demo OTP", "message": "College SSO/MFA must be configured for production."})


@app.post("/api/auth/request-code")
def auth_request_code():
    if APP_ENV == "production":
        return jsonify({"error": "Production authentication must use the college Microsoft identity tenant; local demo OTP is disabled."}), 503
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    if not _email_is_valid(email):
        return jsonify({"error": "Enter a valid email address."}), 400
    user = get_user_by_email(email, active_only=True)
    if not user:
        return jsonify({"message": "If the address is active in the access directory, a sign-in code is available."})
    code = f"{secrets.randbelow(1_000_000):06d}"
    now_ts = time_module.time()
    try:
        store_login_code(email, _code_digest(email, code), now_ts + 300, now_ts, request.remote_addr or "")
    except TimeoutError as exc:
        return jsonify({"error": str(exc)}), 429
    response = {"message": "One-time code created; delivery is simulated in this local demo."}
    if DEMO_AUTH_SHOW_OTP:
        response["demoCode"] = code
        response["demoOnly"] = True
    return jsonify(response)


@app.post("/api/auth/verify-code")
def auth_verify_code():
    if APP_ENV == "production":
        return jsonify({"error": "Production authentication must use the college Microsoft identity tenant."}), 503
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    code = str(payload.get("code") or "").strip()
    user = get_user_by_email(email, active_only=True) if _email_is_valid(email) else None
    if not user or not re.fullmatch(r"\d{6}", code) or not verify_login_code(email, _code_digest(email, code), time_module.time()):
        return jsonify({"error": "The code is invalid or expired, or this account is not active in the access directory."}), 401
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"user": _public_user(user), "csrfToken": session["csrf_token"], "demoOnly": True})


@app.get("/api/auth/me")
@login_required
def auth_me():
    return jsonify({"user": _public_user(get_current_user()), "csrfToken": session.get("csrf_token", ""), "demoOnly": True})


@app.post("/api/auth/logout")
@login_required
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/catalog")
@roles_required("system_admin", "academic_office", "faculty")
def academic_catalog():
    catalog = get_catalog()
    user = get_current_user()
    if user["role"] == "faculty":
        catalog["schools"] = [school for school in catalog["schools"] if school["name"] == user.get("school")]
    return jsonify(catalog)


@app.get("/api/admin/users")
@roles_required("system_admin")
def admin_list_users():
    return jsonify({"users": list_users(), "roles": ROLE_CHOICES, "catalog": get_catalog()})


@app.post("/api/admin/users")
@roles_required("system_admin")
def admin_add_user():
    payload = request.get_json(silent=True) or {}
    email, name, role = str(payload.get("email") or "").strip().lower(), str(payload.get("name") or "").strip(), str(payload.get("role") or "faculty")
    if not _email_is_valid(email) or not name:
        return jsonify({"error": "Enter a valid email and full name."}), 400
    if role not in ROLES:
        return jsonify({"error": "Choose a valid role."}), 400
    try:
        user = db_add_user(email, name, role, payload.get("school") or None, payload.get("department") or None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"error": "That email already exists in the access directory."}), 409
        raise
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": "allowlisted_user_added", "actor": get_current_user()["email"], "target": user["email"]})
    return jsonify({"user": user}), 201


@app.patch("/api/admin/users/<user_id>")
@roles_required("system_admin")
def admin_update_user(user_id: str):
    payload = request.get_json(silent=True) or {}
    current, admin = get_user_by_id(user_id, active_only=False), get_current_user()
    if not current:
        return jsonify({"error": "Account not found."}), 404
    requested_role = payload.get("role", current["role"])
    requested_active = bool(payload.get("active", current["active"]))
    if current["id"] == admin["id"] and (not requested_active or requested_role != "system_admin"):
        return jsonify({"error": "You cannot deactivate or demote your own System Administrator account."}), 400
    if current["role"] == "system_admin" and (not requested_active or requested_role != "system_admin") and count_active_admins() <= 1:
        return jsonify({"error": "At least one active System Administrator must remain."}), 400
    try:
        updated = db_update_user(user_id, payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": "allowlisted_user_updated", "actor": admin["email"], "target": updated["email"]})
    return jsonify({"user": updated})


@app.get("/api/workspace")
@login_required
def get_current_workspace():
    user = get_current_user()
    workspace = None
    if user["role"] == "faculty":
        workspace = workspace_for_owner(user["id"])
    elif user["role"] == "academic_office":
        workspace = latest_pending_workspace()
    elif user["role"] == "external_member":
        from auth_store import connect as _connect
        with _connect() as db:
            rows = db.execute("SELECT workspace_id FROM workspaces WHERE status='approved' ORDER BY updated_at DESC").fetchall()
        for row in rows:
            if workspace_access_for_email(row["workspace_id"], user["email"]):
                workspace = get_workspace(row["workspace_id"])
                break
    else:
        return jsonify({"error": "System Administrators manage the access directory, not meeting content."}), 403
    return jsonify(_external_workspace_payload(workspace) if user["role"] == "external_member" else _workspace_payload(workspace))


@app.get("/api/workspaces/inbox")
@roles_required("academic_office")
def workspace_inbox():
    return jsonify({"workspaces": list_pending_workspaces()})


@app.get("/api/workspaces/mine")
@roles_required("faculty")
def my_workspaces():
    user = get_current_user()
    return jsonify({"workspaces": list_workspaces_for_owner(user["id"])})


@app.get("/api/workspaces/<workspace_id>")
@login_required
def get_workspace_detail(workspace_id: str):
    workspace = get_workspace(workspace_id)
    if not workspace:
        return jsonify({"error": "Workspace not found."}), 404
    user = get_current_user()
    allowed = ((user["role"] == "faculty" and workspace["ownerId"] == user["id"])
               or (user["role"] == "academic_office" and workspace["status"] == "pending")
               or (user["role"] == "external_member" and workspace_access_for_email(workspace_id, user["email"])))
    if not allowed:
        return jsonify({"error": "This meeting is outside your access scope."}), 403
    return jsonify(_external_workspace_payload(workspace) if user["role"] == "external_member" else _workspace_payload(workspace))


@app.post("/api/workspace/save")
@roles_required("faculty")
def save_current_workspace():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    state = payload.get("state") or {}
    meeting = state.get("meeting") or {}
    workspace_id = str(payload.get("workspaceId") or meeting.get("id") or "").strip()
    if not workspace_id or len(workspace_id) > 120:
        return jsonify({"error": "Missing or invalid workspace identifier."}), 400
    existing = get_workspace(workspace_id)
    if existing and existing["ownerId"] != user["id"]:
        return jsonify({"error": "This workspace belongs to another account."}), 403
    error = _validate_workspace_proposal(state, user)
    if error and state.get("status") in {"pending", "approved"}:
        return jsonify({"error": error}), 400
    status = existing["status"] if existing else "draft"
    if existing and status == "approved":
        if state.get("status") == "revision" and not meeting_start_passed(existing["payload"].get("meeting") or {}):
            change_request = {**existing["payload"], "status": "revision", "officeComment": "Faculty proposed a change; resubmission requires Academic Office review.", "changeRequest": True}
            save_workspace(workspace_id, user["id"], change_request, "revision")
            return jsonify({"ok": True, "state": change_request, "status": "revision"})
        if state.get("status") != "approved" or not can_edit_minutes(state):
            return jsonify({"error": "Approved meeting content is locked until the scheduled end time has passed AND the meeting is marked completed."}), 409
        if not _validate_owned_uploads(user["id"], state):
            return jsonify({"error": "An attachment is not owned by this account."}), 403
        old, new_meeting = existing["payload"], state.get("meeting") or {}
        old_meeting = old.get("meeting") or {}
        immutable_fields = ("meetingNo", "academicYear", "semester", "school", "department", "schoolCode", "departmentCode", "previousMeetingNo", "previousMeetingDate", "date", "startTime", "endTime", "venue", "mode", "onlineLink", "chairName", "chairEmail")
        if any(new_meeting.get(field) != old_meeting.get(field) for field in immutable_fields):
            return jsonify({"error": "Approved meeting details and agenda wording are read-only; submit a change for reapproval."}), 403
        if [item.get("id") for item in new_meeting.get("agendas", [])] != [item.get("id") for item in old_meeting.get("agendas", [])]:
            return jsonify({"error": "Approved agenda wording and sequence are immutable."}), 403
        old_members, new_members = old_meeting.get("members", []), new_meeting.get("members", [])
        if [{key: member.get(key) for key in ("id", "name", "designation", "role", "email")} for member in new_members] != [{key: member.get(key) for key in ("id", "name", "designation", "role", "email")} for member in old_members]:
            return jsonify({"error": "The approved invitee roster is immutable in the MoM."}), 403
        old_items = {item.get("id"): item for item in old.get("momItems", [])}
        new_items = {item.get("id"): item for item in state.get("momItems", [])}
        if set(old_items) != set(new_items):
            return jsonify({"error": "Approved MoM sections cannot be added or removed."}), 403
        merged = dict(old)
        merged_meeting = dict(old_meeting)
        merged_meeting["completed"] = bool(new_meeting.get("completed"))
        merged_meeting["attendanceConfirmed"] = bool(new_meeting.get("attendanceConfirmed"))
        merged_meeting["members"] = [{**member, "present": bool(new_members[index].get("present"))} for index, member in enumerate(old_members)]
        merged["meeting"] = merged_meeting
        merged["meetingCompletedAt"] = state.get("meetingCompletedAt", old.get("meetingCompletedAt", ""))
        merged["momItems"] = [{**old_items[item_id], **{key: new_items[item_id].get(key) for key in ("discussion", "recommendation", "noRecommendation", "attachments")}} for item_id in old_items]
        merged["additionalDiscussions"] = state.get("additionalDiscussions") or []
        merged["photos"] = state.get("photos") or []
        merged["actionItems"] = state.get("actionItems") or []
        merged["aiReport"] = state.get("aiReport")
        merged["pdfGenerated"] = False
        save_workspace(workspace_id, user["id"], merged, "approved")
        return jsonify({"ok": True, "state": merged, "status": "approved"})
    if existing and status == "pending":
        return jsonify({"ok": True, "status": "pending", "state": existing["payload"]})
    if state.get("status") not in ({"draft", "revision", "rejected"} if existing else {"draft"}):
        return jsonify({"error": "Only an editable draft can be autosaved."}), 409
    if not _meeting_profile_matches(meeting, user):
        return jsonify({"error": "Meeting organizer, school and department must match the signed-in faculty profile."}), 403
    state["status"] = status if existing else "draft"
    save_workspace(workspace_id, user["id"], state, state["status"])
    return jsonify({"ok": True, "status": state["status"]})


@app.post("/api/workspace/submit")
@roles_required("faculty")
def submit_workspace():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    state = payload.get("state") or {}
    meeting = state.get("meeting") or {}
    workspace_id = str(payload.get("workspaceId") or meeting.get("id") or "").strip()
    if not workspace_id:
        return jsonify({"error": "Missing meeting workspace identifier."}), 400
    error = _validate_workspace_proposal(state, user)
    if error:
        return jsonify({"error": error}), 400
    existing = get_workspace(workspace_id)
    if existing and existing["ownerId"] != user["id"]:
        return jsonify({"error": "This workspace belongs to another account."}), 403
    if existing and existing["status"] not in {"draft", "revision", "rejected"}:
        is_premeeting_change = existing["status"] == "approved" and state.get("status") == "revision" and not meeting_start_passed(existing["payload"].get("meeting") or {})
        if not is_premeeting_change:
            return jsonify({"error": "This request is not editable or is already pending review."}), 409
        state["changeRequest"] = True
    state["status"] = "pending"
    state["submittedAt"] = datetime.now(COLLEGE_TZ).strftime("%d %b %Y, %H:%M")
    state["submittedVersion"] = int(state.get("submittedVersion") or 0) + 1
    state["officeComment"] = ""
    save_workspace(workspace_id, user["id"], state, "pending")
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": "request_submitted", "actor": user["email"], "workspaceId": workspace_id})
    return jsonify({"ok": True, "workspaceId": workspace_id, "state": state})


@app.post("/api/workspace/decision")
@roles_required("academic_office")
def decide_workspace():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    workspace_id = str(payload.get("workspaceId") or "")
    decision, comment = str(payload.get("decision") or ""), str(payload.get("comment") or "").strip()
    workspace = get_workspace(workspace_id)
    if not workspace or workspace["status"] != "pending":
        return jsonify({"error": "This request is no longer pending review."}), 409
    if decision not in {"approved", "revision", "rejected"}:
        return jsonify({"error": "Choose approve, return for revision, or reject."}), 400
    if decision in {"revision", "rejected"} and not comment:
        return jsonify({"error": "Add a specific review comment or rejection reason."}), 400
    state = workspace["payload"]
    if decision == "approved":
        owner = get_user_by_id(workspace["ownerId"], active_only=True)
        proposal_error = _validate_workspace_proposal(state, owner) if owner else "The meeting owner account is no longer active."
        if proposal_error:
            return jsonify({"error": f"The request can no longer be approved: {proposal_error}"}), 409
        state = _approved_mom_snapshot(state)
    else:
        state = {**state, "status": decision, "officeComment": comment}
    save_workspace(workspace_id, workspace["ownerId"], state, decision)
    event = "agenda_and_members_approved" if decision == "approved" else "request_returned_for_revision" if decision == "revision" else "request_rejected"
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": event, "actor": user["email"], "workspaceId": workspace_id, "comment": comment})
    return jsonify({"ok": True, "workspaceId": workspace_id, "state": state, "status": decision})


@app.post("/api/workspace/complete")
@roles_required("faculty")
def mark_workspace_completed():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    workspace_id = str(payload.get("workspaceId") or "")
    workspace = get_workspace(workspace_id)
    if not workspace or workspace["ownerId"] != user["id"] or workspace["status"] != "approved":
        return jsonify({"error": "An approved meeting owned by this account is required."}), 403
    state = workspace["payload"]
    meeting = {**(state.get("meeting") or {}), "completed": True}
    state = {**state, "meeting": meeting, "meetingCompletedAt": datetime.now(COLLEGE_TZ).strftime("%d %b %Y, %H:%M")}
    save_workspace(workspace_id, user["id"], state, "approved")
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": "meeting_marked_completed", "actor": user["email"], "workspaceId": workspace_id})
    return jsonify({"ok": True, "state": state})


@app.post("/api/workspace/demo/fast-forward")
@roles_required("faculty")
def fast_forward_workspace_end():
    if APP_ENV == "production":
        return jsonify({"error": "Demo schedule fast-forward is disabled in production."}), 403
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    workspace_id = str(payload.get("workspaceId") or "")
    workspace = get_workspace(workspace_id)
    if not workspace or workspace["ownerId"] != user["id"] or workspace["status"] != "approved":
        return jsonify({"error": "An approved meeting owned by this account is required."}), 403
    from datetime import timedelta
    yesterday = (datetime.now(COLLEGE_TZ) - timedelta(days=1)).date().isoformat()
    state = workspace["payload"]
    meeting = {**(state.get("meeting") or {}), "date": yesterday, "completed": True}
    approved = state.get("approvedMeeting")
    if approved:
        approved = {**approved, "date": yesterday}
    state = {**state, "meeting": meeting, "approvedMeeting": approved,
             "meetingCompletedAt": datetime.now(COLLEGE_TZ).strftime("%d %b %Y, %H:%M")}
    save_workspace(workspace_id, user["id"], state, "approved")
    _append_json(AUDIT_PATH, {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": "demo_meeting_end_fast_forwarded", "actor": user["email"], "workspaceId": workspace_id})
    return jsonify({"ok": True, "state": state})


@app.post("/api/upload")
@roles_required("faculty")
def upload():
    file_storage = request.files.get("file")
    if not file_storage:
        return jsonify({"error": "Choose a file to upload."}), 400
    try:
        safe_name, raw = _validate_upload(file_storage)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    file_id = uuid.uuid4().hex
    extension = Path(safe_name).suffix.lower()
    target = UPLOAD_DIR / f"{file_id}{extension}"
    target.write_bytes(raw)
    create_upload_record(file_id, get_current_user()["id"], safe_name, extension, len(raw))
    mimetype = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return jsonify({
        "id": file_id,
        "name": safe_name,
        "size": len(raw),
        "type": mimetype,
        "extension": extension,
        "previewUrl": f"/api/file/{file_id}",
    })


@app.get("/api/file/<file_id>")
@login_required
def get_file(file_id: str):
    path = get_upload_path(file_id)
    record = get_upload_record(file_id)
    if not path or not record:
        return jsonify({"error": "File not found."}), 404
    user = get_current_user()
    if record["owner_id"] != user["id"] and user["role"] != "academic_office":
        return jsonify({"error": "This file is outside your access scope. Guest annexure sharing is not enabled in this demo."}), 403
    response = send_file(path, mimetype=mimetypes.guess_type(path.name)[0] or "application/octet-stream", as_attachment=False, download_name=path.name)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.post("/api/validate")
@roles_required("faculty", "academic_office")
def validate_endpoint():
    payload = request.get_json(silent=True) or {}
    return jsonify(validate_mom(payload))


@app.post("/api/outbox")
@roles_required("academic_office")
def outbox_endpoint():
    payload = request.get_json(silent=True) or {}
    meeting_id = str((payload.get("meeting") or {}).get("id") or "")
    workspace = get_workspace(meeting_id)
    if not workspace or workspace["status"] != "approved":
        return jsonify({"error": "An approved meeting workspace is required to create an invitation record."}), 403
    meeting = dict(workspace["payload"].get("meeting") or {})
    meeting["agendas"] = [{**agenda, "title": _agenda_document_title(agenda, meeting)} for agenda in (meeting.get("agendas") or [])]
    members = meeting.get("members", [])
    recipients = [str(member.get("email", "")) for member in members if member.get("email")]
    if not recipients:
        return jsonify({"error": "No approved invitees are listed."}), 400
    for member in members:
        invited = get_user_by_email(str(member.get("email") or ""), active_only=True)
        if not invited or ((member.get("role") == "External Member") != (invited.get("role") == "external_member")):
            return jsonify({"error": f"The approved invitee {member.get('email', '')} is no longer active or has an inconsistent role."}), 409
    organizer_email = str(meeting.get("chairEmail") or "")
    if str(payload.get("from") or "").lower() != organizer_email.lower():
        return jsonify({"error": "Invitation sender does not match the meeting-specific organizer."}), 403
    record = {
        "id": uuid.uuid4().hex,
        "createdAt": datetime.now(COLLEGE_TZ).isoformat(),
        "from": organizer_email,
        "recipients": recipients,
        "subject": str(payload.get("subject") or "DAC meeting invitation"),
        "meeting": meeting,
        "status": "DEMO ONLY — not sent to email",
    }
    _append_json(OUTBOX_PATH, record)
    _append_json(AUDIT_PATH, {"at": record["createdAt"], "event": "invitation_simulated", "meeting": record["meeting"].get("id", "")})
    return jsonify(record), 201


@app.get("/api/outbox")
@roles_required("academic_office", "faculty")
def get_outbox():
    rows = _read_json(OUTBOX_PATH, [])
    user = get_current_user()
    if user["role"] == "faculty":
        rows = [row for row in rows if owner_for_workspace(str((row.get("meeting") or {}).get("id") or "")) == user["id"]]
    return jsonify(rows)


@app.post("/api/audit")
@roles_required("system_admin", "academic_office", "faculty")
def audit_endpoint():
    payload = request.get_json(silent=True) or {}
    user = get_current_user()
    record = {"at": datetime.now(COLLEGE_TZ).isoformat(), "event": str(payload.get("event") or "workflow_event")[:100],
              "actor": user["email"], "role": user["role"],
              "details": {"note": str((payload.get("details") or {}).get("note") or "")[:300],
                          "meetingId": str((payload.get("details") or {}).get("meetingId") or "")[:120]}}
    _append_json(AUDIT_PATH, record)
    return jsonify({"ok": True})


@app.get("/api/audit")
@roles_required("system_admin", "academic_office")
def get_audit():
    return jsonify(_read_json(AUDIT_PATH, []))


@app.post("/api/demo/reset")
@roles_required("system_admin")
def reset_demo():
    # Demo-only reset; production applications need authenticated, audited retention controls.
    for path in UPLOAD_DIR.iterdir():
        if path.is_file():
            path.unlink()
    for path in (OUTBOX_PATH, AUDIT_PATH):
        if path.exists():
            path.unlink()
    delete_all_demo_workspaces()
    return jsonify({"ok": True})


@app.get("/README")
def readme():
    readme_path = BASE_DIR / "README.md"
    return send_file(readme_path, mimetype="text/markdown")


@app.post("/api/export")
@roles_required("faculty")
def export_pdf():
    user = get_current_user()
    request_payload = request.get_json(silent=True) or {}
    meeting_id = str((request_payload.get("meeting") or {}).get("id") or "")
    owner_id = owner_for_workspace(meeting_id)
    if not owner_id or owner_id != user["id"]:
        return jsonify({"error": "This meeting is outside your access scope."}), 403
    workspace = get_workspace(meeting_id)
    payload = workspace["payload"] if workspace else {}
    if not can_edit_minutes(payload):
        return jsonify({"error": "The final MoM can be exported only after approval, the scheduled end time has passed, and the meeting is marked complete."}), 409
    try:
        pdf = build_final_pdf(payload)
    except Exception as exc:
        app.logger.exception("Could not generate the final MoM PDF")
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500
    meeting = payload.get("meeting") or {}
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"DAC-{meeting.get('meetingNo', 'Meeting')}-{meeting.get('department', 'MoM')}").strip("-") or "DAC-MoM"
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=f"{slug}.pdf")


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Upload is too large for this demo."}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
