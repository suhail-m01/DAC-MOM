import { useState } from "react";

async function apiFetch(url, options = {}) {
  return fetch(url, { ...options, credentials: "same-origin" });
}

const DEMO_IDENTITIES = [
  ["admin@college.example", "System Administrator"],
  ["academic.office@college.example", "Academic Office"],
  ["asha.rao@college.example", "Faculty · Engineering"],
  ["secretary@college.example", "Faculty · Engineering"],
  ["devika.nair@college.example", "Faculty · Computer Engineering"],
  ["kiran.kumar@college.example", "Faculty · Information Science"],
  ["mira.shah@college.example", "Faculty · Commerce"],
  ["alex@example.org", "External Member"],
];

export default function LoginScreen({ onAuthenticated }) {
  const [email, setEmail] = useState("admin@college.example");
  const [code, setCode] = useState("");
  const [demoCode, setDemoCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);

  async function requestCode(event) {
    event?.preventDefault(); setBusy(true); setError(""); setMessage(""); setDemoCode("");
    try {
      const response = await apiFetch("/api/auth/request-code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not request a sign-in code.");
      setRequested(true); setMessage(data.message || "Check your inbox for a sign-in code.");
      if (data.demoCode) { setDemoCode(data.demoCode); setCode(data.demoCode); }
    } catch (requestError) { setError(requestError.message || "Sign-in code request failed."); }
    finally { setBusy(false); }
  }
  async function verifyCode(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await apiFetch("/api/auth/verify-code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, code }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Sign-in failed.");
      onAuthenticated(data);
    } catch (authError) { setError(authError.message || "Sign-in failed."); }
    finally { setBusy(false); }
  }

  return <main className="login-screen">
    <section className="login-brand-panel">
      <a className="brand login-brand" href="#signin"><span className="brand-mark"><span /><span /><span /></span><span><strong>DAC Minutes</strong><small>Secure academic workflow</small></span></a>
      <div className="login-brand-copy"><div className="eyebrow">Departmental Academic Committee</div><h1>One workspace.<br />A clear record.</h1><p>Meeting proposals, Academic Office decisions and final minutes—connected through an account directory and role-based access.</p><div className="login-feature"><span>✓</span><div><b>Access is provisioned</b><small>Only active accounts in the System Administrator’s directory may sign in.</small></div></div><div className="login-feature"><span>✓</span><div><b>Organizer is meeting-specific</b><small>The faculty member scheduling a meeting becomes its organizer for that meeting only.</small></div></div></div>
      <div className="login-brand-footer">LOCAL DEVELOPMENT PREVIEW · NOT A PRODUCTION IDENTITY SERVICE</div>
    </section>
    <section className="login-form-panel" id="signin">
      <div className="login-card"><div className="eyebrow">Welcome</div><h2>Sign in to DAC Minutes</h2><p className="login-subtitle">Use an email address that has been activated by the System Administrator.</p>
        {!requested ? <form onSubmit={requestCode}><label className="field"><span>College / guest email</span><input autoComplete="email" type="email" required value={email} onChange={event => setEmail(event.target.value.trimStart())} placeholder="name@college.edu" /></label><button className="btn btn-primary login-submit" type="submit" disabled={busy}>{busy ? "Requesting…" : "Request one-time code →"}</button></form> : <form onSubmit={verifyCode}><div className="login-address">Code requested for <b>{email}</b><button className="btn-text" type="button" onClick={() => { setRequested(false); setCode(""); setDemoCode(""); }}>Change</button></div><label className="field"><span>Six-digit sign-in code</span><input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" required /></label><button className="btn btn-primary login-submit" type="submit" disabled={busy || code.length !== 6}>{busy ? "Verifying…" : "Verify and continue →"}</button></form>}
        {message && <div className="login-message">{message}{demoCode && <div className="demo-code-box"><small>LOCAL DEMO CODE · NOT EMAILED</small><b>{demoCode}</b></div>}</div>}
        {error && <div className="notice error login-error"><span className="notice-icon">!</span><span>{error}</span></div>}
        <div className="login-rule"><b>Identity boundary</b><span>This demo does not ask for or store college passwords. The locally displayed OTP simulates delivery only; production must use the college Microsoft Entra tenant and MFA.</span></div>
        <div className="demo-account-list"><div className="mini-label">Seeded demo accounts</div>{DEMO_IDENTITIES.map(([account, label]) => <button type="button" key={account} onClick={() => { setEmail(account); setRequested(false); setCode(""); setDemoCode(""); setError(""); }}><span>{label}</span><b>{account}</b></button>)}</div>
      </div>
      <div className="login-footnote">If your account is not listed, ask the demo System Administrator to add and activate it.</div>
    </section>
  </main>;
}
