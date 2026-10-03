import { useState, useEffect } from "react";
import { api } from "./api";

const list = async (p) => { const r = await api(p + "?page_size=200"); return r.ok ? (await r.json()).results : []; };

export default function Students({ d }) {
  const [x, setX] = useState(null), [f, setF] = useState({ first: "", last: "", adm: "", stream: "" }), [msg, setMsg] = useState("");
  const load = async () => {
    const [sm, cl, tm, st] = await Promise.all(["streams", "class-levels", "terms", "students"].map((p) => list("/api/" + p + "/")));
    const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name || "") + " " + s.name;
    setX({ sm: sm.map((s) => ({ ...s, label: lab(s) })), year: (tm.find((t) => t.id === d.active_term.id) || {}).academic_year, count: st.length });
  };
  useEffect(() => { load(); }, []);
  if (!x) return <p>Loading...</p>;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const add = async () => {
    const r = await api("/api/students/", "POST", { first_name: f.first, last_name: f.last, admission_number: f.adm }), s = await r.json();
    if (!r.ok) return setMsg("Failed: " + JSON.stringify(s));
    const q = x.sm.find((z) => String(z.id) === f.stream);
    const e = await api("/api/enrollments/", "POST", { student: s.id, academic_year: x.year, class_level: q.class_level, stream: q.id, is_active: true });
    setMsg(e.ok ? "Added " + f.first : "Student saved but enrolment failed: " + JSON.stringify(await e.json()));
    setF({ first: "", last: "", adm: "", stream: f.stream }); load();
  };
  return (<div><h3>Add student ({x.count} total)</h3>
    <input placeholder="First name" value={f.first} onChange={set("first")} /> <input placeholder="Last name" value={f.last} onChange={set("last")} />
    <input placeholder="Admission number" value={f.adm} onChange={set("adm")} />
    <select value={f.stream} onChange={set("stream")}><option value="">Class / stream</option>{x.sm.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select>
    <button onClick={add} disabled={!f.first || !f.last || !f.adm || !f.stream}>Add student</button><p>{msg}</p></div>);
}
