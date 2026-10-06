import { useState, useEffect } from "react";
import { api } from "./api";
import { Card, Badge, DataTable } from "./ui";
import { EmptyState, Loading, ErrorState } from "./ui";

const track = { height: 10, borderRadius: 6, background: "#E2E8F0",
  overflow: "hidden", minWidth: 80 };

export default function Analytics({ d }) {
  const [s, setS] = useState(null), [bad, setBad] = useState(false);
  const id = d.active_term && d.active_term.id;
  const load = async () => {
    try {
      const r = await api("/api/analytics/term-summary/" + id + "/");
      if (!r.ok) throw new Error("load");
      setS(await r.json()); setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { if (id) load(); }, [id]);
  if (!id) return <EmptyState title="No active term"
    text="Ask the school admin to set the active term." />;
  if (bad) return <ErrorState text="Could not load analytics." onRetry={load} />;
  if (!s) return <Loading />;
  const bar = (x) => (
    <div style={track}><div style={{ width: Math.min(x.average, 100) + "%",
      height: "100%", background: "#0F8B8D" }} /></div>);
  const cols = [
    { label: "Subject", key: "subject", sort: true },
    { label: "Average", key: "average", sort: true,
      render: (x) => x.average + "%" },
    { label: "Highest", key: "highest", sort: true },
    { label: "Lowest", key: "lowest", sort: true },
    { label: "Entries", key: "entries", sort: true },
    { label: "Average chart", render: bar },
  ];
  const u = s.unofficial || {};
  const un = (u.draft || 0) + (u.submitted || 0);
  const ucols = [
    { label: "Subject", key: "subject", sort: true },
    { label: "Average (not final)", key: "average", sort: true,
      render: (x) => x.average + "%" },
    { label: "Entries", key: "entries", sort: true },
  ];
  return (
    <div>
      <h2>Term summary: {s.term} {s.academic_year}</h2>
      {s.pending_marks > 0 && <p><Badge kind="warn">Attention</Badge>{" "}
        {s.pending_marks} marks not yet approved are excluded.</p>}
      <Card>
        <DataTable cols={cols} rows={s.subjects || []} search="Search subjects"
          empty="No approved marks yet." />
      </Card>
      {un > 0 && <Card title="Unofficial marks (not final)">
        <p>{u.note} Draft: {u.draft}. Submitted: {u.submitted}.</p>
        <DataTable cols={ucols} rows={u.subjects || []}
          empty="No unofficial marks." />
      </Card>}
    </div>
  );
}
