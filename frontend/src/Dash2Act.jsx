import { useState, useEffect } from "react";
import { api } from "./api";
import "./dash2.css";

const hues = { draft: "#4b7bec", submitted: "#f1a927", approved: "#31b88a", locked: "#8c68d8" };

const ago = (t) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(t)) / 60000));
  if (Number.isNaN(m)) return "";
  if (m < 1) return "just now";
  if (m < 60) return m + " min ago";
  return m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago";
};

export default function Dash2Act({ go }) {
  const [rows, setRows] = useState(null);
  const [bad, setBad] = useState(false);

  const load = () => {
    setBad(false);
    api("/api/audit-logs/")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("load"))))
      .then((j) => setRows((Array.isArray(j) ? j : j.results || []).slice(0, 6)))
      .catch(() => setBad(true));
  };
  useEffect(() => { load(); }, []);

  let body;
  if (bad) {
    body = (
      <p className="d2-empty">
        Could not load activity.{" "}
        <button type="button" className="d2-link" onClick={load}>Retry</button>
      </p>
    );
  } else if (rows === null) body = <p className="d2-empty">Loading...</p>;
  else if (rows.length === 0) body = <p className="d2-empty">No recent activity yet.</p>;
  else body = rows.map((x) => {
    const d = x.details || {};
    const color = hues[d.to] || "#4a7de7";
    return (
      <div className="d2-act" key={x.id}>
        <span className="d2-dot" style={{ background: color }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <b>{x.user || "System"}</b> {x.action}
          {d.to && (
            <div style={{ color, fontSize: ".75rem", fontWeight: 600 }}>
              {d.from ? d.from + " \u2192 " + d.to : d.to}
            </div>
          )}
          <time>{ago(x.timestamp)}</time>
        </div>
      </div>
    );
  });

  return (
    <div className="dash2">
      <article className="d2-panel">
        <div className="d2-head">
          <h3>Recent Activity</h3>
          <button type="button" className="d2-link" onClick={() => go("Audit")}>View all activity</button>
        </div>
        {body}
      </article>
    </div>
  );
}
