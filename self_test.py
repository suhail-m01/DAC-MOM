"""End-to-end checks for DAC workflow, role gates, scoped files and PDF export."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

# Use an isolated database and filesystem so the test cannot alter the local demo data.
_TEST_TMP = tempfile.TemporaryDirectory(prefix="dac-mom-self-test-")
_TEST_ROOT = Path(_TEST_TMP.name)
os.environ["APP_ENV"] = "demo"
os.environ["DEMO_AUTH_SHOW_OTP"] = "1"
os.environ["DAC_DATABASE_PATH"] = str(_TEST_ROOT / "dac-test.sqlite3")

import app as server
from auth_store import get_catalog
from PIL import Image
from pypdf import PdfReader

app = server.app
app.config["TESTING"] = True
server.UPLOAD_DIR = _TEST_ROOT / "uploads"
server.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
server.OUTBOX_PATH = _TEST_ROOT / "demo-outbox.json"
server.AUDIT_PATH = _TEST_ROOT / "demo-audit.json"


def sign_in(email: str):
    client = app.test_client()
    requested = client.post("/api/auth/request-code", json={"email": email})
    assert requested.status_code == 200, requested.get_data(as_text=True)
    request_data = requested.get_json()
    if "demoCode" not in request_data:
        return client, "", None
    assert len(request_data["demoCode"]) == 6
    verified = client.post("/api/auth/verify-code", json={"email": email, "code": request_data["demoCode"]})
    assert verified.status_code == 200, verified.get_data(as_text=True)
    data = verified.get_json()
    return client, data["csrfToken"], data["user"]


def post(client, csrf: str, path: str, payload: dict):
    return client.post(path, json=payload, headers={"X-CSRF-Token": csrf})


def patch(client, csrf: str, path: str, payload: dict):
    return client.patch(path, json=payload, headers={"X-CSRF-Token": csrf})


# Pure business rules: minutes unlock only for an approved and completed meeting after its scheduled end.
meeting_gate = {"date": "2030-01-02", "endTime": "12:00", "completed": False}
assert not server.meeting_end_passed(meeting_gate, datetime.fromisoformat("2030-01-02T11:59:00"))
assert not server.can_edit_minutes({"status": "approved", "meeting": meeting_gate}, datetime.fromisoformat("2030-01-02T12:00:00"))
assert not server.can_edit_minutes({"status": "approved", "meeting": {**meeting_gate, "completed": True}}, datetime.fromisoformat("2030-01-02T11:59:00"))
assert server.can_edit_minutes({"status": "approved", "meeting": {**meeting_gate, "completed": True}}, datetime.fromisoformat("2030-01-02T12:00:00"))
assert not server.can_edit_minutes({"status": "pending", "meeting": {**meeting_gate, "completed": True}}, datetime.fromisoformat("2030-01-02T12:00:00"))

# The local consistency check examines typed text only, never annexure evidence.
aligned = server.validate_mom({"momItems": [{
    "title": "Review of curriculum changes",
    "discussion": "The committee reviewed the curriculum changes and discussed course outcomes.",
    "recommendation": "The curriculum changes were approved.",
    "attachments": [{"name": "supporting-evidence.pdf", "id": "not-used-by-validator"}],
}]})
assert aligned["summary"]["items"] == 1
assert aligned["items"][0]["status"] == "aligned"
conflict = server.validate_mom({"momItems": [{
    "title": "Approval of previous minutes",
    "discussion": "The previous minutes were deferred for the next meeting.",
    "recommendation": "The previous minutes were approved.",
}]})
assert any(check["name"] == "Outcome consistency" for check in conflict["items"][0]["checks"])

# Catalog contains the required schools and dependent departments.
catalog = get_catalog()
schools = {school["name"]: {department["name"] for department in school["departments"]} for school in catalog["schools"]}
assert {"Computer Engineering", "Engineering", "Information Science", "Commerce", "Arts", "Design", "Health Care"}.issubset(schools)
assert {"Mechanical Engineering", "Electrical & Electronics Engineering", "Civil Engineering"}.issubset(schools["Engineering"])
assert {"Artificial Intelligence & Machine Learning", "Cyber Security"}.issubset(schools["Computer Engineering"])
assert {"MCA", "BCA", "BCA (Data Science)"}.issubset(schools["Information Science"])

# API access starts behind the active email allow-list and a per-session CSRF token.
unauth = app.test_client()
assert unauth.get("/api/admin/users").status_code == 401
assert unauth.post("/api/export", json={}).status_code == 401
unknown, _, _ = sign_in("not-in-directory@example.edu")
unknown_response = unknown.post("/api/auth/verify-code", json={"email": "not-in-directory@example.edu", "code": "123456"})
assert unknown_response.status_code == 401

admin, admin_csrf, admin_user = sign_in("admin@college.example")
assert admin_user["role"] == "system_admin"
assert admin.get("/api/admin/users").status_code == 200
assert admin.get("/api/workspace").status_code == 403  # administrators manage accounts, not meeting content
assert post(admin, "", "/api/admin/users", {"email": "blocked@example.edu", "name": "Blocked", "role": "faculty", "school": "Engineering", "department": "Mechanical Engineering"}).status_code == 403

bad_assignment = post(admin, admin_csrf, "/api/admin/users", {
    "email": "bad-assignment@example.edu", "name": "Bad Assignment", "role": "faculty",
    "school": "Engineering", "department": "MCA",
})
assert bad_assignment.status_code == 400
created = post(admin, admin_csrf, "/api/admin/users", {
    "email": "new.faculty@example.edu", "name": "New Faculty", "role": "faculty",
    "school": "Design", "department": "Communication Design",
})
assert created.status_code == 201, created.get_data(as_text=True)
new_user_id = created.get_json()["user"]["id"]
assert post(admin, admin_csrf, "/api/admin/users", {
    "email": "new.faculty@example.edu", "name": "Duplicate", "role": "faculty",
    "school": "Design", "department": "Communication Design",
}).status_code == 409
updated = patch(admin, admin_csrf, f"/api/admin/users/{new_user_id}", {
    "name": "New Faculty", "role": "faculty", "school": "Design", "department": "Product Design", "active": False,
})
assert updated.status_code == 200
inactive, _, inactive_user = sign_in("new.faculty@example.edu")
assert inactive_user is None  # inactive database entries receive no local code
assert inactive.post("/api/auth/verify-code", json={"email": "new.faculty@example.edu", "code": "123456"}).status_code == 401

faculty, faculty_csrf, faculty_user = sign_in("asha.rao@college.example")
assert faculty_user["role"] == "faculty"
faculty_catalog = faculty.get("/api/catalog").get_json()
assert [school["name"] for school in faculty_catalog["schools"]] == ["Engineering"]
assert faculty.get("/api/admin/users").status_code == 403
assert faculty.get("/api/workspaces/inbox").status_code == 403
assert post(faculty, "", "/api/audit", {"event": "missing-csrf"}).status_code == 403

workspace_id = f"test-{uuid4().hex}"
proposal = {
    "status": "draft", "workspaceId": workspace_id, "approvalVersion": 0, "submittedVersion": 0,
    "meeting": {
        "id": workspace_id, "meetingNo": "2", "academicYear": "2026-27", "semester": "Odd",
        "school": "School of Engineering", "department": "Department of Mechanical Engineering",
        "schoolCode": "ENG", "departmentCode": "MEC", "previousMeetingNo": "1", "previousMeetingDate": "2026-06-30",
        "date": "2030-01-02", "startTime": "10:30", "endTime": "12:00", "venue": "Room 1",
        "mode": "Offline", "onlineLink": "", "chairName": "Dr. Asha Rao", "chairEmail": "asha.rao@college.example",
        "completed": False, "attendanceConfirmed": False,
        "agendas": [
            {"id": "std-mom", "kind": "standard", "title": "Approval of the previous MoM", "rationale": ""},
            {"id": "std-atr", "kind": "standard", "title": "Action Taken Report of the previous DAC meeting", "rationale": ""},
            {"id": "std-curriculum", "kind": "standard", "title": "Review curriculum matters", "rationale": ""},
        ],
        "members": [
            {"id": "chair", "name": "Dr. Asha Rao", "designation": "Professor", "role": "Chairperson", "email": "asha.rao@college.example", "external": False, "present": False},
            {"id": "secretary", "name": "Prof. Devika Nair", "designation": "Associate Professor", "role": "Member Secretary", "email": "secretary@college.example", "external": False, "present": False},
            {"id": "guest", "name": "Dr. Alex Morgan", "designation": "External Academic", "role": "External Member", "email": "alex@example.org", "external": True, "present": False},
        ],
    },
    "momItems": [], "additionalDiscussions": [], "photos": [], "actionItems": [], "agendaBank": [],
}
wrong_scope = json.loads(json.dumps(proposal))
wrong_scope["meeting"]["school"] = "School of Computer Engineering"
assert post(faculty, faculty_csrf, "/api/workspace/save", {"workspaceId": f"bad-{uuid4().hex}", "state": wrong_scope}).status_code == 403
saved = post(faculty, faculty_csrf, "/api/workspace/save", {"workspaceId": workspace_id, "state": proposal})
assert saved.status_code == 200, saved.get_data(as_text=True)
assert any(row["workspaceId"] == workspace_id for row in faculty.get("/api/workspaces/mine").get_json()["workspaces"])

# Uploads are authenticated and private to the owner and Academic Office; not to guests or other faculty.
uploaded = faculty.post("/api/upload", data={"file": (BytesIO(b"private test attachment\n"), "meeting-note.txt")}, headers={"X-CSRF-Token": faculty_csrf}, content_type="multipart/form-data")
assert uploaded.status_code == 200, uploaded.get_data(as_text=True)
file_id = uploaded.get_json()["id"]
assert faculty.get(f"/api/file/{file_id}").status_code == 200

other_faculty, other_csrf, other_user = sign_in("devika.nair@college.example")
assert other_user["school"] == "Computer Engineering"
assert other_faculty.get(f"/api/workspaces/{workspace_id}").status_code == 403
assert other_faculty.get(f"/api/file/{file_id}").status_code == 403
assert post(other_faculty, other_csrf, "/api/workspace/save", {"workspaceId": workspace_id, "state": proposal}).status_code == 403
assert post(other_faculty, other_csrf, "/api/export", {"meeting": {"id": workspace_id}}).status_code == 403

submitted = post(faculty, faculty_csrf, "/api/workspace/submit", {"workspaceId": workspace_id, "state": proposal})
assert submitted.status_code == 200, submitted.get_data(as_text=True)
assert submitted.get_json()["state"]["status"] == "pending"

office, office_csrf, office_user = sign_in("academic.office@college.example")
assert office_user["role"] == "academic_office"
assert office.get("/api/workspaces/mine").status_code == 403
queue = office.get("/api/workspaces/inbox").get_json()["workspaces"]
assert any(row["workspaceId"] == workspace_id for row in queue)
assert office.get(f"/api/workspaces/{workspace_id}").status_code == 200
assert office.get(f"/api/file/{file_id}").status_code == 200
assert office.get("/api/admin/users").status_code == 403

# Deactivating a proposed member blocks approval until the directory entry is reactivated.
external_id = next(user["id"] for user in admin.get("/api/admin/users").get_json()["users"] if user["email"] == "alex@example.org")
assert patch(admin, admin_csrf, f"/api/admin/users/{external_id}", {"active": False}).status_code == 200
blocked_approval = post(office, office_csrf, "/api/workspace/decision", {"workspaceId": workspace_id, "decision": "approved", "comment": ""})
assert blocked_approval.status_code == 409
assert patch(admin, admin_csrf, f"/api/admin/users/{external_id}", {"active": True}).status_code == 200

approved_response = post(office, office_csrf, "/api/workspace/decision", {"workspaceId": workspace_id, "decision": "approved", "comment": ""})
assert approved_response.status_code == 200, approved_response.get_data(as_text=True)
approved_state = approved_response.get_json()["state"]
assert approved_state["status"] == "approved"
assert len(approved_state["momItems"]) == 3
assert "1st Departmental Academic Committee meeting held on 30.06.2026" in approved_state["momItems"][0]["title"]
assert office.get(f"/api/workspaces/{workspace_id}").status_code == 403  # Office detail is pending-only

# The simulated invitation uses canonical, stored meeting data and the per-meeting organizer.
invite = post(office, office_csrf, "/api/outbox", {
    "meeting": {"id": workspace_id}, "from": "asha.rao@college.example", "subject": "Test invitation",
})
assert invite.status_code == 201, invite.get_data(as_text=True)
invite_data = invite.get_json()
assert invite_data["from"] == "asha.rao@college.example"
assert invite_data["meeting"]["agendas"][0]["title"].startswith("To consider the approval of the MoM")
assert office.get("/api/outbox").status_code == 200
assert admin.get("/api/outbox").status_code == 403
assert len(faculty.get("/api/outbox").get_json()) == 1
assert other_faculty.get("/api/outbox").get_json() == []
assert other_faculty.get(f"/api/file/{file_id}").status_code == 403

# Guest receives only the explicitly invited approved meeting's safe schedule/agenda projection.
guest, guest_csrf, guest_user = sign_in("alex@example.org")
assert guest_user["role"] == "external_member"
guest_workspace = guest.get("/api/workspace").get_json()
assert guest_workspace["workspaceId"] == workspace_id
safe_state = guest_workspace["state"]
assert set(safe_state) == {"status", "meeting", "approvedMeeting", "momItems"}
assert "members" not in safe_state["meeting"] and "chairEmail" not in safe_state["meeting"]
assert safe_state["momItems"] == []
assert "asha.rao@college.example" not in json.dumps(guest_workspace)
assert guest.get(f"/api/workspaces/{workspace_id}").status_code == 200
assert guest.get(f"/api/file/{file_id}").status_code == 403
assert guest.get("/api/catalog").status_code == 403
assert guest.get("/api/workspaces/inbox").status_code == 403
assert post(guest, guest_csrf, "/api/validate", {"momItems": []}).status_code == 403

# Meeting completion alone does not unlock before the scheduled end; demo fast-forward is owner-only.
assert faculty.get("/api/workspace").get_json()["state"]["status"] == "approved"
complete = post(faculty, faculty_csrf, "/api/workspace/complete", {"workspaceId": workspace_id})
assert complete.status_code == 200
locked_export = post(faculty, faculty_csrf, "/api/export", {"meeting": {"id": workspace_id}})
assert locked_export.status_code == 409
fast_forward = post(faculty, faculty_csrf, "/api/workspace/demo/fast-forward", {"workspaceId": workspace_id})
assert fast_forward.status_code == 200, fast_forward.get_data(as_text=True)
exported = post(faculty, faculty_csrf, "/api/export", {"meeting": {"id": workspace_id}})
assert exported.status_code == 200, exported.get_data(as_text=True)
assert exported.mimetype == "application/pdf"
assert len(PdfReader(BytesIO(exported.data)).pages) >= 4

# PDF renderer: reference sections, actual attendance, pagination beyond four pages and annexure assembly.
sample_meeting = {
    "meetingNo": "2", "academicYear": "2026-27", "semester": "Odd",
    "school": "School of Computer Engineering", "department": "Department of Computer Science & Engineering",
    "schoolCode": "CEN", "departmentCode": "CSE",
    "previousMeetingNo": "1", "previousMeetingDate": "2026-06-30",
    "date": "2030-01-02", "startTime": "10:00", "endTime": "12:00",
    "venue": "Room 1", "mode": "Offline", "chairName": "Dr. Asha Rao", "chairEmail": "asha.rao@college.example",
    "members": [
        {"name": "Asha Rao", "designation": "Professor", "role": "Chairperson", "present": True},
        {"name": "Alex Morgan", "designation": "External Academic", "role": "External Member", "present": False},
    ],
}
pdf = server.build_final_pdf({
    "status": "approved", "meeting": sample_meeting,
    "momItems": [
        {"id": "mom-1", "agendaId": "std-mom", "agendaNo": 1, "title": "Approval of previous MoM", "discussion": "The previous MoM was reviewed.", "recommendation": "The previous MoM was approved.", "attachments": []},
        {"id": "mom-2", "agendaId": "std-curriculum", "agendaNo": 2, "title": "Review curriculum", "discussion": "The committee reviewed the curriculum.", "recommendation": "The proposed changes were approved.", "attachments": []},
    ],
    "photos": [],
    "actionItems": [{"agendaNo": "2", "text": "Update the syllabus", "owner": "Member Secretary", "targetDate": "2030-02-01"}],
    "additionalDiscussions": [{"title": "Library access", "discussion": "Access hours were discussed.", "recommendation": "The matter was noted."}],
})
reader = PdfReader(BytesIO(pdf))
assert len(reader.pages) >= 4
pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
for required_text in (
    "Minutes of Meeting Template", "Ref No. PU/CEN-CSE/DAC-02/2026-27/Odd/MoM-02",
    "Members Present:", "Agenda No: 01", "Discussion:", "Recommendations:",
    "Geo-Tagged Photos and Online Platform Screenshots", "Action Items:",
    "Person(s) Responsible", "Additional discussion points (if any)", "Member Secretary", "Chairperson", "Encl: Annexures",
):
    assert required_text in pdf_text, f"Missing document content: {required_text}"
assert "Alex Morgan" not in pdf_text, "Final attendance must not include an absent invitee."

long_items = [{
    "id": f"long-{index}", "agendaId": f"custom-{index}", "agendaNo": index,
    "title": f"Expanded agenda item {index}", "discussion": ("Recorded committee discussion. " * 55),
    "recommendation": ("The committee considered the recorded matter and recommended the next academic action. " * 20),
    "attachments": [],
} for index in range(1, 9)]
long_pdf = server.build_final_pdf({"status": "approved", "meeting": sample_meeting, "momItems": long_items,
                                  "photos": [], "actionItems": [], "additionalDiscussions": []})
assert len(PdfReader(BytesIO(long_pdf)).pages) > 4

frozen_title = "To consider the approval of the MoM of the 1st Departmental Academic Committee meeting held on 30.06.2026."
frozen_pdf = server.build_final_pdf({
    "status": "approved", "meeting": {**sample_meeting, "previousMeetingDate": "2026-07-30"},
    "momItems": [{"id": "mom-frozen", "agendaId": "std-mom", "agendaNo": 1, "title": frozen_title,
                  "discussion": "", "recommendation": "", "attachments": []}],
    "photos": [], "actionItems": [], "additionalDiscussions": [],
})
frozen_text = " ".join(" ".join((page.extract_text() or "").split()) for page in PdfReader(BytesIO(frozen_pdf)).pages)
assert " ".join(frozen_title.split()) in frozen_text
assert "held on 30.07.2026" not in frozen_text

attachment_id = uuid4().hex
attachment_path = server.UPLOAD_DIR / f"{attachment_id}.png"
Image.new("RGB", (20, 12), color=(230, 230, 230)).save(attachment_path, format="PNG")
try:
    annexure_pdf = server.build_final_pdf({
        "status": "approved", "meeting": sample_meeting,
        "momItems": [{"id": "mom-annexure", "agendaId": "std-curriculum", "agendaNo": 1,
                      "title": "Review curriculum", "discussion": "", "recommendation": "",
                      "attachments": [{"id": attachment_id, "name": "curriculum-reference.png", "size": 80, "type": "image/png"}]}],
        "photos": [], "actionItems": [], "additionalDiscussions": [],
    })
    annexure_reader = PdfReader(BytesIO(annexure_pdf))
    annexure_text = "\n".join(page.extract_text() or "" for page in annexure_reader.pages)
    assert len(annexure_reader.pages) >= 6
    assert "Annexure Index" in annexure_text
    assert "1.1" in annexure_text and "curriculum-reference.png" in annexure_text
finally:
    attachment_path.unlink(missing_ok=True)

print("Self-test passed: allow-list/OTP, admin provisioning, role and owner scopes, CSRF, office approval, guest/file redaction, AND unlock gate, typed-text checks and consolidated PDF export.")
