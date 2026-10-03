import { useState, useEffect } from "react";
import { api } from "./api";

export default function Analytics({ d }) {
  const [s, setS] = useState(null);
  useEffect(() => { (async () => { const r = await api("/api/analytics/term-summary/" + d.active_term.id + "/"); if (r.ok) setS(await r.json()); })(); }, []);
  if (!s) return <p className="sub">Loading analytics...</p>;
  return (<div><h3>Term summary: {s.term} {s.academic_year}</h3>
    {s.pending_marks > 0 && <p className="err">{s.pending_marks} marks not yet approved are excluded.</p>}
    {s.subjects.length === 0 && <p>No approved marks yet.</p>}
    {s.subjects.map((x) => (<div key={x.subject} style={{ margin: "12px 0" }}>
      <b>{x.subject}</b> <span className="sub">avg {x.average}% · high {x.highest} · low {x.lowest} · {x.entries} entries</span>
      <div style={{ height: 10, borderRadius: 6, background: "#06153a", overflow: "hidden" }}><div style={{ width: Math.min(x.average, 100) + "%", height: "100%", background: "linear-gradient(90deg,#2563EB,#22C55E)" }} /></div></div>))}</div>);
}
