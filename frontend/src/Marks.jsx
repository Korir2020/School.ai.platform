import { useState, useEffect } from "react";
import { api } from "./api";

const list = async (p) => { const r = await api(p + "?page_size=200"); return r.ok ? (await r.json()).results : []; };

export default function Marks({ d }) {
  const [data, setData] = useState(null), [sel, setSel] = useState(""), [vals, setVals] = useState({}), [msg, setMsg] = useState("");
  const load = async () => {
    const names = ["teacher-assignments", "enrollments", "students", "terms", "performance"];
    const [ta, en, st, tm, pf] = await Promise.all(names.map((x) => list("/api/" + x + "/")));
    setData({ ta, en, st, tm, pf });
  };
  useEffect(() => { load(); }, []);
  if (!data) return <p>Loading marks...</p>;
  if (!d.active_term) return <p>No active term.</p>;
  const term = data.tm.find((t) => t.id === d.active_term.id);
  const a = data.ta.find((x) => String(x.id) === sel);
  const rows = a ? data.en.filter((e) => e.stream === a.stream && e.is_active) : [];
  const nameOf = (id) => { const s = data.st.find((x) => x.id === id); return s ? s.first_name + " " + s.last_name : "Student " + id; };
  const old = (sid) => a && data.pf.find((p) => p.student === sid && p.subject === a.subject && p.term === term.id && p.paper_number === 1 && p.assessment_type === "end");
  const save = async () => {
    let ok = 0, bad = 0;
    for (const e of rows) {
      const m = vals[e.student];
      if (m === undefined || m === "" || old(e.student)) continue;
      const r = await api("/api/performance/", "POST", { student: e.student, subject: a.subject, academic_year: term.academic_year, term: term.id, assessment_type: "end", paper_number: 1, marks: m });
      if (r.ok) ok++; else bad++;
    }
    setMsg("Saved " + ok + ", failed " + bad); setVals({}); load();
  };
  const submit = async (p) => { await api("/api/performance/" + p.id + "/submit/", "POST"); load(); };
  return (<div><h3>Enter marks (end-term, Paper 1)</h3>
    <select value={sel} onChange={(e) => setSel(e.target.value)}><option value="">Choose class and subject</option>
      {d.assignments.map((x) => <option key={x.id} value={x.id}>{x.subject} - {x.class_level} {x.stream}</option>)}</select>
    {rows.map((e) => { const o = old(e.student); return (
      <p key={e.id}>{nameOf(e.student)}: {o
        ? <span>{o.marks} ({o.status}) {o.status === "draft" && <button onClick={() => submit(o)}>Submit</button>}</span>
        : <input type="number" min="0" max="100" value={vals[e.student] ?? ""} onChange={(ev) => setVals({ ...vals, [e.student]: ev.target.value })} />}</p>); })}
    {a && <button onClick={save}>Save marks</button>}<p>{msg}</p></div>);
}
