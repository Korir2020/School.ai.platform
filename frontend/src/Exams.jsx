import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, Badge, DataTable } from "./ui";
import { ConfirmDialog, Loading, ErrorState } from "./ui";

const paths = ["exams", "enrollments", "class-levels"];

export default function Exams({ d }) {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [name, setName] = useState(""), [lvl, setLvl] = useState("");
  const [assessmentType, setAssessmentType] = useState("end");
  const [res, setRes] = useState(null), [ask, setAsk] = useState(null);
  const [busy, setBusy] = useState(false);
  const [scope, setScope] = useState("class");
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [ex, en, cl] = await Promise.all(paths.map(get));
      const ids = [...new Set(en.map((e) => e.class_level))];
      setX({ ex, levels: cl.filter((c) => ids.includes(c.id)) });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const create = async () => {
    setBusy(true);
    const r = await api("/api/exams/", "POST", { name, term: d.active_term.id,
      assessment_type: assessmentType, class_level: lvl });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) { toast("Exam created", "ok"); setName(""); setAssessmentType("end"); load(); }
    else toast("Failed: " + JSON.stringify(j), "err");
  };
  const publish = async (e) => {
    setAsk(null);
    const r = await api("/api/exams/" + e.id + "/publish/", "POST");
    const j = await r.json().catch(() => ({}));
    const more = j.count ? " (" + j.count + " problems)" : "";
    if (r.ok) toast("Published " + e.name, "ok");
    else toast((j.detail || "Failed") + more, "err");
    load();
  };
  const view = async (e) => {
    const r = await api("/api/exams/" + e.id + "/results/");
    if (r.ok) setRes(await r.json());
    else toast("Could not load results", "err");
  };
  if (bad) return <ErrorState text="Could not load exams." onRetry={load} />;
  if (!x) return <Loading />;
  const cols = [
    { label: "Exam", key: "name", sort: true },
    { label: "Assessment", key: "assessment_type", sort: true,
      render: (e) => ({ opener: "Opener", mid: "Mid-term", end: "End-term" }[e.assessment_type] || e.assessment_type) },
    { label: "Status", key: "status", sort: true, render: (e) => (
      <Badge kind={e.status === "draft" ? "info" : "ok"}>{e.status}</Badge>) },
    { label: "Actions", render: (e) => (e.status === "draft"
      ? <Button kind="teal" size="sm" onClick={() => setAsk(e)}>Publish</Button>
      : <Button kind="secondary" size="sm" onClick={() => view(e)}>Results</Button>
    ) },
  ];
  const isStream = scope === "stream";
  const pos = (r) => (isStream ? r.stream_rank : r.class_rank);
  const other = (r) => (isStream ? r.class_rank : r.stream_rank);
  const rk = (v) => (v == null ? "No rank" : v);
  const showRanks = res?.result_mode !== "achievement_levels" && res?.rankings_enabled !== false;
  const rcols = [
    ...(showRanks ? [
      { label: isStream ? "Stream position" : "Class position", key: isStream ? "stream_rank" : "class_rank", sort: true, render: (r) => rk(pos(r)) },
    ] : []),
    { label: "Student", key: "name", sort: true },
    { label: "Admission no.", key: "admission_number", sort: true },
    ...(res?.framework_key === "cbe_senior" ? [
      { label: "Pathway", key: "pathway", sort: true, render: (r) => r.pathway || "—" },
      { label: "Registered subject combination", get: (r) => (r.subject_combination || []).join(", "),
        render: (r) => (r.subject_combination || []).join(", ") || "—" },
    ] : []),
    { label: res?.result_mode === "achievement_levels" ? "Overall progress summary" : "Average", key: "overall_average", sort: true,
      render: (r) => res?.result_mode === "achievement_levels" ? (r.overall_summary || "—") : r.overall_average + "%" },
    ...(res?.result_mode === "marks" && ["cbe_primary", "cbe_junior_levels", "cbe_senior"].includes(res?.framework_key) ? [
      { label: "School-configured overall grade", key: "overall_grade", render: (r) => r.overall_grade || "—" },
      { label: "Subject results (percentage · grade)", get: (r) => Object.entries(r.subject_scores || {}).map(([subject, score]) => `${subject}: ${score}% · ${r.subject_grades?.[subject] || "—"}`).join("; "),
        render: (r) => Object.entries(r.subject_scores || {}).map(([subject, score]) => `${subject}: ${score}% · ${r.subject_grades?.[subject] || "—"}`).join("; ") || "—" },
    ] : []),
    ...(res?.result_mode === "achievement_levels" ? [{
      label: "School-defined subject levels", get: (r) => Object.entries(r.subject_scores || {}).map(([subject, level]) => `${subject}: ${level.label}`).join("; "),
      render: (r) => Object.entries(r.subject_scores || {}).map(([subject, level]) => `${subject}: ${level.label}`).join("; ") || "—",
    }] : []),
    ...(res?.result_mode === "achievement_levels" ? [] : [{
      label: "Paper dispositions", get: (r) => Object.entries(r.subject_statuses || {}).map(
        ([subjectName, papers]) => `${subjectName} ${Object.entries(papers).map(([paper, status]) => `P${paper}: ${status.replaceAll("_", " ")}`).join(", ")}`,
      ).join("; "), render: (r) => {
        const text = Object.entries(r.subject_statuses || {}).map(
          ([subjectName, papers]) => `${subjectName}: ${Object.entries(papers).map(([paper, status]) => `P${paper} ${status.replaceAll("_", " ")}`).join(", ")}`,
        ).join("; ");
        return text || "—";
      },
    }]),
    ...(showRanks ? [
      { label: isStream ? "Class position" : "Stream position", key: isStream ? "class_rank" : "stream_rank", sort: true, render: (r) => rk(other(r)) },
    ] : []),
  ];
  const byScope = (a, b) => (pos(a) ?? 1e9) - (pos(b) ?? 1e9);
  return (
    <div>
      <h2>Examinations</h2>
      <p className="sub">Create one Opener, Mid-term, or End-term examination per class and term. Each examination has its own approval, publication, results, and report route.</p>
      <Card>
        <DataTable cols={cols} rows={x.ex} search="Search exams"
          empty="No exams yet" />
      </Card>
      <Card title="Create exam">
        <Input id="ex-name" label="Exam name" value={name}
          onChange={(e) => setName(e.target.value)} />
        <Select id="ex-lvl" label="Class level" value={lvl}
          onChange={(e) => setLvl(e.target.value)}>
          <option value="">Select...</option>
          {x.levels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select id="ex-assessment" label="Assessment type" value={assessmentType}
          onChange={(e) => setAssessmentType(e.target.value)}>
          <option value="opener">Opener</option>
          <option value="mid">Mid-term</option>
          <option value="end">End-term</option>
        </Select>
        <Button kind="teal" busy={busy} onClick={create}
          disabled={!name || !lvl}>Create exam</Button>
      </Card>
      {res && <Card title={"Results: " + res.exam}>
        <p className="sub">{res.result_mode === "achievement_levels"
          ? res.notice
          : `Internal school assessment results for this examination; positions are not comparable with other exams. ${res.results.length} learner${res.results.length === 1 ? "" : "s"} listed.`}</p>
        {showRanks && <Select id="rank-scope" label="Ranking scope" value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="class">Class position</option>
          <option value="stream">Stream position</option>
        </Select>}
        {res.result_mode === "achievement_levels" && res.performance_summary && <div>
          <p><b>Class descriptor distribution:</b> {Object.entries(res.performance_summary.class || {}).map(([label, n]) => `${label}: ${n}`).join(" · ") || "No approved descriptor outcomes."}</p>
          {Object.entries(res.performance_summary.streams || {}).map(([stream, counts]) => <p key={stream}><b>{stream || "No stream"}:</b> {Object.entries(counts).map(([label, n]) => `${label}: ${n}`).join(" · ")}</p>)}
        </div>}
        <DataTable cols={rcols} rows={[...res.results].sort(byScope)} search="Search students"
          empty="No results" />
        <Button kind="ghost" size="sm" onClick={() => setRes(null)}>Close</Button>
      </Card>}
      {ask && <ConfirmDialog title={"Publish " + ask.name + "?"} confirm="Publish"
        text="This publishes the internal school results. Numeric rankings are shown only where school policy enables them."
        onYes={() => publish(ask)} onNo={() => setAsk(null)} />}
    </div>
  );
}
