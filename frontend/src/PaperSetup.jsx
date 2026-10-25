import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, Loading, ErrorState } from "./ui";

const num = (v) => Number(v);
const two = (n) => Math.round(n * 100) / 100;

const rowsFor = (papers, sid) =>
  papers
    .filter((p) => String(p.subject) === String(sid))
    .sort((a, b) => a.paper_number - b.paper_number)
    .map((p) => ({
      id: p.id,
      n: String(p.paper_number),
      max: String(num(p.max_marks)),
      w: String(num(p.weight)),
      was: { w: num(p.weight), max: num(p.max_marks) },
    }));

export default function PaperSetup() {
  const toast = useToast();
  const [subjects, setSubjects] = useState(null);
  const [papers, setPapers] = useState([]);
  const [bad, setBad] = useState(false);
  const [sel, setSel] = useState("");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let on = true;
    (async () => {
      try {
        const [s, p] = await Promise.all([list("/api/subjects/"), list("/api/subject-papers/")]);
        if (on) { setSubjects(s); setPapers(p); }
      } catch { if (on) setBad(true); }
    })();
    return () => { on = false; };
  }, []);

  const reload = async () => {
    try {
      const [s, p] = await Promise.all([list("/api/subjects/"), list("/api/subject-papers/")]);
      setSubjects(s); setPapers(p); setBad(false);
      if (sel) setRows(rowsFor(p, sel));
    } catch { setBad(true); }
  };

  const pick = (id) => { setSel(id); setRows(id ? rowsFor(papers, id) : []); };
  const upd = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const drop = (i) => setRows(rows.filter((_, j) => j !== i));
  const add = () => {
    const used = rows.map((r) => num(r.n) || 0);
    setRows([...rows, { id: null, n: String(Math.max(0, ...used) + 1), max: "100", w: "" }]);
  };
  const total = two(rows.reduce((t, r) => t + (num(r.w) || 0), 0));

  const fromMarks = () => {
    const mx = rows.map((r) => num(r.max));
    const sum = mx.reduce((a, b) => a + b, 0);
    if (!sum || mx.some((m) => !(m > 0))) { toast("Enter every maximum first", "err"); return; }
    let used = 0;
    const ws = mx.map((m, i) => {
      if (i === mx.length - 1) return two(100 - used);
      const w = two((m * 100) / sum);
      used = two(used + w);
      return w;
    });
    setRows(rows.map((r, i) => ({ ...r, w: String(ws[i]) })));
  };

  const problem = () => {
    const seen = new Set();
    for (const r of rows) {
      const n = num(r.n);
      const m = num(r.max);
      const w = num(r.w);
      if (!Number.isInteger(n) || n < 1) return "Paper numbers must be 1, 2, 3 and so on.";
      if (seen.has(n)) return "Each paper number can be used once.";
      seen.add(n);
      if (!(m >= 1 && m <= 100)) return "Maximum marks must be between 1 and 100.";
      if (!(w > 0 && w <= 100)) return "Each weight must be above 0 and at most 100.";
    }
    if (rows.length && total !== 100) return "Weights must total 100 (now " + total + ").";
    return "";
  };

  const save = async () => {
    const why = problem();
    if (why) { toast(why, "err"); return; }
    setBusy(true);
    const call = async (path, method, body) => {
      const r = await api(path, method, body);
      if (r.ok) return "";
      const j = await r.json().catch(() => ({}));
      return j.detail || (Object.keys(j).length ? JSON.stringify(j) : "Error " + r.status);
    };
    const old = papers.filter((p) => String(p.subject) === String(sel));
    const keep = new Set(rows.filter((r) => r.id).map((r) => r.id));
    const gone = old.filter((p) => !keep.has(p.id));
    const edits = rows
      .filter((r) => r.id && (num(r.w) !== r.was.w || num(r.max) !== r.was.max))
      .sort((a, b) => num(a.w) - a.was.w - (num(b.w) - b.was.w));
    const fresh = rows.filter((r) => !r.id);
    let err = "";
    for (const p of gone) {
      err = await call("/api/subject-papers/" + p.id + "/", "DELETE");
      if (err) break;
    }
    if (!err) {
      for (const r of edits) {
        err = await call("/api/subject-papers/" + r.id + "/", "PATCH",
          { weight: String(num(r.w)), max_marks: String(num(r.max)) });
        if (err) break;
      }
    }
    if (!err) {
      for (const r of fresh) {
        err = await call("/api/subject-papers/", "POST",
          { subject: num(sel), paper_number: num(r.n), weight: String(num(r.w)), max_marks: String(num(r.max)) });
        if (err) break;
      }
    }
    setBusy(false);
    toast(err ? "Not saved: " + err : "Papers saved", err ? "err" : "ok");
    reload();
  };

  if (bad) return <ErrorState text="Could not load papers." onRetry={reload} />;
  if (!subjects) return <Loading />;
  return (
    <Card title="Subject papers">
      <p className="sub">
        A subject with no papers is one mark out of 100. If a subject has several papers (for
        example theory and practical), add them here with each paper's maximum and weight. Weights
        must total 100. Papers lock once a published exam uses the subject.
      </p>
      <Select id="pp-sub" label="Subject" value={sel} onChange={(e) => pick(e.target.value)}>
        <option value="">Select...</option>
        {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
      {sel && (
        <div>
          {rows.length === 0 && <p className="sub">No papers yet. This subject is one mark out of 100.</p>}
          {rows.map((r, i) => (
            <div key={r.id || "new" + i}
              style={{ borderTop: "1px solid rgba(128,128,128,0.3)", paddingTop: 8, marginTop: 8 }}>
              {r.id
                ? <p><b>Paper {r.n}</b></p>
                : <Input id={"pp-n" + i} label="Paper number" type="number" value={r.n}
                    onChange={(e) => upd(i, "n", e.target.value)} />}
              <Input id={"pp-m" + i} label="Maximum marks" type="number" value={r.max}
                onChange={(e) => upd(i, "max", e.target.value)} />
              <Input id={"pp-w" + i} label="Weight (%)" type="number" value={r.w}
                onChange={(e) => upd(i, "w", e.target.value)} />
              <Button kind="ghost" size="sm" onClick={() => drop(i)}>Remove paper</Button>
            </div>
          ))}
          <p>Weights total: <b>{total}</b> of 100</p>
          <Button kind="ghost" size="sm" onClick={add}>Add paper</Button>{" "}
          {rows.length > 0 && <Button kind="ghost" size="sm" onClick={fromMarks}>Weights from marks</Button>}
          <p><Button kind="teal" busy={busy} disabled={busy} onClick={save}>Save papers</Button></p>
        </div>
      )}
    </Card>
  );
}
