import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Card, Badge, StatCard, DataTable } from "./ui";
import { ConfirmDialog, Loading, ErrorState } from "./ui";

const paths = ["performance", "students", "subjects"];
const kinds = { submitted: "warn", approved: "ok" };
const words = { approve: "Approved", reject: "Rejected", lock: "Locked" };

export default function Approvals() {
  const toast = useToast();
  const [d, setD] = useState(null), [bad, setBad] = useState(false);
  const [ask, setAsk] = useState(null);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [pf, st, sj] = await Promise.all(paths.map(get));
      setD({ pf, st, sj }); setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  if (bad) return <ErrorState text="Could not load approvals." onRetry={load} />;
  if (!d) return <Loading />;
  const nm = (id) => {
    const s = d.st.find((x) => x.id === id);
    return s ? s.first_name + " " + s.last_name : "Student " + id;
  };
  const sb = (id) => {
    const s = d.sj.find((x) => x.id === id);
    return s ? s.name : "Subject " + id;
  };
  const act = async ({ p, a }) => {
    setAsk(null);
    const r = await api("/api/performance/" + p.id + "/" + a + "/", "POST");
    const j = await r.json().catch(() => ({}));
    if (r.ok) toast(words[a] + ": " + nm(p.student), "ok");
    else toast("Failed: " + (j.detail || a), "err");
    load();
  };
  const rows = d.pf.filter((p) => kinds[p.status]);
  const count = (s) => rows.filter((p) => p.status === s).length;
  const cols = [
    { label: "Student", get: (p) => nm(p.student), sort: true },
    { label: "Subject", get: (p) => sb(p.subject), sort: true },
    { label: "Marks", key: "marks", sort: true },
    { label: "Status", key: "status", sort: true, render: (p) => (
      <Badge kind={kinds[p.status]}>{p.status}</Badge>) },
    { label: "Actions", render: (p) => (p.status === "submitted" ? (<>
      <Button kind="teal" size="sm" onClick={() => act({ p, a: "approve" })}>
        Approve</Button>
      <Button kind="secondary" size="sm" onClick={() => setAsk({ p, a: "reject" })}>
        Reject</Button></>) : (
      <Button kind="secondary" size="sm" onClick={() => setAsk({ p, a: "lock" })}>
        Lock</Button>)) },
  ];
  return (
    <div>
      <h2>Marks awaiting action</h2>
      <StatCard label="Awaiting approval" value={count("submitted")} />
      <StatCard label="Approved, awaiting lock" value={count("approved")} />
      <Card>
        <DataTable cols={cols} rows={rows} search="Search approvals"
          empty="Nothing waiting." />
      </Card>
      {ask && <ConfirmDialog danger={ask.a === "lock"}
        title={(ask.a === "lock" ? "Lock" : "Reject") + " this mark?"}
        text={ask.a === "lock" ? "Locked marks can never be changed."
          : "This mark will not be approved."}
        confirm={ask.a === "lock" ? "Lock" : "Reject"}
        onYes={() => act(ask)} onNo={() => setAsk(null)} />}
    </div>
  );
}
