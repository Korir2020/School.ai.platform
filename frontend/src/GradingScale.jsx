import { useState, useEffect } from "react";
import { api } from "./api";
import { Button, Card, Select, Input, Alert, Loading } from "./ui";

const P = "/api/report-module/grading-config/";
const blank = () => ({ label: "", min: "", max: "", points: "" });
const PRESETS = {
  kcse: { pass: 40, best: "7", bands: [["E",0,30,1],["D-",30,35,2],["D",35,40,3],["D+",40,45,4],["C-",45,50,5],["C",50,55,6],["C+",55,60,7],["B-",60,65,8],["B",65,70,9],["B+",70,75,10],["A-",75,80,11],["A",80,100,12]] },
  kjsea: { pass: 0, best: "", bands: [["BE2",0,11,1],["BE1",11,21,2],["AE2",21,31,3],["AE1",31,41,4],["ME2",41,58,5],["ME1",58,75,6],["EE2",75,90,7],["EE1",90,100,8]] },
};
const nice = (s) => String(s).replace(/_/g, " ");

export default function GradingScale({ onSaved }) {
  const [opt, setOpt] = useState(null);
  const [rows, setRows] = useState([blank()]);
  const [pass, setPass] = useState("");
  const [dec, setDec] = useState("2");
  const [rnd, setRnd] = useState("half_up");
  const [mean, setMean] = useState("total_over_max");
  const [absent, setAbsent] = useState("pending");
  const [best, setBest] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [pre, setPre] = useState("");

  useEffect(() => {
    api(P).then(async (r) => {
      if (!r.ok) return setErr("Could not load grading options.");
      const d = await r.json();
      setOpt(d.options);
      if (d.configured) {
        setRows(d.bands.map((b) => ({ label: b[0], min: b[1], max: b[2], points: b[3] })));
        setPass(d.pass_pct); setDec(String(d.decimals)); setRnd(d.rounding);
        setMean(d.mean_rule); setAbsent(d.absent_policy);
        setBest(d.best_n == null ? "" : String(d.best_n));
      }
    }).catch(() => setErr("Could not reach the server."));
  }, []);

  const applyPreset = (k) => {
    setPre(k);
    const q = PRESETS[k];
    if (!q) return;
    setRows(q.bands.map((b) => ({ label: b[0], min: String(b[1]), max: String(b[2]), points: String(b[3]) })));
    setPass(String(q.pass)); setDec("2"); setRnd("half_up"); setMean("total_over_max"); setAbsent("pending"); setBest(q.best);
  };

  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  const check = () => {
    const b = rows.map((r) => ({ label: r.label.trim(), min: Number(r.min), max: Number(r.max), points: Number(r.points), full: r.label.trim() && r.min !== "" && r.max !== "" && r.points !== "" }));
    if (b.some((x) => !x.full || isNaN(x.min) || isNaN(x.max) || isNaN(x.points))) return "Fill every band: label, from, to and points.";
    if (new Set(b.map((x) => x.label)).size !== b.length) return "Two bands have the same label.";
    const o = [...b].sort((a, c) => a.min - c.min);
    if (o[0].min !== 0) return "The lowest band must start at 0.";
    if (o[o.length - 1].max !== 100) return "The highest band must end at 100.";
    for (let i = 0; i < o.length; i++) {
      if (o[i].max <= o[i].min) return "Band " + o[i].label + ": 'to' must be more than 'from'.";
      if (i && o[i].min !== o[i - 1].max) return "Bands must join exactly: check " + o[i - 1].label + " and " + o[i].label + ".";
    }
    if (pass === "" || isNaN(Number(pass))) return "Enter the pass mark.";
    return "";
  };

  const save = async () => {
    const bad = check();
    if (bad) return setErr(bad);
    setErr(""); setBusy(true);
    const body = { bands: rows.map((r) => [r.label.trim(), String(r.min), String(r.max), String(r.points)]), pass_pct: String(pass), decimals: Number(dec), rounding: rnd, mean_rule: mean, absent_policy: absent, best_n: best === "" ? null : Number(best) };
    try {
      const r = await api(P, "PUT", body);
      if (r.ok) onSaved();
      else { let m = "Could not save."; try { const d = await r.json(); m = d.message || d.detail || m; } catch { m = "Could not save."; } setErr(m); }
    } catch { setErr("Could not reach the server."); }
    setBusy(false);
  };

  if (!opt) return err ? <Alert>{err}</Alert> : <Loading />;

  return (
    <div>
      <Card title="Grading scale">
        <p>Enter this school's grade bands. The first must start at 0, the last must end at 100, and each band must start where the one before ends.</p>
        <Select id="gs-pre" label="Start from a standard scale (optional)" value={pre} onChange={(e) => applyPreset(e.target.value)}>
          <option value="">Enter my own</option>
          <option value="kcse">Secondary 8-4-4: KCSE 12-point scale</option>
          <option value="kjsea">Junior school CBE: KJSEA 8 levels</option>
        </Select>
        <p>A starting point only. KNEC does not publish fixed KCSE percentage ranges, so check these against your school's rules and edit any row before saving.</p>
        {rows.map((r, i) => (
          <div key={i}>
            <Input id={"gs-l" + i} label="Grade" value={r.label} onChange={(e) => set(i, "label", e.target.value)} />
            <Input id={"gs-a" + i} label="From %" inputMode="decimal" value={r.min} onChange={(e) => set(i, "min", e.target.value)} />
            <Input id={"gs-b" + i} label="To %" inputMode="decimal" value={r.max} onChange={(e) => set(i, "max", e.target.value)} />
            <Input id={"gs-p" + i} label="Points" inputMode="decimal" value={r.points} onChange={(e) => set(i, "points", e.target.value)} />
            {rows.length > 1 && <p><Button onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove band</Button></p>}
            <hr />
          </div>
        ))}
        <p><Button onClick={() => setRows([...rows, blank()])}>Add band</Button></p>
      </Card>
      <Card title="Rules">
        <Input id="gs-pass" label="Pass mark %" inputMode="decimal" value={pass} onChange={(e) => setPass(e.target.value)} />
        <Input id="gs-dec" label="Decimal places" inputMode="numeric" value={dec} onChange={(e) => setDec(e.target.value)} />
        <Select id="gs-rnd" label="Rounding" value={rnd} onChange={(e) => setRnd(e.target.value)}>{opt.rounding.map((x) => <option key={x} value={x}>{nice(x)}</option>)}</Select>
        <Select id="gs-mean" label="Mean rule" value={mean} onChange={(e) => setMean(e.target.value)}>{opt.mean_rule.map((x) => <option key={x} value={x}>{nice(x)}</option>)}</Select>
        <Select id="gs-abs" label="Absent policy" value={absent} onChange={(e) => setAbsent(e.target.value)}>{opt.absent_policy.map((x) => <option key={x} value={x}>{nice(x)}</option>)}</Select>
        <Input id="gs-best" label="Best N subjects (leave empty for all)" inputMode="numeric" value={best} onChange={(e) => setBest(e.target.value)} />
        {err && <Alert>{err}</Alert>}
        <p><Button busy={busy} onClick={save}>Save grading scale</Button></p>
      </Card>
    </div>
  );
}
