import { useEffect, useState } from "react";
import LoginScreen from "./LoginScreen.jsx";

let csrfToken = "";
const STATE_KEY = "dac-minutes-studio-react-v3";
function apiFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return fetch(url, { ...options, headers, credentials: "same-origin" });
}
const ALLOWED_ANNEXURES = ".pdf,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.pptx,.txt,.csv";
const DEFAULT_BANK = [
  { id: "std-mom", title: "Approval of the previous MoM", note: "Template wording uses the previous meeting number and date." },
  { id: "std-atr", title: "Action Taken Report (ATR) of the previous DAC meeting", note: "Template wording uses the previous meeting number and date." },
  { id: "std-curriculum", title: "Review of syllabus, course delivery and curriculum matters", note: "Academic review" },
  { id: "std-students", title: "Review of student performance, progression and academic support", note: "Academic review" },
  { id: "std-calendar", title: "Review of academic calendar and planned academic activities", note: "Academic planning" },
  { id: "std-other", title: "Any other matter with the permission of the Chairperson", note: "Additional item" },
];
const NAV = {
  system_admin: [["overview", "Overview", "◫"], ["directory", "Access directory", "♙"], ["security", "Security & audit", "◇"]],
  faculty: [["overview", "Overview", "◫"], ["request", "Meeting request", "▤"], ["mom", "MoM workspace", "✎"], ["outbox", "Invitations", "↗"], ["security", "Security & audit", "◇"]],
  academic_office: [["overview", "Overview", "◫"], ["review", "Approval queue", "✓"], ["library", "Agenda library", "▦"], ["outbox", "Invitation log", "↗"], ["security", "Security & audit", "◇"]],
  external_member: [["member", "My meeting access", "▤"], ["security", "Security notes", "◇"]],
};
const ROLE_LABEL = { system_admin: "System Administrator", academic_office: "Academic Office", faculty: "Faculty / meeting organizer", external_member: "External Member" };
const VIEW_LABEL = { overview: "Overview", directory: "Access directory", request: "Meeting request", review: "Academic Office review", library: "Common agenda library", mom: "MoM workspace", outbox: "Invitation log", security: "Security & audit", member: "Guest meeting access" };

function pad2(value) { return String(value ?? "").padStart(2, "0"); }
function isoDate(date) { return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`; }
function daysFromNow(days) { const date = new Date(); date.setDate(date.getDate() + days); return isoDate(date); }
function uid(prefix = "id") { return `${prefix}-${Math.random().toString(36).slice(2, 8)}-${Date.now().toString(36)}`; }
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function ordinal(value) {
  const match = String(value || "1").match(/\d+/);
  if (!match) return String(value || "1");
  const number = Number(match[0]);
  const suffix = number % 100 >= 11 && number % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[number % 10] || "th");
  return `${number}${suffix}`;
}
function numberOnly(value) { const match = String(value ?? "").match(/\d+/); return match ? String(Number(match[0])) : String(value ?? "").trim(); }
function dmy(value) {
  if (!value) return "DD.MM.YYYY";
  const parts = String(value).slice(0, 10).split("-");
  return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : String(value);
}
function longDate(value) {
  if (!value) return "Not set";
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}
function stripPrefix(value, prefix) { return String(value || "").replace(new RegExp(`^${prefix}\\s*`, "i"), "").trim(); }
function schoolName(meeting) { return stripPrefix(meeting.school, "School of") || "__________"; }
function departmentName(meeting) { return stripPrefix(meeting.department, "Department of") || "__________"; }
function referenceNumber(meeting) {
  const num = String(Number(numberOnly(meeting.meetingNo)) || "xx").padStart(2, "0");
  const school = (String(meeting.schoolCode || "School").replace(/[^a-z0-9]/gi, "") || "School").toUpperCase();
  const dept = (String(meeting.departmentCode || "Dept").replace(/[^a-z0-9]/gi, "") || "Dept").toUpperCase();
  return `PU/${school}-${dept}/DAC-${num}/${meeting.academicYear || "Academic Year"}/${meeting.semester || "Semester"}/MoM-${num}`;
}
function agendaTitle(item, meeting) {
  const id = item.agendaId || item.id;
  const previousNumber = ordinal(meeting.previousMeetingNo || Math.max(1, Number(numberOnly(meeting.meetingNo) || 1) - 1));
  const previousDate = dmy(meeting.previousMeetingDate);
  if (id === "std-mom") return `To consider the approval of the MoM of the ${previousNumber} Departmental Academic Committee meeting held on ${previousDate}.`;
  if (id === "std-atr") return `To consider the approval of the Action Taken Report (ATR) of the ${previousNumber} Departmental Academic Committee meeting held on ${previousDate}.`;
  return item.title || "Agenda";
}
function defaultState(user = {}) {
  const school = user.school || "Engineering";
  const department = user.department || "Mechanical Engineering";
  const organizerName = user.name || "Faculty Organizer";
  const organizerEmail = user.email || "professor@college.example";
  const workspaceId = `DAC-${String(user.id || "demo").slice(0, 7)}-${Date.now().toString(36)}`;
  return {
    status: "draft", workspaceId,
    meeting: {
      id: workspaceId, meetingNo: "1", academicYear: "2026-27", semester: "Odd",
      school: `School of ${school}`, department: `Department of ${department}`,
      schoolCode: school.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase(), departmentCode: department.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase(),
      previousMeetingNo: "1", previousMeetingDate: daysFromNow(-90), date: daysFromNow(7), startTime: "10:30", endTime: "12:00",
      venue: "Seminar Hall, Block B", mode: "Offline", onlineLink: "", chairName: organizerName, chairEmail: organizerEmail,
      secretaryName: "Prof. Devika Nair", secretaryEmail: "secretary@college.example", attendanceConfirmed: false,
      agendas: [
        { id: "std-mom", kind: "standard", title: DEFAULT_BANK[0].title, rationale: "" },
        { id: "std-atr", kind: "standard", title: DEFAULT_BANK[1].title, rationale: "" },
        { id: "std-curriculum", kind: "standard", title: DEFAULT_BANK[2].title, rationale: "" },
      ],
      members: [
        { id: "m-chair", name: organizerName, designation: "Professor", role: "Chairperson", email: organizerEmail, external: false, present: false },
        { id: "m-sec", name: "Prof. Devika Nair", designation: "Associate Professor", role: "Member Secretary", email: "secretary@college.example", external: false, present: false },
        { id: "m-1", name: "Dr. Kiran Kumar", designation: "Professor", role: "Member", email: "kiran.kumar@college.example", external: false, present: false },
        { id: "m-2", name: "Prof. Mira Shah", designation: "Assistant Professor", role: "Member", email: "mira.shah@college.example", external: false, present: false },
        { id: "m-ext", name: "Dr. Alex Morgan", designation: "External Academic", role: "External Member", email: "alex@example.org", external: true, present: false },
      ],
    },
    agendaBank: copy(DEFAULT_BANK), approvedMeeting: null, approvalVersion: 0, submittedVersion: 0,
    submittedAt: "", officeComment: "", changeRequest: false, meetingCompletedAt: "", momItems: [],
    additionalDiscussions: [], photos: [], actionItems: [], aiReport: null, outbox: [], audit: [], pdfGenerated: false,
  };
}
function loadState(user = {}) {
  const storageKey = `${STATE_KEY}:${user.id || "demo"}`;
  const fresh = defaultState(user);
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (!saved) return fresh;
    const meeting = { ...fresh.meeting, ...(saved.meeting || {}) };
    if (saved.meeting && saved.meeting.attendanceConfirmed !== true) {
      meeting.members = (meeting.members || []).map(member => ({ ...member, present: false }));
      meeting.attendanceConfirmed = false;
    }
    return { ...fresh, ...saved, workspaceId: saved.workspaceId || meeting.id, meeting, agendaBank: saved.agendaBank || fresh.agendaBank };
  } catch {
    return fresh;
  }
}
function endTimePassed(meeting) {
  if (!meeting?.date || !meeting?.endTime) return false;
  const end = new Date(`${meeting.date}T${meeting.endTime}:00`);
  return !Number.isNaN(end.getTime()) && Date.now() >= end.getTime();
}
function meetingStarted(meeting) {
  if (!meeting?.date || !meeting?.startTime) return false;
  const start = new Date(`${meeting.date}T${meeting.startTime}:00`);
  return !Number.isNaN(start.getTime()) && Date.now() >= start.getTime();
}
function unlocked(state) {
  return state.status === "approved" && state.meeting?.completed === true && endTimePassed(state.meeting);
}
function pillClass(status) {
  return ({ draft: "draft", pending: "pending", revision: "revision", rejected: "rejected", approved: "approved", complete: "complete", aligned: "aligned", review: "review", needs_revision: "needs_revision" })[status] || "neutral";
}
function statusText(status) {
  return ({ draft: "Draft", pending: "Pending review", revision: "Revision requested", rejected: "Rejected", approved: "Approved", complete: "Complete", aligned: "No mismatch found", review: "Review suggested", needs_revision: "Needs revision" })[status] || "Demo";
}
function StatusPill({ status = "neutral", children }) { return <span className={`status-pill status-${pillClass(status)}`}><span>{children || statusText(status)}</span></span>; }
function InlineInput({ value, onChange, className = "", type = "text", disabled = false, ariaLabel, placeholder, ...rest }) {
  return <input className={`doc-inline-field ${className}`} type={type} value={value ?? ""} onChange={event => onChange(event.target.value)} disabled={disabled} aria-label={ariaLabel} placeholder={placeholder} {...rest} />;
}
function InlineSelect({ value, onChange, className = "", disabled = false, ariaLabel, options }) {
  return <select className={`doc-inline-select ${className}`} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} aria-label={ariaLabel}>{options.map(option => <option key={option} value={option}>{option}</option>)}</select>;
}
function ToolCard({ title, tag, children, className = "" }) {
  return <section className={`doc-tool-card ${className}`}><div className="doc-tool-heading"><h3>{title}</h3>{tag && <span className="tag">{tag}</span>}</div>{children}</section>;
}
function Page({ className = "", children }) { return <section className={`dac-page ${className}`}>{children}</section>; }
function SectionHeading({ eyebrow, title, description, actions }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="heading-actions">{actions}</div>}</div>;
}

function MeetingDescription({ meeting, editable, premeeting, onChange }) {
  const numberInput = editable
    ? <InlineInput className="doc-number-input" value={ordinal(meeting.meetingNo)} onChange={value => onChange("meetingNo", numberOnly(value))} ariaLabel="Meeting number" />
    : ordinal(meeting.meetingNo);
  const deptInput = departmentName(meeting);
  const schoolInput = schoolName(meeting);
  const dateInput = editable
    ? <InlineInput type="date" className="doc-date-input" value={meeting.date} onChange={value => onChange("date", value)} ariaLabel="Meeting date" />
    : dmy(meeting.date);
  const startTime = editable
    ? <InlineInput type="time" className="doc-time-input" value={meeting.startTime} onChange={value => onChange("startTime", value)} ariaLabel="Meeting start time" />
    : meeting.startTime || "—";
  const endTime = editable
    ? <InlineInput type="time" className="doc-time-input" value={meeting.endTime} onChange={value => onChange("endTime", value)} ariaLabel="Meeting end time" />
    : meeting.endTime || "—";
  const venue = editable
    ? <InlineInput className="doc-name-input" value={meeting.venue} onChange={value => onChange("venue", value)} ariaLabel="Venue" placeholder="Venue" />
    : meeting.venue || "Venue not recorded";
  const mode = editable
    ? <InlineSelect value={meeting.mode} onChange={value => onChange("mode", value)} ariaLabel="Meeting mode" options={["Offline", "Online", "Hybrid"]} />
    : String(meeting.mode || "Offline").toLowerCase();
  const modeSentence = <span>The meeting {premeeting ? "will be held" : "was held"} in {mode} mode{meeting.mode === "Online" ? "" : " at the University campus in Bengaluru"}.</span>;
  const link = meeting.onlineLink
    ? <> The meeting link is provided below: {editable ? <InlineInput className="doc-link-input" value={meeting.onlineLink} onChange={value => onChange("onlineLink", value)} ariaLabel="Online meeting link" /> : meeting.onlineLink}</>
    : <> The meeting link is provided below.{editable && meeting.mode !== "Offline" && <> {<InlineInput className="doc-link-input" value="" onChange={value => onChange("onlineLink", value)} ariaLabel="Online meeting link" placeholder="Paste meeting link" />}</>}</>;
  return <>
    The {numberInput} Meeting of the Departmental Academic Committee of the Department of {deptInput}, School of {schoolInput}, University, {premeeting ? "is proposed to be held" : "was convened"} on {dateInput}, at {startTime}{editable && <span className="doc-end-time-inline"> (expected end {endTime})</span>} in the {venue}. {modeSentence}{link}
  </>;
}

function ReferenceLine({ meeting, editable, onChange }) {
  const number = String(Number(numberOnly(meeting.meetingNo)) || 0).padStart(2, "0");
  if (!editable) return <><span>Ref No. {referenceNumber(meeting)}</span><span>Date: {dmy(meeting.date)}</span></>;
  return <>
    <span className="doc-ref-edit">Ref No. PU/<InlineInput className="doc-code-input" value={meeting.schoolCode} onChange={value => onChange("schoolCode", value.toUpperCase())} ariaLabel="School code" />-<InlineInput className="doc-code-input" value={meeting.departmentCode} onChange={value => onChange("departmentCode", value.toUpperCase())} ariaLabel="Department code" />/DAC-{number}/{<InlineInput className="doc-year-input" value={meeting.academicYear} onChange={value => onChange("academicYear", value)} ariaLabel="Academic year" />}/{<InlineSelect className="doc-semester-select" value={meeting.semester} onChange={value => onChange("semester", value)} ariaLabel="Semester" options={["Odd", "Even", "Annual"]} />}/MoM-{number}</span>
    <span>Date: <InlineInput type="date" className="doc-date-input" value={meeting.date} onChange={value => onChange("date", value)} ariaLabel="Meeting date" /></span>
  </>;
}

function RequestDocument({ meeting, editable, catalog, onMeetingChange, onSchoolChange, onDepartmentChange, onMemberChange, onMemberRoleChange, onRemoveMember, onRemoveAgenda }) {
  const meetingNo = editable
    ? <InlineInput className="doc-number-input" value={ordinal(meeting.meetingNo)} onChange={value => onMeetingChange("meetingNo", numberOnly(value))} ariaLabel="Meeting number" />
    : ordinal(meeting.meetingNo);
  const schoolOptions = (catalog?.schools || []).map(school => school.name);
  const currentSchool = (catalog?.schools || []).find(school => school.name === schoolName(meeting));
  const departmentOptions = (currentSchool?.departments || []).map(department => department.name);
  return <div className="document-stack request-document-stack">
    <Page className="dac-page-one">
      <div className="doc-template-title"><b>Minutes of Meeting Template</b></div>
      <div className="doc-school-heading">SCHOOL OF {editable && schoolOptions.length ? <InlineSelect className="doc-heading-select" value={schoolName(meeting)} options={schoolOptions} onChange={onSchoolChange} ariaLabel="School" /> : schoolName(meeting)}</div>
      <div className="doc-department-heading">DEPARTMENT OF {editable && departmentOptions.length ? <InlineSelect className="doc-heading-select" value={departmentName(meeting)} options={departmentOptions} onChange={onDepartmentChange} ariaLabel="Department" /> : departmentName(meeting)}</div>
      <div className="doc-reference-line"><ReferenceLine meeting={meeting} editable={editable} onChange={onMeetingChange} /></div>
      <h1 className="doc-meeting-title">Minutes of the {meetingNo} Meeting of Departmental Academic Committee</h1>
      <p className="doc-description"><MeetingDescription meeting={meeting} editable={editable} premeeting onChange={onMeetingChange} /></p>
      <p className="doc-section-intro"><b>Proposed Members / Invitees:</b> <span className="doc-premeeting-note">(For invitation approval; this list is not a record of attendance.)</span></p>
      <table className="doc-table doc-members-table"><thead><tr><th>Sl. No.</th><th>Name and Designation</th><th>Role</th><th>Official Email</th></tr></thead><tbody>
        {(meeting.members || []).map((member, index) => <tr key={member.id}>
          <td className="doc-center">{pad2(index + 1)}</td>
          <td>{editable && member.role !== "Chairperson" ? <><InlineInput className="doc-table-input" value={member.name} onChange={value => onMemberChange(member.id, "name", value)} ariaLabel="Member name" /><br /><InlineInput className="doc-table-input doc-designation-input" value={member.designation} onChange={value => onMemberChange(member.id, "designation", value)} ariaLabel="Member designation" /></> : <>{member.name}<br /><span className="doc-designation">{member.designation}{member.role === "Chairperson" ? " · scheduled by signed-in faculty" : ""}</span></>}</td>
          <td>{editable && member.role !== "Chairperson" ? <select className="doc-inline-select doc-role-select" value={member.role} onChange={event => onMemberRoleChange(member.id, event.target.value)} aria-label="Member role">{["Member Secretary", "Member", "External Member"].map(role => <option key={role}>{role}</option>)}</select> : member.role}</td>
          <td>{editable && member.role !== "Chairperson" ? <><InlineInput type="email" className="doc-table-input" value={member.email} onChange={value => onMemberChange(member.id, "email", value)} ariaLabel="Official email" /><button className="doc-remove no-print" onClick={() => onRemoveMember(member.id)} aria-label={`Remove ${member.name}`}>×</button></> : member.email}{member.external && <span className="doc-guest-tag no-print">Guest</span>}</td>
        </tr>)}
        {!meeting.members?.length && <tr><td colSpan="4" className="doc-empty-row">No proposed members added.</td></tr>}
      </tbody></table>
      <div className="doc-page-footnote">Pre-meeting approval copy · Proposed invitees only</div>
    </Page>
    <Page className="dac-page-agenda">
      <div className="doc-continuation-heading">Minutes of Meeting Template · continued</div>
      <h2 className="doc-section-title">Proposed Agenda Items</h2>
      <p className="doc-premeeting-context">Agenda wording shown here is submitted for Academic Office approval. Discussion and Recommendations are intentionally not presented as completed content before the meeting.</p>
      {(meeting.agendas || []).map((agenda, index) => <div className="doc-proposed-agenda" key={agenda.id}>
        <p><b>Agenda No: {pad2(index + 1)}</b> &nbsp; {agendaTitle(agenda, meeting)}</p>
        <div className="doc-agenda-meta no-print"><span className={`doc-source-label ${agenda.kind === "custom" ? "doc-custom-label" : ""}`}>{agenda.kind === "custom" ? "Meeting-specific proposal" : "Academic Office common agenda"}</span>{agenda.rationale && <span className="doc-rationale">Reason: {agenda.rationale}</span>}{editable && <button className="doc-remove" onClick={() => onRemoveAgenda(agenda.id)}>Remove</button>}</div>
      </div>)}
      {!meeting.agendas?.length && <p className="doc-empty-row">No agenda items selected for approval.</p>}
      {(meeting.agendas || []).some(item => ["std-mom", "std-atr"].includes(item.id)) && <p className="doc-previous-reference">Previous meeting reference: {ordinal(meeting.previousMeetingNo)} DAC meeting held on {dmy(meeting.previousMeetingDate)}.</p>}
      <div className="doc-page-footnote">Approval copy · Agenda sequence becomes read-only after approval</div>
    </Page>
  </div>;
}

function FileList({ files = [], onRemove, canRemove = false }) {
  if (!files.length) return <div className="doc-annexure-empty no-print">No annexure attached.</div>;
  return <div className="file-list">{files.map(file => <div className="file-item" key={file.id}>
    <span className="file-icon">{String(file.extension || file.name?.split(".").pop() || "FILE").replace(".", "").slice(0, 4).toUpperCase()}</span>
    <span className="file-meta"><b title={file.name}>{file.name}</b><small>{Math.round((file.size || 0) / 1024)} KB · {file.type || "file"}</small></span>
    <a href={file.previewUrl || `/api/file/${file.id}`} target="_blank" rel="noreferrer">Open</a>
    {canRemove && <button className="no-print" onClick={() => onRemove(file.id)} aria-label={`Remove ${file.name}`}>×</button>}
  </div>)}</div>;
}

function FinalDocument({ meeting, momItems, additionalDiscussions, photos, actionItems, isUnlocked, onMomChange, onToggleNoRecommendation, onUploadAgenda, onRemoveFile, onPhotoChange, onUploadPhotos, onRemovePhoto, onAdditionalChange, onRemoveAdditional, onRemoveAction }) {
  const present = (meeting.members || []).filter(member => member.present);
  return <div className="document-stack final-document-stack">
    <Page className="dac-page-one">
      <div className="doc-template-title"><b>Minutes of Meeting Template</b></div>
      <div className="doc-school-heading">SCHOOL OF {schoolName(meeting)}</div>
      <div className="doc-department-heading">DEPARTMENT OF {departmentName(meeting)}</div>
      <div className="doc-reference-line"><ReferenceLine meeting={meeting} editable={false} /></div>
      <h1 className="doc-meeting-title">Minutes of the {ordinal(meeting.meetingNo)} Meeting of Departmental Academic Committee</h1>
      <p className="doc-description"><MeetingDescription meeting={meeting} editable={false} premeeting={false} onChange={() => {}} /></p>
      <p className="doc-section-intro"><b>Members Present:</b> (Provide the list of members who are present at the meeting)</p>
      <table className="doc-table doc-members-table"><thead><tr><th>Sl. No.</th><th>Name and Designation</th><th>Role</th><th>Signature</th></tr></thead><tbody>
        {present.map((member, index) => <tr key={member.id}><td className="doc-center">{pad2(index + 1)}</td><td>{member.name}<br /><span className="doc-designation">{member.designation}</span></td><td>{member.role}</td><td className="doc-signature-cell">&nbsp;</td></tr>)}
        {!present.length && <tr><td className="doc-empty-row" colSpan="4">No actual attendees have been marked present.</td></tr>}
      </tbody></table>
    </Page>
    <Page className="dac-page-agenda">
      <div className="doc-continuation-heading">Minutes of Meeting Template · continued</div>
      <p className="doc-opening-statement">The Chairperson welcomed all the members. The member secretary delivered the opening remarks and deliberated on the following agenda points.</p>
      {momItems.map((item, index) => {
        const agendaNumber = Number(item.agendaNo || index + 1);
        const files = item.attachments || [];
        const refs = files.length ? files.map((file, fileIndex) => <span className="doc-annexure-name" key={file.id}>Annexure {agendaNumber}.{fileIndex + 1} · {file.name}</span>) : <span className="doc-annexure-name">Annexure {pad2(agendaNumber)}</span>;
        return <article className="doc-agenda-item" key={item.id}>
          <p className="doc-agenda-title"><b>Agenda No: {pad2(agendaNumber)}</b> &nbsp; {item.title}</p>
          <div className={`doc-form-field ${isUnlocked ? "" : "doc-form-locked"}`}><label>Discussion:</label><textarea className="doc-textarea" rows="3" value={item.discussion || ""} onChange={event => onMomChange(item.id, "discussion", event.target.value)} disabled={!isUnlocked} aria-label={`Discussion for Agenda ${agendaNumber}`} placeholder={isUnlocked ? "Record what the committee actually discussed." : "Locked until the scheduled end time has passed AND the meeting is marked COMPLETED."} /></div>
          <div className={`doc-form-field ${isUnlocked ? "" : "doc-form-locked"}`}><label>Recommendations:</label><textarea className="doc-textarea" rows="3" value={item.recommendation || ""} onChange={event => onMomChange(item.id, "recommendation", event.target.value)} disabled={!isUnlocked || item.noRecommendation} aria-label={`Recommendations for Agenda ${agendaNumber}`} placeholder={item.noRecommendation ? "Uncheck ‘No separate recommendation’ to enter text." : isUnlocked ? "Record an outcome, advice or action arising from this agenda." : "Locked until both meeting gates are satisfied."} /></div>
          {item.noRecommendation && <p className="doc-no-recommendation">No separate recommendation was recorded for this agenda item.</p>}
          <label className="doc-no-rec-toggle no-print"><input type="checkbox" checked={!!item.noRecommendation} onChange={() => onToggleNoRecommendation(item.id)} disabled={!isUnlocked} /> No separate recommendation was recorded</label>
          <div className="doc-ref-area"><b>{item.agendaId === "std-mom" ? "Document:" : "Ref. Document:"}</b> {refs}
            <div className="doc-annexure-editor no-print"><label className="doc-file-button">Attach document<input type="file" accept={ALLOWED_ANNEXURES} multiple disabled={!isUnlocked} onChange={event => onUploadAgenda(item.id, event)} /></label><span>Files stay with this approved agenda.</span></div>
            <FileList files={files} canRemove={isUnlocked} onRemove={fileId => onRemoveFile(item.id, fileId)} />
          </div>
        </article>;
      })}
      {!momItems.length && <p className="doc-empty-row">No approved agenda items were recorded.</p>}
      <section className="doc-additional-section"><h2 className="doc-section-title">Additional discussion points (if any)</h2>
        {additionalDiscussions.map((item, index) => <article className="doc-additional-item" key={item.id}>
          <p className="doc-agenda-title"><b>Additional discussion {pad2(index + 1)}:</b> {item.title} <span className="doc-audit-label no-print">Additional · not on the approved agenda</span><button className="doc-remove no-print" onClick={() => onRemoveAdditional(item.id)} disabled={!isUnlocked}>Remove</button></p>
          <div className="doc-form-field"><label>Discussion:</label><textarea className="doc-textarea" rows="3" value={item.discussion || ""} onChange={event => onAdditionalChange(item.id, "discussion", event.target.value)} disabled={!isUnlocked} aria-label={`Additional discussion ${index + 1}`} placeholder={isUnlocked ? "Record only what was actually discussed." : "Locked until both meeting gates are satisfied."} /></div>
          <div className="doc-form-field"><label>Recommendations:</label><textarea className="doc-textarea" rows="3" value={item.recommendation || ""} onChange={event => onAdditionalChange(item.id, "recommendation", event.target.value)} disabled={!isUnlocked} aria-label={`Additional recommendation ${index + 1}`} placeholder={isUnlocked ? "Record an outcome, advice or action, if any." : "Locked until both meeting gates are satisfied."} /></div>
        </article>)}
        {!additionalDiscussions.length && <p className="doc-empty-row">No additional discussion points recorded.</p>}
      </section>
    </Page>
    <Page className="dac-page-photos">
      <h2 className="doc-section-title doc-photo-title">Geo-Tagged Photos and Online Platform Screenshots – Departmental Academic Committee</h2>
      {photos.map((photo, index) => <figure className="doc-photo-entry" key={photo.id}>
        {photo.file?.previewUrl && <img src={photo.file.previewUrl} alt={photo.caption || photo.file.name || `Image ${index + 1}`} />}
        <figcaption><b>Image {index + 1}:</b> {photo.caption || photo.file?.name || "Description or caption of the image"}{photo.location && <> · Location: {photo.location}</>}{photo.capturedAt && <> · Date/time: {photo.capturedAt}</>}</figcaption>
        <div className="doc-photo-edit no-print"><span className="doc-file-name">{photo.file?.name}</span>
          <input className="doc-tool-input" value={photo.caption || ""} onChange={event => onPhotoChange(photo.id, "caption", event.target.value)} placeholder="Caption" aria-label="Photo caption" disabled={!isUnlocked} />
          <input className="doc-tool-input" value={photo.location || ""} onChange={event => onPhotoChange(photo.id, "location", event.target.value)} placeholder="Location (if known)" aria-label="Photo location" disabled={!isUnlocked} />
          <input className="doc-tool-input" value={photo.capturedAt || ""} onChange={event => onPhotoChange(photo.id, "capturedAt", event.target.value)} placeholder="Date/time (if known)" aria-label="Photo date and time" disabled={!isUnlocked} />
          <button className="doc-remove" onClick={() => onRemovePhoto(photo.id)} disabled={!isUnlocked}>Remove image</button>
        </div>
      </figure>)}
      <div className="doc-photo-upload no-print"><label className="doc-file-button">Add images / screenshots<input type="file" accept=".png,.jpg,.jpeg,.webp" multiple disabled={!isUnlocked} onChange={onUploadPhotos} /></label><span>Multiple images · original aspect ratio retained · captions and available location/time metadata are included.</span></div>
      <h2 className="doc-action-title">Action Items:</h2>
      <table className="doc-table doc-actions-table"><thead><tr><th>Agenda No</th><th>Action(s) to be Taken</th><th>Person(s) Responsible</th><th>Target Date</th></tr></thead><tbody>
        {actionItems.map(item => <tr key={item.id}><td>{item.agendaNo}</td><td>{item.text}<div className="doc-source-recommendation no-print">Linked recommendation: {item.sourceRecommendation}</div></td><td>{item.owner}</td><td>{item.targetDate ? dmy(item.targetDate) : ""}<button className="doc-remove no-print" onClick={() => onRemoveAction(item.id)} disabled={!isUnlocked}>Remove</button></td></tr>)}
        {!actionItems.length && <tr><td colSpan="4">&nbsp;</td></tr>}
      </tbody></table>
      {!actionItems.length && <p className="doc-empty-row no-print">No action rows added. Add only actions linked to a recorded recommendation.</p>}
    </Page>
    <Page className="dac-page-closing">
      <p className="doc-closing-statement">The Chairperson and the Member Secretary thanked all the members for their contributions and requested their continued support.</p>
      <div className="doc-signature-area"><div className="doc-signature-block"><span>______________________________</span><b>Member Secretary</b></div><div className="doc-signature-block"><span>______________________________</span><b>Chairperson</b></div></div>
      <p className="doc-enclosures">Encl: Annexures</p>
    </Page>
  </div>;
}

function App() {
  const [authUser, setAuthUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  useEffect(() => {
    apiFetch("/api/auth/me").then(async response => {
      if (!response.ok) throw new Error("Sign in to continue.");
      const data = await response.json();
      csrfToken = data.csrfToken || "";
      setAuthUser(data.user);
    }).catch(() => setAuthUser(null)).finally(() => setAuthLoading(false));
  }, []);
  async function signedOut() {
    try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch { /* session may already have expired */ }
    csrfToken = ""; setAuthUser(null); setAuthError("");
  }
  if (authLoading) return <div className="auth-loading"><div className="brand-mark"><span /><span /><span /></div><b>Loading secure workspace…</b></div>;
  if (authError || !authUser) return <LoginScreen onAuthenticated={data => { csrfToken = data.csrfToken || ""; setAuthUser(data.user); setAuthError(""); }} />;
  return <Workspace key={authUser.id} user={authUser} onLogout={signedOut} />;
}

function Workspace({ user, onLogout }) {
  const role = user.role;
  const initialView = role === "academic_office" ? "review" : role === "external_member" ? "member" : role === "system_admin" ? "directory" : "overview";
  const [state, setState] = useState(() => loadState(user));
  const [view, setView] = useState(initialView);
  const [loaded, setLoaded] = useState(role === "system_admin");
  const [catalog, setCatalog] = useState({ schools: [] });
  const [inbox, setInbox] = useState([]);
  const [mine, setMine] = useState([]);
  const [lastSaved, setLastSaved] = useState("");
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [, setClock] = useState(Date.now());
  const [customAgenda, setCustomAgenda] = useState({ title: "", reason: "" });
  const [memberDraft, setMemberDraft] = useState({ name: "", designation: "", role: "Member", email: "" });
  const [additionalTitle, setAdditionalTitle] = useState("");
  const [actionDraft, setActionDraft] = useState({ agendaId: "", text: "", owner: "", targetDate: "" });
  const [reviewComment, setReviewComment] = useState("");

  useEffect(() => {
    const storageKey = `${STATE_KEY}:${user.id}`;
    if (role === "system_admin") { setLoaded(true); return; }
    Promise.all([
      apiFetch("/api/workspace").then(response => response.ok ? response.json() : null).catch(() => null),
      apiFetch("/api/catalog").then(response => response.ok ? response.json() : { schools: [] }).catch(() => ({ schools: [] })),
    ]).then(([workspaceData, catalogData]) => {
      setCatalog(catalogData || { schools: [] });
      if (workspaceData?.state) {
        const loadedState = { ...loadState(user), ...workspaceData.state, workspaceId: workspaceData.workspaceId || workspaceData.state.workspaceId || workspaceData.state.meeting?.id };
        setState(loadedState); setReviewComment(loadedState.officeComment || "");
      } else {
        const fresh = defaultState(user); setState(fresh);
      }
    }).finally(() => setLoaded(true));
  }, [role, user]);
  useEffect(() => { if (!loaded || role === "system_admin") return; localStorage.setItem(`${STATE_KEY}:${user.id}`, JSON.stringify(state)); }, [state, loaded, role, user.id]);
  useEffect(() => {
    if (!loaded || role !== "faculty" || ["pending"].includes(state.status)) return undefined;
    const timer = setTimeout(async () => {
      try {
        const response = await apiFetch("/api/workspace/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id, state }) });
        const result = await response.json();
        if (response.ok) {
          setLastSaved(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
          if (!mine.some(item => item.workspaceId === (state.workspaceId || state.meeting.id))) {
            apiFetch("/api/workspaces/mine").then(listResponse => listResponse.ok ? listResponse.json() : { workspaces: [] }).then(data => setMine(data.workspaces || [])).catch(() => {});
          }
        } else if (response.status !== 409) showToast(result.error || "Autosave failed.", true);
      } catch { /* the local cache remains available if the API is briefly unavailable */ }
    }, 500);
    return () => clearTimeout(timer);
  }, [state, loaded, role, mine]);
  useEffect(() => {
    if (!loaded || !["faculty", "academic_office"].includes(role)) return;
    apiFetch("/api/outbox").then(response => response.ok ? response.json() : []).then(rows => {
      if (Array.isArray(rows)) setState(current => ({ ...current, outbox: rows.slice(-100) }));
    }).catch(() => {});
  }, [loaded, role]);
  useEffect(() => {
    if (!loaded || !["system_admin", "academic_office"].includes(role)) return;
    apiFetch("/api/audit").then(response => response.ok ? response.json() : []).then(rows => {
      if (Array.isArray(rows)) setState(current => ({ ...current, audit: [...rows].reverse().slice(0, 100) }));
    }).catch(() => {});
  }, [loaded, role]);
  useEffect(() => {
    if (!loaded || role !== "faculty") return;
    apiFetch("/api/workspaces/mine").then(response => response.ok ? response.json() : { workspaces: [] }).then(data => setMine(data.workspaces || [])).catch(() => setMine([]));
  }, [loaded, role, state.status]);
  useEffect(() => {
    if (role !== "academic_office") return;
    apiFetch("/api/workspaces/inbox").then(response => response.ok ? response.json() : { workspaces: [] }).then(async data => {
      const rows = data.workspaces || []; setInbox(rows);
      if (rows.length && state.status !== "pending") {
        const response = await apiFetch(`/api/workspaces/${encodeURIComponent(rows[0].workspaceId)}`);
        if (response.ok) {
          const detail = await response.json(); setState({ ...loadState(user), ...detail.state, workspaceId: detail.workspaceId }); setReviewComment(detail.state.officeComment || "");
        }
      }
    }).catch(() => setInbox([]));
  }, [role, state.status]);
  useEffect(() => { if (!toast) return undefined; const timer = setTimeout(() => setToast(null), 4400); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 15000); return () => clearInterval(timer); }, []);

  const isUnlocked = unlocked(state);
  const endPassed = endTimePassed(state.meeting);
  const canEditRequest = role === "faculty" && ["draft", "revision", "rejected"].includes(state.status);
  const meetingLabel = `DAC-${String(Number(numberOnly(state.meeting.meetingNo)) || 0).padStart(2, "0")} · ${state.meeting.department || "Department not set"}`;
  const presentCount = (state.meeting.members || []).filter(member => member.present).length;
  const agendaBank = state.agendaBank || DEFAULT_BANK;
  const selectedActionAgenda = state.momItems.find(item => item.id === actionDraft.agendaId) || state.momItems[0];

  function showToast(message, isError = false) { setToast({ message, isError }); }
  async function openWorkspace(workspaceId) {
    try {
      const response = await apiFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Meeting request could not be opened.");
      setState({ ...loadState(user), ...result.state, workspaceId: result.workspaceId });
      setReviewComment(result.state.officeComment || "");
      if (role === "faculty") setView(result.state.status === "approved" ? "mom" : "request");
    } catch (error) { showToast(error.message || "Meeting request could not be opened.", true); }
  }
  function createNewMeeting() {
    if (role !== "faculty") return;
    setState(defaultState(user)); setView("request"); showToast("New meeting request created for your provisioned school and department.");
  }
  function auditEvent(event, note = "") {
    const record = { at: new Date().toISOString(), event, role, details: { note, meetingId: state.meeting.id, status: state.status } };
    setState(current => ({ ...current, audit: [record, ...(current.audit || [])].slice(0, 100) }));
    apiFetch("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(record) }).catch(() => {});
  }
  function updateSchool(name) {
    if (role === "faculty") {
      if (name !== user.school) showToast("This faculty account is scoped to its provisioned school.", true);
      return;
    }
    const school = (catalog.schools || []).find(item => item.name === name);
    if (!school) return;
    const firstDepartment = school.departments?.[0]?.name || "";
    setState(current => ({ ...current, meeting: { ...current.meeting, school: `School of ${school.name}`, department: firstDepartment ? `Department of ${firstDepartment}` : "", schoolCode: school.name.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase(), departmentCode: firstDepartment.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase() } }));
  }
  function updateDepartment(name) {
    if (role === "faculty" && name !== user.department) { showToast("This faculty account is scoped to its provisioned department.", true); return; }
    setState(current => ({ ...current, meeting: { ...current.meeting, department: `Department of ${name}`, departmentCode: name.replace(/[^A-Z]/gi, "").slice(0, 3).toUpperCase() } }));
  }
  function updateMeeting(field, value) {
    setState(current => {
      const meeting = { ...current.meeting, [field]: value };
      if (field === "chairName" || field === "chairEmail") {
        meeting.members = current.meeting.members.map(member => member.role === "Chairperson"
          ? { ...member, [field === "chairName" ? "name" : "email"]: value }
          : member);
      }
      return { ...current, meeting, pdfGenerated: false };
    });
  }
  function updateMember(memberId, field, value) {
    setState(current => {
      const meeting = { ...current.meeting };
      meeting.members = current.meeting.members.map(member => {
        if (member.id !== memberId) return member;
        const updated = { ...member, [field]: value };
        if (updated.role === "Chairperson") {
          if (field === "name") meeting.chairName = value;
          if (field === "email") meeting.chairEmail = value;
        }
        if (updated.role === "Member Secretary") {
          if (field === "name") meeting.secretaryName = value;
          if (field === "email") meeting.secretaryEmail = value;
        }
        return updated;
      });
      return { ...current, meeting, pdfGenerated: false };
    });
  }
  function updateMemberRole(memberId, value) {
    const existingChair = state.meeting.members.find(member => member.role === "Chairperson" && member.id !== memberId);
    if (value === "Chairperson" && existingChair) { showToast("Only one Chairperson may be in the proposed roster.", true); return; }
    setState(current => {
      const meeting = { ...current.meeting };
      meeting.members = current.meeting.members.map(member => {
        if (member.id !== memberId) return member;
        if (member.role === "Chairperson" && value !== "Chairperson") { meeting.chairName = ""; meeting.chairEmail = ""; }
        if (member.role === "Member Secretary" && value !== "Member Secretary") { meeting.secretaryName = ""; meeting.secretaryEmail = ""; }
        const updated = { ...member, role: value, external: value === "External Member" };
        if (value === "Chairperson") { meeting.chairName = updated.name; meeting.chairEmail = updated.email; }
        if (value === "Member Secretary") { meeting.secretaryName = updated.name; meeting.secretaryEmail = updated.email; }
        return updated;
      });
      return { ...current, meeting };
    });
  }
  function updateMomItem(itemId, field, value) {
    setState(current => {
      const momItems = current.momItems.map(item => item.id === itemId ? { ...item, [field]: value } : item);
      const actionItems = field === "recommendation" ? current.actionItems.map(action => action.agendaId === itemId ? { ...action, sourceRecommendation: value } : action) : current.actionItems;
      return { ...current, momItems, actionItems, aiReport: null, pdfGenerated: false };
    });
  }
  function updatePhoto(photoId, field, value) {
    setState(current => ({ ...current, photos: current.photos.map(photo => photo.id === photoId ? { ...photo, [field]: value } : photo), pdfGenerated: false }));
  }
  function updateAdditional(itemId, field, value) {
    setState(current => ({ ...current, additionalDiscussions: current.additionalDiscussions.map(item => item.id === itemId ? { ...item, [field]: value } : item), pdfGenerated: false }));
  }
  function toggleCommonAgenda(id, checked) {
    const common = agendaBank.find(item => item.id === id);
    if (!common) return;
    setState(current => ({ ...current, meeting: { ...current.meeting, agendas: checked
      ? [...current.meeting.agendas, { id: common.id, kind: "standard", title: common.title, rationale: "" }]
      : current.meeting.agendas.filter(item => item.id !== id) }, aiReport: null, pdfGenerated: false }));
    auditEvent(checked ? "common_agenda_selected" : "proposal_agenda_removed", "Meeting request agenda list updated");
  }
  function addCustomAgenda() {
    const title = customAgenda.title.trim();
    if (!title) { showToast("Enter a proposed agenda title.", true); return; }
    if (state.meeting.agendas.some(item => item.title.toLowerCase() === title.toLowerCase())) { showToast("That agenda is already selected.", true); return; }
    setState(current => ({ ...current, meeting: { ...current.meeting, agendas: [...current.meeting.agendas, { id: uid("custom"), kind: "custom", title, rationale: customAgenda.reason.trim() }] }, aiReport: null, pdfGenerated: false }));
    setCustomAgenda({ title: "", reason: "" }); auditEvent("meeting_specific_agenda_proposed", "Meeting-specific agenda added to request draft");
  }
  function removeAgenda(id) {
    setState(current => ({ ...current, meeting: { ...current.meeting, agendas: current.meeting.agendas.filter(item => item.id !== id) }, aiReport: null, pdfGenerated: false }));
    auditEvent("proposal_agenda_removed", "Agenda removed from current request draft");
  }
  function addMember() {
    const { name, designation, role: memberRole, email } = memberDraft;
    if (!name.trim() || !email.trim()) { showToast("Enter the proposed member’s name and email.", true); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showToast("Enter a valid email address.", true); return; }
    if (state.meeting.members.some(member => member.email.toLowerCase() === email.toLowerCase())) { showToast("That email is already on the proposed roster.", true); return; }
    const newMember = { id: uid("member"), name: name.trim(), designation: designation.trim(), role: memberRole, email: email.trim(), external: memberRole === "External Member", present: false };
    setState(current => ({ ...current, meeting: { ...current.meeting, members: [...current.meeting.members, newMember] } }));
    setMemberDraft({ name: "", designation: "", role: "Member", email: "" }); auditEvent("proposed_invitee_added", "Invitee added to current request roster");
  }
  function removeMember(id) {
    const target = state.meeting.members.find(member => member.id === id);
    if (target?.role === "Chairperson") { showToast("Assign another Chairperson before removing this roster entry.", true); return; }
    setState(current => ({ ...current, meeting: { ...current.meeting, members: current.meeting.members.filter(member => member.id !== id) } }));
    auditEvent("proposed_invitee_removed", "Invitee removed from current request roster");
  }
  function validateRequest() {
    const meeting = state.meeting;
    const required = ["meetingNo", "academicYear", "semester", "school", "department", "schoolCode", "departmentCode", "chairName", "chairEmail", "date", "startTime", "endTime", "venue"];
    const missing = required.filter(field => !String(meeting[field] || "").trim());
    if (missing.length) return `Complete required meeting details: ${missing.join(", ")}.`;
    if (!Number(numberOnly(meeting.meetingNo))) return "Meeting number must be a positive number.";
    if (!meeting.agendas.length) return "Select or add at least one agenda item.";
    if (meeting.agendas.some(item => ["std-mom", "std-atr"].includes(item.id)) && (!meeting.previousMeetingNo || !meeting.previousMeetingDate)) return "Add the previous meeting number and date for the selected MoM / ATR agenda.";
    if (meeting.members.filter(member => member.role === "Chairperson").length !== 1) return "Keep exactly one Chairperson in the proposed member roster.";
    if (meeting.members.some(member => !member.name.trim() || !member.email.trim())) return "Complete the name and email for every proposed member.";
    const badEmail = meeting.members.find(member => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(member.email || ""));
    if (badEmail) return `Check the email address for ${badEmail.name || "a proposed member"}.`;
    if (meeting.chairEmail.toLowerCase() !== user.email.toLowerCase()) return "The meeting organizer must be the currently signed-in faculty member.";
    if (schoolName(meeting) !== user.school || departmentName(meeting) !== user.department) return "The selected school and department must match your provisioned faculty scope. Ask the System Administrator to change your assignment if needed.";
    if (new Set(meeting.members.map(member => member.email.toLowerCase())).size !== meeting.members.length) return "The proposed member list contains a duplicate email address.";
    if (meeting.startTime >= meeting.endTime) return "Expected end time must be after start time.";
    if (meeting.mode !== "Offline" && !meeting.onlineLink.trim()) return "Add an online meeting link for the Online or Hybrid meeting.";
    return "";
  }
  async function submitRequest() {
    const error = validateRequest();
    if (error) { showToast(error, true); return; }
    setBusy(true);
    try {
      const response = await apiFetch("/api/workspace/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id, state }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Request could not be submitted.");
      setState(result.state); setView("overview");
      auditEvent("request_submitted", result.state.changeRequest ? "Change request submitted for reapproval" : "Meeting proposal submitted");
      showToast("Request sent to the Academic Office review queue.");
    } catch (error) { showToast(error.message || "Request could not be submitted.", true); }
    finally { setBusy(false); }
  }
  async function sendSimulatedInvite(meeting, isUpdate) {
    const payload = {
      from: meeting.chairEmail,
      recipients: meeting.members.map(member => member.email),
      subject: `${isUpdate ? "Updated invitation" : "Invitation"}: DAC Meeting ${meeting.meetingNo} — ${meeting.department}`,
      meeting: { ...meeting, agendas: meeting.agendas.map(item => ({ ...item, title: agendaTitle(item, meeting) })) },
    };
    let result;
    try {
      const response = await apiFetch("/api/outbox", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save invitation record");
      result = data;
    } catch {
      result = { ...payload, id: uid("outbox"), createdAt: new Date().toISOString(), status: "DEMO ONLY — not sent" };
    }
    setState(current => ({ ...current, outbox: [...current.outbox, result].slice(-100) }));
    auditEvent("invitation_simulated", "Invitation record added; no email sent");
  }
  async function decideRequest(decision) {
    if (role !== "academic_office" || state.status !== "pending") return;
    const comment = reviewComment.trim();
    if (["revision", "rejected"].includes(decision) && !comment) { showToast(decision === "revision" ? "Add a comment explaining what should be revised." : "Add a reason before rejecting the request.", true); return; }
    setBusy(true);
    try {
      const response = await apiFetch("/api/workspace/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id, decision, comment }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "The review decision could not be saved.");
      setState(result.state); setReviewComment("");
      if (decision === "approved") {
        await sendSimulatedInvite(result.state.meeting, !!result.state.changeRequest);
        showToast("Approved. A locked MoM snapshot was created and the invitation was logged."); setView("overview");
      } else {
        showToast(decision === "revision" ? "Returned to the meeting organizer for revision." : "Request rejected.", decision === "rejected");
      }
    } catch (error) { showToast(error.message || "The review decision could not be saved.", true); }
    finally { setBusy(false); }
  }
  function approveRequest() { return decideRequest("approved"); }
  function getOfficeComment() { return reviewComment.trim(); }
  function returnForRevision() { return decideRequest("revision"); }
  function rejectRequest() { return decideRequest("rejected"); }
  function proposeChange() {
    if (state.status !== "approved" || isUnlocked || meetingStarted(state.meeting)) return;
    setState(current => ({ ...current, changeRequest: true, status: "revision", officeComment: "Chairperson proposed changes to an approved meeting request. Review the updated version." }));
    auditEvent("approved_request_change_started", "Changes require Academic Office reapproval"); setView("request");
  }
  function addBankItem(title, note) {
    const cleanTitle = title.trim();
    if (!cleanTitle) { showToast("Enter an agenda title.", true); return; }
    if (state.agendaBank.some(item => item.title.toLowerCase() === cleanTitle.toLowerCase())) { showToast("That common agenda already exists.", true); return; }
    setState(current => ({ ...current, agendaBank: [...current.agendaBank, { id: uid("std"), title: cleanTitle, note: note.trim() || "Common agenda item" }] }));
    auditEvent("common_agenda_added", "Academic Office added an item to the shared agenda bank"); showToast("Added to the common agenda bank.");
  }
  function removeBankItem(id) {
    setState(current => ({ ...current, agendaBank: current.agendaBank.filter(item => item.id !== id), meeting: ["draft", "revision", "rejected"].includes(current.status) ? { ...current.meeting, agendas: current.meeting.agendas.filter(item => item.id !== id) } : current.meeting }));
    auditEvent("common_agenda_removed", "Shared bank changed; submitted and approved meeting snapshots were preserved");
  }
  function restoreBank() { setState(current => ({ ...current, agendaBank: copy(DEFAULT_BANK) })); showToast("Restored the sample agenda bank."); }
  function toggleAttendance(memberId, checked) {
    setState(current => ({ ...current, meeting: { ...current.meeting, attendanceConfirmed: true, members: current.meeting.members.map(member => member.id === memberId ? { ...member, present: checked } : member) }, pdfGenerated: false }));
    auditEvent("actual_attendance_updated", "Attendance changed for the final Members Present table");
  }
  async function markCompleted() {
    try {
      const response = await apiFetch("/api/workspace/complete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Completion could not be recorded.");
      setState(result.state);
      showToast(endPassed ? "Meeting marked COMPLETED; both gates are satisfied." : "Meeting marked COMPLETED. Minutes remain locked until the scheduled end time passes.");
    } catch (error) { showToast(error.message || "Completion could not be recorded.", true); }
  }
  async function fastForwardEnd() {
    if (!window.confirm("Demo only: move the sample meeting date to yesterday and mark the meeting completed? This is not a real meeting signal.")) return;
    try {
      const response = await apiFetch("/api/workspace/demo/fast-forward", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Demo schedule change failed.");
      setState(result.state); showToast("Demo schedule fast-forwarded; both completion gates are now satisfied.");
    } catch (error) { showToast(error.message || "Demo schedule change failed.", true); }
  }
  function addAdditional() {
    const title = additionalTitle.trim();
    if (!title) { showToast("Enter the title of the additional discussion point.", true); return; }
    setState(current => ({ ...current, additionalDiscussions: [...current.additionalDiscussions, { id: uid("additional"), title, discussion: "", recommendation: "" }], pdfGenerated: false }));
    setAdditionalTitle(""); auditEvent("additional_discussion_point_added", "Additional discussion point added outside the approved agenda");
  }
  function removeAdditional(id) {
    setState(current => ({ ...current, additionalDiscussions: current.additionalDiscussions.filter(item => item.id !== id), pdfGenerated: false }));
    auditEvent("additional_discussion_point_removed", "Additional discussion point removed");
  }
  function toggleNoRecommendation(item) {
    const linked = state.actionItems.some(action => action.agendaId === item.id);
    if (!item.noRecommendation && linked) { showToast("Remove linked actions before marking this agenda as having no recommendation.", true); return; }
    setState(current => ({ ...current, momItems: current.momItems.map(row => row.id === item.id ? { ...row, noRecommendation: !row.noRecommendation, recommendation: !row.noRecommendation ? "" : row.recommendation } : row), aiReport: null, pdfGenerated: false }));
  }
  function addActionItem() {
    const agenda = selectedActionAgenda;
    if (!agenda) { showToast("Select an approved agenda for the action.", true); return; }
    if (!agenda.recommendation?.trim() || agenda.noRecommendation) { showToast("Record a recommendation for this agenda before linking an action.", true); return; }
    if (!actionDraft.text.trim() || !actionDraft.owner.trim()) { showToast("Enter the action and person responsible.", true); return; }
    const item = { id: uid("action"), agendaId: agenda.id, agendaNo: String(agenda.agendaNo), sourceRecommendation: agenda.recommendation, text: actionDraft.text.trim(), owner: actionDraft.owner.trim(), targetDate: actionDraft.targetDate };
    setState(current => ({ ...current, actionItems: [...current.actionItems, item], pdfGenerated: false }));
    setActionDraft({ agendaId: agenda.id, text: "", owner: "", targetDate: "" });
    auditEvent("recommendation_linked_action_added", `Action linked to approved agenda ${agenda.agendaNo}`); showToast("Action linked to its agenda and recommendation.");
  }
  function removeAction(id) {
    setState(current => ({ ...current, actionItems: current.actionItems.filter(item => item.id !== id), pdfGenerated: false }));
    auditEvent("recommendation_linked_action_removed", "Action item removed from the MoM");
  }
  async function uploadOne(file) {
    const form = new FormData(); form.append("file", file);
    const response = await apiFetch("/api/upload", { method: "POST", body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Upload failed.");
    auditEvent("file_uploaded", `${result.name} uploaded to the local demo`);
    return result;
  }
  async function uploadAgendaFiles(agendaId, event) {
    const files = [...(event.target.files || [])];
    for (const file of files) {
      try {
        const result = await uploadOne(file);
        setState(current => ({ ...current, momItems: current.momItems.map(item => item.id === agendaId ? { ...item, attachments: [...item.attachments, result] } : item), pdfGenerated: false }));
        showToast(`${result.name} attached to the agenda.`);
      } catch (error) { showToast(error.message || "Upload failed.", true); }
    }
    event.target.value = "";
  }
  async function uploadPhotos(event) {
    const files = [...(event.target.files || [])];
    for (const file of files) {
      if (!/\.(png|jpe?g|webp)$/i.test(file.name)) { showToast("Only PNG, JPG or WEBP photos are accepted.", true); continue; }
      try {
        const result = await uploadOne(file);
        setState(current => ({ ...current, photos: [...current.photos, { id: uid("photo"), file: result, caption: file.name.replace(/\.[^.]+$/, ""), location: "", capturedAt: "" }], pdfGenerated: false }));
        showToast(`${result.name} added to the photo section.`);
      } catch (error) { showToast(error.message || "Upload failed.", true); }
    }
    event.target.value = "";
  }
  function removeAgendaFile(agendaId, fileId) {
    setState(current => ({ ...current, momItems: current.momItems.map(item => item.id === agendaId ? { ...item, attachments: item.attachments.filter(file => file.id !== fileId) } : item), pdfGenerated: false }));
    auditEvent("agenda_annexure_removed", "Agenda-linked annexure removed from MoM");
  }
  function removePhoto(photoId) {
    setState(current => ({ ...current, photos: current.photos.filter(photo => photo.id !== photoId), pdfGenerated: false }));
    auditEvent("photo_removed", "Photo removed from the template photo section");
  }
  async function runTextCheck() {
    const payload = state.momItems.map(item => ({ title: item.title, discussion: item.discussion, recommendation: item.recommendation, noRecommendation: item.noRecommendation }));
    try {
      const response = await apiFetch("/api/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ momItems: payload }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "The local check could not run.");
      setState(current => ({ ...current, aiReport: result }));
      auditEvent("demo_consistency_check_run", "Typed MoM text check only; no annexures or photos sent");
      showToast("Local relevance/coherence check complete. Review the notes; no text was changed.");
    } catch (error) { showToast(error.message || "The text check could not run.", true); }
  }
  async function exportPdf(printMode = false) {
    if (!isUnlocked) { showToast("The final MoM stays locked until the scheduled end time has passed AND the meeting is marked COMPLETED.", true); return; }
    const printWindow = printMode ? window.open("about:blank", "_blank") : null;
    setBusy(true);
    try {
      const saveResponse = await apiFetch("/api/workspace/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspaceId: state.workspaceId || state.meeting.id, state }) });
      const saveResult = await saveResponse.json();
      if (!saveResponse.ok) throw new Error(saveResult.error || "The latest minutes could not be saved.");
      const response = await apiFetch("/api/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ meeting: state.meeting }) });
      if (!response.ok) { const err = await response.json(); throw new Error(err.error || "PDF generation failed."); }
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      if (printMode && printWindow) {
        printWindow.location.href = url;
        setState(current => ({ ...current, pdfGenerated: true })); auditEvent("final_pdf_print_opened", "Consolidated PDF opened using the download renderer");
        showToast("The consolidated PDF opened in a new tab. Use its PDF viewer Print control.");
      } else {
        if (printMode) showToast("Pop-up blocked; the consolidated PDF will download for printing.");
        const link = document.createElement("a"); link.href = url; link.download = `DAC-${state.meeting.meetingNo}-${state.meeting.department.replace(/[^a-z0-9]+/gi, "-")}.pdf`; document.body.appendChild(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
        setState(current => ({ ...current, pdfGenerated: true })); auditEvent(printMode ? "final_pdf_print_fallback" : "final_pdf_generated", "Consolidated MoM PDF generated");
        showToast(printMode ? "PDF downloaded; open it and print." : "Consolidated PDF downloaded.");
      }
    } catch (error) {
      if (printWindow && !printWindow.closed) printWindow.close();
      showToast(error.message || "PDF generation failed.", true);
    } finally { setBusy(false); }
  }
  async function resetDemo() {
    if (role !== "system_admin" || !window.confirm("Reset demo meetings, audit data, simulated invitations and uploaded files? User accounts and the school/department catalog will remain.")) return;
    try {
      const response = await apiFetch("/api/demo/reset", { method: "POST" });
      if (!response.ok) throw new Error("The demo could not be reset.");
      localStorage.removeItem(`${STATE_KEY}:${user.id}`); setState(defaultState(user)); setView("directory");
      showToast("Demo meeting data reset. Allow-listed user accounts were retained.");
    } catch (error) { showToast(error.message || "Reset failed.", true); }
  }

  const workflow = <div className="workflow">{[
    ["Meeting proposal", ["draft", "pending", "revision", "rejected", "approved"].includes(state.status)],
    ["Office approval", state.status === "approved"],
    ["Meeting completed", isUnlocked],
    ["Final MoM", !!state.pdfGenerated],
  ].map(([label, done], index) => <div className={`workflow-step ${done ? "done" : ""} ${index === (state.status === "draft" || state.status === "revision" || state.status === "rejected" ? 0 : state.status === "pending" ? 1 : isUnlocked ? 3 : 2) ? "active" : ""}`} key={label}><span className="step-num">{done ? "✓" : index + 1}</span><span>{label}</span></div>)}</div>;

  function meetingControls(editable) {
    const selected = new Set(state.meeting.agendas.filter(item => item.kind === "standard").map(item => item.id));
    const hasPrevious = state.meeting.agendas.some(item => ["std-mom", "std-atr"].includes(item.id));
    if (!editable) return <><ToolCard title="Request status" tag={statusText(state.status)}><p>{state.status === "pending" ? "This submitted approval copy is read-only while the Academic Office reviews it." : "The approved agenda wording is the baseline for the final MoM."}</p>{state.status === "approved" && <><div className="doc-tool-kv"><span>Approved version</span><b>{state.approvalVersion}</b></div><div className="doc-tool-kv"><span>Generated agenda blocks</span><b>{state.momItems.length}</b></div></>}</ToolCard>
      {state.status === "approved" && <ToolCard title="Approved request" tag="Read only"><p>Approved agenda wording is immutable in the MoM. Significant changes return to the Academic Office for reapproval.</p>{!isUnlocked && !meetingStarted(state.meeting) && <><div className="notice info"><span className="notice-icon">i</span><span>Discussion, Recommendations and annexure fields unlock only after the scheduled end time has passed AND the meeting is marked COMPLETED.</span></div><div className="doc-tool-actions mt-16"><button className="btn btn-outline" onClick={proposeChange}>Propose a change</button><button className="btn btn-primary" onClick={() => setView("mom")}>Open MoM workspace</button></div></>}</ToolCard>}</>;
    return <ToolCard title="Request controls" tag={`${state.meeting.agendas.length} agendas`}><p>Edit the official-looking document directly. These controls manage the shared agenda bank and invitee roster.</p>
      <div className="doc-tool-subheading">Academic Office agenda bank</div><div className="doc-bank-list">{agendaBank.map(item => <label className="doc-bank-row" key={item.id}><input type="checkbox" checked={selected.has(item.id)} onChange={event => toggleCommonAgenda(item.id, event.target.checked)} /><span><b>{item.title}</b><small>{item.note || "Common agenda"}</small></span></label>)}</div>
      <div className="doc-tool-subheading">Add meeting-specific agenda</div><input className="doc-tool-input" value={customAgenda.title} onChange={event => setCustomAgenda(current => ({ ...current, title: event.target.value }))} placeholder="Proposed agenda wording" aria-label="New agenda title" /><input className="doc-tool-input mt-8" value={customAgenda.reason} onChange={event => setCustomAgenda(current => ({ ...current, reason: event.target.value }))} placeholder="Reason / decision sought" aria-label="Reason for agenda" /><button className="btn btn-outline btn-small mt-8" onClick={addCustomAgenda}>Add proposed agenda</button>
      {hasPrevious && <><div className="doc-tool-subheading">Previous meeting reference</div><div className="doc-tool-grid"><label>Meeting no.<input className="doc-tool-input" value={state.meeting.previousMeetingNo} onChange={event => updateMeeting("previousMeetingNo", event.target.value)} /></label><label>Meeting date<input type="date" className="doc-tool-input" value={state.meeting.previousMeetingDate} onChange={event => updateMeeting("previousMeetingDate", event.target.value)} /></label></div></>}
      <div className="doc-tool-subheading">Meeting-specific organizer</div><div className="doc-organizer-card"><b>{user.name}</b><span>{user.email}</span><small>For this meeting only · assigned from your active faculty account</small></div>
      <div className="doc-tool-subheading">Add proposed member / invitee</div><input className="doc-tool-input" value={memberDraft.name} onChange={event => setMemberDraft(current => ({ ...current, name: event.target.value }))} placeholder="Full name" aria-label="New member name" /><div className="doc-tool-grid mt-8"><input className="doc-tool-input" value={memberDraft.designation} onChange={event => setMemberDraft(current => ({ ...current, designation: event.target.value }))} placeholder="Designation" aria-label="Designation" /><select className="doc-tool-input" value={memberDraft.role} onChange={event => setMemberDraft(current => ({ ...current, role: event.target.value }))} aria-label="New member role"><option>Member</option><option>Member Secretary</option><option>External Member</option></select></div><div className="doc-tool-grid mt-8"><input className="doc-tool-input" type="email" value={memberDraft.email} onChange={event => setMemberDraft(current => ({ ...current, email: event.target.value }))} placeholder="Official email" aria-label="Official email" /><button className="btn btn-outline btn-small" onClick={addMember}>Add member</button></div>
      <div className="doc-tool-actions mt-16"><button className="btn btn-outline" onClick={() => showToast(lastSaved ? `Draft autosaved at ${lastSaved}.` : "Draft is syncing to the secure local database.")}>Save draft</button><button className="btn btn-primary" onClick={submitRequest}>{state.status === "revision" || state.changeRequest ? "Resubmit for approval" : "Submit to Academic Office"} <span>→</span></button></div>
    </ToolCard>;
  }

  function requestView() {
    if (role !== "faculty") return <><SectionHeading eyebrow="Before the meeting" title="Meeting request & agenda approval" description="The signed-in faculty member schedules this DAC meeting and becomes its meeting-specific Chairperson/organizer." /><div className="empty-state"><h3>Faculty workspace</h3><p>Only an active, allow-listed faculty account may schedule a meeting.</p></div></>;
    const editable = canEditRequest;
    const side = <div className="document-side-panel"><ToolCard title="My meeting workspaces" tag={`${mine.length} saved`}><p>Each workspace is owned by your signed-in faculty account.</p><button className="btn btn-outline btn-small mb-8" onClick={createNewMeeting}>＋ New DAC meeting</button>{mine.map(item => <button className={`workspace-pick-row ${item.workspaceId === state.workspaceId ? "selected" : ""}`} key={item.workspaceId} onClick={() => openWorkspace(item.workspaceId)}><b>{item.department} · {longDate(item.date)}</b><small>{item.school} · Meeting {item.meetingNo} · {statusText(item.status)}</small></button>)}</ToolCard>{meetingControls(editable)}</div>;
    return <><SectionHeading eyebrow="Before the meeting" title="Meeting request & agenda approval" description="One structured meeting record feeds the request, approval preview, locked MoM and final PDF." />{workflow}{statusBanner(state)}
      <div className="document-workspace request-workspace"><main className="document-canvas-column"><RequestDocument meeting={state.meeting} editable={editable} catalog={role === "faculty" ? { schools: (catalog.schools || []).filter(school => school.name === user.school).map(school => ({ ...school, departments: (school.departments || []).filter(department => department.name === user.department) })) } : catalog} onSchoolChange={updateSchool} onDepartmentChange={updateDepartment} onMeetingChange={updateMeeting} onMemberChange={updateMember} onMemberRoleChange={updateMemberRole} onRemoveMember={removeMember} onRemoveAgenda={removeAgenda} /></main>{side}</div>
    </>;
  }
  function statusBanner(current) {
    if (current.status === "pending") return <div className="notice warning"><span className="notice-icon">…</span><span>Your request is with the Academic Office. Agenda wording and invitees are read-only while review is pending.</span></div>;
    if (current.status === "revision") return <div className="notice warning"><span className="notice-icon">↺</span><span><b>Revision requested.</b> {current.officeComment || "Review the office comment, update the document and resubmit."}</span></div>;
    if (current.status === "rejected") return <div className="notice error"><span className="notice-icon">!</span><span><b>Request rejected.</b> {current.officeComment || "The office rejected the proposal."} You can revise and resubmit.</span></div>;
    if (current.status === "approved") return <div className="notice success"><span className="notice-icon">✓</span><span>Approved. Invitations are recorded in the demo outbox; no real email was sent. Significant changes require reapproval.</span></div>;
    return <div className="notice info"><span className="notice-icon">i</span><span>Choose common agenda items, add meeting-specific proposals, and submit the complete package for review.</span></div>;
  }

  function reviewView() {
    if (role !== "academic_office") return <><SectionHeading eyebrow="Academic Office" title="Approval queue" description="Only Academic Office may approve the agenda and invitee package." /><div className="empty-state"><h3>Academic Office access required</h3></div></>;
    if (state.status !== "pending") return <><SectionHeading eyebrow="Academic Office" title="Approval queue" description="Review agenda wording, meeting details and Official Email addresses." /><div className="empty-state"><h3>No pending request</h3><p>Current request status: {statusText(state.status)}. Submit one as Chairperson to try the review flow.</p><button className="btn btn-outline mt-16" onClick={() => setView("library")}>Manage common agenda list</button></div></>;
    return <><SectionHeading eyebrow="Academic Office" title="Review meeting request" description="The pre-meeting preview shows proposed invitees and agenda wording only—not completed Discussion or Recommendations." />{workflow}
      <div className="document-workspace review-workspace mt-16"><main className="document-canvas-column"><RequestDocument meeting={state.meeting} editable={false} catalog={catalog} /></main><aside className="document-side-panel">
        {inbox.length > 1 && <ToolCard title="Pending requests" tag={`${inbox.length} in queue`}>{inbox.map(item => <button className={`admin-queue-row ${item.workspaceId === state.workspaceId ? "selected" : ""}`} key={item.workspaceId} onClick={() => openWorkspace(item.workspaceId)}><b>{item.ownerName} · {item.department}</b><small>{item.ownerEmail} · {item.school} · {longDate(item.date)}</small></button>)}</ToolCard>}
        <ToolCard title="Approval checklist" tag="Human review"><ul className="doc-checklist"><li>Reference number and meeting details</li><li>Previous MoM / ATR reference if selected</li><li>Agenda order, clarity and scope</li><li>Proposed invitees and Official Email</li></ul><div className="notice warning mt-10"><span className="notice-icon">!</span><span>Approval generates locked MoM blocks and a simulated invitation log.</span></div></ToolCard>
        <ToolCard title="Review decision" tag="Office"><p>Return with a specific revision note, reject with a reason, or approve the agenda and roster.</p><label className="doc-tool-label" htmlFor="office-comment">Comments for the Chairperson</label><textarea id="office-comment" className="doc-tool-input doc-comment" value={reviewComment} onChange={event => setReviewComment(event.target.value)} placeholder="Example: Please clarify agenda 3 and correct the proposed time." /><div className="doc-tool-actions vertical mt-12"><button className="btn btn-outline" onClick={returnForRevision}>Return for revision</button><button className="btn btn-danger" onClick={rejectRequest}>Reject request</button><button className="btn btn-primary" disabled={busy} onClick={approveRequest}>Approve agenda & members <span>→</span></button></div></ToolCard>
        <ToolCard title="Shared agenda bank" tag={`${agendaBank.length} items`}>{agendaBank.map(item => <div className="doc-bank-summary" key={item.id}><b>{item.title}</b><small>{item.note}</small></div>)}</ToolCard>
      </aside></div>
    </>;
  }

  function renderAiReport() {
    if (!state.aiReport) return <div className="ai-empty"><span className="ai-empty-mark">✦</span><b>No review run yet</b><p>Run a text check to see notes on Discussion and Recommendations.</p></div>;
    return <div className="ai-report"><p className="ai-report-notice">{state.aiReport.notice || "This is not factual verification."}</p>{(state.aiReport.items || []).map(item => <article className="ai-review-item" key={item.agendaNo}><div className="ai-review-head"><b>Agenda {item.agendaNo}: {item.agendaTitle}</b><StatusPill status={item.status} /></div>{(item.checks || []).map((check, index) => <div className="ai-check" key={`${item.agendaNo}-${index}`}><div><b>{check.name}</b><p>{check.message}</p>{check.evidence && <blockquote>{check.evidence}</blockquote>}<div className="ai-suggestion"><b>Human review suggestion:</b> {check.suggestion}</div></div><StatusPill status={check.status} /></div>)}</article>)}<div className="notice warning mt-10"><span className="notice-icon">!</span><span>Local demo rules only. No model is connected; no fact verification. Annexures/photos are not examined. Suggestions never edit records and annotations stay out of the PDF.</span></div></div>;
  }
  function renderAttendanceCard() {
    return <ToolCard title="Actual attendance" tag={`${presentCount} present`}><p>Only members marked present appear in the final table. No invitee is treated as an attendee by default.</p><div className="doc-attendance-list">{state.meeting.members.map(member => <label className="doc-attendance-row" key={member.id}><input type="checkbox" checked={!!member.present} disabled={!isUnlocked} onChange={event => toggleAttendance(member.id, event.target.checked)} /><span><b>{member.name}</b><small>{member.role} · {member.designation}</small></span></label>)}</div></ToolCard>;
  }
  function renderActionsCard() {
    return <ToolCard title="Action item entry" tag="Agenda-linked"><p>Select an approved agenda with a recorded recommendation. The official table keeps its four template columns.</p><label className="doc-tool-label" htmlFor="action-agenda">Approved agenda</label><select id="action-agenda" className="doc-tool-input" value={actionDraft.agendaId || state.momItems[0]?.id || ""} disabled={!isUnlocked} onChange={event => setActionDraft(current => ({ ...current, agendaId: event.target.value }))}>{state.momItems.map((item, index) => <option value={item.id} key={item.id}>Agenda {pad2(index + 1)} · {item.title}</option>)}</select><div className="doc-linked-recommendation">{selectedActionAgenda?.recommendation || "No recommendation has been recorded for this agenda yet."}</div><label className="doc-tool-label mt-8" htmlFor="action-text">Action(s) to be taken</label><input id="action-text" className="doc-tool-input" value={actionDraft.text} onChange={event => setActionDraft(current => ({ ...current, text: event.target.value }))} placeholder="Action arising from the recommendation" disabled={!isUnlocked} /><div className="doc-tool-grid mt-8"><label>Person(s) responsible<input className="doc-tool-input" value={actionDraft.owner} onChange={event => setActionDraft(current => ({ ...current, owner: event.target.value }))} placeholder="Name / role" disabled={!isUnlocked} /></label><label>Target date<input className="doc-tool-input" type="date" value={actionDraft.targetDate} onChange={event => setActionDraft(current => ({ ...current, targetDate: event.target.value }))} disabled={!isUnlocked} /></label></div><button className="btn btn-outline btn-small mt-8" onClick={addActionItem} disabled={!isUnlocked}>Add action item</button>{state.actionItems.map(item => <div className="doc-tool-action-row" key={item.id}><div><b>Agenda {item.agendaNo} · {item.text}</b><small>{item.owner} · {item.targetDate ? dmy(item.targetDate) : "Target date not set"}</small><small>Linked recommendation: {item.sourceRecommendation}</small></div><button className="btn-text" onClick={() => removeAction(item.id)} disabled={!isUnlocked}>Remove</button></div>)}</ToolCard>;
  }
  function renderAdditionalCard() {
    return <ToolCard title="Additional discussion" tag="Separate from approved agenda"><p>Add only a point actually discussed. It is separately labelled in the record and audit trail.</p><div className="doc-tool-grid"><input className="doc-tool-input" value={additionalTitle} onChange={event => setAdditionalTitle(event.target.value)} placeholder="Additional discussion point" disabled={!isUnlocked} /><button className="btn btn-outline btn-small" onClick={addAdditional} disabled={!isUnlocked}>Add point</button></div>{state.additionalDiscussions.map((item, index) => <div className="doc-tool-action-row" key={item.id}><div><b>Additional {pad2(index + 1)} · {item.title}</b><small>Not part of the approved agenda</small></div><button className="btn-text" onClick={() => removeAdditional(item.id)} disabled={!isUnlocked}>Remove</button></div>)}</ToolCard>;
  }
  function momView() {
    if (role !== "faculty") return <><SectionHeading eyebrow="After the meeting" title="MoM workspace" description="The authorized meeting team completes the minutes after the meeting." /><div className="empty-state"><h3>Faculty meeting workspace</h3><p>This account does not have the faculty permission required to complete these minutes.</p></div></>;
    if (state.status !== "approved") return <><SectionHeading eyebrow="After the meeting" title="MoM workspace" description="Agenda blocks are generated from the approved snapshot only." />{workflow}<div className="empty-state"><h3>Waiting for Academic Office approval</h3><p>No Discussion or Recommendations blocks are created before approval.</p><button className="btn btn-outline mt-16" onClick={() => setView("request")}>Return to meeting request</button></div></>;
    const lockMessage = isUnlocked
      ? <div className="notice success"><span className="notice-icon">✓</span><span>Both gates are satisfied: the scheduled end time has passed AND the meeting is marked COMPLETED. MoM fields are editable.</span></div>
      : <div className="notice warning"><span className="notice-icon">◷</span><span>Discussion, Recommendations and Ref. Document remain locked until BOTH conditions are true: scheduled end time has passed {endPassed ? "(satisfied)" : `(${dmy(state.meeting.date)} at ${state.meeting.endTime} Asia/Kolkata)`} AND meeting is marked COMPLETED {state.meeting.completed ? "(satisfied)" : "(not yet marked)"}.</span></div>;
    return <><SectionHeading eyebrow="After the meeting" title="Complete the minutes" description="Edit the official A4 document in place. Approved agenda wording remains read-only; this structured record also feeds the final PDF." actions={<button className="btn btn-outline" onClick={() => setView("request")}>View approved request</button>} />{workflow}
      <div className="document-workspace mom-document-workspace"><main className="document-canvas-column"><div className="doc-status-bar"><div><b>{meetingLabel}</b><span>{dmy(state.meeting.date)} · {state.meeting.startTime}–{state.meeting.endTime} · {state.meeting.venue}</span></div><StatusPill status={isUnlocked ? "complete" : "pending"}>{isUnlocked ? "Editable" : "Locked"}</StatusPill></div>{lockMessage}
        <FinalDocument meeting={state.meeting} momItems={state.momItems} additionalDiscussions={state.additionalDiscussions} photos={state.photos} actionItems={state.actionItems} isUnlocked={isUnlocked} onMomChange={updateMomItem} onToggleNoRecommendation={id => toggleNoRecommendation(state.momItems.find(item => item.id === id))} onUploadAgenda={uploadAgendaFiles} onRemoveFile={removeAgendaFile} onPhotoChange={updatePhoto} onUploadPhotos={uploadPhotos} onRemovePhoto={removePhoto} onAdditionalChange={updateAdditional} onRemoveAdditional={removeAdditional} onRemoveAction={removeAction} />
      </main><aside className="document-side-panel">
        <ToolCard title="Meeting completion gate" tag={state.meeting.completed ? "Completed" : "Not completed"}><p>Both scheduled time and completion attestation are required. Fast-forward is a demo test fixture only.</p><div className="doc-tool-actions">{!state.meeting.completed ? <button className="btn btn-outline btn-small" onClick={markCompleted}>Mark meeting COMPLETED</button> : <span className="tag">Meeting marked COMPLETED {state.meetingCompletedAt && `· ${state.meetingCompletedAt}`}</span>}{!endPassed && <button className="btn btn-outline btn-small" onClick={fastForwardEnd}>Demo: fast-forward scheduled end</button>}</div></ToolCard>
        {renderAttendanceCard()}{renderActionsCard()}{renderAdditionalCard()}
        <ToolCard title="Contextual AI assistance" tag="Local demo check" className="ai-context-panel"><p>Checks typed MoM text for relevance and internal coherence only. It cannot verify facts or inspect annexures/photos.</p><button className="btn btn-outline btn-small" onClick={runTextCheck} disabled={!isUnlocked}>Run relevance & coherence check</button><div className="ai-annotation-note">Human review required · no silent edits · annotations are excluded from the official PDF.</div>{renderAiReport()}</ToolCard>
        <ToolCard title="Final document" tag="One consolidated PDF"><p>Print and Download use the same renderer: MoM pages, photos, Annexure Index and agenda-linked attachments.</p><div className="doc-tool-actions vertical"><button className="btn btn-outline" onClick={() => exportPdf(true)} disabled={!isUnlocked || busy}>Print</button><button className="btn btn-primary" onClick={() => exportPdf(false)} disabled={!isUnlocked || busy}>{busy ? "Preparing PDF…" : "Download consolidated PDF ↓"}</button></div><div className={`notice ${isUnlocked ? "success" : "warning"} mt-10`}><span className="notice-icon">{isUnlocked ? "✓" : "◷"}</span><span>{isUnlocked ? "PDF export available; Office documents use readable demo conversion." : "PDF export remains locked until both meeting gates are satisfied."}</span></div></ToolCard>
      </aside></div>
    </>;
  }

  function overviewView() {
    if (role === "system_admin") return <><SectionHeading eyebrow="System administration" title="Manage who can enter the DAC workspace." description="Add professor accounts, assign application permissions and scope faculty to their school and department." actions={<button className="btn btn-primary" onClick={() => setView("directory")}>Open access directory →</button>} /><div className="grid grid-2"><section className="panel panel-pad"><div className="panel-header"><div><h2>Allow-list is the front door</h2><p>Every login code request is checked against the active SQLite directory.</p></div><StatusPill status="approved">Enabled</StatusPill></div><p className="muted">No account-wide Chairperson exists. The faculty member who creates a meeting request is set as the organizer for that meeting only.</p></section><section className="panel panel-pad"><div className="panel-header"><div><h2>Development authentication</h2><p>Local one-time code only; the demo never asks for a college password.</p></div><span className="tag tag-new">Replace for production</span></div><p className="muted">Connect the college’s Microsoft Entra tenant and MFA policy before production deployment.</p></section></div></>;
    const actions = role === "faculty" ? <button className="btn btn-primary" onClick={() => setView(state.status === "approved" ? "mom" : "request")}>{state.status === "approved" ? "Open MoM workspace" : "Continue meeting request"} →</button> : role === "academic_office" ? <button className="btn btn-primary" onClick={() => setView("review")}>Open approval queue →</button> : <button className="btn btn-primary" onClick={() => setView("member")}>View approved meeting →</button>;
    return <><SectionHeading eyebrow="DAC · meeting lifecycle" title="Minutes, with a clear chain of accountability." description="Prepare the request, secure Academic Office approval, then complete the MoM only after the meeting." actions={actions} />{workflow}
      <div className="stat-grid"><div className="stat-card"><span className="stat-label">Request state</span><strong style={{ fontSize: 17 }}>{statusText(state.status)}</strong><small>Academic Office is the final approver</small></div><div className="stat-card"><span className="stat-label">Agenda items</span><strong>{state.meeting.agendas.length}</strong><small>Common + meeting-specific</small></div><div className="stat-card"><span className="stat-label">Proposed invitees</span><strong>{state.meeting.members.length}</strong><small>Attendance not assumed</small></div><div className="stat-card"><span className="stat-label">MoM sections</span><strong>{state.momItems.length}</strong><small>{state.status === "approved" ? "Generated at approval" : "Generated only after approval"}</small></div></div>
      <div className="grid grid-2 mt-16"><section className="panel panel-pad"><div className="panel-header"><div><h2>Your next step</h2><p>Approved agenda wording is the reference for the final minutes.</p></div><StatusPill status={state.status} /></div><div className="meeting-card"><div className="card-label">Current request</div><h3>{meetingLabel}</h3><p>{state.meeting.school} · Academic year {state.meeting.academicYear} · {state.meeting.semester} semester</p><div className="meeting-card-grid"><div><span>Date</span><b>{longDate(state.meeting.date)}</b></div><div><span>Time</span><b>{state.meeting.startTime}–{state.meeting.endTime}</b></div><div><span>Venue</span><b>{state.meeting.venue}</b></div><div><span>Mode</span><b>{state.meeting.mode}</b></div></div></div></section>
        <section className="panel panel-pad"><div className="panel-header"><div><h2>{role === "academic_office" ? "Office review" : role === "external_member" ? "Guest access" : "Meeting at a glance"}</h2><p>Current meeting checkpoint</p></div></div>{role === "academic_office" ? <div className="timeline"><div className={`timeline-row ${state.status === "pending" ? "" : "pending"}`}><span className="timeline-dot" /><div><b>{state.status === "pending" ? "Request is waiting" : `Request status: ${statusText(state.status)}`}</b><small>Review agenda, members and meeting details.</small></div></div><div className="timeline-row"><span className="timeline-dot" /><div><b>Invitation follows approval</b><small>Outbox events are simulated; no mail is sent.</small></div></div></div> : <div className="kv-list"><div className="kv"><span>Meeting</span><b>{ordinal(state.meeting.meetingNo)}</b></div><div className="kv"><span>School</span><b>{state.meeting.school}</b></div><div className="kv"><span>Department</span><b>{state.meeting.department}</b></div><div className="kv"><span>Scheduled</span><b>{longDate(state.meeting.date)} · {state.meeting.startTime}</b></div></div>}</section>
      </div>
      <section className="panel panel-pad mt-16"><div className="panel-header"><div><h2>Workflow in this demo</h2><p>The meeting organizer is the faculty member who schedules this particular meeting; there is no global Chairperson account.</p></div></div><div className="grid grid-3"><div className="security-card"><div className="security-icon">1</div><h3>Submit the proposal</h3><p>Select common agenda items, add meeting-specific topics and proposed invitees.</p></div><div className="security-card"><div className="security-icon">2</div><h3>Review and approve</h3><p>The Academic Office may approve, return or reject. Invitation entries are simulated.</p></div><div className="security-card"><div className="security-icon">3</div><h3>Complete the MoM</h3><p>Blocks appear at approval and stay locked until end time passed AND COMPLETED.</p></div></div></section>
    </>;
  }

  function outboxView() {
    return <><SectionHeading eyebrow="Notifications" title="Invitation log" description="The automatic post-approval invitation is simulated in this local demo." actions={<span className="tag tag-new">No real email sent</span>} />{state.outbox.length ? [...state.outbox].reverse().map(mail => <article className="outbox-card" key={mail.id || mail.createdAt}><header><div><h3>{mail.subject || "DAC meeting invitation"}</h3><p>From {mail.from || "Organizer"} · {mail.createdAt || "Demo timestamp"}</p></div><span className="status-pill status-review">SIMULATED</span></header><p><b>Recipients:</b> {(mail.recipients || []).join(", ")}</p><p><b>Meeting:</b> {mail.meeting?.meetingNo} · {mail.meeting?.department} · {longDate(mail.meeting?.date)}</p><pre>{`Agenda: ${(mail.meeting?.agendas || []).map(item => item.title).join("; ")}\nTime: ${mail.meeting?.startTime}–${mail.meeting?.endTime}\nVenue: ${mail.meeting?.venue}\n\nDEMO ONLY — this invitation was not sent.`}</pre></article>) : <div className="empty-state"><h3>No invitations recorded</h3><p>Approval will add a simulated outbox row; Microsoft 365 delivery is not connected.</p></div>}<div className="notice warning mt-16"><span className="notice-icon">!</span><span>Production mail should use scoped delegated Microsoft Graph permission, never stored mailbox passwords.</span></div></>;
  }
  function securityView() {
    return <><SectionHeading eyebrow="Security baseline" title="Private data needs layered protection." description="The allow-list, OTP session, CSRF checks and API role gates are enforced in this local prototype; production still requires college SSO/MFA and secure deployment." actions={role === "system_admin" ? <button className="btn btn-outline" onClick={resetDemo}>Reset demo meetings</button> : null} /><div className="notice warning"><span className="notice-icon">!</span><span><b>Do not enter real credentials or confidential meeting records.</b> The allow-list + local OTP is a development fixture; `.example` accounts are not real college identities.</span></div><div className="security-grid mt-16"><SecurityCard icon="◎" title="College Microsoft sign-in + MFA" text="Production should use the college’s single-tenant Entra sign-in and college-managed MFA/Conditional Access." tag="Not connected" /><SecurityCard icon="↗" title="Least-privilege Outlook sending" text="Outbox is local and simulated. Real delivery needs institutional setup and delegated Microsoft Graph Mail.Send." tag="Simulated" /><SecurityCard icon="⇄" title="TLS in transit" text="Use HTTPS/TLS for every request, upload and download in production." tag="Deployment configuration" /><SecurityCard icon="▣" title="Private document storage" text="This demo saves uploads locally. Production needs encrypted private storage, malware scanning and retention rules." tag="Local demo storage" /><SecurityCard icon="⌑" title="Meeting-scoped authorization" text="Role changes are enforced by the API in this demo. Production still needs college Entra identity, MFA, meeting-scoped authorization and audit controls." tag="Demo role enforcement" /><SecurityCard icon="◷" title="External guest access" text="Guests should see only explicitly shared meetings and files, read-only by default, auditable and revocable." tag="Simulated" /></div><section className="panel panel-pad mt-16"><div className="panel-header"><div><h2>Demo activity log</h2><p>Workflow events only; avoid putting sensitive content in audit comments.</p></div><span className="tag">{state.audit.length} events</span></div>{state.audit.length ? <div className="timeline">{state.audit.slice(0, 15).map((row, index) => <div className="timeline-row" key={`${row.at}-${index}`}><span className="timeline-dot" /><div><b>{row.event}</b><small>{row.at} · {row.role} {row.details?.note && `· ${row.details.note}`}</small></div></div>)}</div> : <p className="muted">No workflow events yet.</p>}</section></>;
  }
  function memberView() {
    if (role !== "external_member") return <><SectionHeading eyebrow="External access" title="Meeting access" description="This view represents limited guest access in the local demo." /><div className="empty-state"><h3>External Member access required</h3></div></>;
    if (state.status !== "approved" || !state.approvedMeeting) return <><SectionHeading eyebrow="External guest · read only" title="No approved meeting shared" description="A guest cannot browse other meetings in the production design." /><div className="empty-state"><h3>Nothing has been shared</h3><p>Once approved, this demo shows this meeting’s agenda read-only.</p></div></>;
    return <><SectionHeading eyebrow="External guest · read only" title="Your meeting materials" description="Limited to the current approved meeting in this local demo." /><div className="meeting-card"><div className="card-label">Approved meeting</div><h3>{meetingLabel}</h3><p>{state.meeting.school} · {state.meeting.academicYear}</p><div className="meeting-card-grid"><div><span>Date</span><b>{longDate(state.meeting.date)}</b></div><div><span>Time</span><b>{state.meeting.startTime}–{state.meeting.endTime}</b></div><div><span>Venue</span><b>{state.meeting.venue}</b></div><div><span>Access</span><b>Read-only demo</b></div></div></div><section className="panel panel-pad mt-16"><div className="panel-header"><div><h2>Approved agenda</h2><p>Visible to the explicitly represented guest role only.</p></div><StatusPill status="approved" /></div>{(state.approvedMeeting.agendas || []).map((item, index) => <div className="bank-item" key={item.id}><span className="tag">Agenda {pad2(index + 1)}</span><span><b>{item.title}</b><small>{item.kind === "custom" ? "Meeting-specific" : "Common agenda"}</small></span></div>)}</section><div className="notice warning mt-16"><span className="notice-icon">i</span><span>The active allow-listed guest email must appear in the approved invitee roster. This demo shares schedule/agenda only; annexures and final MoM are not exposed to guests.</span></div></>;
  }

  let content;
  switch (view) {
    case "request": content = requestView(); break;
    case "review": content = reviewView(); break;
    case "mom": content = momView(); break;
    case "library": content = role === "academic_office" ? <AgendaLibrary bank={agendaBank} onAdd={addBankItem} onRemove={removeBankItem} onRestore={restoreBank} /> : <div className="empty-state"><h3>Academic Office permission required</h3></div>; break;
    case "directory": content = role === "system_admin" ? <UserDirectory currentUser={user} /> : <div className="empty-state"><h3>System Administrator permission required</h3></div>; break;
    case "outbox": content = outboxView(); break;
    case "security": content = securityView(); break;
    case "member": content = memberView(); break;
    default: content = overviewView();
  }
  const navItems = NAV[role] || NAV.faculty;

  return <>
    <div className="demo-strip"><span className="demo-pulse" /> LOCAL DEMO · Do not enter real college credentials or confidential records</div>
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#top" onClick={event => { event.preventDefault(); setView("overview"); }}><span className="brand-mark"><span /><span /><span /></span><span><strong>DAC Minutes</strong><small>Document-first workflow</small></span></a>
        <div className="side-label">WORKSPACE</div><nav className="nav-list" aria-label="Main navigation">{navItems.map(([key, label, icon]) => <button className={`nav-item ${view === key ? "active" : ""}`} key={key} onClick={() => setView(key)}><span className="nav-icon">{icon}</span><span>{label}</span>{key === "review" && state.status === "pending" && <span className="nav-count">1</span>}</button>)}</nav>
        <div className="sidebar-bottom"><div className="side-status"><span className="status-dot" /><span><b>Local demo environment</b><small>Production integrations simulated</small></span></div><a className="docs-link" href="/README" target="_blank" rel="noreferrer">Project & security notes <span>↗</span></a></div>
      </aside>
      <main className="main-area" id="top">
        <header className="topbar"><div className="crumb"><span>University workspace</span><span className="crumb-sep">/</span><b>{VIEW_LABEL[view] || "Overview"}</b></div><div className="top-actions"><span className="environment-pill"><i /> SECURE DEMO</span><div className="signed-in-user"><span className="avatar">{(user.name || user.email).slice(0, 1).toUpperCase()}</span><span><b>{user.name}</b><small>{ROLE_LABEL[role]} · {user.email}</small></span></div><button className="btn btn-outline btn-small" onClick={onLogout}>Sign out</button></div></header>
        <div className="integration-banner"><span className="banner-icon">i</span><div><b>Prototype only.</b> College SSO/MFA, Microsoft 365 mail, production AI, TLS deployment, malware scanning and private cloud storage are not connected.</div></div>
        <div className="view-root">{content}</div>
      </main>
    </div>
    <div className="toast-region" aria-live="polite">{toast && <div className={`toast${toast.isError ? " error" : ""}`}>{toast.message}</div>}</div>
  </>;
}

function UserDirectory({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState(["system_admin", "academic_office", "faculty", "external_member"]);
  const [catalog, setCatalog] = useState({ schools: [] });
  const [edits, setEdits] = useState({});
  const [form, setForm] = useState({ name: "", email: "", role: "faculty", school: "Engineering", department: "Mechanical Engineering" });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const schoolNames = catalog.schools.map(school => school.name);
  const departmentsFor = schoolNameValue => catalog.schools.find(school => school.name === schoolNameValue)?.departments || [];
  const formDepartments = departmentsFor(form.school);

  async function refresh() {
    setLoading(true); setError("");
    try {
      const response = await apiFetch("/api/admin/users");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load the access directory.");
      setUsers(data.users || []); setRoles(data.roles || roles); setCatalog(data.catalog || { schools: [] });
      setForm(current => ({ ...current, school: current.school || data.catalog?.schools?.[0]?.name || "", department: current.department || data.catalog?.schools?.[0]?.departments?.[0]?.name || "" }));
    } catch (loadError) { setError(loadError.message || "Could not load the access directory."); }
    finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, []);
  function changeForm(field, value) {
    setForm(current => {
      if (field === "school") return { ...current, school: value, department: departmentsFor(value)[0]?.name || "" };
      if (field === "role" && value !== "faculty") return { ...current, role: value, school: "", department: "" };
      if (field === "role" && value === "faculty") {
        const school = current.school || schoolNames[0] || "";
        return { ...current, role: value, school, department: current.department || departmentsFor(school)[0]?.name || "" };
      }
      return { ...current, [field]: value };
    });
  }
  function editValue(user, key) {
    const saved = edits[user.id] || {};
    if (key in saved) return saved[key];
    if (key === "name") return user.name;
    if (key === "role") return user.role;
    if (key === "active") return user.active;
    if (key === "school") return user.school || "";
    if (key === "department") return user.department || "";
    return "";
  }
  function changeUser(user, key, value) {
    if (key === "role" && value === "faculty") {
      const school = editValue(user, "school") || schoolNames[0] || "";
      const department = editValue(user, "department") || departmentsFor(school)[0]?.name || "";
      setEdits(current => ({ ...current, [user.id]: { ...(current[user.id] || {}), role: value, school, department } }));
      return;
    }
    if (key === "role" && value !== "faculty") {
      setEdits(current => ({ ...current, [user.id]: { ...(current[user.id] || {}), role: value, school: "", department: "" } }));
      return;
    }
    setEdits(current => ({ ...current, [user.id]: { ...(current[user.id] || {}), [key]: value } }));
    if (key === "school") {
      const nextDepartment = departmentsFor(value)[0]?.name || "";
      setEdits(current => ({ ...current, [user.id]: { ...(current[user.id] || {}), school: value, department: nextDepartment } }));
    }
  }
  async function addUser(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const response = await apiFetch("/api/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not provision the account.");
      setMessage(`${data.user.email} added to the active access directory.`);
      setForm(current => ({ ...current, name: "", email: "" })); await refresh();
    } catch (addError) { setError(addError.message || "Could not provision the account."); }
    finally { setBusy(false); }
  }
  async function saveUser(user) {
    const draft = { ...user, ...(edits[user.id] || {}) };
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await apiFetch(`/api/admin/users/${user.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: draft.name, role: draft.role, active: draft.active, school: draft.school || null, department: draft.department || null }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not update this account.");
      setUsers(current => current.map(item => item.id === user.id ? data.user : item));
      setEdits(current => { const next = { ...current }; delete next[user.id]; return next; });
      setMessage(`Saved access settings for ${data.user.email}.`);
    } catch (saveError) { setError(saveError.message || "Could not update this account."); }
    finally { setBusy(false); }
  }
  const activeCount = users.filter(user => user.active).length;

  return <>
    <SectionHeading eyebrow="System Administrator" title="Access directory" description="Provision users by email and assign application roles and academic scope. An account must be active here before the sign-in code flow will work." actions={<button className="btn btn-outline" onClick={refresh} disabled={loading}>Refresh directory</button>} />
    <div className="notice warning"><span className="notice-icon">!</span><span><b>Development access only.</b> Local OTP codes are displayed for testing; production must replace this with college Microsoft Entra sign-in and MFA. Do not add real college credentials.</span></div>
    <div className="stat-grid mt-16"><div className="stat-card"><span className="stat-label">Active accounts</span><strong>{activeCount}</strong><small>Only active allow-listed emails may sign in</small></div><div className="stat-card"><span className="stat-label">Faculty profiles</span><strong>{users.filter(user => user.role === "faculty").length}</strong><small>School/department scoped</small></div><div className="stat-card"><span className="stat-label">Academic Office</span><strong>{users.filter(user => user.role === "academic_office" && user.active).length}</strong><small>Meeting approval permissions</small></div><div className="stat-card"><span className="stat-label">External guests</span><strong>{users.filter(user => user.role === "external_member" && user.active).length}</strong><small>Explicit guest identities</small></div></div>
    <div className="grid grid-2 mt-16"><section className="panel panel-pad"><div className="panel-header"><div><h2>Add account to allow-list</h2><p>No passwords are collected or stored.</p></div><span className="tag">Admin only</span></div><form onSubmit={addUser} className="admin-user-form"><label className="field"><span>Full name</span><input required value={form.name} onChange={event => changeForm("name", event.target.value)} placeholder="Professor name" /></label><label className="field"><span>Email address</span><input required type="email" value={form.email} onChange={event => changeForm("email", event.target.value)} placeholder="professor@college.edu" /></label><label className="field"><span>Application role</span><select value={form.role} onChange={event => changeForm("role", event.target.value)}>{roles.map(role => <option key={role} value={role}>{ROLE_LABEL[role] || role}</option>)}</select></label>
      {form.role === "faculty" && <><label className="field"><span>School / college</span><select required value={form.school} onChange={event => changeForm("school", event.target.value)}>{schoolNames.map(school => <option key={school}>{school}</option>)}</select></label><label className="field"><span>Department</span><select required value={form.department} onChange={event => changeForm("department", event.target.value)}>{formDepartments.map(department => <option key={department.id}>{department.name}</option>)}</select></label></>}
      <button className="btn btn-primary mt-16" disabled={busy}>{busy ? "Saving…" : "Add to access directory →"}</button></form>
      <div className="notice info mt-16"><span className="notice-icon">i</span><span>The role determines permitted application sections. Faculty are scoped to the selected school and department. Chairperson is not a global account role: the scheduling faculty member is the organizer for that meeting only.</span></div>
    </section><section className="panel panel-pad"><div className="panel-header"><div><h2>Role permissions</h2><p>Server checks are applied to API routes, not just navigation.</p></div></div><div className="permission-row"><b>System Administrator</b><span>Provision, activate, deactivate and assign roles to users.</span></div><div className="permission-row"><b>Academic Office</b><span>Review and decide submitted meeting requests; maintain common agenda items.</span></div><div className="permission-row"><b>Faculty</b><span>Create requests within their provisioned school/department; edit only their own meeting MoM.</span></div><div className="permission-row"><b>External Member</b><span>Read-only access to an explicitly approved meeting that lists their email.</span></div><div className="admin-current-user">Signed in as <b>{currentUser.name}</b> · {currentUser.email}</div></section></div>
    {message && <div className="notice success mt-16"><span className="notice-icon">✓</span><span>{message}</span></div>}{error && <div className="notice error mt-16"><span className="notice-icon">!</span><span>{error}</span></div>}
    <section className="panel panel-pad mt-16"><div className="panel-header"><div><h2>Provisioned accounts</h2><p>Email is the access-directory key; inactive accounts cannot request a sign-in code.</p></div><span className="tag">{users.length} total</span></div>
      {loading ? <p className="muted">Loading accounts…</p> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Person / email</th><th>Role</th><th>School</th><th>Department</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map(user => {
        const selectedRole = editValue(user, "role");
        const selectedSchool = editValue(user, "school");
        const rowDepartments = departmentsFor(selectedSchool);
        return <tr key={user.id}><td><b>{user.name}</b><small>{user.email}</small>{user.id === currentUser.id && <span className="tag">You</span>}</td>
          <td><select value={selectedRole} onChange={event => changeUser(user, "role", event.target.value)}>{roles.map(role => <option key={role} value={role}>{ROLE_LABEL[role] || role}</option>)}</select></td>
          <td>{selectedRole === "faculty" ? <select value={selectedSchool} onChange={event => changeUser(user, "school", event.target.value)}>{schoolNames.map(school => <option key={school}>{school}</option>)}</select> : <span className="muted">—</span>}</td>
          <td>{selectedRole === "faculty" ? <select value={editValue(user, "department")} onChange={event => changeUser(user, "department", event.target.value)}>{rowDepartments.map(department => <option key={department.id}>{department.name}</option>)}</select> : <span className="muted">—</span>}</td>
          <td><StatusPill status={user.active ? "approved" : "rejected"}>{user.active ? "Active" : "Inactive"}</StatusPill></td>
          <td><div className="admin-actions"><button className="btn btn-outline btn-small" onClick={() => saveUser(user)} disabled={busy}>Save</button><button className="btn-text" onClick={() => changeUser(user, "active", !editValue(user, "active"))}>{editValue(user, "active") ? "Deactivate" : "Activate"}</button></div></td></tr>;
      })}</tbody></table></div>}
    </section>
  </>;
}

function AgendaLibrary({ bank, onAdd, onRemove, onRestore }) {
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  return <><SectionHeading eyebrow="Academic Office" title="Common agenda library" description="Maintain recurring agenda options available to Chairpersons. Meeting-specific proposals are not added automatically." actions={<button className="btn btn-outline" onClick={onRestore}>Restore demo list</button>} /><div className="grid grid-2"><section className="panel panel-pad"><div className="panel-header"><div><h2>Shared agenda items</h2><p>Current local demo list</p></div><span className="tag">{bank.length} items</span></div><div className="bank-list">{bank.map((item, index) => <div className="bank-item" key={item.id}><span className="tag">{pad2(index + 1)}</span><span><b>{item.title}</b><small>{item.note}</small></span><button className="btn-text" onClick={() => onRemove(item.id)}>Remove</button></div>)}</div></section><section className="panel panel-pad"><div className="panel-header"><div><h2>Add a common agenda item</h2><p>Only Academic Office maintains this list.</p></div></div><label className="field"><span>Agenda title</span><input value={title} onChange={event => setTitle(event.target.value)} placeholder="Concise recurring agenda title" /></label><label className="field mt-10"><span>Category / note</span><input value={note} onChange={event => setNote(event.target.value)} placeholder="e.g. Academic review" /></label><button className="btn btn-primary mt-16" onClick={() => { onAdd(title, note); setTitle(""); setNote(""); }}>Add to common list</button><hr className="divider" /><div className="notice info"><span className="notice-icon">i</span><span>Promoting a meeting-specific item into the shared library is an explicit Office action.</span></div></section></div></>;
}
function SecurityCard({ icon, title, text, tag }) { return <article className="security-card"><div className="security-icon">{icon}</div><h3>{title}</h3><p>{text}</p><span className="tag tag-new mt-10">{tag}</span></article>; }

export default App;
