import { useState, useEffect } from "react";
import { api } from "./api";

export default function ReportCards({ d }) {
  const [st, setSt] = useState([]), [rc, setRc] = useState(null);
  useEffect(() => { (async () => { const r = await api("/api/students/?page_size=200"); if (r.ok) setSt((await r.json()).results); })(); }, []);
  const open = async (id) => { if (!id) return setRc(null); const r = await api("/api/report-card/" + id + "/" + d.active_term.id + "/"); setRc(r.ok ? await r.json() : null); };
  return (<div><h3>Report cards</h3>
    <select onChange={(e) => open(e.target.value)}><option value="">Choose student</option>{st.map((s) => <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>)}</select>
    {rc && <div><h4>{rc.student.name} (Adm {rc.student.admission_number})</h4><p>{rc.term}, {rc.academic_year}</p>
      {rc.subjects.map((s) => <p key={s.subject}>{s.subject}: {s.average}%</p>)}
      <p><b>Overall: {rc.overall_average}%</b></p>
      {rc.published_results.map((r) => <p key={r.exam}>{r.exam}: class rank {r.class_rank}, stream rank {r.stream_rank}</p>)}
      {rc.pending_marks > 0 && <p>{rc.pending_marks} marks still pending approval</p>}
      <button onClick={() => window.print()}>Print</button></div>}</div>);
}
