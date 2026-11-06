import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Alert, Badge, Button, Select } from "./ui";

const ASSESSMENT = { opener: "Opener", mid: "Mid-term", end: "End-term" };
const OUTCOME_LABELS = {
  scored: "Scored", absent: "Absent", exempted: "Exempted",
  not_assessed: "Not assessed", pending: "Pending", missing: "Missing",
};
const WORKFLOW_LABELS = {
  draft: "Draft", submitted: "Awaiting approval", approved: "Approved", locked: "Locked",
};

function groupKey(exam) {
  return JSON.stringify([exam.term, exam.assessment_type, exam.name]);
}

async function readAll(path) {
  const output = [];
  let url = `${path}${path.includes("?") ? "&" : "?"}page_size=200`;
  for (let page = 0; page < 200 && url; page += 1) {
    const response = await api(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Could not load dashboard setup (${response.status}).`);
    }
    const body = await response.json();
    if (Array.isArray(body)) return body;
    output.push(...(body.results || []));
    if (!body.next) break;
    const next = new URL(body.next, window.location.origin);
    url = `${next.pathname}${next.search}`;
  }
  return output;
}

const pct = (value) => value == null ? "—" : `${Number(value).toFixed(1)}%`;
const count = (value) => Number(value || 0).toLocaleString();

function ProgressBar({ value }) {
  const width = value == null ? 0 : Math.max(0, Math.min(100, Number(value)));
  return <div className="d2-exam-progress" role="progressbar"
    aria-valuenow={width} aria-valuemin="0" aria-valuemax="100"
    aria-label={`Completion ${width}%`}>
    <i style={{ width: `${width}%` }} />
  </div>;
}

function Stat({ label, value, note, tone }) {
  return <div className={`d2-exam-stat ${tone || ""}`}>
    <small>{label}</small><b>{value}</b>{note && <span>{note}</span>}
  </div>;
}

function StatusCell({ cell }) {
  const disposition = OUTCOME_LABELS[cell.mark_status] || cell.mark_status;
  const workflow = cell.workflow_status ? WORKFLOW_LABELS[cell.workflow_status] : "";
  const scored = cell.mark_status === "scored" && cell.mark != null;
  const className = cell.mark_status === "missing" ? "missing"
    : cell.mark_status === "pending" ? "pending"
      : cell.mark_status === "absent" ? "absent"
        : cell.workflow_status === "submitted" ? "submitted" : "complete";
  return <span className={`d2-exam-cell ${className}`}>
    <b>{scored ? cell.mark : disposition}</b>
    {workflow && <small>{workflow}</small>}
  </span>;
}

export default function ExamOperations({ go }) {
  const [catalogue, setCatalogue] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [groupId, setGroupId] = useState("");
  const [classId, setClassId] = useState("");
  const [streamId, setStreamId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [catalogueReload, setCatalogueReload] = useState(0);

  useEffect(() => {
    let live = true;
    setLoadError("");
    Promise.all([
      readAll("/api/exams/"), readAll("/api/terms/"), readAll("/api/class-levels/"),
    ]).then(([exams, terms, classes]) => {
      if (live) setCatalogue({ exams, terms, classes });
    }).catch((error) => { if (live) setLoadError(error.message); });
    const refresh = () => {
      setReload((value) => value + 1);
      setCatalogueReload((value) => value + 1);
    };
    window.addEventListener("marian:dashboard-refresh", refresh);
    return () => {
      live = false;
      window.removeEventListener("marian:dashboard-refresh", refresh);
    };
  }, [catalogueReload]);

  const groups = useMemo(() => {
    if (!catalogue) return [];
    const terms = new Map(catalogue.terms.map((term) => [String(term.id), term]));
    const byKey = new Map();
    for (const exam of catalogue.exams) {
      const term = terms.get(String(exam.term));
      if (!term) continue;
      const key = groupKey(exam);
      if (!byKey.has(key)) byKey.set(key, {
        id: key, name: exam.name, term, assessment_type: exam.assessment_type, exams: [],
      });
      byKey.get(key).exams.push(exam);
    }
    return [...byKey.values()].sort((a, b) =>
      String(b.term.start_date || "").localeCompare(String(a.term.start_date || ""))
      || a.name.localeCompare(b.name));
  }, [catalogue]);

  useEffect(() => {
    if (!groups.length) {
      setGroupId(""); setClassId(""); setStreamId(""); setSubjectId("");
      return;
    }
    if (!groups.some((group) => group.id === groupId)) {
      setGroupId(groups[0].id);
      setClassId(""); setStreamId(""); setSubjectId("");
    }
  }, [groups, groupId]);

  const selectedGroup = groups.find((group) => group.id === groupId);
  const classOptions = useMemo(() => {
    if (!catalogue || !selectedGroup) return [];
    const available = new Set(selectedGroup.exams.map((exam) => String(exam.class_level)));
    return catalogue.classes.filter((item) => available.has(String(item.id)))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [catalogue, selectedGroup]);

  useEffect(() => {
    if (!classOptions.length) {
      setClassId(""); setStreamId(""); setSubjectId("");
      return;
    }
    if (!classOptions.some((item) => String(item.id) === String(classId))) {
      setClassId(String(classOptions[0].id));
      setStreamId(""); setSubjectId("");
    }
  }, [classOptions, classId]);

  const selectedExam = selectedGroup?.exams.find(
    (exam) => String(exam.class_level) === String(classId),
  );
  const selectedClass = classOptions.find((item) => String(item.id) === String(classId));

  useEffect(() => {
    if (!selectedExam) {
      setDashboard(null);
      setDashboardError("");
      setDashboardLoading(false);
      return undefined;
    }
    let live = true;
    const query = new URLSearchParams({ exam_id: selectedExam.id, page: String(page), page_size: "50" });
    if (streamId) query.set("stream_id", streamId);
    if (subjectId) query.set("subject_id", subjectId);
    setDashboard(null);
    setDashboardLoading(true);
    setDashboardError("");
    api(`/api/dashboard/exams/?${query.toString()}`)
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Could not load examination progress (${response.status}).`);
        }
        return response.json();
      })
      .then((data) => { if (live) setDashboard(data); })
      .catch((error) => { if (live) setDashboardError(error.message); })
      .finally(() => { if (live) setDashboardLoading(false); });
    return () => { live = false; };
  }, [selectedExam?.id, streamId, subjectId, page, reload]);

  const selectGroup = (value) => {
    setGroupId(value); setClassId(""); setStreamId(""); setSubjectId("");
    setDashboard(null); setPage(1);
  };
  const selectClass = (value) => {
    setClassId(value); setStreamId(""); setSubjectId(""); setDashboard(null); setPage(1);
  };
  const selectStream = (value) => {
    setStreamId(value); setSubjectId(""); setPage(1);
  };
  const selectSubject = (value) => { setSubjectId(value); setPage(1); };

  if (loadError) return <article className="d2-panel"><div className="d2-head"><h3>Examination management</h3></div>
    <Alert kind="err">{loadError}</Alert><Button kind="secondary" onClick={() => setCatalogueReload((value) => value + 1)}>Retry</Button></article>;
  if (!catalogue) return <article className="d2-panel"><div className="d2-head"><h3>Examination management</h3></div><p className="d2-empty">Loading examination dashboard…</p></article>;
  if (!groups.length) return <article className="d2-panel"><div className="d2-head"><h3>Examination management</h3></div><p className="d2-empty">No examinations are available for this school yet. Create one in Exams to start tracking progress.</p></article>;

  const summary = dashboard?.summary || {};
  const learners = dashboard?.learners;
  const paperDefinitions = dashboard?.paper_definitions || [];
  const subjectName = dashboard?.subjects?.find((subject) => String(subject.id) === String(subjectId))?.name;

  return (
    <article className="d2-panel d2-exam-ops">
      <div className="d2-head">
        <div><h3>Examination management</h3>
          <p className="d2-muted">Track entry and approval progress from examination to individual learners.</p></div>
        <div className="d2-exam-actions">
          <Button kind="ghost" size="sm" onClick={() => go?.("Approve")}>Review approvals</Button>
          <Button kind="ghost" size="sm" onClick={() => {
            setReload((value) => value + 1);
            setCatalogueReload((value) => value + 1);
          }}>Refresh</Button>
        </div>
      </div>
      <div className="d2-exam-crumbs" aria-label="Examination drill-down">
        <span>Examination</span><i>›</i><span>Class</span><i>›</i><span>Stream</span><i>›</i><span>Subject</span><i>›</i><span>Learners</span>
      </div>
      <div className="d2-exam-selectors">
        <Select label="Examination" value={groupId} onChange={(event) => selectGroup(event.target.value)}>
          {groups.map((group) => <option key={group.id} value={group.id}>
            {group.name} · {group.term.name} {group.term.academic_year ? `(${group.term.academic_year})` : ""} · {ASSESSMENT[group.assessment_type] || group.assessment_type}
          </option>)}
        </Select>
        <Select label="Class" value={classId} onChange={(event) => selectClass(event.target.value)} disabled={!classOptions.length}>
          {classOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
        <Select label="Stream" value={streamId} onChange={(event) => selectStream(event.target.value)} disabled={!dashboard && !dashboardLoading}>
          <option value="">All streams</option>
          {(dashboard?.streams || []).map((stream) => <option key={stream.id} value={stream.id}>{stream.name} ({count(stream.learner_count)})</option>)}
        </Select>
        <Select label="Subject" value={subjectId} onChange={(event) => selectSubject(event.target.value)} disabled={!dashboard || dashboard.subjects.length === 0}>
          <option value="">All registered subjects</option>
          {(dashboard?.subjects || []).map((subject) => <option key={subject.id} value={subject.id}>{subject.name} ({count(subject.registration_count)} registered)</option>)}
        </Select>
      </div>
      <div className="d2-exam-context">
        <span><small>Selected class</small><b>{selectedClass?.name || "—"}</b></span>
        <span><small>Examination status</small><Badge kind={selectedExam?.status === "published" ? "ok" : "info"}>{selectedExam?.status || "—"}</Badge></span>
        <span><small>Term</small><b>{selectedGroup ? `${selectedGroup.term.name} · ${selectedGroup.term.academic_year || ""}` : "—"}</b></span>
      </div>
      {dashboardError && <Alert kind="err">{dashboardError} <Button kind="secondary" size="sm" onClick={() => setReload((value) => value + 1)}>Retry</Button></Alert>}
      {dashboardLoading && !dashboard && <p className="d2-empty">Loading examination progress…</p>}
      {dashboard && <>
        <div className="d2-exam-summary">
          <Stat label="Completion" value={pct(summary.completion_percentage)} note={`${count(summary.resolved_cells)} / ${count(summary.expected_cells)} paper cells complete`} tone="green" />
          <Stat label="Missing marks" value={count(summary.missing_marks)} note={`${count(summary.expected_cells)} expected registered paper cells`} tone={summary.missing_marks ? "danger" : "green"} />
          <Stat label="Pending approvals" value={count(summary.pending_approvals)} note="Submitted marks awaiting administrator action" tone={summary.pending_approvals ? "warning" : "green"} />
          <Stat label="Approved / locked" value={`${count(summary.approved_marks)} / ${count(summary.locked_marks)}`} note={`Approval coverage ${pct(summary.approval_percentage)}`} tone="green" />
          <Stat label="Average score" value={pct(summary.average_score_pct)} note={`${count(summary.finalized_subject_scores)} finalized registered-subject scores; zero is valid`} />
          <Stat label="Score range" value={summary.lowest_score_pct == null ? "—" : `${pct(summary.lowest_score_pct)} – ${pct(summary.highest_score_pct)}`} note={`${count(summary.pending_dispositions)} pending dispositions`} />
        </div>
        <div className="d2-exam-progress-row">
          <span>Resolved outcomes</span><ProgressBar value={summary.completion_percentage} /><b>{pct(summary.completion_percentage)}</b>
        </div>
        <div className="d2-exam-outcomes" aria-label="Mark outcome statistics">
          {Object.entries(summary.outcomes || {}).map(([status, value]) => <span key={status}>
            <b>{count(value)}</b>{OUTCOME_LABELS[status] || status}
          </span>)}
          <span><b>{count(summary.draft_marks)}</b>Draft workflow</span>
          <span><b>{count(summary.submitted_marks)}</b>Submitted workflow</span>
        </div>

        <div className="d2-exam-tables">
          {!streamId && <section>
            <div className="d2-exam-section-head"><h4>Streams</h4><small>{dashboard.streams.length} roster groups</small></div>
            <div className="d2-exam-table-wrap"><table className="d2-exam-table">
              <thead><tr><th>Stream</th><th>Learners</th><th>Completion</th><th>Missing</th><th>Pending approval</th><th>Average</th><th></th></tr></thead>
              <tbody>{dashboard.streams.map((stream) => <tr key={stream.id}>
                <td><button type="button" className="d2-exam-drill" onClick={() => selectStream(stream.id)}>{stream.name}</button></td>
                <td>{count(stream.learner_count)}</td>
                <td>{pct(stream.progress.completion_percentage)} <small>({count(stream.progress.resolved_cells)}/{count(stream.progress.expected_cells)})</small></td>
                <td>{count(stream.progress.missing_marks)}</td>
                <td>{count(stream.progress.pending_approvals)}</td>
                <td>{pct(stream.progress.average_score_pct)}</td>
                <td><Button kind="ghost" size="sm" onClick={() => selectStream(stream.id)}>View</Button></td>
              </tr>)}</tbody>
            </table></div>
            {!dashboard.streams.length && <p className="d2-empty">No active enrolled learners in this class.</p>}
          </section>}
          <section>
            <div className="d2-exam-section-head"><h4>{streamId ? `${dashboard.streams.find((item) => String(item.id) === String(streamId))?.name || "Selected stream"} subjects` : "Registered subjects"}</h4><small>Only academic-year registrations are included</small></div>
            <div className="d2-exam-table-wrap"><table className="d2-exam-table">
              <thead><tr><th>Subject</th><th>Registered learners</th><th>Completion</th><th>Missing</th><th>Pending approval</th><th>Average</th><th></th></tr></thead>
              <tbody>{dashboard.subjects.map((subject) => <tr key={subject.id}>
                <td><button type="button" className="d2-exam-drill" onClick={() => selectSubject(String(subject.id))}>{subject.name}</button>
                  <small className="d2-exam-paper-note">Papers: {subject.papers.join(", ")}</small></td>
                <td>{count(subject.registration_count)}</td>
                <td>{pct(subject.progress.completion_percentage)} <small>({count(subject.progress.resolved_cells)}/{count(subject.progress.expected_cells)})</small></td>
                <td>{count(subject.progress.missing_marks)}</td>
                <td>{count(subject.progress.pending_approvals)}</td>
                <td>{pct(subject.progress.average_score_pct)}</td>
                <td><Button kind="ghost" size="sm" onClick={() => selectSubject(String(subject.id))}>Learners</Button></td>
              </tr>)}</tbody>
            </table></div>
            {!dashboard.subjects.length && <p className="d2-empty">No learners are registered for subjects in this scope.</p>}
          </section>
        </div>

        {subjectId && <section className="d2-exam-learners">
          <div className="d2-exam-section-head"><h4>{subjectName || "Subject"} · Learners</h4>
            <small>{count(learners?.count)} registered learner{learners?.count === 1 ? "" : "s"}</small></div>
          {dashboardLoading ? <p className="d2-empty">Loading learner paper statuses…</p> :
            <div className="d2-exam-table-wrap"><table className="d2-exam-table">
              <thead><tr><th>Learner</th><th>Admission no.</th>{!streamId && <th>Stream</th>}
                {paperDefinitions.map((paper) => <th key={paper.paper_number}>Paper {paper.paper_number}<small>Max {paper.max_marks}</small></th>)}
              </tr></thead>
              <tbody>{(learners?.results || []).map((learner) => <tr key={learner.id}>
                <td>{learner.name}</td><td>{learner.admission_number}</td>{!streamId && <td>{learner.stream}</td>}
                {learner.papers.map((cell) => <td key={cell.paper_number}><StatusCell cell={cell} /></td>)}
              </tr>)}</tbody>
            </table></div>}
          {learners && <div className="d2-exam-page">
            <span>Page {page} · {count(learners.count)} learners</span>
            <div><Button kind="secondary" size="sm" disabled={!learners.previous || dashboardLoading} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</Button>
              <Button kind="secondary" size="sm" disabled={!learners.next || dashboardLoading} onClick={() => setPage((value) => value + 1)}>Next</Button></div>
          </div>}
          {!dashboardLoading && learners?.count === 0 && <p className="d2-empty">No learners are registered for this subject in the selected stream.</p>}
        </section>}
        <p className="d2-exam-footnote">Completion counts only registered paper cells with a recorded non-pending outcome. Missing means no mark record; a zero score, absence, exemption, and not-assessed outcome remain distinct.</p>
      </>}
    </article>
  );
}
