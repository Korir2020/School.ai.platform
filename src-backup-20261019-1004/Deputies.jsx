import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Modal, ConfirmDialog, Card } from "./ui";
import { DataTable, Loading, ErrorState } from "./ui";

const blank = { username: "", password: "", first_name: "", last_name: "" };

export default function Deputies() {
  const toast = useToast();
  const [ds, setDs] = useState(null), [bad, setBad] = useState(false);
  const [f, setF] = useState(blank), [busy, setBusy] = useState(false);
  const [rm, setRm] = useState(null), [rp, setRp] = useState(null);
  const [pw, setPw] = useState("");
  const load = async () => {
    try {
      const r = await api("/api/deputies/");
      if (!r.ok) throw new Error("load");
      const j = await r.json();
      setDs(Array.isArray(j) ? j : j.results || []);
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const fail = async (r) => {
    const j = await r.json().catch(() => ({}));
    toast("Failed: " + (j.detail || JSON.stringify(j)), "err");
  };
  const add = async () => {
    setBusy(true);
    const r = await api("/api/deputies/", "POST", f);
    setBusy(false);
    if (r.ok) { toast("Deputy appointed", "ok"); setF(blank); load(); }
    else await fail(r);
  };
  const remove = async (d) => {
    setRm(null);
    const r = await api("/api/deputies/" + d.id + "/", "DELETE");
    toast(r.ok ? "Deputy removed" : "Failed to remove", r.ok ? "ok" : "err");
    load();
  };
  const reset = async () => {
    const p = "/api/admin-accounts/" + rp.id + "/reset-password/";
    const r = await api(p, "POST", { password: pw });
    if (r.ok) {
      toast("Password reset for " + rp.username, "ok"); setRp(null); setPw("");
    } else await fail(r);
  };
  if (bad) return <ErrorState text="Could not load deputies." onRetry={load} />;
  if (!ds) return <Loading />;
  const cols = [
    { label: "Name", key: "name", sort: true },
    { label: "Username", key: "username", sort: true },
    { label: "Actions", render: (d) => (<>
      <Button kind="ghost" size="sm" onClick={() => setRp(d)}>Reset password</Button>
      <Button kind="ghost" size="sm" onClick={() => setRm(d)}>Remove</Button></>) },
  ];
  const close = () => { setRp(null); setPw(""); };
  return (
    <div>
      <h2>Deputies</h2>
      <p>A deputy can do everything you can, except appoint or remove deputies.</p>
      <Card>
        <DataTable cols={cols} rows={ds} search="Search deputies"
          empty="No deputies yet" />
      </Card>
      <Card title="Appoint deputy">
        {Object.keys(blank).map((k) => (
          <Input key={k} id={"dp-" + k} label={k.replace("_", " ")}
            type={k === "password" ? "password" : "text"} value={f[k]}
            onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        ))}
        <Button kind="teal" busy={busy} onClick={add}
          disabled={!f.username || !f.password}>Appoint deputy</Button>
      </Card>
      {rm && <ConfirmDialog danger title={"Remove " + rm.name + "?"}
        text="They will no longer be able to log in." confirm="Remove"
        onYes={() => remove(rm)} onNo={() => setRm(null)} />}
      {rp && <Modal title={"Reset password: " + rp.username} onClose={close}
        actions={<>
          <Button kind="secondary" onClick={close}>Cancel</Button>
          <Button kind="teal" disabled={!pw} onClick={reset}>Reset</Button></>}>
        <Input id="dp-pw" label="New password" type="password" value={pw}
          onChange={(e) => setPw(e.target.value)} />
        <p>They will be signed out everywhere.</p>
      </Modal>}
    </div>
  );
}
