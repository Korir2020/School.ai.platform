import { useState, useEffect, useMemo } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Modal, ConfirmDialog, Alert, Loading, ErrorState } from "./ui";
import SetupSection from "./SetupSection";
import "./setup2.css";

// Turn any server reply into a sentence, so the red message is never blank.
const NAMES = { academic_year: "Academic year", name: "Term name",
  start_date: "Start date", end_date: "End date", non_field_errors: "" };
function explain(status, e) {
  if (e && typeof e.detail === "string" && e.detail) return e.detail;
  const parts = Object.entries(e || {}).map(([k, v]) => {
    const msg = Array.isArray(v) ? v.join(" ") : String(v);
    const n = NAMES[k] === undefined ? k : NAMES[k];
    return n ? n + ": " + msg : msg;
  }).filter(Boolean);
  if (parts.length) return parts.join(" ");
  if (status === 403) return "You do not have permission to do this.";
  if (status === 401) return "Please sign in again.";
  if (status >= 500) return "The server had a problem (error " + status + "). Please try again.";
  return "Unexpected error (" + status + ").";
}

const iso = (d) => d.toISOString().slice(0, 10);
const day = (s) => new Date(s + "T00:00:00Z");
const addDays = (s, n) => { const d = day(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
const fmt = (s) => (s ? day(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—");
const weeks = (a, b) => Math.max(0, Math.round(((day(b) - day(a)) / 86400000 + 1) / 7));
const todayIso = () => iso(new Date());
const EMPTY_LIST = [];

function suggestTerm(yid, keep, years, terms) {
  const year = years.find((item) => String(item.id) === String(yid));
  if (!year) return { ...keep, academic_year: yid };
  const matchingTerms = terms.filter((item) => String(item.academic_year) === String(yid))
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
  const used = new Set(matchingTerms.map((item) => item.name.trim().toLowerCase()));
  let number = 1;
  while (used.has("term " + number)) number++;
  const last = matchingTerms[matchingTerms.length - 1];
  const start = last ? addDays(last.end_date, 1) : year.start_date;
  const suggestedStart = start > year.end_date ? year.end_date : start;
  const suggestedEnd = addDays(suggestedStart, 7 * 13 - 1) > year.end_date
    ? year.end_date
    : addDays(suggestedStart, 7 * 13 - 1);
  return {
    ...keep,
    academic_year: String(yid),
    name: "Term " + number,
    start_date: suggestedStart,
    end_date: suggestedEnd,
  };
}

// Pure validation, shared by the add form and the edit dialog.
function termProblems(t, year, others) {
  const p = [];
  if (!year) return ["Choose an academic year."];
  if (!t.name.trim()) p.push("Enter a term name.");
  if (!t.start_date || !t.end_date) p.push("Choose both start and end dates.");
  else {
    if (t.end_date < t.start_date) p.push("End date must not be before start date.");
    if (t.start_date < year.start_date || t.end_date > year.end_date)
      p.push(`Dates must fall inside ${year.name} (${fmt(year.start_date)} – ${fmt(year.end_date)}).`);
  }
  if (others.some((o) => o.name.trim().toLowerCase() === t.name.trim().toLowerCase()))
    p.push(`${year.name} already has a term called "${t.name.trim()}".`);
  return p;
}
function overlaps(t, others) {
  if (!t.start_date || !t.end_date) return [];
  return others.filter((o) => t.start_date <= o.end_date && t.end_date >= o.start_date);
}

const emptyYear = { name: "", start_date: "", end_date: "" };

export default function Terms() {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [y, setY] = useState(emptyYear);
  const [t, setT] = useState({ academic_year: "", name: "", start_date: "", end_date: "", is_active: true });
  const [ed, setEd] = useState(null), [ask, setAsk] = useState(null);
  const [busy, setBusy] = useState(""), [err, setErr] = useState({});
  const load = async (initializeTerm = false) => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [yr, tm] = await Promise.all(["academic-years", "terms"].map(get));
      yr.sort((a, b) => (b.start_date || "").localeCompare(a.start_date || ""));
      setX({ yr, tm }); setBad(false);
      if (initializeTerm && yr.length) {
        setT((current) => current.academic_year
          ? current
          : suggestTerm(yr[0].id, current, yr, tm));
      }
      return { yr, tm };
    } catch { setBad(true); return null; }
  };
  useEffect(() => {
    // This effect initiates async API reads; state updates happen after the requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    load(true);
  }, []);

  const send = async (key, path, method, body, ok, afterLoad) => {
    setBusy(key); setErr((e) => ({ ...e, [key]: "" }));
    let r, e = {};
    try { r = await api(path, method, body); if (!r.ok) e = await r.json().catch(() => ({})); }
    catch { r = { ok: false, status: 0 }; e = { detail: "Network problem. Check your connection and try again." }; }
    setBusy("");
    if (r.ok) {
      toast(ok || "Saved", "ok");
      window.dispatchEvent(new Event("marian:dashboard-refresh"));
    } else {
      const m = explain(r.status, e);
      setErr((s) => ({ ...s, [key]: m })); toast("Could not save: " + m, "err");
    }
    const data = await load();
    if (r.ok && afterLoad) afterLoad(data);
    return r.ok;
  };

  const yrs = x ? x.yr : EMPTY_LIST;
  const tms = x ? x.tm : EMPTY_LIST;
  const yearOf = (id) => yrs.find((a) => String(a.id) === String(id));
  const termsOf = (id) => tms.filter((m) => String(m.academic_year) === String(id))
    .sort((a, b) => a.start_date.localeCompare(b.start_date));

  const current = useMemo(() => {
    const act = tms.filter((m) => m.is_active).sort((a, b) => b.start_date.localeCompare(a.start_date));
    return act[0] || null;
  }, [tms]);

  if (bad) return <ErrorState text="Could not load terms." onRetry={() => load(true)} />;
  if (!x) return <Loading />;

  const ty = yearOf(t.academic_year);
  const others = ty ? termsOf(ty.id) : [];
  const probs = termProblems(t, ty, others);
  const clash = overlaps(t, others);

  const addTerm = async () => {
    const body = { academic_year: Number(t.academic_year), name: t.name.trim(),
      start_date: t.start_date, end_date: t.end_date, is_active: !!t.is_active };
    await send("term", "/api/terms/", "POST", body, `${body.name} added to ${ty.name}`, (data) => {
      if (data) setT((currentForm) => suggestTerm(currentForm.academic_year, currentForm, data.yr, data.tm));
    });
  };
  const yProbs = [];
  if (y.start_date && y.end_date && y.end_date < y.start_date) yProbs.push("End date must not be before start date.");
  if (y.name && yrs.some((a) => a.name.trim().toLowerCase() === y.name.trim().toLowerCase())) yProbs.push(`Year "${y.name}" already exists.`);
  const addYear = async () => {
    const body = { ...y, name: y.name.trim(), is_active: true };
    if (await send("year", "/api/academic-years/", "POST", body, `Academic year ${body.name} added`, (data) => {
      if (data && !t.academic_year && data.yr.length) {
        setT((currentForm) => currentForm.academic_year
          ? currentForm
          : suggestTerm(data.yr[0].id, currentForm, data.yr, data.tm));
      }
    })) setY(emptyYear);
  };
  const nextYear = () => {
    const n = (yrs[0] && parseInt(yrs[0].name, 10)) || new Date().getFullYear();
    const nm = String(yrs.length ? n + 1 : n);
    setY({ name: nm, start_date: nm + "-01-01", end_date: nm + "-12-31" });
  };

  const tpath = (m) => "/api/terms/" + m.id + "/";
  const toggle = (m) => (m.is_active ? setAsk(m)
    : send("row" + m.id, tpath(m), "PATCH", { is_active: true }, m.name + " turned on"));

  const edYear = ed && ed.kind === "term" ? yearOf(ed.row.academic_year) : null;
  const edProbs = ed && ed.kind === "term"
    ? termProblems(ed, edYear, termsOf(ed.row.academic_year).filter((o) => o.id !== ed.row.id))
    : ed && ed.end_date < ed.start_date ? ["End date must not be before start date."] : [];
  const saveEdit = async () => {
    const body = { start_date: ed.start_date, end_date: ed.end_date };
    if (ed.kind === "term") body.name = ed.name.trim();
    if (await send("edit", ed.path, "PATCH", body, "Changes saved")) setEd(null);
  };

  const now = todayIso();
  const prog = current ? Math.min(100, Math.max(0, Math.round(((day(now) - day(current.start_date)) / (day(current.end_date) - day(current.start_date) || 1)) * 100))) : 0;
  const left = current ? Math.ceil((day(current.end_date) - day(now)) / 86400000) : 0;
  const status = (m) => (!m.is_active ? ["off", "Off"] : current && m.id === current.id ? ["live", "In use"] : m.end_date < now ? ["done", "Ended"] : m.start_date > now ? ["next", "Upcoming"] : ["on", "Active"]);

  const calendarComplete = yrs.length > 0 && tms.some((m) => m.is_active);
  return (
    <SetupSection id="setup-terms" title="Academic calendar" summary={`${yrs.length} year${yrs.length === 1 ? "" : "s"}, ${tms.length} term${tms.length === 1 ? "" : "s"}${current ? " · active term" : ""}`} complete={calendarComplete}>

      <div className={"s2-now" + (current ? "" : " empty")}>
        {current ? <>
          <div><small>Term in use</small><b>{current.name} · {(yearOf(current.academic_year) || {}).name}</b>
            <span>{fmt(current.start_date)} – {fmt(current.end_date)}</span></div>
          <div className="s2-prog"><i style={{ width: prog + "%" }} /></div>
          <em>{left > 0 ? `${left} days left` : left === 0 ? "Ends today" : "Ended — add or turn on the next term"}</em>
        </> : <div><small>No term in use</small><b>Add a term and keep it switched on</b><span>Marks, exams and reports need an active term.</span></div>}
      </div>

      <div className="s2-cols">
        <div className="s2-panel">
          <h4>Calendar</h4>
          {yrs.length === 0 ? <p className="s2-mut">No academic years yet. Add one to start.</p> : yrs.map((a) => {
            const ts = termsOf(a.id);
            return (
              <div key={a.id} className="s2-year">
                <div className="s2-yh">
                  <div><b>{a.name}</b><span>{fmt(a.start_date)} – {fmt(a.end_date)} · {ts.length} term{ts.length === 1 ? "" : "s"}</span></div>
                  <div className="s2-acts">
                    <Button kind="ghost" size="sm" onClick={() => setT((c) => suggestTerm(a.id, c, yrs, tms))}>+ Term</Button>
                    <Button kind="ghost" size="sm" onClick={() => setEd({ kind: "year", path: "/api/academic-years/" + a.id + "/", row: a, start_date: a.start_date, end_date: a.end_date })}>Edit</Button>
                  </div>
                </div>
                {ts.length === 0 ? <p className="s2-mut s2-pad">No terms in this year yet.</p> : (
                  <ul className="s2-terms">
                    {ts.map((m) => { const [k, l] = status(m); return (
                      <li key={m.id}>
                        <div className="s2-tn"><b>{m.name}</b><span>{fmt(m.start_date)} – {fmt(m.end_date)} · {weeks(m.start_date, m.end_date)} wks</span></div>
                        <span className={"s2-pill " + k}>{l}</span>
                        <div className="s2-acts">
                          <Button kind="ghost" size="sm" busy={busy === "row" + m.id} onClick={() => toggle(m)}>{m.is_active ? "Turn off" : "Turn on"}</Button>
                          <Button kind="ghost" size="sm" onClick={() => setEd({ kind: "term", path: tpath(m), row: m, name: m.name, start_date: m.start_date, end_date: m.end_date })}>Edit</Button>
                        </div>
                      </li>); })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>

        <div className="s2-stack">
          <div className="s2-panel" id="setup-add-term">
            <h4>Add term</h4>
            {yrs.length === 0 ? <Alert kind="info">Add an academic year first, then its terms.</Alert> : <>
              <Select id="tm-year" label="Academic year" value={t.academic_year}
                onChange={(e) => setT((c) => suggestTerm(e.target.value, c, yrs, tms))}>
                <option value="">Select...</option>
                {yrs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </Select>
              {ty && <p className="s2-hint">{ty.name} runs {fmt(ty.start_date)} – {fmt(ty.end_date)}</p>}
              <div className="s2-chips">{["Term 1", "Term 2", "Term 3"].map((n) => (
                <button type="button" key={n} className={"s2-chip" + (t.name === n ? " on" : "")} onClick={() => setT({ ...t, name: n })}>{n}</button>))}</div>
              <Input id="tm-name" label="Term name" maxLength={20} value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
              <div className="s2-two">
                <Input id="tm-start" label="Starts" type="date" min={ty && ty.start_date} max={ty && ty.end_date} value={t.start_date} onChange={(e) => setT({ ...t, start_date: e.target.value })} />
                <Input id="tm-end" label="Ends" type="date" min={t.start_date || (ty && ty.start_date)} max={ty && ty.end_date} value={t.end_date} onChange={(e) => setT({ ...t, end_date: e.target.value })} />
              </div>
              {t.start_date && t.end_date && t.end_date >= t.start_date && <p className="s2-hint">{weeks(t.start_date, t.end_date)} weeks</p>}
              <label className="s2-check"><input type="checkbox" checked={!!t.is_active} onChange={(e) => setT({ ...t, is_active: e.target.checked })} /> Switch on now</label>
              {t.academic_year && probs.length > 0 && <ul className="s2-errs">{probs.map((p) => <li key={p}>{p}</li>)}</ul>}
              {probs.length === 0 && clash.length > 0 && <Alert kind="warn">Overlaps {clash.map((c) => c.name).join(", ")}. You can still save.</Alert>}
              {err.term && <Alert kind="err">{err.term}</Alert>}
              <Button kind="teal" busy={busy === "term"} disabled={probs.length > 0 || !!busy} onClick={addTerm}>Add term</Button>
            </>}
          </div>

          <div className="s2-panel">
            <div className="s2-ph"><h4>Add academic year</h4><button type="button" className="s2-chip" onClick={nextYear}>Fill {yrs.length ? "next" : "this"} year</button></div>
            <Input id="yr-name" label="Year name, e.g. 2026" value={y.name} onChange={(e) => setY({ ...y, name: e.target.value })} />
            <div className="s2-two">
              <Input id="yr-start" label="Starts" type="date" value={y.start_date} onChange={(e) => setY({ ...y, start_date: e.target.value })} />
              <Input id="yr-end" label="Ends" type="date" min={y.start_date} value={y.end_date} onChange={(e) => setY({ ...y, end_date: e.target.value })} />
            </div>
            {yProbs.length > 0 && <ul className="s2-errs">{yProbs.map((p) => <li key={p}>{p}</li>)}</ul>}
            {err.year && <Alert kind="err">{err.year}</Alert>}
            <Button kind="teal" busy={busy === "year"} disabled={!y.name.trim() || !y.start_date || !y.end_date || yProbs.length > 0 || !!busy} onClick={addYear}>Add year</Button>
          </div>
        </div>
      </div>

      {ed && <Modal title={ed.kind === "term" ? "Edit " + ed.row.name : "Edit " + ed.row.name + " dates"} onClose={() => setEd(null)} actions={<>
        <Button kind="secondary" onClick={() => setEd(null)}>Cancel</Button>
        <Button kind="teal" busy={busy === "edit"} disabled={edProbs.length > 0} onClick={saveEdit}>Save</Button></>}>
        {ed.kind === "term" && <Input id="ed-name" label="Term name" maxLength={20} value={ed.name} onChange={(e) => setEd({ ...ed, name: e.target.value })} />}
        <Input id="ed-start" label="Starts" type="date" value={ed.start_date} onChange={(e) => setEd({ ...ed, start_date: e.target.value })} />
        <Input id="ed-end" label="Ends" type="date" value={ed.end_date} onChange={(e) => setEd({ ...ed, end_date: e.target.value })} />
        {edProbs.length > 0 && <ul className="s2-errs">{edProbs.map((p) => <li key={p}>{p}</li>)}</ul>}
        {err.edit && <Alert kind="err">{err.edit}</Alert>}
      </Modal>}
      {ask && <ConfirmDialog title={"Turn off " + ask.name + "?"} danger
        text="The app uses the active term with the latest start date, so this may change which term is used."
        confirm="Turn off" onYes={() => {
          send("row" + ask.id, tpath(ask), "PATCH", { is_active: false }, ask.name + " turned off"); setAsk(null); }}
        onNo={() => setAsk(null)} />}
    </SetupSection>
  );
}
