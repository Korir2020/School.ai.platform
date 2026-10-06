import { useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Button, Input, Loading } from "./ui";
import "./pub.css";

export default function JoinStatus({ me, out }) {
  const [s, setS] = useState(null), [code, setCode] = useState("");
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [n, setN] = useState(0);
  useEffect(() => { (async () => {
    const r = await api("/api/join/my-request/");
    setS(r.ok ? await r.json() : { status: "error" });
  })(); }, [n]);
  const finish = async () => {
    setErr(""); setBusy(true);
    const body = { code: code.trim().toUpperCase() };
    const r = await api("/api/join/complete/", "POST", body);
    if (r.ok) { window.location.reload(); return; }
    const d = await r.json().catch(() => ({}));
    setErr(d.detail || "Could not complete joining."); setBusy(false);
  };
  const st = s && s.status;
  const body = !s ? <Loading />
    : st === "approved" ? (<><Alert kind="ok">{s.message}</Alert>
      <Input label="Invitation code" value={code} autoCapitalize="characters"
        style={{ letterSpacing: "2px" }}
        onChange={(e) => setCode(e.target.value)} />
      {err && <Alert kind="err">{err}</Alert>}
      <Button kind="teal" busy={busy} onClick={finish}>Join school</Button></>)
    : st === "pending" ? (<><Alert kind="warn">{s.message}</Alert>
      <Button kind="secondary" onClick={() => setN(n + 1)}>Check again</Button></>)
    : st === "joined" ? (<Alert kind="ok">{s.message} Your tasks will appear
      here when your school sets them up.</Alert>)
    : <Alert kind={st === "rejected" ? "err" : "info"}>{s.message ||
      "Your account is not linked to a school yet."}</Alert>;
  return (<div className="mu-pub"><div className="mu-pub-in">
    <div className="mu-pub-card"><h2>Hello, {me.username}</h2>
      <div className="mu-pub-form">{body}</div>
      <Button kind="ghost" onClick={out}>Sign out</Button></div></div></div>);
}
