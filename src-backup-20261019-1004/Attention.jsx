import { useState, useEffect } from "react";
import { api } from "./api";
import { Button, Card, Badge, StatCard } from "./ui";

export default function Attention({ d, go }) {
  const [flag, setFlag] = useState(0);
  useEffect(() => {
    let live = true;
    api("/api/approvals/summary/")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => { if (live && s) setFlag(s.flagged_groups || 0); })
      .catch(() => {});
    return () => { live = false; };
  }, []);
  const wait = d.awaiting_approval || 0;
  const drafts = (d.exams && d.exams.draft) || 0;
  const items = [];
  const add = (tab, text, label) => items.push({ tab, text, label });
  if (wait > 0) add("Approve", wait + " marks waiting for approval", "Review");
  if (flag > 0) add("Approve", flag + " mark groups look unusual", "Check");
  if (drafts > 0) add("Exams", drafts + " draft exams not published", "Open");
  return (
    <div>
      <Card title="Needs attention">
        {items.length === 0 && <Badge kind="ok">All clear: nothing is waiting</Badge>}
        {items.map((i) => (
          <p key={i.text}>
            <Badge kind="warn">{i.text}</Badge>{" "}
            <Button kind="secondary" onClick={() => go(i.tab)}>{i.label}</Button>
          </p>
        ))}
      </Card>
      <div className="mu-stats">
        <StatCard label="Students" value={d.students}
          note={d.active_enrollments + " enrolled"} />
        <StatCard label="Teachers" value={d.teachers} />
        <StatCard label="Streams" value={d.streams} />
        <StatCard label="Subjects" value={d.subjects} />
      </div>
    </div>
  );
}
