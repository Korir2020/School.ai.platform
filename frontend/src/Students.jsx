import { useState, useEffect } from "react";
import { api, listAll as list, upload } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, StatCard, DataTable } from "./ui";
import { Loading, ErrorState } from "./ui";
import StudentCenter from "./StudentCenter";

const blank = (stream) => ({ first: "", last: "", adm: "", stream, pathway: "" });
const paths = ["streams", "class-levels", "terms", "students", "curriculums", "curriculum-pathways"];

const cols = [
  { label: "Name", sort: true, get: (r) => r.first_name + " " + r.last_name },
  { label: "Admission no.", key: "admission_number", sort: true },
];

export default function Students({ d }) {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [profile, setProfile] = useState(null);
  const [csv, setCsv] = useState(null), [preview, setPreview] = useState(null), [csvBusy, setCsvBusy] = useState(false);
  const [f, setF] = useState(blank("")), [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, cl, tm, st, cu, pathways] = await Promise.all(paths.map(get));
      const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name || "")
        + " " + s.name;
      const curriculumCode = (level) => (cu.find((row) => row.id === level?.curriculum) || {}).code || "";
      const term = tm.find((t) => t.id === d.active_term.id) || {};
      setX({ sm: sm.map((s) => ({ ...s, label: lab(s) })), cl, pathways,
        curriculumCode, year: term.academic_year, count: st.length, list: st });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const add = async () => {
    if (!selectedStream || (isSenior && !f.pathway)) return;
    setBusy(true);
    const r = await api("/api/students/", "POST", { first_name: f.first,
      last_name: f.last, admission_number: f.adm });
    const s = await r.json().catch(() => ({}));
    if (!r.ok) {
      setBusy(false);
      return toast("Failed: " + (s.detail || JSON.stringify(s)), "err");
    }
    const q = x.sm.find((z) => String(z.id) === f.stream);
    const e = await api("/api/enrollments/", "POST", { student: s.id,
      academic_year: x.year, class_level: q.class_level, stream: q.id,
      ...(isSenior ? { pathway: Number(f.pathway) } : {}),
      is_active: true });
    setBusy(false);
    if (e.ok) toast("Added " + f.first, "ok");
    else toast("Student saved but enrolment failed: "
      + JSON.stringify(await e.json().catch(() => ({}))), "err");
    setF(blank(f.stream)); load();
  };
  if (bad) return <ErrorState text="Could not load students." onRetry={load} />;
  if (!x) return <Loading />;
  if (profile) return <StudentCenter canReceipt studentId={profile} termId={d.active_term && d.active_term.id} onBack={() => setProfile(null)} />;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const selectedStream = x.sm.find((row) => String(row.id) === String(f.stream));
  const selectedLevel = selectedStream && x.cl.find((row) => String(row.id) === String(selectedStream.class_level));
  const isSenior = !!selectedLevel && x.curriculumCode(selectedLevel) === "CBC"
    && selectedLevel.level_number >= 10 && selectedLevel.level_number <= 12;
  const availablePathways = isSenior ? x.pathways.filter((row) =>
    row.curriculum_code === "CBC" && (row.class_levels || []).some((id) => String(id) === String(selectedLevel.id))) : [];
  const downloadCsv = async () => { const r = await api("/api/students/import/"); if (!r.ok) return; const b = await r.blob(); const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "students.csv"; a.click(); URL.revokeObjectURL(u); };
  const inspectCsv = async (commit = false) => { if (!csv) return; setCsvBusy(true); const fd = new FormData(); fd.append("file", csv); fd.append("commit", String(commit)); const r = await upload("/api/students/import/", fd); const j = await r.json().catch(() => ({})); setCsvBusy(false); if (!r.ok) return toast(j.detail || "Could not process CSV", "err"); setPreview(j); if (j.committed) { toast(`${j.created} students imported`, "ok"); setCsv(null); load(); } };
  const tableCols = [...cols, { label: "Profile", render: (r) => <Button size="sm" kind="secondary" onClick={() => setProfile(r.id)}>Open</Button> }];
  return (
    <div>
      <h2>Students</h2>
      <StatCard label="Total students" value={x.count} />
      <Card title="Add student">
        <Input id="st-first" label="First name" value={f.first} onChange={set("first")} />
        <Input id="st-last" label="Last name" value={f.last} onChange={set("last")} />
        <Input id="st-adm" label="Admission number" value={f.adm} onChange={set("adm")} />
        <Select id="st-stream" label="Class / stream" value={f.stream}
          onChange={(e) => setF({ ...f, stream: e.target.value, pathway: "" })}>
          <option value="">Select...</option>
          {x.sm.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </Select>
        {isSenior && <Select id="st-pathway" label="CBC Senior pathway for this academic year" value={f.pathway}
          onChange={set("pathway")}>
          <option value="">Choose a pathway</option>
          {availablePathways.map((pathway) => <option key={pathway.id} value={pathway.id}>{pathway.name}</option>)}
        </Select>}
        {isSenior && availablePathways.length === 0 && <p>No active pathway is configured for this CBC Senior grade.</p>}
        <Button kind="teal" busy={busy} onClick={add}
          disabled={!f.first || !f.last || !f.adm || !f.stream || (isSenior && (!f.pathway || !availablePathways.some((p) => String(p.id) === String(f.pathway))))}>Add student</Button>
      </Card>
        <Card title="Student CSV tools"><p className="sub">Required columns: first_name, last_name, admission_number. Optional: class_level, stream, pathway. For an enrolled CBC Senior learner, pathway is required and must be the configured pathway code or name for that grade. Imports are previewed and rejected rows never commit.</p><div className="csv-actions"><Input label="CSV file" type="file" accept=".csv,text/csv" onChange={e => { setCsv(e.target.files[0] || null); setPreview(null); }} /><Button kind="secondary" onClick={downloadCsv}>Export roster</Button><Button kind="teal" busy={csvBusy} disabled={!csv} onClick={() => inspectCsv(false)}>Preview import</Button></div>{preview && <div className="csv-preview"><b>{preview.preview.length} valid rows · {preview.errors.length} errors</b>{preview.errors.map(x => <p className="csv-error" key={x.row}>Row {x.row}: {x.error}</p>)}{preview.ready && <Button kind="teal" busy={csvBusy} onClick={() => inspectCsv(true)}>Commit valid rows</Button>}</div>}</Card>
        <Card title="All students">
            <DataTable search="Search students" rows={x.list} cols={tableCols}
            empty="No students yet. Add the first one above." />
        </Card>
    </div>
  );
}
