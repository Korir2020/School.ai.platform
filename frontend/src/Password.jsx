import { useState } from "react";
import { api } from "./api";

export default function Password() {
  const [o, setO] = useState(""), [n, setN] = useState(""), [c, setC] = useState(""), [msg, setMsg] = useState(""), [open, setOpen] = useState(false);
  const go = async () => {
    const r = await api("/api/auth/change-password/", "POST", { old_password: o, new_password: n });
    const e = await r.json().catch(() => ({}));
    setMsg(r.ok ? "Password changed" : "Failed: " + (e.detail || "try again"));
    if (r.ok) { setO(""); setN(""); setC(""); setOpen(false); }
  };
  if (!open) return (<div><button className="ghost" onClick={() => setOpen(true)}>Change password</button><p>{msg}</p></div>);
  return (<div><h3>Change password</h3>
    <input type="password" placeholder="Current password" value={o} onChange={(e) => setO(e.target.value)} />
    <input type="password" placeholder="New password" value={n} onChange={(e) => setN(e.target.value)} />
    <input type="password" placeholder="Repeat new password" value={c} onChange={(e) => setC(e.target.value)} />
    {n && c && n !== c && <p className="err">Passwords do not match</p>}
    <button disabled={!o || !n || n !== c} onClick={go}>Change password</button><button className="ghost" onClick={() => setOpen(false)}>Cancel</button><p>{msg}</p></div>);
}
