import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Modal, Card, Badge } from "./ui";
import { DataTable, Loading, ErrorState } from "./ui";

export default function Accounts() {
  const toast = useToast();
  const [rows, setRows] = useState(null), [bad, setBad] = useState(false);
  const [rp, setRp] = useState(null), [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const r = await api("/api/admin-accounts/");
      if (!r.ok) throw new Error("load");
      const j = await r.json();
      setRows(Array.isArray(j) ? j : j.results || []);
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const close = () => { setRp(null); setPw(""); };
  const reset = async () => {
    setBusy(true);
    const p = "/api/admin-accounts/" + rp.id + "/reset-password/";
    const r = await api(p, "POST", { password: pw });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) { toast("Password reset for " + rp.username, "ok"); close(); }
    else toast("Failed: " + (j.detail || JSON.stringify(j)), "err");
  };
  if (bad) return <ErrorState text="Could not load administrators." onRetry={load} />;
  if (!rows) return <Loading />;
  const role = (p) => (p.is_deputy ? "Deputy" : "Administrator");
  const state = (p) => (p.is_active ? "Active" : "Inactive");
  const cols = [
    { label: "School", key: "school", sort: true },
    { label: "Username", key: "username", sort: true },
    { label: "Role", get: role, sort: true },
    { label: "Status", get: state, sort: true, render: (p) => (
      <Badge kind={p.is_active ? "ok" : "warn"}>{state(p)}</Badge>) },
    { label: "Actions", render: (p) => (
      <Button kind="ghost" size="sm" onClick={() => setRp(p)}>Reset password</Button>) },
  ];
  return (
    <div>
      <h2>Administrators</h2>
      <p>Forgotten password? Reset it here and give the person the new one.</p>
      <Card>
        <DataTable cols={cols} rows={rows} search="Search administrators"
          empty="No administrators yet" />
      </Card>
      {rp && <Modal title={"Reset password: " + rp.username} onClose={close}
        actions={<>
          <Button kind="secondary" onClick={close}>Cancel</Button>
          <Button kind="teal" busy={busy} disabled={!pw} onClick={reset}>Reset</Button></>}>
        <Input id="ac-pw" label="New password" type="password" value={pw}
          onChange={(e) => setPw(e.target.value)} />
        <p>They will be signed out everywhere.</p>
      </Modal>}
    </div>
  );
}
