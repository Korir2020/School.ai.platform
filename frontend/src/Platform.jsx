import { useState } from "react";
import { api } from "./api";

const blank = { name: "", code: "", admin_username: "", admin_password: "", admin_first_name: "", admin_last_name: "" };

export default function Platform({ d }) {
  const [f, setF] = useState(blank), [msg, setMsg] = useState(""), [made, setMade] = useState([]);
  const add = async () => {
    const r = await api("/api/schools/", "POST", f), j = await r.json().catch(() => ({}));
    setMsg(r.ok ? "School created: " + j.name : "Failed: " + (j.detail || JSON.stringify(j)));
    if (r.ok) { setMade([...made, j]); setF(blank); }
  };
  return (<div><h3>Schools</h3>
    <p className="sub">Create a school and its first administrator, then give that person the login.</p>
    {d.schools.map((s) => <p key={s.id}>{s.name} ({s.students} students, {s.teachers} teachers)</p>)}
    {made.map((m) => <p key={"n" + m.id}>{m.name} (new, admin {m.admin_username})</p>)}
    {Object.keys(blank).map((k) => <input key={k} type={k === "admin_password" ? "password" : "text"} placeholder={k.replace(/_/g, " ")} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
    <button disabled={!f.name || !f.code || !f.admin_username || !f.admin_password} onClick={add}>Create school</button><p>{msg}</p></div>);
}
