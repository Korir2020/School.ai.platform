import { useState } from "react";
import { api } from "./api";
import { Button, Card, Input, Alert } from "./ui";

export default function Password() {
  const [o, setO] = useState("");
  const [n, setN] = useState("");
  const [c, setC] = useState("");
  const [msg, setMsg] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const mismatch = n && c && n !== c;
  const reset = () => { setO(""); setN(""); setC(""); setOpen(false); };
  const go = async () => {
    setBusy(true);
    try {
      const body = { old_password: o, new_password: n };
      const r = await api("/api/auth/change-password/", "POST", body);
      const e = await r.json().catch(() => ({}));
      if (r.ok) {
        setMsg({ kind: "ok", text: "Password changed" });
        reset();
      } else {
        setMsg({ kind: "err", text: "Failed: " + (e.detail || "try again") });
      }
    } catch {
      setMsg({ kind: "err", text: "Network problem, try again" });
    }
    setBusy(false);
  };
  const note = msg && <Alert kind={msg.kind}>{msg.text}</Alert>;
  if (!open) {
    const show = () => { setMsg(null); setOpen(true); };
    return (<div><Button kind="ghost" onClick={show}>Change password</Button>{note}</div>);
  }
  return (
    <Card title="Change password">
      <Input label="Current password" type="password" value={o}
        autoComplete="current-password" onChange={(e) => setO(e.target.value)} />
      <Input label="New password" type="password" value={n}
        autoComplete="new-password" onChange={(e) => setN(e.target.value)} />
      <Input label="Repeat new password" type="password" value={c}
        autoComplete="new-password" onChange={(e) => setC(e.target.value)}
        error={mismatch ? "Passwords do not match" : undefined} />
      {note}
      <p>
        <Button busy={busy} disabled={!o || !n || n !== c || busy} onClick={go}>
          Change password
        </Button>{" "}
        <Button kind="ghost" onClick={reset}>Cancel</Button>
      </p>
    </Card>
  );
}
