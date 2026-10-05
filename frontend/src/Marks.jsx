import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Select, Card, Badge, DataTable } from "./ui";
import { ConfirmDialog, EmptyState, Loading, ErrorState, Alert } from "./ui";
import PasteMarks from "./PasteMarks";

const names = ["teacher-assignments", "enrollments", "students", "terms",
  "performance"];
const extra = ["subjects", "streams", "class-levels", "subject-papers"];
const kindNames = { opener: "Opener", mid: "Mid-term", end: "End-term" };
const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };

export default function Marks({ d }) {
  const toast = useToast();
  const [data, setData] = useState(null), [bad, setBad] = useState(false);
  const [sel, setSel] = useState(""), [vals, setVals] = useState({});
  const [kind, setKind] = useState("end"), [paper, setPaper] = useState("1");
  const [ask, setAsk] = useState(null), [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const soft = (p) => get(p).catch(() => []);
      const [ta, en, st, tm, pf] = await Promise.all(names.map(get));
      const [sj, sm, cl, sp] = await Promise.all(extra.map(soft));
      setData({ ta, en, st, tm, pf, sj, sm, cl, sp });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  if (bad) return <ErrorState text="Could not load marks." onRetry={load} />;
  if (!data) return <Loading />;
  if (!d.active_term) return <EmptyState title="No active term"
    text="Ask the school admin to set the active term." />;
  const term = data.tm.find((t) => t.id === d.active_term.id);
  if (!term) return <ErrorState text="Active term not found." onRetry={load} />;
  const a = data.ta.find((x) => String(x.id) === sel);
  const rows = a ? data.en.filter((e) => e.stream === a.stream && e.is_active) : [];
  const pick = (arr, id) => arr.find((z) => z.id === id) || {};
  const nameOf = (id) => {
    const s = data.st.find((x) => x.id === id);
    return s ? s.first_name + " " + s.last_name : "Student " + id;
  };
  const label = (x) => (pick(data.sj, x.subject).name || "Subject " + x.subject)
    + " - " + (pick(data.cl, x.class_level).name || x.class_level)
    + " " + (pick(data.sm, x.stream).name || x.stream);
  const nums = a ? data.sp.filter((x) => x.subject === a.subject)
    .map((x) => x.paper_number).sort((x, y) => x - y) : [];
  const papers = nums.length ? nums : [1];
  const pn = papers.includes(Number(paper)) ? Number(paper) : papers[0];
  const old = (sid) => a && data.pf.find((p) => p.student === sid
    && p.subject === a.subject && p.term === term.id && p.paper_number === pn
    && p.assessment_type === kind);
  const badVal = (v) => v !== "" && !(Number(v) >= 1 && Number(v) <= 100);
  const nBad = Object.values(vals).filter(badVal).length;
  const nNew = Object.values(vals).filter((v) => v !== "").length;
  const save = async () => {
    setBusy(true);
    let ok = 0, fail = 0;
    for (const e of rows) {
      const m = vals[e.student];
      if (m === undefined || m === "" || old(e.student)) continue;
      const r = await api("/api/performance/", "POST", { student: e.student,
        subject: a.subject, academic_year: term.academic_year, term: term.id,
        assessment_type: kind, paper_number: pn, marks: m });
      if (r.ok) ok++; else fail++;
    }
    setBusy(false);
    toast("Saved " + ok + ", failed " + fail, fail ? "err" : "ok");
    setVals({}); load();
  };
  const submit = async (p) => {
    setAsk(null);
    const r = await api("/api/performance/" + p.id + "/submit/", "POST");
    toast(r.ok ? "Marks submitted" : "Could not submit", r.ok ? "ok" : "err");
    load();
  };
  const table = rows.map((e) => { const o = old(e.student);
    return { id: e.id, student: e.student, name: nameOf(e.student), o,
      status: o ? o.status : "not entered" }; });
  const cols = [
    { label: "Student", key: "name", sort: true },
    { label: "Marks", render: (r) => (r.o ? r.o.marks :
      <input type="number" min="1" max="100" value={vals[r.student] ?? ""}
        aria-label={"Marks for " + r.name}
        onChange={(ev) => setVals({ ...vals, [r.student]: ev.target.value })} />) },
    { label: "Status", key: "status", sort: true, render: (r) => (r.o
      ? <Badge kind={kinds[r.o.status] || "info"}>{r.o.status}</Badge>
      : "Not entered") },
    { label: "Action", render: (r) => (r.o && r.o.status === "draft"
      ? <Button kind="teal" size="sm" onClick={() => setAsk(r.o)}>Submit</Button>
      : (r.o ? null : <Button kind="ghost" size="sm" onClick={() => setVals({
        ...vals, [r.student]: "1" })}>Absent</Button>)) },
  ];
  return (
    <div>
      <h2>Enter marks</h2>
      <p>{kindNames[kind]}, Paper {pn}</p>
      <Card>
        <Select id="mk-sel" label="Class and subject" value={sel}
          onChange={(e) => { setSel(e.target.value); setVals({}); setPaper("1"); }}>
          <option value="">Choose class and subject</option>
          {(d.assignments || data.ta).map((x) => (
            <option key={x.id} value={x.id}>{label(x)}</option>))}
        </Select>
        {a && <Select id="mk-kind" label="Assessment" value={kind}
          onChange={(e) => { setKind(e.target.value); setVals({}); }}>
          {Object.keys(kindNames).map((k) => (
            <option key={k} value={k}>{kindNames[k]}</option>))}
        </Select>}
        {a && <Select id="mk-paper" label="Paper" value={String(pn)}
          onChange={(e) => { setPaper(e.target.value); setVals({}); }}>
          {papers.map((n) => <option key={n} value={n}>Paper {n}</option>)}
        </Select>}
      </Card>
      {a && <Card>
        <PasteMarks rows={table} st={data.st} vals={vals} setVals={setVals} />
        <DataTable cols={cols} rows={table} search="Search students"
          empty="No students in this class" />
        <p>Absent? Tap Absent to enter 1. Missed every exam? Leave the row empty.</p>
        {nBad > 0 && <Alert kind="err">Marks must be numbers from 1 to 100.</Alert>}
        <Button kind="teal" busy={busy} onClick={save}
          disabled={nNew === 0 || nBad > 0}>
          Save marks{nNew ? " (" + nNew + ")" : ""}</Button>
      </Card>}
      {ask && <ConfirmDialog title="Submit these marks?" confirm="Submit"
        text="Submitted marks go to the admin for approval."
        onYes={() => submit(ask)} onNo={() => setAsk(null)} />}
    </div>
  );
}
