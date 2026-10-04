import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";

const blank = { username: "", password: "", first_name: "", last_name: "" };

export default function Teachers() {
  const [x, setX] = useState(null), [f, setF] = useState(blank), [a, setA] = useState({ teacher: "", subject: "", stream: "" }), [msg, setMsg] = useState("");
  const load = async () => {
    const [tc, sj, sm, cl, as] = await Promise.all(["teachers", "subjects", "streams", "class-levels", "teacher-assignments"].map((p) => list("/api/" + p + "/")));
    const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name || "") + " " + s.name;
    setX({ tc, sj, sm: sm.map((s) => ({ ...s, label: lab(s) })), as });
  };
  useEffect(() => { load(); }, []);
  if (!x) return <p>Loading teachers...</p>;
  const post = async (path, body, ok) => { const r = await api(path, "POST", body), j = await r.json(); setMsg(r.ok ? ok : "Failed: " + (j.detail || JSON.stringify(j))); load(); return r.ok; };
  const nm = (arr, id) => arr.find((z) => z.id === id) || {};
  const toggle = async (t) => {
    if (t.is_active && !window.confirm("Deactivate " + t.name + "? They will not be able to log in.")) return;
    const r = await api("/api/teachers/" + t.id + "/", "PATCH", { is_active: !t.is_active });
    setMsg(r.ok ? (t.is_active ? "Deactivated " : "Activated ") + t.name : "Failed to update " + t.name);
    load();
  };
  const reset = async (t) => {
    const pw = window.prompt("New password for " + t.username + " (they will be signed out everywhere):");
    if (!pw) return;
    const r = await api("/api/teachers/" + t.id + "/reset-password/", "POST", { password: pw }), j = await r.json().catch(() => ({}));
    setMsg(r.ok ? "Password reset for " + t.username : "Failed: " + (j.detail || JSON.stringify(j)));
  };
  const sel = (k, ph, opts) => <select value={a[k]} onChange={(e) => setA({ ...a, [k]: e.target.value })}><option value="">{ph}</option>{opts.map((o) => <option key={o.id} value={o.id}>{o.label || o.name}</option>)}</select>;
  return (<div><h3>Teachers</h3>
    {x.tc.length === 0 && <p>No teachers yet</p>}
    {x.tc.map((t) => <p key={t.id}>{t.name} ({t.username}{t.is_active ? "" : ", inactive"}) <button className="ghost" onClick={() => toggle(t)}>{t.is_active ? "Deactivate" : "Activate"}</button> <button className="ghost" onClick={() => reset(t)}>Reset password</button></p>)}
    {Object.keys(blank).map((k) => <input key={k} type={k === "password" ? "password" : "text"} placeholder={k.replace("_", " ")} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
    <button disabled={!f.username || !f.password} onClick={async () => { if (await post("/api/teachers/", f, "Teacher created")) setF(blank); }}>Add teacher</button>
    <h4>Assign to class</h4>
    {sel("teacher", "Teacher", x.tc)}{sel("subject", "Subject", x.sj)}{sel("stream", "Class / stream", x.sm)}
    <button disabled={!a.teacher || !a.subject || !a.stream} onClick={() => post("/api/teacher-assignments/", a, "Assigned")}>Assign</button>
    {x.as.map((s) => <p key={s.id}>{nm(x.tc, s.teacher).name} - {nm(x.sj, s.subject).name} - {nm(x.sm, s.stream).label}</p>)}<p>{msg}</p></div>);
}
