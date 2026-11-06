import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Modal, Loading, ErrorState } from "./ui";
import "./calendar.css";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const KINDS = [["event", "Event"], ["exam", "Exam"], ["meeting", "Meeting"], ["holiday", "Holiday"], ["other", "Other"]];
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
const short = (s) => { const [, m, d] = parts(s); return d + " " + MONTHS[m - 1].slice(0, 3); };
const endOf = (e) => e.end_date || e.start_date;
const span = (e) => (e.end_date && e.end_date !== e.start_date ? short(e.start_date) + " – " + nice(e.end_date) : nice(e.start_date));
const covers = (e, day) => e.start_date <= day && endOf(e) >= day;
const kc = (k) => "k-" + (KIND_NAME[k] ? k : "other");
const days = (a, b) => { const [y1, m1, d1] = parts(a); const [y2, m2, d2] = parts(b); return Math.round((new Date(y2, m2 - 1, d2) - new Date(y1, m1 - 1, d1)) / 864e5); };

export default function Calendar() {
  const toast = useToast();
  const today = todayIso();
  const [month, setMonth] = useState(() => today.slice(0, 7));
  const [data, setData] = useState(null);
  const [bad, setBad] = useState(false);
  const [tick, setTick] = useState(0);
  const [form, setForm] = useState(null);
  const [view, setView] = useState(null); // event being viewed
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(false);
  const [hide, setHide] = useState({});
  const [q, setQ] = useState("");
  const [drag, setDrag] = useState(null); // {a, b} while selecting a range
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

  useEffect(() => {
    const up = () => setDrag((d) => { if (d) finishDrag(d); return null; });
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  });

  const reload = () => setTick((n) => n + 1);
  if (!data && bad) return <ErrorState text="Could not load the calendar." onRetry={reload} />;
  if (!data) return <Loading />;

  const canEdit = !!data.can_edit;
  const terms = (data.terms || []).filter((t) => t.start_date && t.end_date);
  const all = data.events || [];
  const ql = q.trim().toLowerCase();
  const events = all.filter((e) => !hide[KIND_NAME[e.kind] ? e.kind : "other"] && (!ql || (e.title + " " + (e.location || "")).toLowerCase().includes(ql)));
  const [y, m] = parts(month + "-01");
  const upcoming = events.filter((e) => endOf(e) >= today).sort((a, b) => a.start_date.localeCompare(b.start_date)).slice(0, 8);
  const inRange = (d) => drag && d >= (drag.a < drag.b ? drag.a : drag.b) && d <= (drag.a < drag.b ? drag.b : drag.a);

  const go = (k) => setMonth(shiftMonth(month, k));
  const openAdd = (start, end) => { if (!canEdit) return; setErr(""); setView(null); setForm({ ...BLANK, start_date: start || today, end_date: end && end !== start ? end : "" }); };
  const openEdit = (e) => { setErr(""); setView(null); setForm({ id: e.id, title: e.title, kind: e.kind, start_date: e.start_date, end_date: e.end_date || "", location: e.location || "", notes: e.notes || "" }); };
  function finishDrag(d) { const [a, b] = d.a < d.b ? [d.a, d.b] : [d.b, d.a]; openAdd(a, b); }
  const set = (k) => (ev) => setForm({ ...form, [k]: ev.target.value });
  const setDur = (n) => setForm({ ...form, end_date: n ? addDays(form.start_date || today, n) : "" });

  const save = async () => {
    const f = form;
    if (!f.title.trim()) { setErr("Give it a name."); return; }
    if (!f.start_date) { setErr("Choose a start date."); return; }
    if (f.end_date && f.end_date < f.start_date) { setErr("End date can't be before the start."); return; }
    setBusy(true); setErr("");
    const body = { title: f.title.trim(), kind: f.kind, start_date: f.start_date, end_date: f.end_date || null, location: f.location.trim(), notes: f.notes.trim() };
    let r;
    try { r = f.id ? await api("/api/calendar/events/" + f.id + "/", "PATCH", body) : await api("/api/calendar/events/", "POST", body); }
    catch { setBusy(false); setErr("Could not reach the server."); return; }
    setBusy(false);
    if (!r.ok) { let msg = "Could not save."; try { msg = (await r.json()).message || msg; } catch { /* ignore */ } setErr(msg); return; }
    toast(f.id ? "Event updated" : "Event added", "ok");
    setForm(null); setMonth(f.start_date.slice(0, 7)); reload();
  };

  const remove = async (id) => {
    setBusy(true);
    let r = null;
    try { r = await api("/api/calendar/events/" + id + "/", "DELETE"); } catch { r = null; }
    setBusy(false); setAsk(false);
    if (r && r.ok) { toast("Event deleted", "ok"); setView(null); reload(); } else toast("Could not delete", "err");
  };

  const cells = [];
  for (let i = 0; i < 42; i++) {
    const date = addDays(from, i);
    cells.push({ date, out: date.slice(0, 7) !== month, ev: events.filter((e) => covers(e, date)), term: terms.find((t) => t.start_date <= date && t.end_date >= date) });
  }

  return (
    <div className="cal">
      <header className="cal-top">
        <div className="cal-nav">
          <button className="cal-ic" onClick={() => go(-1)} aria-label="Previous month">‹</button>
          <h2 aria-live="polite">{MONTHS[m - 1]} <span>{y}</span></h2>
          <button className="cal-ic" onClick={() => go(1)} aria-label="Next month">›</button>
          <button className="cal-chip" onClick={() => setMonth(today.slice(0, 7))}>Today</button>
        </div>
        <div className="cal-tools">
          <input className="cal-search" placeholder="Search events…" value={q} onChange={(e) => setQ(e.target.value)} />
          {canEdit && <Button kind="teal" size="sm" onClick={() => openAdd(today)}>+ New event</Button>}
        </div>
      </header>

      <div className="cal-filters" role="group" aria-label="Show event types">
        {KINDS.map(([k, n]) => (
          <button key={k} className={"cal-filter " + kc(k) + (hide[k] ? " off" : "")} aria-pressed={!hide[k]} onClick={() => setHide({ ...hide, [k]: !hide[k] })}>
            <i />{n}
          </button>
        ))}
        {canEdit && <span className="cal-hint">Tip: click a day to add, or drag across days for a multi‑day event.</span>}
      </div>
      <section className="cal-stats" aria-label="Overview">
        {(() => {
          const mf = month + "-01", me = addDays(shiftMonth(month, 1) + "-01", -1);
          const mon = events.filter((e) => e.start_date <= me && endOf(e) >= mf);
          const wk = events.filter((e) => e.start_date <= addDays(today, 6) && endOf(e) >= today);
          const next = upcoming[0];
          const term = terms.find((t) => t.start_date <= today && t.end_date >= today);
          return [
            ["This month", mon.length, "events"],
            ["Next 7 days", wk.length, wk.length === 1 ? "event" : "events"],
            ["Exams", mon.filter((e) => e.kind === "exam").length, "this month"],
            ["Next up", next ? next.title : "—", next ? span(next) : "Nothing scheduled", next],
            ["Term", term ? term.name : "Break", term ? days(today, term.end_date) + " days left" : "No active term"],
          ].map(([l, v, s, ev]) => (
            <button key={l} type="button" className={"cal-stat" + (ev ? " wide" : "")} onClick={() => ev && setView(ev)} disabled={!ev}>
              <small>{l}</small><strong>{v}</strong><span>{s}</span>
            </button>
          ));
        })()}
      </section>
      {bad && <p className="cal-err" role="alert">Could not refresh. Showing the last loaded data.</p>}

      <div className="cal-body">
        <div className="cal-grid" onMouseLeave={() => drag && setDrag({ ...drag })}>
          {WD.map((d) => <div key={d} className="cal-wd">{d}</div>)}
          {cells.map((c) => (
            <div
              key={c.date}
              className={"cal-day" + (c.out ? " out" : "") + (c.term ? " term" : "") + (c.date === today ? " today" : "") + (inRange(c.date) ? " pick" : "") + (canEdit ? " editable" : "")}
              title={c.term ? c.term.name : undefined}
              onMouseDown={(e) => { if (canEdit && e.button === 0 && !e.target.closest(".cal-ev")) { e.preventDefault(); setDrag({ a: c.date, b: c.date }); } }}
              onMouseEnter={() => drag && setDrag({ ...drag, b: c.date })}
            >
              <span className="cal-n">{Number(c.date.slice(8))}</span>
              <div className="cal-evs">
                {c.ev.slice(0, 3).map((e) => (
                  <button key={e.id} className={"cal-ev " + kc(e.kind) + (e.start_date === c.date ? " first" : "")} onClick={() => setView(e)} title={e.title}>
                    {e.start_date === c.date || c.date.endsWith("-01") || WD[(cells.indexOf(c)) % 7] === "Mon" ? e.title : "\u00a0"}
                  </button>
                ))}
                {c.ev.length > 3 && <span className="cal-more">+{c.ev.length - 3} more</span>}
              </div>
            </div>
          ))}
        </div>

        <aside className="cal-side">
          <h3>Coming up</h3>
          {upcoming.length === 0 && <p className="cal-empty">Nothing scheduled.</p>}
          {upcoming.map((e) => {
            const n = days(today, e.start_date);
            return (
              <button key={e.id} className="cal-up" onClick={() => setView(e)}>
                <span className={"cal-bar " + kc(e.kind)} />
                <span className="cal-upt"><strong>{e.title}</strong><small>{span(e)}{e.location ? " · " + e.location : ""}</small></span>
                <span className="cal-in">{n <= 0 ? "Now" : n === 1 ? "Tomorrow" : "in " + n + "d"}</span>
              </button>
            );
          })}
          {terms.length > 0 && <><h3>Terms</h3>{terms.map((t) => <p key={t.id} className="cal-term">{t.name}: {short(t.start_date)} – {short(t.end_date)}</p>)}</>}
        </aside>
      </div>

      {view && (
        <Modal title={view.title} onClose={() => { setView(null); setAsk(false); }}
          actions={canEdit && (ask ? (
            <><span>Delete this event?</span><Button kind="secondary" size="sm" onClick={() => remove(view.id)} disabled={busy}>Yes, delete</Button><Button kind="ghost" size="sm" onClick={() => setAsk(false)}>Keep</Button></>
          ) : (
            <><Button kind="teal" size="sm" onClick={() => openEdit(view)}>Edit</Button><Button kind="ghost" size="sm" onClick={() => setAsk(true)}>Delete</Button></>
          ))}>
          <p className="cal-tag"><i className={kc(view.kind)} />{KIND_NAME[view.kind] || "Other"}</p>
          <p><strong>{span(view)}</strong>{view.location ? " · " + view.location : ""}</p>
          {view.notes && <p className="cal-notes">{view.notes}</p>}
        </Modal>
      )}

      {form && (
        <Modal title={form.id ? "Edit event" : "New event"} onClose={() => !busy && setForm(null)}
          actions={<><Button kind="ghost" size="sm" onClick={() => setForm(null)} disabled={busy}>Cancel</Button><Button kind="teal" size="sm" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button></>}>
          <div className="cal-form" onKeyDown={(e) => e.key === "Enter" && e.target.tagName !== "TEXTAREA" && save()}>
            <input className="cal-title-in" autoFocus placeholder="Event name, e.g. End-term exams" value={form.title} onChange={set("title")} maxLength={120} />
            <div className="cal-types">
              {KINDS.map(([k, n]) => <button key={k} type="button" className={"cal-filter " + kc(k) + (form.kind === k ? " on" : " off")} onClick={() => setForm({ ...form, kind: k })}><i />{n}</button>)}
            </div>
            <div className="cal-dates">
              <label>Starts<input type="date" value={form.start_date} onChange={set("start_date")} /></label>
              <label>Ends<input type="date" value={form.end_date} onChange={set("end_date")} min={form.start_date || undefined} /></label>
            </div>
            <div className="cal-quick">
              <span>Length:</span>
              {[["1 day", 0], ["2 days", 1], ["1 week", 6], ["2 weeks", 13]].map(([l, n]) => (
                <button key={l} type="button" className={"cal-chip" + ((form.end_date ? days(form.start_date, form.end_date) : 0) === n ? " on" : "")} onClick={() => setDur(n)}>{l}</button>
              ))}
            </div>
            <label>Location<input value={form.location} onChange={set("location")} maxLength={120} placeholder="Optional" /></label>
            <label>Notes<textarea rows={3} value={form.notes} onChange={set("notes")} maxLength={1000} placeholder="Optional" /></label>
            {err && <p className="cal-err" role="alert">{err}</p>}
          </div>
        </Modal>
      )}
    </div>
  );
}
