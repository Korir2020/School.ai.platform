import { useState, useEffect } from "react";
import { api } from "./api";

const list = async (p) => { const r = await api(p + "?page_size=200"); return r.ok ? (await r.json()).results : []; };

export default function Setup() {
  const [x, setX] = useState(null), [lvl, setLvl] = useState(""), [sn, setSn] = useState(""), [bn, setBn] = useState(""), [bc, setBc] = useState(""), [msg, setMsg] = useState("");
  const load = async () => {
    const [sm, sj, cl, cu] = await Promise.all(["streams", "subjects", "class-levels", "curriculums"].map((p) => list("/api/" + p + "/")));
    const lab = (c) => ((cu.find((u) => u.id === c.curriculum) || {}).code || "") + " " + (c.name || "");
    setX({ sm: sm.map((s) => ({ ...s, label: lab(cl.find((c) => c.id === s.class_level) || {}) + " " + s.name })), sj, cl: cl.map((c) => ({ id: c.id, label: lab(c) })) });
  };
  useEffect(() => { load(); }, []);
  if (!x) return <p>Loading setup...</p>;
  const post = async (path, body) => { const r = await api(path, "POST", body); setMsg(r.ok ? "Saved" : "Failed: " + JSON.stringify(await r.json())); load(); };
  return (<div><h3>Classes and subjects</h3>
    <p>Streams: {x.sm.map((s) => s.label).join(", ") || "none"}</p>
    <select value={lvl} onChange={(e) => setLvl(e.target.value)}><option value="">Class level</option>{x.cl.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
    <input placeholder="Stream name" value={sn} onChange={(e) => setSn(e.target.value)} />
    <button disabled={!lvl || !sn} onClick={() => { post("/api/streams/", { class_level: lvl, name: sn, is_active: true }); setSn(""); }}>Add stream</button>
    <p>Subjects: {x.sj.map((s) => s.name).join(", ") || "none"}</p>
    <input placeholder="Subject name" value={bn} onChange={(e) => setBn(e.target.value)} /> <input placeholder="Code" value={bc} onChange={(e) => setBc(e.target.value)} />
    <button disabled={!bn || !bc} onClick={() => { post("/api/subjects/", { name: bn, code: bc, is_active: true }); setBn(""); setBc(""); }}>Add subject</button><p>{msg}</p></div>);
}
