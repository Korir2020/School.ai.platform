import { useState, useEffect } from "react";
import { api } from "./api";

const list = async (p) => { const r = await api(p + "?page_size=200"); return r.ok ? (await r.json()).results : []; };
const empty = { name: "", start_date: "", end_date: "" };

export default function Terms() {
  const [x, setX] = useState(null), [y, setY] = useState(empty), [t, setT] = useState({ ...empty, academic_year: "" }), [msg, setMsg] = useState("");
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
  const yname = (id) => (x.yr.find((a) => a.id === id) || {}).name || "";
  return (<div><h3>Academic years and terms</h3>
    <p className="sub">The active term with the latest start date is the one the app uses.</p>
    {x.yr.map((a) => <p key={a.id}>{a.name}: {a.start_date} to {a.end_date}</p>)}
    <input placeholder="Year name, e.g. 2026" value={y.name} onChange={(e) => setY({ ...y, name: e.target.value })} />
    <label className="sub">Starts</label><input type="date" value={y.start_date} onChange={(e) => setY({ ...y, start_date: e.target.value })} />
    <label className="sub">Ends</label><input type="date" value={y.end_date} onChange={(e) => setY({ ...y, end_date: e.target.value })} />
    <button disabled={!y.name || !y.start_date || !y.end_date} onClick={async () => { if (await send("/api/academic-years/", "POST", { ...y, is_active: true })) setY(empty); }}>Add year</button>
    <h4>Terms</h4>
    {x.tm.map((m) => <p key={m.id}>{yname(m.academic_year)} {m.name}: {m.start_date} to {m.end_date} {m.is_active ? "(active)" : "(off)"}
      <button className="ghost" onClick={() => send("/api/terms/" + m.id + "/", "PATCH", { is_active: !m.is_active })}>{m.is_active ? "Turn off" : "Turn on"}</button></p>)}
    <select value={t.academic_year} onChange={(e) => setT({ ...t, academic_year: e.target.value })}><option value="">Academic year</option>{x.yr.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
    <input placeholder="Term name, e.g. Term 1" value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
    <label className="sub">Starts</label><input type="date" value={t.start_date} onChange={(e) => setT({ ...t, start_date: e.target.value })} />
    <label className="sub">Ends</label><input type="date" value={t.end_date} onChange={(e) => setT({ ...t, end_date: e.target.value })} />
    <button disabled={!t.academic_year || !t.name || !t.start_date || !t.end_date} onClick={async () => { if (await send("/api/terms/", "POST", { ...t, is_active: true })) setT({ ...empty, academic_year: t.academic_year }); }}>Add term</button>
    <p>{msg}</p></div>);
}
