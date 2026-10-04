import { useState, useEffect } from "react";
import { api } from "./api";
const ago = (t) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(t)) / 60000));
  return m < 1 ? "just now" : m < 60 ? m + "m ago" : m < 1440 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago";
};
export default function Activity() {
  const [rows, setRows] = useState(null);
  useEffect(() => { (async () => {
    const r = await api("/api/audit-logs/");
    setRows(r.ok ? (await r.json()).slice(0, 6) : []);
  })(); }, []);
  if (!rows) return null;
  return (
    <div className="act">
      <h3>Recent activity</h3>
      {!rows.length && <p className="sub">No activity yet.</p>}
      {rows.map((x) => (
        <div className="arow" key={x.id}>
          <i className={"s-" + (x.details && x.details.to ? x.details.to : "draft")} />
          <span><b>{x.user || "System"}</b> {x.action}
            {x.details && x.details.from ? " (" + x.details.from + " → " + x.details.to + ")" : ""}</span>
          <em>{ago(x.timestamp)}</em>
        </div>))}
    </div>
  );
}
