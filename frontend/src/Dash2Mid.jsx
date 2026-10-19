import { useState, useEffect } from "react";
import { api } from "./api";
import Ic from "./icons";
import "./dash2.css";

const K = [
  ["draft", "Draft", "#4b7bec"],
  ["submitted", "Submitted", "#f1a927"],
  ["approved", "Approved", "#31b88a"],
  ["locked", "Locked", "#8c68d8"],
];

function Performance({ termId, go }) {
  const [rows, setRows] = useState(null);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    let live = true;
    if (!termId) return undefined;
    api("/api/analytics/advanced/" + termId + "/")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("load"))))
      .then((j) => { if (live) setRows(Array.isArray(j.subjects) ? j.subjects : []); })
      .catch(() => { if (live) setBad(true); });
    return () => { live = false; };
  }, [termId]);

  const list = (rows || []).filter(
    (s) => s && s.average !== null && Number.isFinite(Number(s.average))
  );
  const top = list.length
    ? list.reduce((a, b) => (Number(b.average) > Number(a.average) ? b : a))
    : null;

  let body;
  if (!termId) body = <p className="d2-empty">No active term yet.</p>;
  else if (bad) body = <p className="d2-empty">Could not load subject performance.</p>;
  else if (rows === null) body = <p className="d2-empty">Loading...</p>;
  else if (!list.length) body = <p className="d2-empty">No data yet. Averages appear once marks are finalized.</p>;
  else body = (
    <div className="d2-perf">
      <div>
        <p className="d2-muted">Average mark (%) by subject</p>
        <div className="d2-bars" role="img" aria-label="Average performance by subject">
          {list.map((s) => (
            <div className="d2-bar" key={s.subject}>
              <span>{Math.round(Number(s.average))}%</span>
              <i style={{ height: Number(s.average) * 0.85 + "%" }} />
            </div>
          ))}
        </div>
        <div className="d2-names">
          {list.map((s) => <span key={s.subject} title={s.subject}>{s.subject}</span>)}
        </div>
      </div>
      <div className="d2-top">
        <span className="d2-ico t-orange"><Ic n="Trophy" size={20} /></span>
        <p className="d2-muted">Top performer</p>
        <h4>{top.subject}</h4>
        <b>{Math.round(Number(top.average))}% average</b>
        <p className="d2-muted">Highest finalized subject average this term.</p>
      </div>
    </div>
  );

  return (
    <article className="d2-panel">
      <div className="d2-head">
        <h3>Academic Performance Overview</h3>
        <button type="button" className="d2-link" onClick={() => go("Analytics")}>View detailed report</button>
      </div>
      {body}
    </article>
  );
}

function Workflow({ d, go }) {
  const m = d.marks_by_status || {};
  const vals = K.map(([k]) => Number(m[k]) || 0);
  const total = vals.reduce((a, b) => a + b, 0);
  const pcts = vals.map((v) => (total ? (v / total) * 100 : 0));
  const starts = pcts.map((_, i) => pcts.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <article className="d2-panel">
      <div className="d2-head">
        <h3>Marks Workflow</h3>
        <button type="button" className="d2-link" onClick={() => go("Approve")}>View details</button>
      </div>
      <div className="d2-wf">
        <div className="d2-ring" role="img" aria-label="Marks workflow">
          <svg viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e8edf5" strokeWidth="4" />
            {total > 0 && K.map(([k, , c], i) => pcts[i] > 0 && (
              <circle key={k} cx="18" cy="18" r="15.9155" fill="none" stroke={c} strokeWidth="4"
                strokeDasharray={pcts[i] + " " + (100 - pcts[i])} strokeDashoffset={-starts[i]} />
            ))}
          </svg>
          <div><b>{total}</b>Total records</div>
        </div>
        <div className="d2-leg">
          {K.map(([k, label, c], i) => (
            <div key={k}>
              <i style={{ background: c }} />
              <span>{label}</span>
              <b>{vals[i]} ({Math.round(pcts[i])}%)</b>
            </div>
          ))}
        </div>
      </div>
      {total === 0 && <p className="d2-empty">No marks entered this term yet.</p>}
    </article>
  );
}

export default function Dash2Mid({ d, go }) {
  const t = d.active_term;
  return (
    <div className="dash2">
      <section className="d2-grid d2-two">
        <Performance termId={t ? t.id : null} go={go} />
        <Workflow d={d} go={go} />
      </section>
    </div>
  );
}
