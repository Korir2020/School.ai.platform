import { useState, useEffect } from "react";
import { api, listAll } from "./api";
import { useToast } from "./toastctx";
import { Button, Select, Modal } from "./ui";
import { Card, Badge, DataTable, Loading, ErrorState } from "./ui";

const KIND = { pending: "warn", joined: "ok" };

function Assign({ q, onClose }) {
  const toast = useToast();
  const [x, setX] = useState(null), [a, setA] = useState({ s: "", t: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { (async () => {
    const g = (p) => listAll("/api/" + p + "/");
    const [sj, sm, cl] = await Promise.all(
      ["subjects", "streams", "class-levels"].map(g));
    const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name
      || "") + " " + s.name;
    setX({ sj, sm: sm.map((s) => ({ ...s, label: lab(s) })) });
  })(); }, []);
  const go = async () => {
    setBusy(true);
    const body = { teacher: q.teacher_id, subject: a.s, stream: a.t };
    const r = await api("/api/teacher-assignments/", "POST", body);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) { toast("Assigned", "ok"); setA({ s: "", t: "" }); }
    else toast(j.detail || JSON.stringify(j), "err");
  };
  const opt = (arr) => arr.map((o) => (
    <option key={o.id} value={o.id}>{o.label || o.name}</option>));
  return (<Modal title={"Assign: " + q.name} onClose={onClose}
    actions={<><Button kind="secondary" onClick={onClose}>Close</Button>
      <Button kind="teal" busy={busy} disabled={!a.s || !a.t}
        onClick={go}>Assign</Button></>}>
    {!x ? <p>Loading...</p> : <>
      <Select label="Subject" id="st-s" value={a.s}
        onChange={(e) => setA({ ...a, s: e.target.value })}>
        <option value="">Select...</option>{opt(x.sj)}</Select>
      <Select label="Class / stream" id="st-t" value={a.t}
        onChange={(e) => setA({ ...a, t: e.target.value })}>
        <option value="">Select...</option>{opt(x.sm)}</Select>
      <p>A teacher can have at most 4 subjects.</p></>}
  </Modal>);
}

export default function Staff() {
  const toast = useToast();
  const [rows, setRows] = useState(null), [bad, setBad] = useState(false);
  const [who, setWho] = useState(null), [busy, setBusy] = useState(false);
  const load = async () => {
    const r = await api("/api/join-requests/");
    if (!r.ok) { setBad(true); return; }
    setRows((await r.json()).results); setBad(false);
  };
  useEffect(() => { load(); }, []);
  const decide = async (q, what) => {
    setBusy(true);
    const r = await api("/api/join-requests/" + q.id + "/" + what + "/", "POST");
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    toast(r.ok ? "Done" : j.detail || "Failed", r.ok ? "ok" : "err");
    load();
  };
  if (bad) return <ErrorState text="Could not load staff." onRetry={load} />;
  if (!rows) return <Loading />;
  const act = (q) => (<>
    {q.status === "pending" && <>
      <Button kind="teal" size="sm" busy={busy}
        onClick={() => decide(q, "approve")}>Approve</Button>
      <Button kind="ghost" size="sm" busy={busy}
        onClick={() => decide(q, "reject")}>Reject</Button></>}
    {q.status === "approved" && <Button kind="ghost" size="sm" busy={busy}
      onClick={() => decide(q, "approve")}>New code</Button>}
    {q.status === "joined" && q.teacher_id && <Button kind="teal" size="sm"
      onClick={() => setWho(q)}>Assign</Button>}</>);
  const cols = [
    { label: "Name", key: "name", sort: true },
    { label: "Role", key: "role", sort: true },
    { label: "Status", key: "status", sort: true, render: (q) => (
      <Badge kind={KIND[q.status]}>{q.status}</Badge>) },
    { label: "Invitation code", render: (q) => (q.code
      ? <b>{q.code}</b> : "") },
    { label: "Actions", render: act },
  ];
  return (<div>
    <Card title="Join requests">
      <DataTable cols={cols} rows={rows} search="Search staff"
        empty="No join requests yet" /></Card>
    {who && <Assign q={who} onClose={() => setWho(null)} />}
  </div>);
}
