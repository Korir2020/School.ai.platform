import { useEffect, useMemo, useState } from "react";
import { api, listAll } from "./api";
import { Alert, Button, Card, EmptyState, Loading, Select } from "./ui";

const same = (a, b) => String(a ?? "") === String(b ?? "");
const labels = { opener: "Opener", mid: "Mid-term", end: "End-term" };

export default function AdminFinalMarks() {
  const [data, setData] = useState(null);
  const [examId, setExamId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [rows, setRows] = useState({});
  const [saved, setSaved] = useState({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const paths = ["/api/exams/", "/api/subjects/", "/api/enrollments/", "/api/subject-registrations/", "/api/students/", "/api/terms/"];
      const values = await Promise.all(paths.map(listAll));
      setData({ exams: values[0], subjects: values[1], enrollments: values[2], registrations: values[3], students: values[4], terms: values[5] });
    } catch (e) { setError(e?.message || "Could not load administrator final-mark data."); }
  };
  useEffect(() => { load(); }, []);

  const exam = data?.exams.find((item) => same(item.id, examId));
  const term = data?.terms.find((item) => same(item.id, exam?.term));
  const subjects = useMemo(() => data?.subjects.filter((item) => item.is_active !== false) || [], [data]);
  const subject = subjects.find((item) => same(item.id, subjectId));
  const learners = useMemo(() => {
    if (!data || !exam || !subject) return [];
    const registered = new Set(data.registrations.filter((r) => same(r.subject, subject.id) && same(r.academic_year, term?.academic_year)).map((r) => String(r.student)));
    return data.enrollments.filter((e) => e.is_active !== false && same(e.class_level, exam.class_level) && same(e.academic_year, term?.academic_year) && registered.has(String(e.student)))
      .map((e) => data.students.find((s) => same(s.id, e.student))).filter(Boolean)
      .sort((a, b) => String(a.admission_number || "").localeCompare(String(b.admission_number || "")));
  }, [data, exam, subject, term]);

  useEffect(() => {
    if (!exam || !subject) { setRows({}); setSaved({}); return; }
    let alive = true;
    api(`/api/final-subject-marks/?exam=${exam.id}&subject=${subject.id}`).then(async (r) => {
      if (!r.ok) throw new Error("Could not load saved final marks.");
      const existing = await r.json();
      if (!alive) return;
      const next = {}; const statuses = {};
      existing.forEach((row) => { next[row.student] = row.marks ?? ""; statuses[row.student] = row.mark_status; });
      setRows(next); setSaved(Object.fromEntries(existing.map((row) => [row.student, row])));
    }).catch((e) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [exam?.id, subject?.id]);

  const setValue = (student, value) => setRows((current) => ({ ...current, [student]: value }));
  const save = async () => {
    if (!exam || !subject || !learners.length) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await api("/api/final-subject-marks/", "POST", { exam: exam.id, subject: subject.id,
        entries: learners.map((student) => ({ student: student.id, marks: rows[student.id] === "" ? null : rows[student.id], mark_status: rows[student.id] === "" ? "pending" : "scored" })) });
      const body = await response.json(); if (!response.ok) throw new Error(body.detail || "Could not save final marks.");
      setMessage(`${body.saved} final subject mark${body.saved === 1 ? "" : "s"} saved as draft.`); await loadSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const loadSaved = async () => { if (!exam || !subject) return; const r = await api(`/api/final-subject-marks/?exam=${exam.id}&subject=${subject.id}`); if (r.ok) { const items = await r.json(); setSaved(Object.fromEntries(items.map((item) => [item.student, item]))); } };
  const transition = async (row, action) => {
    const reason = action === "approve" || action === "reject" ? window.prompt("Decision reason") : "Administrator workflow action";
    if (reason === null) return;
    const r = await api(`/api/final-subject-marks/${row.id}/${action}/`, "POST", { reason });
    const body = await r.json(); if (!r.ok) setError(body.detail || "Workflow action failed."); else { setMessage(`Final mark ${action}d.`); await loadSaved(); }
  };

  if (error && !data) return <Alert kind="err">{error}</Alert>;
  if (!data) return <Loading />;
  const draftCount = Object.values(saved).filter((row) => row.status === "draft").length;
  return <div>
    <h2>Administrator final subject marks</h2>
    <p>Enter one final subject mark per registered learner. This workflow bypasses paper components for this subject only; teacher paper calculations remain unchanged.</p>
    {error && <Alert kind="err">{error}</Alert>}{message && <Alert kind="info">{message}</Alert>}
    <Card title="Choose examination and subject">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
        <Select label="Draft examination" value={examId} onChange={(e) => { setExamId(e.target.value); setSubjectId(""); }}><option value="">Choose an examination</option>{data.exams.filter((e) => e.status === "draft").map((e) => <option key={e.id} value={e.id}>{e.name} · {labels[e.assessment_type] || e.assessment_type}</option>)}</Select>
        <Select label="Subject" value={subjectId} disabled={!examId} onChange={(e) => setSubjectId(e.target.value)}><option value="">Choose a subject</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.code ? `${s.name} (${s.code})` : s.name}</option>)}</Select>
      </div>
    </Card>
    {exam && subject && (learners.length ? <Card title={`${subject.name} · ${learners.length} registered learner${learners.length === 1 ? "" : "s"}`}>
      <div style={{ overflowX: "auto" }}><table className="mu-table"><thead><tr><th>Learner</th><th>Admission number</th><th>Final mark / 100</th><th>Workflow</th><th>Action</th></tr></thead><tbody>{learners.map((student) => { const row = saved[student.id]; return <tr key={student.id}><td>{[student.first_name, student.last_name].filter(Boolean).join(" ")}</td><td>{student.admission_number || "—"}</td><td><input aria-label={`Final mark for ${student.admission_number}`} type="number" min="0" max="100" step="0.01" value={rows[student.id] ?? ""} disabled={row && row.status !== "draft"} onChange={(e) => setValue(student.id, e.target.value)} /></td><td>{row?.status || "Not saved"}</td><td>{row && row.status === "draft" && <Button kind="secondary" size="sm" onClick={() => transition(row, "submit")}>Submit</Button>}{row && row.status === "submitted" && <Button kind="secondary" size="sm" onClick={() => transition(row, "approve")}>Approve</Button>}{row && row.status === "approved" && <Button kind="secondary" size="sm" onClick={() => transition(row, "lock")}>Lock</Button>}</td></tr>; })}</tbody></table></div>
      <p><Button busy={busy} disabled={busy} onClick={save}>Save final marks as drafts</Button> {draftCount > 0 && <span>{draftCount} draft mark{draftCount === 1 ? "" : "s"} awaiting submission.</span>}</p>
    </Card> : <EmptyState title="No registered learners" text="Only actively enrolled learners registered for the selected subject can receive a direct final mark." />)}
  </div>;
}
