import { useState, useEffect } from "react";
import { api } from "./api";
import { Button, Card, Badge } from "./ui";
import "./dashboard.css";

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
  const overdue = Number((d.fees && d.fees.overdue_amount) || 0);
  const items = [];
  const add = (tab, text, label, level) => items.push({ tab, text, label, level });
  if (wait > 0) add("Approve", wait + " marks waiting for approval", "Review", "warn");
  if (flag > 0) add("Approve", flag + " mark groups look unusual", "Check", "warn");
  if (overdue > 0) add("Fees", "KES " + overdue.toLocaleString() + " in overdue fees", "Open", "warn");
  if (drafts > 0) add("Exams", drafts + " draft exams not published", "Open", "info");
  const word = { warn: "Warning", info: "Notice" };
  return (
    <Card title="Needs attention">
      {items.length === 0 && <Badge kind="ok">All clear: nothing is waiting</Badge>}
      <ul className="dash-alerts">
        {items.map((i) => (
          <li key={i.text}>
            <Badge kind={i.level}>{word[i.level]}: {i.text}</Badge>
            <Button kind="secondary" size="sm" onClick={() => go(i.tab)}>{i.label}</Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
