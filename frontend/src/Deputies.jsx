import { useState, useEffect } from "react";
import { api } from "./api";

const blank = { username: "", password: "", first_name: "", last_name: "" };

export default function Deputies() {
  const [ds, setDs] = useState(null), [f, setF] = useState(blank), [msg, setMsg] = useState("");
  const load = async () => { const r = await api("/api/deputies/"); setDs(r.ok ? (await r.json()).results : []); };
  useEffect(() => { load(); }, []);
  if (!ds) return <p>Loading deputies...</p>;
  const add = async () => {
    const r = await api("/api/deputies/", "POST", f), j = await r.json().catch(() => ({}));
    setMsg(r.ok ? "Deputy appointed" : "Failed: " + (j.detail || JSON.stringify(j)));
    if (r.ok) setF(blank);
    load();
  };
  const remove = async (d) => {
    if (!window.confirm("Remove " + d.name + " as deputy? They will no longer be able to log in.")) return;
    const r = await api("/api/deputies/" + d.id + "/", "DELETE");
    setMsg(r.ok ? "Deputy removed" : "Failed to remove");
    load();
  };
  return (<div><h3>Deputies</h3>
    <p className="sub">A deputy can do everything you can, except appoint or remove deputies.</p>
    {ds.length === 0 && <p>No deputies yet</p>}
    {ds.map((d) => <p key={d.id}>{d.name} ({d.username}) <button className="ghost" onClick={() => remove(d)}>Remove</button></p>)}
    {Object.keys(blank).map((k) => <input key={k} type={k === "password" ? "password" : "text"} placeholder={k.replace("_", " ")} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
    <button disabled={!f.username || !f.password} onClick={add}>Appoint deputy</button><p>{msg}</p></div>);
}
