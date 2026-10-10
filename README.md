# DAC Minutes Studio — full-stack local workflow demo

A document-first prototype for the Departmental Academic Committee (DAC) meeting request and Minutes of Meeting workflow. The React frontend runs on **port 3000** and the Flask API runs on **port 8000**. Vite proxies same-origin `/api` requests to Flask; browser code does not call a localhost API directly. A SQLite database is the shared source of truth for accounts, academic affiliations and meeting workspaces.

**Template fidelity note:** the workspace contains `assets/reference-mom-template.pdf`, a four-page PDF copy of the supplied reference. The named master file `DAC MoM Template (2)(1).docx` was not available in the workspace while this version was generated. The implementation follows the user-provided master specification and the PDF’s sequence and wording; it does **not** claim a pixel-perfect comparison to the missing DOCX.

> **Local demo only.** College Microsoft sign-in/MFA, real email delivery, a hosted AI model, production TLS termination, malware scanning and production document storage are not connected. Use only the fake demo identities below. Do not enter college passwords, confidential meeting records or sensitive student data.

## Requirements

- Python 3.10+
- Node.js 20+
- npm

## Install and run

From the project root:

```bash
python -m venv .venv
# macOS/Linux
. .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Start both services with `./run_demo.sh`, or use two terminals:

```bash
# Terminal 1 — project root
. .venv/bin/activate       # Windows: .\.venv\Scripts\Activate.ps1
python app.py              # Flask API on 0.0.0.0:8000
```

```bash
# Terminal 2 — project root
cd frontend
npm run dev                # React/Vite UI on 0.0.0.0:3000
```

Open **http://localhost:3000** (or the hosted preview on port 3000). Port 8000 is the API, not the user interface. To build the static frontend bundle, run `cd frontend && npm run build`.

## Demo sign-in and account management

The demo uses a **SQLite active-email allow-list**. Only an active address already in the directory can complete sign-in. On the sign-in screen, request a one-time code; the local demo displays it in the browser to simulate delivery. No passwords are collected or stored, and no email is sent.

Seeded fake identities include:

| Demo email | Role / scope |
| --- | --- |
| `admin@college.example` | System Administrator — account directory only |
| `academic.office@college.example` | Academic Office — request review and agenda library |
| `asha.rao@college.example` | Faculty — Engineering / Mechanical Engineering |
| `devika.nair@college.example` | Faculty — Computer Engineering / Computer Science & Engineering |
| `kiran.kumar@college.example` | Faculty — Information Science / MCA |
| `mira.shah@college.example` | Faculty — Commerce / B.Com |
| `alex@example.org` | External Member — limited approved-meeting view |

Sign out and sign in with another seeded address to test another role; the removed “Acting as” role switcher is not used for authorization. A System Administrator can add, activate, deactivate, or change accounts in **Access directory**. Faculty accounts require a school and dependent department assignment. A faculty member can create and edit only that account’s meetings; the signed-in scheduling faculty member becomes the organizer/Chairperson **for that meeting only**. There is no global Chairperson account role.

The academic catalog includes Computer Engineering, Engineering, Information Science, Commerce, Arts, Design, Health Care and Science, with dependent department lists (including Engineering → Mechanical/Electrical/Civil, Computer Engineering → AI/ML/Cyber Security and Information Science → MCA/BCA/BCA (Data Science)).

## Document structure and workflow

The request and MoM editors use an A4-like document canvas as the primary workspace, with contextual controls alongside it. One structured meeting record feeds the proposal, Academic Office preview, approved MoM and final PDF; users do not re-enter the meeting details.

The PDF renderer preserves the reference’s main sequence:

1. **Page 1:** “Minutes of Meeting Template,” School and Department headings, generated reference/date, meeting title and description, and the appropriate roster. Before the meeting this is a proposed invitee table with **Official Email**; the final MoM contains actual attendees only, with the template’s **Signature** column.
2. **Page 2 onward:** opening statement, one generated section per approved agenda (agenda count is not hardcoded), Discussion, Recommendations, and the agenda’s Document / Ref. Document / Annexure area. Previous-MoM approval and ATR use the previous meeting number/date when supplied. Additional discussion points remain separate and audit-labelled.
3. **Photos and action table:** “Geo-Tagged Photos and Online Platform Screenshots – Departmental Academic Committee,” aspect-ratio-preserving images with captions and available location/date-time metadata, then the template action table.
4. **Closing:** the template closing statement, Member Secretary and Chairperson signature locations, and “Encl: Annexures.” Long content expands past four pages when needed.

### Try the complete flow

1. Sign in as a **Faculty** account. Open **Meeting request** to edit meeting details in the document, select any number of common agendas, and add meeting-specific proposals where needed. The school and department are constrained to that account’s provisioned scope. Every proposed invitee must also be active in the access directory; external invitees must be provisioned as External Members first.
2. Submit the proposal. While pending, agenda wording and invitees are read-only.
3. Sign in as **Academic Office**. In **Approval queue**, select a request and approve, return it with a comment, or reject it. Approval creates locked MoM sections from the approved agenda snapshot and records a simulated invitation; **no email is sent**.
4. Sign back in as the owning **Faculty** account. Open **My meeting workspaces** or the MoM workspace. Record actual attendance separately; the final Members Present table excludes absent invitees. Discussion, Recommendations and annexure fields unlock only after **both** the scheduled end time has passed **and** the meeting is marked **COMPLETED**. The development-only “Demo: fast-forward scheduled end” control is available to test that gate.
5. Once unlocked, enter the recorded discussion/outcome, attach agenda-linked annexures, add photos and actions, and optionally run the local relevance/coherence check. Print and Download use the same consolidated PDF output.

Approved agenda wording is read-only in the MoM. Significant pre-meeting changes go back through Academic Office reapproval. Each faculty member can maintain multiple independently owned meeting workspaces.

## External Member scope

An active allow-listed External Member can see only an approved meeting whose invitee roster explicitly includes that email. The demo returns a redacted schedule/agenda view only. It does **not** expose the final MoM, attendee roster, annexures, uploaded files or file links to guests; explicit document-level sharing and revocation are not implemented here.

## Final PDF and attachments

The final output is one consolidated PDF containing the MoM sections, photos, an Annexure Index and agenda-linked attachments. Annexures are indexed under their agenda and appended after the MoM. PDF files are appended; images are converted while preserving aspect ratio; DOCX/XLSX/PPTX/TXT/CSV are rendered into readable text/table pages in this demo. Office conversion is not pixel-perfect and may omit embedded objects or complex layout. AI annotations are excluded from the official PDF.

## AI/text review boundary

The “AI” control is a transparent, local deterministic demo check—not a language model. It examines typed agenda, Discussion and Recommendation text for relevance/coherence/outcome consistency only. It cannot verify what actually happened, does not use annexures or photos as evidence, explains each finding and offers human-reviewed suggestions only. It never silently edits records.

## Security and production boundary

Local sessions, CSRF checks, active-account checks and API role gates are enforced in the demo. Faculty workspace access is owner-scoped; external file access is denied by default. Data is stored locally under `data/` and in the browser cache. These controls are development scaffolding, not a security certification.

Before production, integrate the college’s single-tenant Microsoft Entra sign-in and college-managed MFA/Conditional Access. The local OTP route is disabled when `APP_ENV=production`, and the Entra integration is **not implemented**. Production also needs a configured `FLASK_SECRET_KEY`, HTTPS/TLS, secure deployment, private encrypted storage, malware scanning, access reviews, retention/deletion controls, and audit procedures. A domain suffix alone is not authentication; do not collect or store college passwords. Real Outlook delivery requires institutional setup and narrowly scoped delegated Microsoft Graph `Mail.Send` authorization. External guest access should use explicitly shared, meeting-scoped documents with least privilege, auditing, expiry and revocation.

## Supported uploads in this demo

`.pdf`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.docx`, `.xlsx`, `.pptx`, `.txt`, `.csv` (15 MB per file). Password-protected PDFs are rejected. These checks are not a substitute for production malware scanning or file validation.

## Quick checks

```bash
python -m py_compile app.py auth_store.py self_test.py
python self_test.py
cd frontend && npm run build
```
