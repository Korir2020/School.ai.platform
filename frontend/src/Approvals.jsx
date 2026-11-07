import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Card, Badge, StatCard, DataTable, Loading, ErrorState,
  Input, Select, Modal, ConfirmDialog, Alert } from "./ui";

const MARK_STATES = [
  ["scored", "Scored"], ["absent", "Absent"], ["exempted", "Exempted"],
  ["not_assessed", "Not assessed"], ["pending", "Pending"],
];
const LABELS = Object.fromEntries(MARK_STATES);
const WORKFLOW_KINDS = { submitted: "warn", approved: "ok" };

export default function Approvals() {
  const toast = useToast();
  const [d, setD] = useState(null), [bad, setBad] = useState(false);
  const [lockAsk, setLockAsk] = useState(null);
  const [decision, setDecision] = useState(null), [reason, setReason] = useState("");
  const [correcting, setCorrecting] = useState(null);
  const [correction, setCorrection] = useState({ mark_status: "scored", marks: "", reason: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [submitted, approved, students, subjects, papers] = await Promise.all([
        list("/api/performance/?status=submitted"),
        list("/api/performance/?status=approved"),
        list("/api/students/"), list("/api/subjects/"), list("/api/subject-papers/"),
      ]);
      setD({ pf: [...submitted, ...approved], st: students, sj: subjects, papers });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  if (bad) return <ErrorState text="Could not load approvals." onRetry={load} />;
  if (!d) return <Loading />;

  const nm = (id) => {
    const s = d.st.find((x) => x.id === id);
    return s ? s.first_name + " " + s.last_name : "Student " + id;
  };
  const sb = (id) => {
    const s = d.sj.find((x) => x.id === id);
    return s ? s.name : "Subject " + id;
  };
  const paperMax = (mark) => Number(d.papers.find((paper) =>
    String(paper.subject) === String(mark.subject)
    && Number(paper.paper_number) === Number(mark.paper_number))?.max_marks) || 100;

  const doDecision = async () => {
    if (!decision || reason.trim().length < 3 || reason.trim().length > 1000) return;
    setBusy(true);
    try {
      const endpoint = decision.action === "return" ? "reject" : "approve";
      const r = await api(`/api/performance/${decision.mark.id}/${endpoint}/`, "POST", {
        reason: reason.trim(),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        toast("Could not record decision: " + (j.detail || j.reason?.[0] || endpoint), "err");
      } else {
        toast(decision.action === "return"
          ? `Returned to teacher: ${nm(decision.mark.student)}`
          : `Approved: ${nm(decision.mark.student)}`, "ok");
        setDecision(null); setReason(""); await load();
      }
    } catch (error) {
      toast(error?.message || "Could not record the decision.", "err");
    } finally { setBusy(false); }
  };

  const openCorrection = (mark) => {
    setCorrecting(mark);
    setCorrection({
      mark_status: mark.mark_status || "scored",
      marks: mark.marks === null || mark.marks === undefined ? "" : String(mark.marks),
      reason: "",
    });
  };

  const saveCorrection = async () => {
    if (!correcting || correction.reason.trim().length < 3
      || correction.reason.trim().length > 1000
      || (correction.mark_status === "scored"
        && (correction.marks === "" || !Number.isFinite(Number(correction.marks))
          || Number(correction.marks) < 0 || Number(correction.marks) > paperMax(correcting)))) return;
    setBusy(true);
    try {
      const r = await api(`/api/performance/${correcting.id}/`, "PATCH", {
        mark_status: correction.mark_status,
        marks: correction.mark_status === "scored" ? correction.marks : null,
        reason: correction.reason.trim(),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) {
        toast("Could not correct the mark: " + (j.detail || j.marks?.[0] || j.reason?.[0] || "Validation failed"), "err");
      } else {
        toast("Correction saved with an audit reason. The mark remains in the approval queue.", "ok");
        setCorrecting(null); await load();
      }
    } catch (error) {
      toast(error?.message || "Could not save the correction.", "err");
    } finally { setBusy(false); }
  };

  const lock = async () => {
    const mark = lockAsk;
    setLockAsk(null);
    if (!mark) return;
    const r = await api(`/api/performance/${mark.id}/lock/`, "POST");
    const j = await r.json().catch(() => ({}));
    if (r.ok) toast(`Locked: ${nm(mark.student)}`, "ok");
    else toast("Could not lock the mark: " + (j.detail || "lock"), "err");
    load();
  };

  const rows = d.pf;
  const count = (status) => rows.filter((p) => p.status === status).length;
  const cols = [
    { label: "Student", get: (p) => nm(p.student), sort: true },
    { label: "Subject", get: (p) => sb(p.subject), sort: true },
    { label: "Assessment", get: (p) => `${p.assessment_type} · Paper ${p.paper_number}`, sort: true },
    { label: "Mark", get: (p) => p.mark_status === "scored" ? p.marks : "—", sort: true },
    { label: "Mark status", get: (p) => LABELS[p.mark_status] || p.mark_status,
      render: (p) => <Badge kind={p.mark_status === "scored" ? "info" : p.mark_status === "absent" ? "warn" : "teal"}>{LABELS[p.mark_status] || p.mark_status}</Badge> },
    { label: "Workflow", key: "status", sort: true,
      render: (p) => <Badge kind={WORKFLOW_KINDS[p.status] || "info"}>{p.status}</Badge> },
    { label: "Actions", render: (p) => p.status === "submitted" ? <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
      <Button kind="secondary" size="sm" disabled={busy} onClick={() => openCorrection(p)}>Correct</Button>
      <Button kind="teal" size="sm" disabled={busy} onClick={() => { setDecision({ mark: p, action: "approve" }); setReason(""); }}>Approve</Button>
      <Button kind="danger" size="sm" disabled={busy} onClick={() => { setDecision({ mark: p, action: "return" }); setReason(""); }}>Return</Button>
    </div> : <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
      <Button kind="secondary" size="sm" disabled={busy} onClick={() => openCorrection(p)}>Correct</Button>
      <Button kind="secondary" size="sm" disabled={busy} onClick={() => setLockAsk(p)}>Lock</Button>
    </div> },
  ];

  return (
    <div>
      <h2>Marks review and approval</h2>
      <p>Review the numeric mark and its separate attendance/disposition state. Approve or return each submission with a recorded reason. Corrections to approved marks return them to the approval queue.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <StatCard label="Awaiting approval" value={count("submitted")} />
        <StatCard label="Approved, awaiting lock" value={count("approved")} />
      </div>
      <Card>
        <DataTable cols={cols} rows={rows} search="Search approvals"
          empty="Nothing waiting for approval or lock." />
      </Card>
      {decision && <Modal title={decision.action === "approve" ? "Approve this mark?" : "Return this mark to the teacher?"}
        onClose={() => { if (!busy) { setDecision(null); setReason(""); } }}
        actions={<>
          <Button kind="secondary" disabled={busy} onClick={() => { setDecision(null); setReason(""); }}>Cancel</Button>
          <Button kind={decision.action === "return" ? "danger" : "teal"} busy={busy}
            disabled={reason.trim().length < 3 || reason.trim().length > 1000}
            onClick={doDecision}>{decision.action === "approve" ? "Approve with reason" : "Return with reason"}</Button>
        </>}>
        <p>{nm(decision.mark.student)} · {sb(decision.mark.subject)} · {decision.mark.mark_status === "scored" ? decision.mark.marks : LABELS[decision.mark.mark_status]}</p>
        <Input label="Decision reason (required)" value={reason} maxLength={1000}
          onChange={(event) => setReason(event.target.value)} />
        <small>Enter at least 3 characters. This explanation is saved in the mark audit trail.</small>
      </Modal>}
      {correcting && <Modal title={`Correct submission for ${nm(correcting.student)}?`}
        onClose={() => { if (!busy) setCorrecting(null); }}
        actions={<>
          <Button kind="secondary" disabled={busy} onClick={() => setCorrecting(null)}>Cancel</Button>
          <Button kind="teal" busy={busy}
            disabled={correction.reason.trim().length < 3 || correction.reason.trim().length > 1000
              || (correction.mark_status === "scored" && (correction.marks === "" || !Number.isFinite(Number(correction.marks)) || Number(correction.marks) < 0 || Number(correction.marks) > paperMax(correcting)))}
            onClick={saveCorrection}>Save correction with reason</Button>
        </>}>
        <p>{sb(correcting.subject)} · {correcting.assessment_type} · Paper {correcting.paper_number}</p>
        <Select label="Mark status" value={correction.mark_status}
          onChange={(event) => setCorrection((current) => ({ ...current, mark_status: event.target.value,
            marks: event.target.value === "scored" ? current.marks : "" }))}>
          {MARK_STATES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        {correction.mark_status === "scored" && <Input label={`Score (0–${paperMax(correcting)}; zero is valid)`} type="number" min="0" max={paperMax(correcting)} step="0.01"
          value={correction.marks} onChange={(event) => setCorrection((current) => ({ ...current, marks: event.target.value }))} />}
        <Input label="Correction reason (required)" value={correction.reason} maxLength={1000}
          onChange={(event) => setCorrection((current) => ({ ...current, reason: event.target.value }))} />
        <Alert kind="info">The before/after score, disposition, workflow state, actor, and reason are audit logged. An already-approved mark must be approved again after correction.</Alert>
      </Modal>}
      {lockAsk && <ConfirmDialog danger title="Lock this approved mark?"
        text="Locked marks are immutable through the normal mark-entry workflow. The action is recorded in the audit trail."
        confirm="Lock" onYes={lock} onNo={() => setLockAsk(null)} />}
    </div>
  );
}
