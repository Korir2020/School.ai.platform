import { useEffect, useState } from "react";
import { api } from "./api";
import "./superhome.css";

const get = async (p) => { try { const r = await api(p); return r.ok ? await r.json() : null; } catch (e) { return null; } };
const list = (j) => (Array.isArray(j) ? j : j && Array.isArray(j.results) ? j.results : []);
const n = (v) => Number(v || 0).toLocaleString();
const ago = (t) => {
  if (!t) return "";
  const s = (Date.now() - new Date(t)) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
};
const human = (a) => String(a || "").replace(/_/g, " ");
const OPEN = ["pending_verification", "pending_approval", "needs_information"];

export default function SuperHome({ me, d, go }) {
  const [x, setX] = useState({ loading: true });
  useEffect(() => {
    let live = true;
    Promise.all([
      get("/api/admin/school-registrations/"), get("/api/teacher-transfers/"),
      get("/api/audit-logs/"), get("/api/backups/status/"), get("/api/feedback/summary/"),
    ]).then(([reg, tr, au, bk, fb]) => live && setX({
      reg: list(reg), tr: list(tr), au: list(au).slice(0, 8), bk, fb, loading: false,
    }));
    return () => { live = false; };
  }, []);

  const schools = d.schools || [];
  const active = schools.filter((s) => !s.is_suspended);
  const suspended = schools.length - active.length;
  const students = schools.reduce((a, s) => a + (Number(s.students) || 0), 0);
  const teachers = schools.reduce((a, s) => a + (Number(s.teachers) || 0), 0);
  const ratio = teachers ? (students / teachers).toFixed(1) : "—";
  const top = [...schools].sort((a, b) => (b.students || 0) - (a.students || 0)).slice(0, 6);
  const maxS = Math.max(1, ...top.map((s) => s.students || 0));
  const empty = schools.filter((s) => !s.is_suspended && (!s.students || !s.teachers));

  const regOpen = (x.reg || []).filter((r) => OPEN.includes(r.status));
  const regReady = regOpen.filter((r) => r.status === "pending_approval").length;
  const trOpen = (x.tr || []).filter((t) => t.status === "pending").length;
  const fbUnread = (x.fb && x.fb.unread) || 0;
  const bkDays = x.bk && x.bk.last_backup ? Math.floor((Date.now() - new Date(x.bk.last_backup)) / 86400000) : null;
  const bkBad = x.bk && (bkDays === null || bkDays > 7);

  const alerts = [
    bkBad && { lv: "crit", t: bkDays === null ? "No platform backup on record" : `Last backup ${bkDays} days ago`, s: "Download a full backup before any update.", to: "Backups", a: "Back up" },
    regReady > 0 && { lv: "warn", t: `${regReady} school registration${regReady > 1 ? "s" : ""} ready for approval`, s: "Email verified, awaiting your decision.", to: "Registrations", a: "Review" },
    trOpen > 0 && { lv: "warn", t: `${trOpen} teacher transfer${trOpen > 1 ? "s" : ""} pending`, s: "Cross-school access changes on approval.", to: "Transfers", a: "Review" },
    suspended > 0 && { lv: "info", t: `${suspended} school${suspended > 1 ? "s" : ""} suspended`, s: "Users at these schools cannot sign in.", to: "Schools", a: "Manage" },
    empty.length > 0 && { lv: "info", t: `${empty.length} active school${empty.length > 1 ? "s" : ""} not yet onboarded`, s: "No students or teachers recorded.", to: "Schools", a: "View" },
    fbUnread > 0 && { lv: "info", t: `${fbUnread} unread feedback message${fbUnread > 1 ? "s" : ""}`, s: "From school users across the platform.", to: "Feedback", a: "Read" },
  ].filter(Boolean);

  const hr = new Date().getHours();
  const greet = hr < 12 ? "Good morning" : hr < 17 ? "Good afternoon" : "Good evening";
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const healthy = schools.length ? Math.round((active.length / schools.length) * 100) : 0;

  return (
    <div className="plain sx">
      <header className="sx-head">
        <div>
          <p className="sx-eyebrow">Platform control · Superadmin</p>
          <h2>{greet}{me && me.username ? ", " + me.username : ""}</h2>
          <p className="sx-date">{today}</p>
        </div>
        <div className="sx-actions">
          <button className="sx-btn" onClick={() => go("Registrations")}>Review registrations</button>
          <button className="sx-btn pri" onClick={() => go("Schools")}>Manage schools</button>
        </div>
      </header>

      <section className="sx-kpis" aria-label="Platform totals">
        <Kpi label="Schools" value={n(schools.length)} note={`${n(active.length)} active · ${n(suspended)} suspended`} />
        <Kpi label="Students" value={n(students)} note={`Across ${n(active.length)} schools`} />
        <Kpi label="Teachers" value={n(teachers)} note={`${ratio} students per teacher`} />
        <Kpi label="Pending actions" value={x.loading ? "…" : n(regOpen.length + trOpen)} note={`${n(regOpen.length)} registrations · ${n(trOpen)} transfers`} hot={regOpen.length + trOpen > 0} />
      </section>

      <div className="sx-grid">
        <section className="sx-card sx-span2">
          <div className="sx-ch"><h3>Enrolment by school</h3><button className="sx-link" onClick={() => go("Schools")}>All schools →</button></div>
          {top.length === 0 ? <p className="sx-empty">No schools registered yet.</p> : (
            <ul className="sx-bars">
              {top.map((s) => (
                <li key={s.id}>
                  <span className="sx-bn">{s.name}{s.is_suspended && <em className="sx-tag crit">Suspended</em>}</span>
                  <span className="sx-track"><i style={{ width: ((s.students || 0) / maxS) * 100 + "%" }} /></span>
                  <span className="sx-bv">{n(s.students)}<small>{n(s.teachers)} tch</small></span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="sx-card">
          <div className="sx-ch"><h3>Needs attention</h3><span className="sx-count">{alerts.length}</span></div>
          {x.loading ? <p className="sx-empty">Checking platform…</p> : alerts.length === 0 ? <p className="sx-empty ok">All clear. Nothing needs your attention.</p> : (
            <ul className="sx-alerts">
              {alerts.map((a, i) => (
                <li key={i} className={a.lv}>
                  <div><b>{a.t}</b><small>{a.s}</small></div>
                  <button className="sx-link" onClick={() => go(a.to)}>{a.a}</button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="sx-card">
          <div className="sx-ch"><h3>Platform health</h3></div>
          <div className="sx-ring" style={{ "--p": healthy }}><b>{healthy}%</b><small>schools active</small></div>
          <dl className="sx-dl">
            <div><dt>Last backup</dt><dd className={bkBad ? "crit" : "okc"}>{x.loading ? "…" : bkDays === null ? "Never" : bkDays === 0 ? "Today" : bkDays + "d ago"}</dd></div>
            <div><dt>Database migrations</dt><dd>{x.bk && x.bk.migrations ? (typeof x.bk.migrations === "object" ? (x.bk.migrations.pending ? "Pending" : "Up to date") : String(x.bk.migrations)) : "—"}</dd></div>
            <div><dt>Feedback rating</dt><dd>{x.fb && x.fb.average ? Number(x.fb.average).toFixed(1) + " / 5" : "—"}</dd></div>
          </dl>
        </section>

        <section className="sx-card">
          <div className="sx-ch"><h3>Registration pipeline</h3><button className="sx-link" onClick={() => go("Registrations")}>Open →</button></div>
          <ul className="sx-pipe">
            {[["Awaiting email", "pending_verification"], ["Ready to approve", "pending_approval"], ["Info requested", "needs_information"], ["Approved", "approved"], ["Rejected", "rejected"]].map(([l, k]) => (
              <li key={k}><span>{l}</span><b>{x.loading ? "…" : (x.reg || []).filter((r) => r.status === k).length}</b></li>
            ))}
          </ul>
        </section>

        <section className="sx-card">
          <div className="sx-ch"><h3>Recent activity</h3><button className="sx-link" onClick={() => go("Audit")}>Audit log →</button></div>
          {x.loading ? <p className="sx-empty">Loading…</p> : x.au.length === 0 ? <p className="sx-empty">No recorded activity yet.</p> : (
            <ul className="sx-feed">
              {x.au.map((e, i) => (
                <li key={e.id || i}><i /><div><b>{human(e.action)}</b><small>{e.user || "System"} · {ago(e.timestamp)}</small></div></li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="sx-quick" aria-label="Superadmin tools">
        {[["Schools", "Create and suspend schools"], ["Registrations", "Approve new schools"], ["Transfers", "Move teachers between schools"], ["Admins", "School administrator accounts"], ["Backups", "Full platform backup"], ["Audit", "Every change, traced"], ["Feedback", "What schools are saying"]].map(([t, s]) => (
          <button key={t} className="sx-tool" onClick={() => go(t)}><b>{t}</b><small>{s}</small></button>
        ))}
      </section>
    </div>
  );
}

function Kpi({ label, value, note, hot }) {
  return <div className={"sx-kpi" + (hot ? " hot" : "")}><span>{label}</span><b>{value}</b><small>{note}</small></div>;
}
