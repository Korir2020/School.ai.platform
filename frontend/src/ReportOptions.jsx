import { useState } from "react";
import { api } from "./api";
import { Button, Alert, Loading } from "./ui";

const P = "/api/report-module/";

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

const LABELS = {
  best_points: "Best points (KCSE best 7)",
  total_marks: "Total marks",
  competition: "Competition (1, 1, 3)",
  dense: "Dense (1, 1, 2)",
  ordinal: "Ordinal (1, 2, 3)",
};

export default function ReportOptions() {
  const [o, setO] = useState(null);
  const [ch, setCh] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const fill = (d) => {
    const x = d.options || {};
    setO({ ...x, footer_note: x.footer_note || "" });
    if (d.choices) setCh(d.choices);
  };

  const load = async () => {
    setMsg(""); setBusy(true);
    try {
      const r = await api(P + "options/");
      if (!r.ok) setMsg(await errText(r));
      else fill(await r.json());
    } catch { setMsg("Could not load options."); }
    setBusy(false);
  };

  const save = async () => {
    const w = Number(o.weak_pct);
    if (!Number.isFinite(w) || w < 0 || w > 100) { setMsg("Weak-subject threshold must be 0 to 100."); return; }
    if ((o.footer_note || "").trim().length > 200) { setMsg("Footer text must be 200 characters or less."); return; }
    setMsg(""); setBusy(true);
    try {
      const body = {
        previous_exams: Number(o.previous_exams),
        rank_by: o.rank_by,
        tie_policy: o.tie_policy,
        allow_provisional: !!o.allow_provisional,
        weak_pct: w,
        footer_note: (o.footer_note || "").trim(),
      };
      const r = await api(P + "options/", "PUT", { options: body });
      if (!r.ok) setMsg(await errText(r));
      else { fill(await r.json()); setMsg("Saved."); }
    } catch { setMsg("Save failed."); }
    setBusy(false);
  };

  const set = (k, v) => setO({ ...o, [k]: v });
  const box = { width: "100%", padding: 8, boxSizing: "border-box" };

  return (
    <div>
      <h4>Report options</h4>
      <p>Applies to every report card in your school. Nothing changes until you save.</p>
      {msg && <Alert>{msg}</Alert>}
      {busy && !o && <Loading />}
      {!o && <p><Button busy={busy} onClick={load}>Load options</Button></p>}
      {o && ch && (
        <div>
          <p><label>Previous exams in Progress History<br />
            <select style={box} value={o.previous_exams} onChange={(e) => set("previous_exams", Number(e.target.value))}>
              {ch.previous_exams.map((n) => <option key={n} value={n}>{n}</option>)}
            </select></label></p>
          <p><label>Rank students by<br />
            <select style={box} value={o.rank_by} onChange={(e) => set("rank_by", e.target.value)}>
              {ch.rank_by.map((v) => <option key={v} value={v}>{LABELS[v] || v}</option>)}
            </select></label></p>
          <p><label>Tie style<br />
            <select style={box} value={o.tie_policy} onChange={(e) => set("tie_policy", e.target.value)}>
              {ch.tie_policy.map((v) => <option key={v} value={v}>{LABELS[v] || v}</option>)}
            </select></label></p>
          <p><label><input type="checkbox" checked={!!o.allow_provisional} onChange={(e) => set("allow_provisional", e.target.checked)} /> Allow provisional reports</label></p>
          <p><label>Weak-subject threshold (%)<br />
            <input type="number" min="0" max="100" style={box} value={o.weak_pct} onChange={(e) => set("weak_pct", e.target.value)} /></label></p>
          <p><label>Footer text (max 200 characters)<br />
            <input type="text" maxLength={200} style={box} value={o.footer_note} onChange={(e) => set("footer_note", e.target.value)} /></label></p>
          <p><Button busy={busy} onClick={save}>Save options</Button></p>
        </div>
      )}
    </div>
  );
}
