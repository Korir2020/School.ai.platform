import { useState, useEffect } from "react";
import { api } from "./api";
import Ic from "./icons";
import "./dash2.css";

const money = (v) => {
  const n = Number(v);
  return v === undefined || v === null || !Number.isFinite(n)
    ? "KES \u2014"
    : "KES " + n.toLocaleString();
};

const ACTIONS = [
  ["Approve", "Approve Marks", "Approve", "green"],
  ["Exams", "Manage Examinations", "Exams", "blue"],
  ["Reports", "View Reports", "Reports", "purple"],
  ["Students", "Manage Students", "Students", "cyan"],
  ["Analytics", "View Analytics", "Analytics", "orange"],
  ["Fees", "Manage Fees", "Fees", "pink"],
];

function FeePanel({ d, go }) {
  const f = d.fees || {};
  const pctNum = Number(f.collection_percentage);
  const has = f.collection_percentage !== undefined && f.collection_percentage !== null && Number.isFinite(pctNum);
  const pct = has ? Math.min(100, Math.max(0, pctNum)) : 0;
  return (
    <article className="d2-panel">
      <div className="d2-head">
        <h3>Fee Collection Overview</h3>
        <button type="button" className="d2-link" onClick={() => go("Fees")}>View report</button>
      </div>
      <div className="d2-wf">
        <div className="d2-ring" role="img" aria-label="Fee collection">
          <svg viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e8edf5" strokeWidth="4" />
            {pct > 0 && (
              <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#31b88a" strokeWidth="4"
                strokeDasharray={pct + " " + (100 - pct)} />
            )}
          </svg>
          <div><b>{has ? pct + "%" : "\u2014"}</b>Collected</div>
        </div>
        <div className="d2-fees">
          <div><small>Amount billed</small><b>{money(f.amount_due)}</b></div>
          <div><small>Amount collected</small><b>{money(f.amount_paid)}</b></div>
          <div><small>Outstanding</small><b>{money(f.balance)}</b></div>
          <div><small>Overdue</small><b>{money(f.overdue_amount)}</b></div>
        </div>
      </div>
    </article>
  );
}

function AttentionPanel({ d, go }) {
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
  if (wait > 0) items.push(["Approve", "Marks awaiting approval", wait + " marks waiting for approval"]);
  if (flag > 0) items.push(["Approve", "Unusual mark groups", flag + " mark groups look unusual"]);
  if (drafts > 0) items.push(["Exams", "Draft examinations", drafts + " draft exams not published"]);
  return (
    <article className="d2-panel">
      <div className="d2-head">
        <h3>Needs Attention</h3>
        {items.length > 0 && <span className="d2-badge">{items.length}</span>}
      </div>
      {items.length === 0 && <p className="d2-empty">All clear. Nothing is waiting for attention.</p>}
      {items.map(([tab, title, text]) => (
        <button type="button" key={title} className="d2-item" onClick={() => go(tab)}>
          <span className="d2-ico t-orange"><Ic n="Alert" size={20} /></span>
          <span style={{ flex: 1 }}>
            <b>{title}</b>
            <small>{text}</small>
          </span>
          <span aria-hidden="true">{"\u2192"}</span>
        </button>
      ))}
    </article>
  );
}

function QuickPanel({ go, tabs }) {
  const items = ACTIONS.filter(([t]) => tabs && tabs[t]);
  return (
    <article className="d2-panel">
      <div className="d2-head"><h3>Quick Actions</h3></div>
      {items.length === 0 ? (
        <p className="d2-empty">Nothing is available for your role.</p>
      ) : (
        <div className="d2-qa">
          {items.map(([t, label, icon, tint]) => (
            <button type="button" key={t} onClick={() => go(t)}>
              <span className={"d2-ico t-" + tint}><Ic n={icon} size={20} /></span>
              {label}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

export default function Dash2Low({ d, go, tabs }) {
  return (
    <div className="dash2">
      <section className="d2-grid d2-three">
        <FeePanel d={d} go={go} />
        <AttentionPanel d={d} go={go} />
        <QuickPanel go={go} tabs={tabs} />
      </section>
    </div>
  );
}
