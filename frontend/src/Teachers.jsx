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
  const sel = (k, ph, opts) => <select value={a[k]} onChange={(e) => setA({ ...a, [k]: e.target.value })}><option value="">{ph}</option>{opts.map((o) => <option key={o.id} value={o.id}>{o.label || o.name}</option>)}</select>;
  return (<div><h3>Teachers</h3>
    <p>{x.tc.map((t) => t.name + " (" + t.username + ")").join(", ") || "No teachers yet"}</p>
    {Object.keys(blank).map((k) => <input key={k} type={k === "password" ? "password" : "text"} placeholder={k.replace("_", " ")} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
    <button disabled={!f.username || !f.password} onClick={async () => { if (await post("/api/teachers/", f, "Teacher created")) setF(blank); }}>Add teacher</button>
    <h4>Assign to class</h4>
    {sel("teacher", "Teacher", x.tc)}{sel("subject", "Subject", x.sj)}{sel("stream", "Class / stream", x.sm)}
    <button disabled={!a.teacher || !a.subject || !a.stream} onClick={() => post("/api/teacher-assignments/", a, "Assigned")}>Assign</button>
    {x.as.map((s) => <p key={s.id}>{nm(x.tc, s.teacher).name} - {nm(x.sj, s.subject).name} - {nm(x.sm, s.stream).label}</p>)}<p>{msg}</p></div>);
}
