import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Card, Loading, ErrorState } from "./ui";
import "./calendar.css";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const KINDS = [["holiday", "Holiday"], ["exam", "Exam"], ["meeting", "Meeting"], ["event", "Event"], ["other", "Other"]];
const KIND_NAME = Object.fromEntries(KINDS);
const BLANK = { id: null, title: "", kind: "event", start_date: "", end_date: "", location: "", notes: "" };

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
const todayIso = () => iso(new Date());
const parts = (s) => s.split("-").map(Number);
const addDays = (s, n) => { const [y, m, d] = parts(s); return iso(new Date(y, m - 1, d + n)); };
const shiftMonth = (mo, k) => { const [y, m] = parts(mo + "-01"); const d = new Date(y, m - 1 + k, 1); return d.getFullYear() + "-" + pad(d.getMonth() + 1); };
const gridStart = (mo) => { const [y, m] = parts(mo + "-01"); return addDays(mo + "-01", -((new Date(y, m - 1, 1).getDay() + 6) % 7)); };
const nice = (s) => { const [y, m, d] = parts(s); return d + " " + MONTHS[m - 1].slice(0, 3) + " " + y; };
const span = (e) => (e.end_date && e.end_date !== e.start_date ? nice(e.start_date) + " to " + nice(e.end_date) : nice(e.start_date));
const covers = (e, day) => e.start_date <= day && (e.end_date || e.start_date) >= day;
const longDay = (s) => { const [y, m, d] = parts(s); return DAYS[(new Date(y, m - 1, d).getDay() + 6) % 7] + " " + d + " " + MONTHS[m - 1] + " " + y; };
const kcls = (k) => "k-" + (KIND_NAME[k] ? k : "other");
const yr = (t) => (typeof t.year === "string" || typeof t.year === "number" ? " " + t.year : "");

export default function Calendar() {
  const toast = useToast();
  const [today] = useState(todayIso);
  const [month, setMonth] = useState(() => todayIso().slice(0, 7));
  const [sel, setSel] = useState(todayIso);
  const [data, setData] = useState(null);
  const [bad, setBad] = useState(false);
  const [tick, setTick] = useState(0);
  const [form, setForm] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(null);
  const from = gridStart(month);
  const to = addDays(from, 41);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const r = await api("/api/calendar/events/?from=" + from + "&to=" + to);
        if (!r.ok) throw new Error("load");
        const j = await r.json();
        if (live) { setData(j); setBad(false); }
      } catch { if (live) setBad(true); }
    })();
    return () => { live = false; };
  }, [from, to, tick]);

  const reload = () => setTick((n) => n + 1);
  if (!data && bad) return <ErrorState text="Could not load the calendar." onRetry={reload} />;
  if (!data) return <Loading />;

  const events = data.events || [];
  const terms = (data.terms || []).filter((t) => t.start_date && t.end_date);
  const canEdit = !!data.can_edit;
  const [y, m] = parts(month + "-01");
  const first = month + "-01";
  const monthEnd = addDays(shiftMonth(month, 1) + "-01", -1);
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const date = addDays(from, i);
    cells.push({ date, out: date.slice(0, 7) !== month, ev: events.filter((e) => covers(e, date)), term: terms.some((t) => t.start_date <= date && t.end_date >= date) });
  }
  const inMonth = events.filter((e) => e.start_date <= monthEnd && (e.end_date || e.start_date) >= first).sort((a, b) => a.start_date.localeCompare(b.start_date) || a.title.localeCompare(b.title));
  const monthTerms = terms.filter((t) => t.start_date <= monthEnd && t.end_date >= first);
  const dayEvents = events.filter((e) => covers(e, sel));

  const pick = (d) => { setSel(d); if (d.slice(0, 7) !== month) setMonth(d.slice(0, 7)); };
  const go = (k) => { const nm = shiftMonth(month, k); setMonth(nm); setSel(nm + "-01"); };
  const goToday = () => { const t = todayIso(); setMonth(t.slice(0, 7)); setSel(t); };
  const openAdd = () => { setErr(""); setAsk(null); setForm({ ...BLANK, start_date: sel }); };
  const openEdit = (e) => { setErr(""); setAsk(null); setForm({ id: e.id, title: e.title, kind: e.kind, start_date: e.start_date, end_date: e.end_date || "", location: e.location || "", notes: e.notes || "" }); };
  const set = (k) => (ev) => setForm({ ...form, [k]: ev.target.value });
  const why = async (r) => { try { const j = await r.json(); return j.message || "Could not save."; } catch { return "Could not save."; } };

  const save = async () => {
    const f = form;
    if (!f.title.trim()) { setErr("Enter a title."); return; }
    if (!f.start_date) { setErr("Choose a start date."); return; }
    if (f.end_date && f.end_date < f.start_date) { setErr("The end date cannot be before the start date."); return; }
    setBusy(true); setErr("");
    const body = { title: f.title.trim(), kind: f.kind, start_date: f.start_date, end_date: f.end_date || null, location: f.location.trim(), notes: f.notes.trim() };
    let r;
    try {
      r = f.id ? await api("/api/calendar/events/" + f.id + "/", "PATCH", body) : await api("/api/calendar/events/", "POST", body);
    } catch { setBusy(false); setErr("Could not reach the server."); return; }
    setBusy(false);
    if (!r.ok) { setErr(await why(r)); return; }
    toast(f.id ? "Event updated" : "Event added", "ok");
    setForm(null); setMonth(f.start_date.slice(0, 7)); setSel(f.start_date); reload();
  };

  const remove = async (id) => {
    setBusy(true);
    let r = null;
    try { r = await api("/api/calendar/events/" + id + "/", "DELETE"); } catch { r = null; }
    setBusy(false); setAsk(null);
    if (r && r.ok) { toast("Event deleted", "ok"); reload(); } else { toast("Could not delete", "err"); }
  };

  return (
    <div className="cal">
      <h2>Calendar</h2>
      <div className="cal-bar">
        <div className="cal-nav">
          <Button kind="ghost" size="sm" onClick={() => go(-1)}>Prev</Button>
          <strong className="cal-title" aria-live="polite">{MONTHS[m - 1]} {y}</strong>
          <Button kind="ghost" size="sm" onClick={() => go(1)}>Next</Button>
        </div>
        <div className="cal-act">
          <Button kind="secondary" size="sm" onClick={goToday}>Today</Button>
          {canEdit && <Button kind="teal" size="sm" onClick={openAdd}>Add event</Button>}
        </div>
      </div>
      {bad && <p className="cal-err" role="alert">Could not refresh. Showing the last loaded data.</p>}
      {monthTerms.map((t) => <p key={t.id} className="cal-term">{t.name}{yr(t)}: {nice(t.start_date)} to {nice(t.end_date)}</p>)}
      <div className="cal-grid" role="group" aria-label={MONTHS[m - 1] + " " + y}>
        {DAYS.map((d) => <div key={d} className="cal-wd">{d.slice(0, 3)}</div>)}
        {cells.map((c) => (
          <button
            key={c.date}
            type="button"
            className={"cal-day" + (c.out ? " out" : "") + (c.term ? " term" : "") + (c.date === today ? " today" : "") + (c.date === sel ? " sel" : "")}
            aria-pressed={c.date === sel}
            aria-current={c.date === today ? "date" : undefined}
            aria-label={nice(c.date) + (c.ev.length ? ", " + c.ev.length + (c.ev.length === 1 ? " event" : " events") : "")}
            onClick={() => pick(c.date)}
          >
            <span className="cal-n">{Number(c.date.slice(8))}</span>
            <span className="cal-dots">{c.ev.slice(0, 3).map((e) => <i key={e.id} className={kcls(e.kind)} />)}</span>
          </button>
        ))}
      </div>
      <ul className="cal-key" aria-label="Event types">
        {KINDS.map(([k, n]) => <li key={k}><i className={"k-" + k} />{n}</li>)}
        <li><i className="cal-termkey" />Term</li>
      </ul>
      {form && (
        <Card title={form.id ? "Edit event" : "Add event"}>
          <div className="cal-form">
            <label>Title<input value={form.title} onChange={set("title")} maxLength={120} /></label>
            <label>Type<select value={form.kind} onChange={set("kind")}>{KINDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
            <label>Starts<input type="date" value={form.start_date} onChange={set("start_date")} /></label>
            <label>Ends (optional)<input type="date" value={form.end_date} onChange={set("end_date")} min={form.start_date || undefined} /></label>
            <label>Location (optional)<input value={form.location} onChange={set("location")} maxLength={120} /></label>
            <label>Notes (optional)<textarea rows={3} value={form.notes} onChange={set("notes")} maxLength={1000} /></label>
            {err && <p className="cal-err" role="alert">{err}</p>}
            <div className="cal-act">
              <Button kind="teal" size="sm" onClick={save} disabled={busy}>{busy ? "Saving" : "Save"}</Button>
              <Button kind="ghost" size="sm" onClick={() => setForm(null)} disabled={busy}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}
      <Card title={longDay(sel)}>
        {dayEvents.length === 0 && <p className="cal-empty">No events on this day.</p>}
        {dayEvents.map((e) => (
          <div key={e.id} className="cal-ev">
            <div className="cal-evh"><i className={kcls(e.kind)} />{KIND_NAME[e.kind] || "Other"}</div>
            <strong>{e.title}</strong>
            <div className="cal-sub">{span(e)}{e.location ? ", " + e.location : ""}</div>
            {e.notes && <p className="cal-notes">{e.notes}</p>}
            {canEdit && (ask === e.id ? (
              <div className="cal-act">
                <span>Delete this event?</span>
                <Button kind="secondary" size="sm" onClick={() => remove(e.id)} disabled={busy}>Yes, delete</Button>
                <Button kind="ghost" size="sm" onClick={() => setAsk(null)}>Keep</Button>
              </div>
            ) : (
              <div className="cal-act">
                <Button kind="secondary" size="sm" onClick={() => openEdit(e)}>Edit</Button>
                <Button kind="ghost" size="sm" onClick={() => setAsk(e.id)}>Delete</Button>
              </div>
            ))}
          </div>
        ))}
      </Card>
      <Card title={"Events in " + MONTHS[m - 1] + " " + y}>
        {inMonth.length === 0 && <p className="cal-empty">No events this month.</p>}
        {inMonth.map((e) => (
          <button key={e.id} type="button" className="cal-row" onClick={() => pick(e.start_date < first ? first : e.start_date)}>
            <i className={kcls(e.kind)} />
            <span className="cal-rt">{e.title}</span>
            <span className="cal-rd">{span(e)}</span>
          </button>
        ))}
      </Card>
    </div>
  );
}
