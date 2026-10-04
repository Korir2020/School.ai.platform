import { useState, useEffect } from "react";
import { api } from "./api";

export default function Accounts() {
  const [rows, setRows] = useState(null), [msg, setMsg] = useState("");
  useEffect(() => { (async () => {
    const r = await api("/api/admin-accounts/");
    setRows(r.ok ? (await r.json()).results : []);
  })(); }, []);
  if (!rows) return <p>Loading administrators...</p>;
  const reset = async (p) => {
    const pw = window.prompt("New password for " + p.username + " (they will be signed out everywhere):");
    if (!pw) return;
    const r = await api("/api/admin-accounts/" + p.id + "/reset-password/", "POST", { password: pw }), j = await r.json().catch(() => ({}));
    setMsg(r.ok ? "Password reset for " + p.username : "Failed: " + (j.detail || JSON.stringify(j)));
  };
  return (<div><h3>Administrators</h3>
    <p className="sub">Forgotten password? Reset it here and give the person the new one.</p>
    {rows.length === 0 && <p>No administrators yet</p>}
    {rows.map((p) => <p key={p.id}>{p.school}: {p.username} ({p.is_deputy ? "deputy" : "administrator"}{p.is_active ? "" : ", inactive"}) <button className="ghost" onClick={() => reset(p)}>Reset password</button></p>)}
    <p>{msg}</p></div>);
}
