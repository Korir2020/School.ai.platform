import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import Ic from "./icons";
import "./teacher-home.css";

// Teacher home dashboard. Uses only existing endpoints:
//   d (from /api/dashboard/): active_term, assignments, my_marks_by_status
//   /api/announcements/ (teacher inbox), /api/calendar/events/ (school dates)

const iso = (x) => x.toISOString().slice(0, 10);
const fmtDay = (s) => new Date(s + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
const daysUntil = (s) => {
  const a = new Date(); a.setHours(0, 0, 0, 0);
  return Math.round((new Date(s + "T00:00:00") - a) / 86400000);
};
const when = (n) => (n <= 0 ? "Today" : n === 1 ? "Tomorrow" : "In " + n + " days");
const greet = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
const ago = (s) => {
  if (!s) return "";
  const m = Math.round((Date.now() - new Date(s)) / 60000);
  if (m < 60) return Math.max(1, m) + "m ago";
  if (m < 1440) return Math.round(m / 60) + "h ago";
  return new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short" });
};
const KIND = { exam: "Exam", holiday: "Holiday", meeting: "Meeting", event: "Event", other: "Other" };

function Section({ title, icon, action, children, className = "" }) {
  return (
    <section className={"th-card " + className}>
      <div className="th-card-head">
        <h2>{icon && <Ic n={icon} size={16} />}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const Link = ({ onClick, children }) => (
  <button type="button" className="th-link" onClick={onClick}>{children}</button>
);

export default function TeacherHome({ me, d, go }) {
  const [ann, setAnn] = useState(null);
  const [cal, setCal] = useState(null);

  useEffect(() => {
    let alive = true;
    api("/api/announcements/").then(async (r) => {
      const j = r.ok ? await r.json() : null;
      if (alive) setAnn(j ? { unread: j.unread || 0, rows: (j.results || []).slice(0, 4) } : { error: true });
    }).catch(() => alive && setAnn({ error: true }));
    const from = new Date(), to = new Date(); to.setDate(to.getDate() + 30);
    api("/api/calendar/events/?from=" + iso(from) + "&to=" + iso(to)).then(async (r) => {
      const j = r.ok ? await r.json() : null;
      if (alive) setCal(j ? (j.events || []).sort((a, b) => a.start_date.localeCompare(b.start_date)) : { error: true });
    }).catch(() => alive && setCal({ error: true }));
    return () => { alive = false; };
  }, []);

  const t = d.active_term;
  const name = me ? (me.first_name || me.username) : "";
  const school = me && me.school ? me.school.name : "";
  const a = d.assignments || [];
  const m = d.my_marks_by_status || {};
  const draft = m.draft || 0, wait = m.submitted || 0, appr = m.approved || 0, lock = m.locked || 0;
  const total = draft + wait + appr + lock;
  const pct = total ? Math.round(((appr + lock) / total) * 100) : 0;

  const classes = useMemo(() => {
    const g = {};
    a.forEach((x) => { const k = x.class_level + " " + x.stream; (g[k] = g[k] || []).push(x.subject); });
    return Object.entries(g).sort((p, q) => p[0].localeCompare(q[0]));
  }, [a]);
  const subjects = new Set(a.map((x) => x.subject)).size;

  const events = Array.isArray(cal) ? cal : [];
  const exams = events.filter((e) => e.kind === "exam");
  const nextExam = exams[0];

  // Priority list: only real, actionable items.
  const todo = [];
  if (draft > 0) todo.push({ tone: "warn", icon: "Marks", title: draft + " draft mark" + (draft > 1 ? "s" : "") + " not submitted", text: "Submit them for approval before the deadline.", cta: "Submit marks", tab: "Marks" });
  if (total === 0 && a.length > 0 && t) todo.push({ tone: "info", icon: "Marks", title: "No marks entered for " + t.name, text: "Start entering marks for your assigned classes.", cta: "Enter marks", tab: "Marks" });
  if (nextExam) todo.push({ tone: daysUntil(nextExam.start_date) <= 7 ? "warn" : "info", icon: "Exams", title: nextExam.title, text: "Exam · " + fmtDay(nextExam.start_date) + " · " + when(daysUntil(nextExam.start_date)), cta: "View calendar", tab: "Calendar" });
  if (ann && ann.unread > 0) todo.push({ tone: "info", icon: "Announcements", title: ann.unread + " unread announcement" + (ann.unread > 1 ? "s" : ""), text: "School notices waiting for you.", cta: "Read", tab: "Announcements" });
  if (a.length === 0) todo.push({ tone: "info", icon: "Teachers", title: "No classes assigned yet", text: "Ask the administrator to assign your subjects.", cta: null });

  const actions = [
    ["Marks", "Enter marks", "Marks"],
    ["Attendance", "Take attendance", "Attendance"],
    ["Levels", "Level entry", "Streams"],
    ...(me && me.is_class_teacher ? [["Report Cards", "Report cards", "Reports"]] : []),
    ["Announcements", "Announcements", "Announcements"],
    ["Calendar", "Calendar", "Calendar"],
  ];

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="plain th">
      <div className="th-hero">
        <div className="th-hero-text">
          <p className="th-eyebrow">{today}</p>
          <h1>{greet()}{name ? ", " + name : ""}</h1>
          <p className="th-sub">
            {school && <span>{school}</span>}
            <span className={"th-term" + (t ? " live" : "")}><i />{t ? t.name + " · " + t.academic_year : "No active term"}</span>
          </p>
        </div>
        <div className="th-kpis">
          <div><span className="th-k-l">Classes</span><b className={"th-k-v"}>{classes.length}</b></div>
          <div><span className="th-k-l">Subjects</span><b className={"th-k-v"}>{subjects}</b></div>
          <div><span className="th-k-l">Marks to submit</span><b className={"th-k-v" + (draft ? " warn" : "")}>{draft}</b></div>
          <div><span className="th-k-l">Awaiting approval</span><b className={"th-k-v"}>{wait}</b></div>
        </div>
      </div>

      <div className="th-actions" role="navigation" aria-label="Quick actions">
        {actions.map(([tab, label, icon]) => (
          <button key={tab} type="button" className="th-action" onClick={() => go(tab)}>
            <span className="th-action-ic"><Ic n={icon} size={18} /></span>{label}
          </button>
        ))}
      </div>

      <div className="th-grid">
        <div className="th-col">
          <Section title="Needs your attention" icon="Alert">
            {todo.length === 0 ? (
              <p className="th-empty"><Ic n="Approve" size={16} /> You're all caught up. Nothing needs action right now.</p>
            ) : (
              <ul className="th-todo">
                {todo.map((x, i) => (
                  <li key={i} className={"tone-" + x.tone}>
                    <span className="th-todo-ic"><Ic n={x.icon} size={16} /></span>
                    <div><b>{x.title}</b><small>{x.text}</small></div>
                    {x.cta && <button type="button" className="th-btn" onClick={() => go(x.tab)}>{x.cta}</button>}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="My classes & subjects" icon="Students" action={a.length > 0 && <Link onClick={() => go("Marks")}>Open marks →</Link>}>
            {classes.length === 0 ? (
              <p className="th-empty">No classes assigned yet. Ask the administrator to assign you to a class.</p>
            ) : (
              <ul className="th-classes">
                {classes.map(([cls, subs]) => (
                  <li key={cls}>
                    <div className="th-class-name"><b>{cls}</b><small>{subs.length} subject{subs.length > 1 ? "s" : ""}</small></div>
                    <div className="th-chips">{subs.map((s) => <span key={s}>{s}</span>)}</div>
                    <div className="th-class-acts">
                      <button type="button" className="th-btn ghost" onClick={() => go("Marks")}>Marks</button>
                      <button type="button" className="th-btn ghost" onClick={() => go("Attendance")}>Attendance</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={"Marks progress" + (t ? " · " + t.name : "")} icon="Analytics">
            {total === 0 ? (
              <p className="th-empty">No marks entered this term yet.</p>
            ) : (
              <>
                <div className="th-progress-top"><b>{pct}%</b><span>approved or locked · {total} entries</span></div>
                <div className="th-bar" role="img" aria-label={pct + "% approved"}>
                  {[["draft", draft], ["submitted", wait], ["approved", appr], ["locked", lock]].map(([k, v]) => v ? <i key={k} className={"b-" + k} style={{ flex: v }} /> : null)}
                </div>
                <ul className="th-legend">
                  {[["Draft", draft, "draft"], ["Submitted", wait, "submitted"], ["Approved", appr, "approved"], ["Locked", lock, "locked"]].map(([l, v, k]) => (
                    <li key={k}><i className={"b-" + k} />{l}<b>{v}</b></li>
                  ))}
                </ul>
              </>
            )}
          </Section>
        </div>

        <div className="th-col">
          <Section title="Upcoming dates" icon="Calendar" action={<Link onClick={() => go("Calendar")}>Calendar →</Link>}>
            {cal === null ? <div className="th-skel" /> : cal.error ? <p className="th-empty">Couldn't load the calendar.</p> : events.length === 0 ? (
              <p className="th-empty">Nothing scheduled in the next 30 days.</p>
            ) : (
              <ul className="th-events">
                {events.slice(0, 5).map((e) => {
                  const dt = new Date(e.start_date + "T00:00:00");
                  return (
                    <li key={e.id}>
                      <span className="th-date"><small>{dt.toLocaleDateString(undefined, { month: "short" })}</small><b>{dt.getDate()}</b></span>
                      <div><b>{e.title}</b><small>{KIND[e.kind] || e.kind} · {when(daysUntil(e.start_date))}{e.location ? " · " + e.location : ""}</small></div>
                      {e.kind === "exam" && <span className="th-tag warn">Exam</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </Section>

          <Section title="Announcements" icon="Announcements" action={<Link onClick={() => go("Announcements")}>View all →</Link>}>
            {ann === null ? <div className="th-skel" /> : ann.error ? <p className="th-empty">Couldn't load announcements.</p> : ann.rows.length === 0 ? (
              <p className="th-empty">No announcements yet.</p>
            ) : (
              <ul className="th-ann">
                {ann.rows.map((x) => (
                  <li key={x.id} className={x.read === false ? "unread" : ""}>
                    <button type="button" onClick={() => go("Announcements")}>
                      <div className="th-ann-top">
                        <b>{x.title}</b>
                        {x.priority === "urgent" && <span className="th-tag err">Urgent</span>}
                      </div>
                      <p>{x.body}</p>
                      <small>{x.author ? x.author + " · " : ""}{ago(x.sent_at || x.created_at)}</small>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
