import { useState, useEffect } from "react";
import { api } from "./api";
import { Button, Input, Card, DataTable } from "./ui";
import { EmptyState, Loading, ErrorState } from "./ui";

const blank = { action: "", user: "", date_from: "", date_to: "" };

export default function AuditLog() {
  const [f, setF] = useState(blank);
  const [applied, setApplied] = useState(blank);
  const [rows, setRows] = useState(null);
  const [bad, setBad] = useState(false);

  const load = async () => {
    try {
      const qs = new URLSearchParams(Object.entries(applied).filter(([, v]) => v));
      const r = await api("/api/audit-logs/?" + qs);
      if (!r.ok) throw new Error("load");
      setRows(await r.json());
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, [JSON.stringify(applied)]);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const cols = [
    { label: "Date and time", key: "timestamp", sort: true, render: (r) => new Date(r.timestamp).toLocaleString() },
    { label: "User", key: "user", sort: true, render: (r) => r.user || "System" },
    { label: "Action", key: "action", sort: true },
    { label: "Details", key: "details" },
    { label: "Record", key: "performance", render: (r) => (r.performance ? "Mark #" + r.performance : "-") },
  ];

  if (bad) return <ErrorState text="Could not load the audit log." onRetry={load} />;
  if (!rows) return <Loading />;
  return (
    <div>
      <h2>Audit log</h2>
      <p className="sub">Recorded mark-change events only, newest first. Shows up to the latest 200 matching entries.</p>
      <Card title="Filters">
        <Input id="al-action" label="Action" value={f.action} onChange={set("action")} />
        <Input id="al-user" label="Username" value={f.user} onChange={set("user")} />
        <Input id="al-from" label="From date" type="date" value={f.date_from} onChange={set("date_from")} />
        <Input id="al-to" label="To date" type="date" value={f.date_to} onChange={set("date_to")} />
        <Button kind="teal" onClick={() => setApplied(f)}>Apply filters</Button>{" "}
        <Button kind="secondary" onClick={() => { setF(blank); setApplied(blank); }}>Clear</Button>
      </Card>
      <Card>
        <DataTable cols={cols} rows={rows} search="Search entries" empty="No recorded events match these filters." />
      </Card>
    </div>
  );
}
