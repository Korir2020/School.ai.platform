import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";

const empty = { name: "", start_date: "", end_date: "" };

export default function Terms() {
  const [x, setX] = useState(null), [y, setY] = useState(empty), [t, setT] = useState({ ...empty, academic_year: "" }), [msg, setMsg] = useState(""), [ed, setEd] = useState(null);
  const load = async () => {
    const [yr, tm] = await Promise.all(["academic-years", "terms"].map((p) => list("/api/" + p + "/")));
    setX({ yr, tm });
  };
  useEffect(() => { load(); }, []);
  if (!x) return <p>Loading years and terms...</p>;
  const send = async (path, method, body) => {
    const r = await api(path, method, body);
    if (r.ok) setMsg("Saved");
    else { const e = await r.json().catch(() => ({})); setMsg("Failed: " + (e.detail || JSON.stringify(e))); }
    load();
    return r.ok;
  };
  const editor = () => (<div>
    <input type="date" value={ed.start_date} onChange={(e) => setEd({ ...ed, start_date: e.target.value })} />
    <input type="date" value={ed.end_date} onChange={(e) => setEd({ ...ed, end_date: e.target.value })} />
    <button onClick={async () => { if (await send(ed.path, "PATCH", { start_date: ed.start_date, end_date: ed.end_date })) setEd(null); }}>Save dates</button>
    <button className="ghost" onClick={() => setEd(null)}>Cancel</button></div>);
  const yname = (id) => (x.yr.find((a) => a.id === id) || {}).name || "";
  return (<div><h3>Academic years and terms</h3>
    <p className="sub">The active term with the latest start date is the one the app uses.</p>
    {x.yr.map((a) => { const path = "/api/academic-years/" + a.id + "/"; return (<div key={a.id}><p>{a.name}: {a.start_date} to {a.end_date}
      <button className="ghost" onClick={() => setEd({ path, start_date: a.start_date, end_date: a.end_date })}>Edit dates</button></p>{ed && ed.path === path && editor()}</div>); })}
    <input placeholder="Year name, e.g. 2026" value={y.name} onChange={(e) => setY({ ...y, name: e.target.value })} />
    <label className="sub">Starts</label><input type="date" value={y.start_date} onChange={(e) => setY({ ...y, start_date: e.target.value })} />
    <label className="sub">Ends</label><input type="date" value={y.end_date} onChange={(e) => setY({ ...y, end_date: e.target.value })} />
    <button disabled={!y.name || !y.start_date || !y.end_date} onClick={async () => { if (await send("/api/academic-years/", "POST", { ...y, is_active: true })) setY(empty); }}>Add year</button>
    <h4>Terms</h4>
    {x.tm.map((m) => { const path = "/api/terms/" + m.id + "/"; return (<div key={m.id}><p>{yname(m.academic_year)} {m.name}: {m.start_date} to {m.end_date} {m.is_active ? "(active)" : "(off)"}
      <button className="ghost" onClick={() => send(path, "PATCH", { is_active: !m.is_active })}>{m.is_active ? "Turn off" : "Turn on"}</button>
      <button className="ghost" onClick={() => setEd({ path, start_date: m.start_date, end_date: m.end_date })}>Edit dates</button></p>{ed && ed.path === path && editor()}</div>); })}
    <select value={t.academic_year} onChange={(e) => setT({ ...t, academic_year: e.target.value })}><option value="">Academic year</option>{x.yr.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
    <input placeholder="Term name, e.g. Term 1" value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
    <label className="sub">Starts</label><input type="date" value={t.start_date} onChange={(e) => setT({ ...t, start_date: e.target.value })} />
    <label className="sub">Ends</label><input type="date" value={t.end_date} onChange={(e) => setT({ ...t, end_date: e.target.value })} />
    <button disabled={!t.academic_year || !t.name || !t.start_date || !t.end_date} onClick={async () => { if (await send("/api/terms/", "POST", { ...t, is_active: true })) setT({ ...empty, academic_year: t.academic_year }); }}>Add term</button>
    <p>{msg}</p></div>);
}
