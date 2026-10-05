import { useState, useEffect } from "react";
import { api } from "./api";
import { Card, Badge, EmptyState, Loading, ErrorState } from "./ui";

const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };
const ago = (t) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(t)) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return m + "m ago";
  return m < 1440 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago";
};

export default function Activity() {
  const [rows, setRows] = useState(null), [bad, setBad] = useState(false);
  const load = async () => {
    try {
      const r = await api("/api/audit-logs/");
      if (!r.ok) throw new Error("load");
      const j = await r.json();
      setRows((Array.isArray(j) ? j : j.results || []).slice(0, 6));
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  if (bad) return <ErrorState text="Could not load activity." onRetry={load} />;
  if (!rows) return <Loading />;
  return (
    <Card title="Recent activity">
      {rows.length === 0 ? <EmptyState title="No activity yet" text="" /> : rows.map((x) => {
        const d = x.details || {};
        return (
          <div key={x.id} style={{ padding: "6px 0" }}>
            <b>{x.user || "System"}</b> {x.action}
            {d.from ? " (" + d.from + " \u2192 " + d.to + ")" : ""}{" "}
            {d.to && <Badge kind={kinds[d.to] || "info"}>{d.to}</Badge>}{" "}
            <em>{ago(x.timestamp)}</em>
          </div>
        );
      })}
    </Card>
  );
}
