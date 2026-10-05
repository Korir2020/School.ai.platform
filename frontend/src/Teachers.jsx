import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Modal, ConfirmDialog } from "./ui";
import { Card, Badge, DataTable, Loading, ErrorState } from "./ui";

const blank = { username: "", password: "", first_name: "", last_name: "" };
const none = { teacher: "", subject: "", stream: "" };
const paths = ["teachers", "subjects", "streams", "class-levels", "teacher-assignments"];

export default function Teachers() {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [f, setF] = useState(blank), [a, setA] = useState(none);
  const [ask, setAsk] = useState(null), [rp, setRp] = useState(null);
  const [pw, setPw] = useState(""), [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [tc, sj, sm, cl, asg] = await Promise.all(paths.map(get));
      const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name || "")
        + " " + s.name;
      setX({ tc, sj, sm: sm.map((s) => ({ ...s, label: lab(s) })), asg });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const nm = (arr, id) => arr.find((z) => z.id === id) || {};
  const post = async (path, body, ok) => {
    setBusy(true);
    const r = await api(path, "POST", body);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) { toast(ok, "ok"); load(); }
    else toast(j.detail || JSON.stringify(j), "err");
    return r.ok;
  };
  const setActive = async (t) => {
    const r = await api("/api/teachers/" + t.id + "/", "PATCH", { is_active: !t.is_active });
    const word = t.is_active ? "Deactivated " : "Activated ";
    toast(r.ok ? word + t.name : "Failed to update " + t.name, r.ok ? "ok" : "err");
    setAsk(null); load();
  };
  const reset = async () => {
    const p = "/api/teachers/" + rp.id + "/reset-password/";
    if (await post(p, { password: pw }, "Password reset for " + rp.username)) {
      setRp(null); setPw("");
    }
  };
  const sel = (k, label, opts) => (
    <Select label={label} id={"as-" + k} value={a[k]}
      onChange={(e) => setA({ ...a, [k]: e.target.value })}>
      <option value="">Select...</option>
      {opts.map((o) => <option key={o.id} value={o.id}>{o.label || o.name}</option>)}
    </Select>
  );
  if (bad) return <ErrorState text="Could not load teachers." onRetry={load} />;
  if (!x) return <Loading />;
  const status = (t) => (t.is_active ? "Active" : "Inactive");
  const cols = [
    { label: "Name", key: "name", sort: true },
    { label: "Username", key: "username", sort: true },
    { label: "Status", get: status, sort: true, render: (t) => (
      <Badge kind={t.is_active ? "ok" : "warn"}>{status(t)}</Badge>) },
    { label: "Actions", render: (t) => (<>
      <Button kind="ghost" size="sm"
        onClick={() => (t.is_active ? setAsk(t) : setActive(t))}>
        {t.is_active ? "Deactivate" : "Activate"}</Button>
      <Button kind="ghost" size="sm" onClick={() => setRp(t)}>Reset password</Button>
    </>) },
  ];
  const acols = [
    { label: "Teacher", get: (s) => nm(x.tc, s.teacher).name || "" },
    { label: "Subject", get: (s) => nm(x.sj, s.subject).name || "" },
    { label: "Class / stream", get: (s) => nm(x.sm, s.stream).label || "" },
  ];
  return (
    <div>
      <h2>Teachers</h2>
      <Card>
        <DataTable cols={cols} rows={x.tc} search="Search teachers"
          empty="No teachers yet" />
      </Card>
      <Card title="Add teacher">
        {Object.keys(blank).map((k) => (
          <Input key={k} id={"t-" + k} label={k.replace("_", " ")}
            type={k === "password" ? "password" : "text"} value={f[k]}
            onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        ))}
        <Button kind="teal" busy={busy} disabled={!f.username || !f.password}
          onClick={async () => {
            if (await post("/api/teachers/", f, "Teacher created")) setF(blank);
          }}>Add teacher</Button>
      </Card>
      <Card title="Assign to class">
        {sel("teacher", "Teacher", x.tc)}
        {sel("subject", "Subject", x.sj)}
        {sel("stream", "Class / stream", x.sm)}
        <Button kind="teal" busy={busy}
          disabled={!a.teacher || !a.subject || !a.stream}
          onClick={async () => {
            if (await post("/api/teacher-assignments/", a, "Assigned")) setA(none);
          }}>Assign</Button>
        <DataTable cols={acols} rows={x.asg} empty="No assignments yet" />
      </Card>
      {ask && <ConfirmDialog title={"Deactivate " + ask.name + "?"} danger
        text="They will not be able to log in." confirm="Deactivate"
        onYes={() => setActive(ask)} onNo={() => setAsk(null)} />}
      {rp && <Modal title={"Reset password: " + rp.username}
        onClose={() => { setRp(null); setPw(""); }}
        actions={<>
          <Button kind="secondary" onClick={() => { setRp(null); setPw(""); }}>Cancel</Button>
          <Button kind="teal" disabled={!pw} onClick={reset}>Reset</Button></>}>
        <Input id="rp-pw" label="New password" type="password" value={pw}
          onChange={(e) => setPw(e.target.value)} />
        <p>They will be signed out everywhere.</p>
      </Modal>}
    </div>
  );
}
