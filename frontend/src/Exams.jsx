import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";


export default function Exams({ d }) {
  const [x, setX] = useState(null), [name, setName] = useState(""), [lvl, setLvl] = useState(""), [msg, setMsg] = useState(""), [res, setRes] = useState(null);
  const load = async () => {
    const [ex, en, cl] = await Promise.all(["exams", "enrollments", "class-levels"].map((p) => list("/api/" + p + "/")));
    const ids = [...new Set(en.map((e) => e.class_level))];
    setX({ ex, levels: cl.filter((c) => ids.includes(c.id)) });
  };
  useEffect(() => { load(); }, []);
  if (!x) return <p>Loading exams...</p>;
  const create = async () => {
    const r = await api("/api/exams/", "POST", { name, term: d.active_term.id, assessment_type: "end", class_level: lvl });
    setMsg(r.ok ? "Exam created" : "Failed: " + JSON.stringify(await r.json())); setName(""); load();
  };
  const publish = async (e) => {
    const r = await api("/api/exams/" + e.id + "/publish/", "POST"), j = await r.json();
    setMsg(r.ok ? "Published" : (j.detail || "Failed") + (j.count ? " (" + j.count + " problems)" : "")); load();
  };
  const view = async (e) => { const r = await api("/api/exams/" + e.id + "/results/"); setRes(r.ok ? await r.json() : null); };
  return (<div><h3>Exams</h3>
    <input placeholder="Exam name" value={name} onChange={(e) => setName(e.target.value)} />
    <select value={lvl} onChange={(e) => setLvl(e.target.value)}><option value="">Class level</option>{x.levels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
    <button onClick={create} disabled={!name || !lvl}>Create exam</button>
    {x.ex.map((e) => (<p key={e.id}>{e.name} ({e.status}) {e.status === "draft" ? <button onClick={() => publish(e)}>Publish</button> : <button onClick={() => view(e)}>Results</button>}</p>))}
    <p>{msg}</p>
    {res && <div><b>{res.exam}</b>{res.results.map((r) => <p key={r.student_id}>#{r.class_rank} {r.name}: {r.overall_average}% (stream rank {r.stream_rank})</p>)}</div>}</div>);
}
