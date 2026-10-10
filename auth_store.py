"""SQLite-backed identity directory, academic catalog and shared meeting workspace."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.environ.get("DAC_DATABASE_PATH", DATA_DIR / "dac-minutes.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

ROLES = {"system_admin", "academic_office", "faculty", "external_member"}
SCHOOLS: dict[str, list[str]] = {
    "Computer Engineering": [
        "Computer Science & Engineering", "Artificial Intelligence & Machine Learning",
        "Cyber Security", "Data Science", "Computer Engineering",
    ],
    "Engineering": [
        "Mechanical Engineering", "Electrical & Electronics Engineering", "Civil Engineering",
        "Electronics & Communication Engineering", "Chemical Engineering", "Robotics & Automation",
    ],
    "Information Science": [
        "MCA", "BCA", "BCA (Data Science)", "B.Sc. Information Technology",
        "Information Science & Engineering",
    ],
    "Commerce": ["B.Com", "BBA", "M.Com", "Accounting & Finance", "Business Analytics"],
    "Arts": ["English", "History", "Economics", "Political Science", "Psychology", "Sociology"],
    "Design": ["Communication Design", "Product Design", "Interaction / UI-UX Design", "Fashion Design", "Interior Design"],
    "Health Care": ["Nursing", "Allied Health Sciences", "Physiotherapy", "Health Administration", "Medical Laboratory Technology"],
    "Science": ["Mathematics", "Physics", "Chemistry", "Biotechnology", "Statistics"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def init_db() -> None:
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL REFERENCES schools(id),
            name TEXT NOT NULL COLLATE NOCASE,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(school_id, name)
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('system_admin','academic_office','faculty','external_member')),
            school_id INTEGER REFERENCES schools(id),
            department_id INTEGER REFERENCES departments(id),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_codes (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            code_hash TEXT NOT NULL,
            expires_at REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            requested_at REAL NOT NULL,
            source_ip TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status, updated_at DESC);
        CREATE TABLE IF NOT EXISTS uploads (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(id),
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        for school_name, departments in SCHOOLS.items():
            db.execute("INSERT OR IGNORE INTO schools(name) VALUES (?)", (school_name,))
            school_id = db.execute("SELECT id FROM schools WHERE name = ?", (school_name,)).fetchone()["id"]
            for department in departments:
                db.execute("INSERT OR IGNORE INTO departments(school_id, name) VALUES (?, ?)", (school_id, department))
        db.commit()
        # Seed only the disposable local demo; never provision fixture identities in a production database.
        if os.environ.get("APP_ENV", "demo").strip().lower() != "production":
            _seed_users(db)


def _school_department_ids(db: sqlite3.Connection, school: str | None, department: str | None) -> tuple[int | None, int | None]:
    if not school:
        return None, None
    row = db.execute("SELECT id FROM schools WHERE name = ? AND active = 1", (school,)).fetchone()
    if not row:
        raise ValueError("Choose a valid school from the academic catalog.")
    school_id = int(row["id"])
    if not department:
        return school_id, None
    dept = db.execute("SELECT id FROM departments WHERE school_id = ? AND name = ? AND active = 1", (school_id, department)).fetchone()
    if not dept:
        raise ValueError("Choose a department that belongs to the selected school.")
    return school_id, int(dept["id"])


def _seed_users(db: sqlite3.Connection) -> None:
    samples = [
        ("admin@college.example", "System Administrator", "system_admin", None, None),
        ("academic.office@college.example", "Academic Office Reviewer", "academic_office", None, None),
        ("asha.rao@college.example", "Dr. Asha Rao", "faculty", "Engineering", "Mechanical Engineering"),
        ("secretary@college.example", "Prof. Devika Nair", "faculty", "Engineering", "Mechanical Engineering"),
        ("devika.nair@college.example", "Prof. Devika Nair", "faculty", "Computer Engineering", "Computer Science & Engineering"),
        ("kiran.kumar@college.example", "Dr. Kiran Kumar", "faculty", "Information Science", "MCA"),
        ("mira.shah@college.example", "Prof. Mira Shah", "faculty", "Commerce", "B.Com"),
        ("alex@example.org", "Dr. Alex Morgan", "external_member", None, None),
    ]
    stamp = now_iso()
    for email, name, role, school, department in samples:
        school_id, department_id = _school_department_ids(db, school, department)
        db.execute(
            """INSERT OR IGNORE INTO users(id,email,full_name,role,school_id,department_id,active,created_at,updated_at)
               VALUES(?,?,?,?,?,?,1,?,?)""",
            (uuid.uuid4().hex, email.lower(), name, role, school_id, department_id, stamp, stamp),
        )
    db.commit()


def _user_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "email": row["email"], "name": row["full_name"],
        "role": row["role"], "active": bool(row["active"]),
        "schoolId": row["school_id"], "school": row["school_name"],
        "departmentId": row["department_id"], "department": row["department_name"],
        "createdAt": row["created_at"], "updatedAt": row["updated_at"],
    }


def get_user_by_email(email: str, active_only: bool = False) -> dict[str, Any] | None:
    where = "WHERE u.email = ?" + (" AND u.active = 1" if active_only else "")
    with connect() as db:
        row = db.execute(f"""SELECT u.*, s.name AS school_name, d.name AS department_name
            FROM users u LEFT JOIN schools s ON s.id=u.school_id
            LEFT JOIN departments d ON d.id=u.department_id {where}""", (email.strip().lower(),)).fetchone()
    return _user_dict(row) if row else None


def get_user_by_id(user_id: str, active_only: bool = True) -> dict[str, Any] | None:
    where = "WHERE u.id = ?" + (" AND u.active = 1" if active_only else "")
    with connect() as db:
        row = db.execute(f"""SELECT u.*, s.name AS school_name, d.name AS department_name
            FROM users u LEFT JOIN schools s ON s.id=u.school_id
            LEFT JOIN departments d ON d.id=u.department_id {where}""", (user_id,)).fetchone()
    return _user_dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("""SELECT u.*, s.name AS school_name, d.name AS department_name
            FROM users u LEFT JOIN schools s ON s.id=u.school_id
            LEFT JOIN departments d ON d.id=u.department_id
            ORDER BY CASE u.role WHEN 'system_admin' THEN 0 WHEN 'academic_office' THEN 1 WHEN 'faculty' THEN 2 ELSE 3 END,
                     u.full_name COLLATE NOCASE""").fetchall()
    return [_user_dict(row) for row in rows]


def add_user(email: str, name: str, role: str, school: str | None = None, department: str | None = None) -> dict[str, Any]:
    email = email.strip().lower()
    name = name.strip()
    if role not in ROLES:
        raise ValueError("Choose a valid application role.")
    if role == "faculty" and (not school or not department):
        raise ValueError("Faculty accounts must be assigned a school and department.")
    if role in {"system_admin", "academic_office", "external_member"}:
        school = school or None
        department = department or None
    with connect() as db:
        school_id, department_id = _school_department_ids(db, school, department)
        stamp = now_iso()
        user_id = uuid.uuid4().hex
        db.execute("INSERT INTO users(id,email,full_name,role,school_id,department_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)",
                   (user_id, email, name, role, school_id, department_id, stamp, stamp))
        db.commit()
    result = get_user_by_id(user_id)
    assert result is not None
    return result


def update_user(user_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"name", "role", "school", "department", "active"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unsupported user fields: " + ", ".join(sorted(unknown)))
    with connect() as db:
        current = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not current:
            return None
        role = str(changes.get("role", current["role"]))
        if role not in ROLES:
            raise ValueError("Choose a valid application role.")
        name = str(changes.get("name", current["full_name"])).strip()
        if not name:
            raise ValueError("Name cannot be blank.")
        school = changes.get("school")
        if "school" not in changes and current["school_id"]:
            school = db.execute("SELECT name FROM schools WHERE id = ?", (current["school_id"],)).fetchone()["name"]
        department = changes.get("department")
        if "department" not in changes and current["department_id"]:
            department = db.execute("SELECT name FROM departments WHERE id = ?", (current["department_id"],)).fetchone()["name"]
        if role == "faculty" and (not school or not department):
            raise ValueError("Faculty accounts must be assigned a school and department.")
        if role != "faculty" and not school:
            school = None
            department = None
        school_id, department_id = _school_department_ids(db, school, department)
        active = int(bool(changes.get("active", current["active"])))
        db.execute("UPDATE users SET full_name=?, role=?, school_id=?, department_id=?, active=?, updated_at=? WHERE id=?",
                   (name, role, school_id, department_id, active, now_iso(), user_id))
        db.commit()
    return get_user_by_id(user_id, active_only=False)


def get_catalog() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute("""SELECT s.id AS school_id, s.name AS school_name, d.id AS department_id, d.name AS department_name
            FROM schools s LEFT JOIN departments d ON d.school_id=s.id AND d.active=1
            WHERE s.active=1 ORDER BY s.name COLLATE NOCASE, d.name COLLATE NOCASE""").fetchall()
    catalog: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = catalog.setdefault(row["school_id"], {"id": row["school_id"], "name": row["school_name"], "departments": []})
        if row["department_id"] is not None:
            entry["departments"].append({"id": row["department_id"], "name": row["department_name"]})
    return {"schools": list(catalog.values())}


def get_workspace(workspace_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        payload = {}
    return {"workspaceId": row["workspace_id"], "ownerId": row["owner_id"], "status": row["status"],
            "payload": payload, "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def workspace_for_owner(owner_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT workspace_id FROM workspaces WHERE owner_id=? ORDER BY updated_at DESC LIMIT 1", (owner_id,)).fetchone()
    return get_workspace(row["workspace_id"]) if row else None


def latest_pending_workspace() -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT workspace_id FROM workspaces WHERE status='pending' ORDER BY updated_at ASC LIMIT 1").fetchone()
    return get_workspace(row["workspace_id"]) if row else None


def list_workspaces_for_owner(owner_id: str) -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("SELECT workspace_id,status,updated_at,payload_json FROM workspaces WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)).fetchall()
        results = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            meeting = payload.get("meeting") or {}
            results.append({"workspaceId": row["workspace_id"], "status": row["status"], "updatedAt": row["updated_at"],
                "meetingNo": meeting.get("meetingNo"), "school": meeting.get("school"),
                "department": meeting.get("department"), "date": meeting.get("date")})
    return results


def list_pending_workspaces() -> list[dict[str, Any]]:
    with connect() as db:
        rows = db.execute("""SELECT w.workspace_id,w.owner_id,w.status,w.updated_at,u.full_name AS owner_name,u.email AS owner_email
            FROM workspaces w JOIN users u ON u.id=w.owner_id WHERE w.status='pending' ORDER BY w.created_at ASC""").fetchall()
        results = []
        for row in rows:
            try:
                payload = json.loads(db.execute("SELECT payload_json FROM workspaces WHERE workspace_id=?", (row["workspace_id"],)).fetchone()["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
            meeting = payload.get("meeting") or {}
            results.append({"workspaceId": row["workspace_id"], "status": row["status"], "updatedAt": row["updated_at"],
                "ownerName": row["owner_name"], "ownerEmail": row["owner_email"],
                "meetingNo": meeting.get("meetingNo"), "school": meeting.get("school"),
                "department": meeting.get("department"), "date": meeting.get("date")})
    return results


def save_workspace(workspace_id: str, owner_id: str, payload: dict[str, Any], status: str | None = None) -> None:
    stamp = now_iso()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with connect() as db:
        existing = db.execute("SELECT owner_id,created_at FROM workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
        if existing:
            if existing["owner_id"] != owner_id:
                raise PermissionError("This workspace belongs to another account.")
            db.execute("UPDATE workspaces SET status=?,payload_json=?,updated_at=? WHERE workspace_id=?",
                       (status or payload.get("status", "draft"), data, stamp, workspace_id))
        else:
            db.execute("INSERT INTO workspaces(workspace_id,owner_id,status,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                       (workspace_id, owner_id, status or payload.get("status", "draft"), data, stamp, stamp))
        db.commit()


def owner_for_workspace(workspace_id: str) -> str | None:
    with connect() as db:
        row = db.execute("SELECT owner_id FROM workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
    return row["owner_id"] if row else None


def create_upload_record(file_id: str, owner_id: str, filename: str, extension: str, size: int) -> None:
    with connect() as db:
        db.execute("INSERT INTO uploads(id,owner_id,filename,extension,size,created_at) VALUES(?,?,?,?,?,?)",
                   (file_id, owner_id, filename, extension, size, now_iso()))
        db.commit()


def get_upload_record(file_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM uploads WHERE id=?", (file_id,)).fetchone()
    return dict(row) if row else None


def remove_user_codes(email: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM login_codes WHERE email=?", (email,))
        db.commit()


def store_login_code(email: str, code_hash: str, expires_at: float, now_ts: float, source_ip: str) -> None:
    with connect() as db:
        row = db.execute("SELECT requested_at FROM login_codes WHERE email=?", (email,)).fetchone()
        if row and now_ts - float(row["requested_at"]) < 20:
            raise TimeoutError("Wait a few seconds before requesting another sign-in code.")
        db.execute("INSERT INTO login_codes(email,code_hash,expires_at,attempts,requested_at,source_ip) VALUES(?,?,?,0,?,?) "
                   "ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0,requested_at=excluded.requested_at,source_ip=excluded.source_ip",
                   (email, code_hash, expires_at, now_ts, source_ip))
        db.commit()


def verify_login_code(email: str, code_hash: str, now_ts: float) -> bool:
    with connect() as db:
        row = db.execute("SELECT * FROM login_codes WHERE email=?", (email,)).fetchone()
        if not row or float(row["expires_at"]) < now_ts or int(row["attempts"]) >= 5:
            db.execute("DELETE FROM login_codes WHERE email=?", (email,))
            db.commit()
            return False
        import hmac
        if not hmac.compare_digest(str(row["code_hash"]), code_hash):
            db.execute("UPDATE login_codes SET attempts=attempts+1 WHERE email=?", (email,))
            db.commit()
            return False
        db.execute("DELETE FROM login_codes WHERE email=?", (email,))
        db.commit()
        return True


def count_active_admins() -> int:
    with connect() as db:
        return int(db.execute("SELECT COUNT(*) FROM users WHERE role='system_admin' AND active=1").fetchone()[0])


def workspace_access_for_email(workspace_id: str, email: str) -> bool:
    workspace = get_workspace(workspace_id)
    if not workspace or workspace["status"] != "approved":
        return False
    members = (workspace["payload"].get("meeting") or {}).get("members") or []
    return any(member.get("role") == "External Member" and str(member.get("email", "")).strip().lower() == email.lower() for member in members)


def delete_all_demo_workspaces() -> None:
    with connect() as db:
        db.execute("DELETE FROM workspaces")
        db.execute("DELETE FROM uploads")
        db.commit()
