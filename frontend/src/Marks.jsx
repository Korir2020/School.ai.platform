import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Select, Card, Badge, DataTable } from "./ui";
import { ConfirmDialog, EmptyState, Loading, ErrorState } from "./ui";

const names = ["teacher-assignments", "enrollments", "students", "terms",
  "performance"];
const extra = ["subjects", "streams", "class-levels"];
const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };

export default function Marks({ d }) {
  const toast = useToast();
  const [data, setData] = useState(null), [bad, setBad] = useState(false);
  const [sel, setSel] = useState(""), [vals, setVals] = useState({});
  const [ask, setAsk] = useState(null), [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const soft = (p) => get(p).catch(() => []);
      const [ta, en, st, tm, pf] = await Promise.all(names.map(get));
      const [sj, sm, cl] = await Promise.all(extra.map(soft));
      setData({ ta, en, st, tm, pf, sj, sm, cl });
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
  const old = (sid) => a && data.pf.find((p) => p.student === sid
    && p.subject === a.subject && p.term === term.id && p.paper_number === 1
    && p.assessment_type === "end");
  const save = async () => {
    setBusy(true);
    let ok = 0, fail = 0;
    for (const e of rows) {
      const m = vals[e.student];
      if (m === undefined || m === "" || old(e.student)) continue;
      const r = await api("/api/performance/", "POST", { student: e.student,
        subject: a.subject, academic_year: term.academic_year, term: term.id,
        assessment_type: "end", paper_number: 1, marks: m });
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
      <input type="number" min="0" max="100" value={vals[r.student] ?? ""}
        aria-label={"Marks for " + r.name}
        onChange={(ev) => setVals({ ...vals, [r.student]: ev.target.value })} />) },
    { label: "Status", key: "status", sort: true, render: (r) => (r.o
      ? <Badge kind={kinds[r.o.status] || "info"}>{r.o.status}</Badge>
      : "Not entered") },
    { label: "Action", render: (r) => (r.o && r.o.status === "draft"
      ? <Button kind="teal" size="sm" onClick={() => setAsk(r.o)}>Submit</Button>
      : null) },
  ];
  return (
    <div>
      <h2>Enter marks</h2>
      <p>End-term, Paper 1</p>
      <Card>
        <Select id="mk-sel" label="Class and subject" value={sel}
          onChange={(e) => setSel(e.target.value)}>
          <option value="">Choose class and subject</option>
          {(d.assignments || data.ta).map((x) => (
            <option key={x.id} value={x.id}>{label(x)}</option>))}
        </Select>
      </Card>
      {a && <Card>
        <DataTable cols={cols} rows={table} search="Search students"
          empty="No students in this class" />
        <Button kind="teal" busy={busy} onClick={save}
          disabled={!Object.keys(vals).length}>Save marks</Button>
      </Card>}
      {ask && <ConfirmDialog title="Submit these marks?" confirm="Submit"
        text="Submitted marks go to the admin for approval."
        onYes={() => submit(ask)} onNo={() => setAsk(null)} />}
    </div>
  );
}
