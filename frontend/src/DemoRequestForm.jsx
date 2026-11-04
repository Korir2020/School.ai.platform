import { useState } from "react";

const BASE = import.meta.env.VITE_API_URL || "";
const EMPTY = { full_name: "", email: "", phone: "", school_name: "", role: "", learners: "", county: "", message: "", website: "" };
const ROLES = [["school_admin", "School administrator"], ["headteacher", "Headteacher / Principal"], ["teacher", "Teacher"], ["bursar", "Bursar / Finance"], ["other", "Other"]];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function check(f) {
  const e = {};
  if (f.full_name.trim().length < 2) e.full_name = "Enter your full name.";
  if (!EMAIL.test(f.email.trim())) e.email = "Enter a valid email address, for example name@school.ac.ke.";
  if (f.phone && !/^[0-9+\-() ]{7,30}$/.test(f.phone.trim())) e.phone = "Use digits, spaces and + only.";
  if (f.school_name.trim().length < 2) e.school_name = "Enter your school's name.";
  if (!f.role) e.role = "Choose your role.";
  if (f.learners && !(Number(f.learners) >= 1 && Number(f.learners) <= 100000)) e.learners = "Enter a number between 1 and 100000.";
  if (f.message.length > 1000) e.message = "Keep the message under 1000 characters.";
  return e;
}

export default function DemoRequestForm() {
  const [f, setF] = useState(EMPTY), [err, setErr] = useState({}), [st, setSt] = useState("idle"), [msg, setMsg] = useState("");
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); if (err[k]) setErr({ ...err, [k]: undefined }); };

  const submit = async (e) => {
    e.preventDefault();
    const v = check(f);
    setErr(v);
    if (Object.keys(v).length) {
      const first = document.getElementById("dr-" + Object.keys(v)[0]);
      if (first) first.focus();
      return;
    }
    setSt("busy"); setMsg("");
    try {
      const body = { ...f, learners: f.learners ? Number(f.learners) : null };
      const r = await fetch(`${BASE}/api/demo-requests/`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (r.status === 429) { setSt("error"); setMsg("Too many requests from this connection. Please try again later."); return; }
      if (!r.ok) {
        const fe = {};
        Object.entries(j).forEach(([k, val]) => { fe[k] = Array.isArray(val) ? val[0] : String(val); });
        setErr(fe); setSt("error"); setMsg(j.detail || "Please check the highlighted fields."); return;
      }
      setSt("done"); setMsg(j.detail || "Thank you. We will be in touch."); setF(EMPTY);
    } catch {
      setSt("error"); setMsg("We could not reach Marian. Check your connection and try again.");
    }
  };

  if (st === "done") return (
    <div className="mw-form mw-done" role="status">
      <h3>Request received</h3>
      <p>{msg}</p>
      <button type="button" className="mw-btn ghost" onClick={() => setSt("idle")}>Send another request</button>
    </div>
  );

  const fld = (k, label, input, hint) => (
    <div className={"mw-fld" + (err[k] ? " bad" : "")}>
      <label htmlFor={"dr-" + k}>{label}</label>
      {input}
      {err[k] ? <span className="mw-err" id={"dr-" + k + "-e"}>{err[k]}</span> : hint && <span className="mw-hint">{hint}</span>}
    </div>
  );
  const ip = (k, extra = {}) => ({ id: "dr-" + k, name: k, value: f[k], onChange: set(k), "aria-invalid": !!err[k], "aria-describedby": err[k] ? "dr-" + k + "-e" : undefined, disabled: st === "busy", ...extra });

  return (
    <form className="mw-form" onSubmit={submit} noValidate aria-label="Request a demo">
      <div className="mw-row">
        {fld("full_name", "Full name *", <input {...ip("full_name", { autoComplete: "name", maxLength: 120 })} />)}
        {fld("email", "Work email *", <input {...ip("email", { type: "email", autoComplete: "email", maxLength: 255, inputMode: "email" })} />)}
      </div>
      <div className="mw-row">
        {fld("phone", "Phone", <input {...ip("phone", { type: "tel", autoComplete: "tel", maxLength: 30 })} />)}
        {fld("role", "Your role *", <select {...ip("role")}><option value="">Choose…</option>{ROLES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>)}
      </div>
      {fld("school_name", "School name *", <input {...ip("school_name", { autoComplete: "organization", maxLength: 200 })} />)}
      <div className="mw-row">
        {fld("county", "County", <input {...ip("county", { maxLength: 100 })} />)}
        {fld("learners", "Number of learners", <input {...ip("learners", { type: "number", min: 1, inputMode: "numeric" })} />)}
      </div>
      {fld("message", "What would you like to see?", <textarea rows={3} {...ip("message", { maxLength: 1000 })} />, "Optional")}
      <div className="mw-hp" aria-hidden="true"><label htmlFor="dr-website">Website</label><input {...ip("website", { tabIndex: -1, autoComplete: "off" })} /></div>
      {st === "error" && msg && <p className="mw-alert" role="alert">{msg}</p>}
      <button type="submit" className="mw-btn lg full" disabled={st === "busy"} aria-busy={st === "busy"}>
        {st === "busy" ? <><span className="mw-spin" aria-hidden="true" />Sending…</> : "Request a demo"}
      </button>
    </form>
  );
}
