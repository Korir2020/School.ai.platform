import { useEffect, useState } from "react";
import { api, listAll } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card, ConfirmDialog, DataTable, EmptyState, Input, Loading, Modal, Select } from "./ui";

const STATUS = { transferred: "Transferred out", left: "Left school", graduated: "Completed school" };
const read = async (r) => r.json().catch(() => ({}));

function YearEnd({ years, toast, onDone }) {
  const active = years.filter((y) => y.is_active);
  const [from, setFrom] = useState(active.length ? String(active[0].id) : "");
  const [to, setTo] = useState("");
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [choice, setChoice] = useState({}), [pathChoice, setPathChoice] = useState({}), [ask, setAsk] = useState(false);

  useEffect(() => {
    setRows(null); setErr(""); setChoice({}); setPathChoice({});
    if (!from || !to) return;
    api(`/api/promotions/preview/?from_year=${from}&to_year=${to}`).then(async (r) => {
      const j = await read(r);
      if (r.ok) {
        setRows(j.students);
        setPathChoice(Object.fromEntries((j.students || []).filter((row) =>
          row.current_pathway_id && [...(row.pathways || []), ...(row.current_pathways || [])]
            .some((pathway) => String(pathway.id) === String(row.current_pathway_id)))
          .map((row) => [row.student_id, String(row.current_pathway_id)])));
      } else setErr(j.detail || "Could not load students.");
    });
  }, [from, to]);

  const pending = (rows || []).filter((x) => !x.already_moved);
  const pick = (id, v) => setChoice({ ...choice, [id]: v });
  const pickPath = (id, v) => setPathChoice({ ...pathChoice, [id]: v });
  const ids = (v) => Object.keys(choice).filter((k) => choice[k] === v).map(Number);
  const needsPath = (row) => choice[row.student_id] === "repeat"
    ? row.current_pathway_required : choice[row.student_id] === "skip" ? false : row.pathway_required;
  const pathRowsMissing = pending.filter((row) => needsPath(row) && !pathChoice[row.student_id]);
  const run = async () => {
    setAsk(false); setBusy(true);
    const pathways = Object.fromEntries(pending.filter((row) => needsPath(row) && pathChoice[row.student_id])
      .map((row) => [row.student_id, Number(pathChoice[row.student_id])]));
    const r = await api("/api/promotions/run/", "POST", { from_year: from, to_year: to, repeat: ids("repeat"), skip: ids("skip"), pathways });
    const j = await read(r); setBusy(false);
    if (!r.ok) return toast(j.detail || "Promotion failed", "err");
    toast(`${j.promoted} promoted, ${j.repeated} repeating, ${j.graduated} completed school`, "ok");
    setTo(""); onDone();
  };

  const cols = [
    { label: "Student", get: (x) => x.name, render: (x) => <><b>{x.name}</b><small>{x.admission_number}</small></> },
    { label: "Now in", key: "current" },
    { label: "Moves to", get: (x) => x.next || "", render: (x) => x.already_moved ? <Badge kind="ok">Already moved</Badge> : choice[x.student_id] === "repeat" ? `${x.current} (repeat)` : choice[x.student_id] === "skip" ? <span className="sub">Not moved</span> : (x.next || <Badge kind="warn">Completes school</Badge>) },
    { label: "Action", render: (x) => x.already_moved ? null : (() => {
      const paths = choice[x.student_id] === "repeat" ? x.current_pathways || [] : x.pathways || [];
      return <div><select aria-label={`Action for ${x.name}`} value={choice[x.student_id] || ""} onChange={(e) => pick(x.student_id, e.target.value)}>
        <option value="">{x.next ? "Promote" : "Complete school"}</option>
        <option value="repeat">Repeat class</option>
        <option value="skip">Don&apos;t move now</option>
      </select>
      {needsPath(x) && <select aria-label={`Senior pathway for ${x.name}`} value={pathChoice[x.student_id] || ""} onChange={(e) => pickPath(x.student_id, e.target.value)}>
        <option value="">Choose Senior pathway...</option>{paths.map((pathway) => <option key={pathway.id} value={pathway.id}>{pathway.name}</option>)}
      </select>}</div>;
    })() },
  ];

  return (<Card title="Year-end promotion">
    <p className="sub">Moves every active student to the next class in the new year. Streams with the same name carry over. Past marks, reports and fees are kept.</p>
    <div className="transfer-form">
      <Select label="Current year" value={from} onChange={(e) => setFrom(e.target.value)}>
        <option value="">Select year...</option>{years.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
      </Select>
      <Select label="New year" value={to} onChange={(e) => setTo(e.target.value)}>
        <option value="">Select year...</option>{years.filter((y) => String(y.id) !== from).map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
      </Select>
    </div>
    {!years.length && <Alert kind="warn">Add academic years in Setup first. You need the current year and the new year.</Alert>}
    {err && <Alert kind="warn">{err}</Alert>}
    {from && to && !err && !rows && <Loading />}
    {rows && (rows.length ? <>
      <DataTable cols={cols} rows={rows} search="Search students or classes" />
      {pathRowsMissing.length > 0 && <Alert kind="warn">Choose a pathway for each learner entering or repeating in Senior School before moving them.</Alert>}
      <Button kind="teal" busy={busy} disabled={!pending.length || pathRowsMissing.length > 0} onClick={() => setAsk(true)}>Move {pending.length} student{pending.length === 1 ? "" : "s"}</Button>
    </> : <EmptyState title="No active students" text="No students are enrolled in the current year." />)}
    {ask && <ConfirmDialog title="Run year-end promotion?" confirm="Move students"
      text={`${pending.length - ids("skip").length} students will move into the new year (${ids("repeat").length} repeating). Students in the final class will be marked as having completed school.`}
      onYes={run} onNo={() => setAsk(false)} />}
  </Card>);
}

function ExitStudent({ students, toast, onDone }) {
  const blank = { student: "", kind: "transferred", destination: "", reason: "", effective_date: new Date().toISOString().slice(0, 10) };
  const [f, setF] = useState(blank), [busy, setBusy] = useState(false), [ask, setAsk] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const ok = f.student && (f.kind === "left" || f.destination.trim());
  const save = async () => {
    setAsk(false); setBusy(true);
    const r = await api(`/api/students/${f.student}/exit/`, "POST", f);
    const j = await read(r); setBusy(false);
    toast(r.ok ? "Student record updated" : (j.detail || "Could not update student"), r.ok ? "ok" : "err");
    if (r.ok) { setF(blank); onDone(); }
  };
  const who = students.find((s) => String(s.id) === f.student);
  return (<Card title="Transfer out or leaving">
    <p className="sub">The student is removed from current class lists. Their history stays, and you can re-admit them later.</p>
    <div className="transfer-form">
      <Select label="Student" value={f.student} onChange={set("student")}>
        <option value="">Select student...</option>
        {students.map((s) => <option key={s.id} value={s.id}>{s.first_name} {s.last_name} · {s.admission_number}</option>)}
      </Select>
      <Select label="Reason for exit" value={f.kind} onChange={set("kind")}>
        <option value="transferred">Transferred to another school</option>
        <option value="left">Left school</option>
      </Select>
      {f.kind === "transferred" && <Input label="New school" value={f.destination} onChange={set("destination")} maxLength={200} />}
      <Input label="Date" type="date" value={f.effective_date} onChange={set("effective_date")} />
      <Input label="Notes (optional)" value={f.reason} onChange={set("reason")} maxLength={300} />
    </div>
    <Button kind="danger" busy={busy} disabled={!ok} onClick={() => setAsk(true)}>Record exit</Button>
    {ask && who && <ConfirmDialog danger title="Record student exit?" confirm="Record exit"
      text={`${who.first_name} ${who.last_name} will be removed from current class lists.`} onYes={save} onNo={() => setAsk(false)} />}
  </Card>);
}

function Former({ rows, toast, onDone }) {
  const [levels, setLevels] = useState([]), [streams, setStreams] = useState([]), [curricula, setCurricula] = useState([]), [pathways, setPathways] = useState([]);
  const [open, setOpen] = useState(null), [f, setF] = useState({ class_level: "", stream: "", pathway: "" }), [busy, setBusy] = useState(false);
  useEffect(() => {
    listAll("/api/class-levels/").then(setLevels); listAll("/api/streams/").then(setStreams);
    listAll("/api/curriculums/").then(setCurricula); listAll("/api/curriculum-pathways/").then(setPathways);
  }, []);
  const save = async () => {
    setBusy(true);
    const r = await api(`/api/students/${open.id}/readmit/`, "POST", f);
    const j = await read(r); setBusy(false);
    toast(r.ok ? "Student re-admitted" : (j.detail || "Could not re-admit"), r.ok ? "ok" : "err");
    if (r.ok) { setOpen(null); onDone(); }
  };
  const lvlStreams = streams.filter((s) => String(s.class_level) === f.class_level && s.is_active !== false);
  const selectedLevel = levels.find((level) => String(level.id) === f.class_level);
  const curriculum = curricula.find((row) => String(row.id) === String(selectedLevel?.curriculum));
  const isSenior = curriculum?.code?.toUpperCase() === "CBC" && Number(selectedLevel?.level_number) >= 10 && Number(selectedLevel?.level_number) <= 12;
  const availablePathways = pathways.filter((pathway) => pathway.class_levels?.some((id) => String(id) === f.class_level));
  const cols = [
    { label: "Student", get: (x) => x.name, render: (x) => <><b>{x.name}</b><small>{x.admission_number}</small></> },
    { label: "Status", get: (x) => STATUS[x.status], render: (x) => <Badge kind={x.status === "graduated" ? "ok" : "warn"}>{STATUS[x.status] || x.status}</Badge> },
    { label: "Last class", key: "last_class" },
    { label: "Details", get: (x) => x.destination, render: (x) => <>{x.destination}{x.date && <small>{x.date}</small>}</> },
    { label: "Action", render: (x) => <Button size="sm" kind="secondary" onClick={() => { setF({ class_level: "", stream: "" }); setOpen(x); }}>Re-admit</Button> },
  ];
  return (<Card title="Former students">
    <DataTable cols={cols} rows={rows} search="Search former students" empty="No students have left or completed school yet." />
    {open && <Modal title={`Re-admit ${open.name}`} onClose={() => setOpen(null)} actions={<>
      <Button kind="secondary" onClick={() => setOpen(null)}>Cancel</Button>
      <Button kind="teal" busy={busy} disabled={!f.class_level || (isSenior && (!f.pathway || !availablePathways.some((p) => String(p.id) === f.pathway)))} onClick={save}>Re-admit</Button></>}>
      <p className="sub">They join the class you choose in the current academic year.</p>
      <Select label="Class" value={f.class_level} onChange={(e) => setF({ class_level: e.target.value, stream: "", pathway: "" })}>
        <option value="">Select class...</option>{levels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </Select>
      {lvlStreams.length > 0 && <Select label="Stream" value={f.stream} onChange={(e) => setF({ ...f, stream: e.target.value })}>
        <option value="">No stream</option>{lvlStreams.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>}
      {isSenior && <Select label="CBC Senior pathway" value={f.pathway} onChange={(e) => setF({ ...f, pathway: e.target.value })}>
        <option value="">Choose a pathway...</option>{availablePathways.map((pathway) => <option key={pathway.id} value={pathway.id}>{pathway.name}</option>)}
      </Select>}
      {isSenior && availablePathways.length === 0 && <Alert kind="warn">No active Senior pathway is configured for this grade.</Alert>}
    </Modal>}
  </Card>);
}

export default function Promotion() {
  const toast = useToast();
  const [years, setYears] = useState(null), [students, setStudents] = useState([]), [former, setFormer] = useState([]);
  const load = async () => {
    const [y, s, f] = await Promise.all([api("/api/promotions/years/"), listAll("/api/students/"), api("/api/students/former/")]);
    setYears(y.ok ? await y.json() : []);
    const gone = f.ok ? await f.json() : [];
    const out = new Set(gone.map((x) => x.id));
    setStudents(s.filter((x) => !out.has(x.id) && (!x.status || x.status === "active")));
    setFormer(gone);
  };
  useEffect(() => { load(); }, []);
  if (!years) return <Loading />;
  return (<div>
    <h2>Promotion and transfers</h2>
    <p className="sub">Move students up at the end of the year, and record students who transfer, leave or complete school.</p>
    <YearEnd years={years} toast={toast} onDone={load} />
    <ExitStudent students={students} toast={toast} onDone={load} />
    <Former rows={former} toast={toast} onDone={load} />
  </div>);
}
