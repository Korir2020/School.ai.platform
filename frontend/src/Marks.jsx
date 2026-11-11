import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Select, Card, Badge, EmptyState, Loading, ErrorState, Alert, ConfirmDialog } from "./ui";
import PasteMarks from "./PasteMarks";
import { getOfflineMetadata, loadOfflinePayload, saveOfflinePayload, updateOfflinePayload } from "./offline/offlineStore";
import { createDraftOperation, retryOperation } from "./offline/operationQueue";
import "./offline/offline.css";

const ASSESSMENTS = { opener: "Opener", mid: "Mid-term", end: "End-term" };
const STATUSES = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };
const MARK_STATUSES = [
  ["scored", "Scored"], ["absent", "Absent"], ["exempted", "Exempted"],
  ["not_assessed", "Not assessed"], ["pending", "Pending"],
];
const MARK_STATUS_LABELS = Object.fromEntries(MARK_STATUSES);
const API_LISTS = {
  exams: "/api/exams/",
  assignments: "/api/teacher-assignments/",
  enrollments: "/api/enrollments/",
  students: "/api/students/",
  terms: "/api/terms/",
  subjects: "/api/subjects/",
  streams: "/api/streams/",
  classes: "/api/class-levels/",
  papers: "/api/subject-papers/",
};

const same = (a, b) => String(a ?? "") === String(b ?? "");
const active = (x) => x === true || x === 1 || x === "1" || x === "true";
const cellKey = (student, paper) => `${student}:${paper}`;

async function listChecked(path) {
  const sep = path.includes("?") ? "&" : "?";
  let url = `${path}${sep}page_size=200`;
  const out = [];
  for (let page = 0; page < 200 && url; page += 1) {
    const response = await api(url);
    if (!response.ok) throw new Error(await responseMessage(response));
    const body = await response.json();
    if (Array.isArray(body)) return body;
    out.push(...(body.results || []));
    if (!body.next) break;
    const next = new URL(body.next, window.location.origin);
    url = `${next.pathname}${next.search}`;
  }
  return out;
}

async function responseMessage(response) {
  try {
    const body = await response.json();
    if (typeof body === "string") return body;
    if (body.detail) return body.detail;
    if (body.message) return body.message;
    if (body.errors?.length) {
      return body.errors.map((item) => item.detail || item.errors?.marks?.[0] || "Invalid entry").join("; ");
    }
    return Object.entries(body).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(" ") : String(value)}`).join(" ")
      || `Request failed (${response.status}).`;
  } catch {
    return `Request failed (${response.status}).`;
  }
}

function examGroupKey(exam) {
  return `${exam.term}:${exam.assessment_type}:${exam.name}`;
}

function makeName(student) {
  return [student?.first_name, student?.middle_name, student?.last_name].filter(Boolean).join(" ")
    || student?.full_name || student?.admission_number || `Learner ${student?.id ?? ""}`;
}

const styles = {
  selectors: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 220px), 1fr))", gap: 10 },
  table: { minWidth: 920 },
  input: { minWidth: 94, maxWidth: 130 },
  number: { textAlign: "right" },
  nowrap: { whiteSpace: "nowrap" },
  small: { display: "block", color: "#64748b", fontSize: 12, fontWeight: 400, whiteSpace: "nowrap" },
  total: { fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", fontWeight: 600 },
  action: { minWidth: 130 },
};

export default function Marks({ _d, offlineMode = false, offlinePayload = null, offlineIdentity = null,
  offlinePassphrase = "", onOfflinePrepared, onForget }) {
  const toast = useToast();
  const cacheSchoolId = offlineIdentity?.school?.id ?? offlineIdentity?.school_id ?? offlineIdentity?.schoolId ?? offlineIdentity?.school?.slug ?? null;
  const [data, setData] = useState(() => offlineMode ? offlinePayload?.data || null : null);
  const [markRows, setMarkRows] = useState(() => offlineMode ? offlinePayload?.markRows || [] : []);
  const [marksError, setMarksError] = useState("");
  const [marksLoading, setMarksLoading] = useState(false);
  const [registrationRows, setRegistrationRows] = useState(() => offlineMode ? offlinePayload?.registrationRows || [] : []);
  const [registrationsError, setRegistrationsError] = useState("");
  const [registrationsLoading, setRegistrationsLoading] = useState(false);
  const [loadingError, setLoadingError] = useState("");
  const [retry, setRetry] = useState(0);
  const [marksReload, setMarksReload] = useState(0);
  const [registrationsReload, setRegistrationsReload] = useState(0);
  const [examGroupId, setExamGroupId] = useState(() => offlineMode ? offlinePayload?.context?.examGroupId || "" : "");
  const [classId, setClassId] = useState(() => offlineMode ? String(offlinePayload?.context?.classId || "") : "");
  const [streamId, setStreamId] = useState(() => offlineMode ? String(offlinePayload?.context?.streamId || "") : "");
  const [subjectId, setSubjectId] = useState(() => offlineMode ? String(offlinePayload?.context?.subjectId || "") : "");
  const [values, setValues] = useState({});
  const [dispositions, setDispositions] = useState({});
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(null);
  const [preparedOffline, setPreparedOffline] = useState(() => offlineMode ? offlinePayload : null);
  const [passphrase, setPassphrase] = useState("");
  const [passphraseAgain, setPassphraseAgain] = useState("");
  const [existingPassphrase, setExistingPassphrase] = useState("");
  const [offlineMetadata, setOfflineMetadata] = useState(null);
  const [offlineError, setOfflineError] = useState("");
  const [offlineExpiry, setOfflineExpiry] = useState(() => offlineMode ? offlinePayload?.offlineMetadata?.expiresAt || null : null);
  const [offlineStoragePersistent, setOfflineStoragePersistent] = useState(null);

  const load = async () => {
    if (offlineMode) return;
    setLoadingError("");
    try {
      const pairs = Object.entries(API_LISTS);
      const loaded = await Promise.all(pairs.map(([, path]) => listChecked(path)));
      setData(Object.fromEntries(pairs.map(([key], index) => [key, loaded[index]])));
    } catch (error) {
      setLoadingError(error?.message || "Could not load marks-entry data. Check your connection and try again.");
    }
  };

  useEffect(() => { load(); }, [retry, offlineMode]);

  useEffect(() => {
    if (offlineMode) return undefined;
    let alive = true;
    (async () => {
      try {
        const metadata = await getOfflineMetadata();
        if (alive) setOfflineMetadata(metadata);
        if (offlinePassphrase && metadata && !metadata.expired) {
          const schoolId = offlineIdentity?.school?.id ?? offlineIdentity?.school_id
            ?? offlineIdentity?.schoolId ?? offlineIdentity?.school?.slug;
          const restored = await loadOfflinePayload(offlinePassphrase, offlineIdentity?.username, schoolId);
          if (alive) { setPreparedOffline(restored); setOfflineExpiry(restored.offlineMetadata?.expiresAt || metadata.expiresAt); }
        }
      } catch { /* The passphrase is never persisted; ask the teacher to unlock explicitly if needed. */ }
    })();
    return () => { alive = false; };
  }, [offlineMode, offlinePassphrase, offlineIdentity]);

  useEffect(() => {
    if (offlineMode || !offlinePassphrase) return undefined;
    let alive = true;
    const refreshVault = async () => {
      try {
        const payload = await loadOfflinePayload(offlinePassphrase, offlineIdentity?.username, cacheSchoolId);
        if (alive) { setPreparedOffline(payload); setOfflineExpiry(payload.offlineMetadata?.expiresAt || null); }
      } catch { /* Keep the existing status visible if the device copy is unavailable. */ }
    };
    window.addEventListener("marian:offline-queue-updated", refreshVault);
    return () => { alive = false; window.removeEventListener("marian:offline-queue-updated", refreshVault); };
  }, [offlineMode, offlinePassphrase, offlineIdentity, cacheSchoolId]);

  const examGroups = useMemo(() => {
    if (!data) return [];
    const classAssignmentPairs = new Set();
    data.assignments.forEach((assignment) => {
      const stream = data.streams.find((item) => same(item.id, assignment.stream));
      if (!stream) return;
      if (data.enrollments.some((enrollment) =>
        active(enrollment.is_active) && same(enrollment.stream, stream.id))) {
        classAssignmentPairs.add(String(stream.class_level));
      }
    });
    const groups = new Map();
    data.exams.filter((exam) => exam.status === "draft").forEach((exam) => {
      const term = data.terms.find((item) => same(item.id, exam.term));
      if (!term || !classAssignmentPairs.has(String(exam.class_level))) return;
      const activeAssignedStream = data.streams.some((stream) =>
        same(stream.class_level, exam.class_level)
        && data.enrollments.some((enrollment) => active(enrollment.is_active)
          && same(enrollment.class_level, exam.class_level)
          && same(enrollment.academic_year, term.academic_year)
          && same(enrollment.stream, stream.id))
        && data.assignments.some((assignment) => same(assignment.stream, stream.id)));
      if (!activeAssignedStream) return;
      const key = examGroupKey(exam);
      if (!groups.has(key)) groups.set(key, { id: key, name: exam.name, term, type: exam.assessment_type, exams: [] });
      groups.get(key).exams.push(exam);
    });
    return [...groups.values()].sort((a, b) => {
      const byDate = String(a.term.start_date || "").localeCompare(String(b.term.start_date || ""));
      return byDate || a.name.localeCompare(b.name);
    });
  }, [data]);

  const selectedGroup = examGroups.find((group) => group.id === examGroupId);
  const classOptions = useMemo(() => {
    if (!data || !selectedGroup) return [];
    const ids = [...new Set(selectedGroup.exams.map((exam) => String(exam.class_level)))];
    return ids.map((id) => data.classes.find((item) => same(item.id, id)))
      .filter(Boolean).sort((a, b) => a.name.localeCompare(b.name));
  }, [data, selectedGroup]);
  const selectedExam = selectedGroup?.exams.find((exam) => same(exam.class_level, classId));
  const selectedTerm = selectedExam ? data.terms.find((term) => same(term.id, selectedExam.term)) : null;
  const selectedStream = data?.streams.find((stream) => same(stream.id, streamId));
  const selectedClass = data?.classes.find((item) => same(item.id, classId));

  const streamOptions = useMemo(() => {
    if (!data || !selectedExam || !selectedTerm) return [];
    const ids = new Set(data.enrollments.filter((enrollment) => active(enrollment.is_active)
      && same(enrollment.academic_year, selectedTerm.academic_year)
      && same(enrollment.class_level, selectedExam.class_level)
      && data.assignments.some((assignment) => same(assignment.stream, enrollment.stream)))
      .map((enrollment) => String(enrollment.stream)));
    return data.streams.filter((stream) => same(stream.class_level, selectedExam.class_level)
      && ids.has(String(stream.id))).sort((a, b) => a.name.localeCompare(b.name));
  }, [data, selectedExam, selectedTerm]);

  const assignments = useMemo(() => {
    if (!data || !streamId) return [];
    const ids = [...new Set(data.assignments.filter((assignment) => same(assignment.stream, streamId))
      .map((assignment) => String(assignment.subject)))];
    return ids.map((id) => data.subjects.find((subject) => same(subject.id, id)))
      .filter((subject) => subject && active(subject.is_active))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data, streamId]);
  const subject = data?.subjects.find((item) => same(item.id, subjectId));

  useEffect(() => {
    if (offlineMode) return undefined;
    if (!data || !selectedExam || !selectedTerm || !subject) {
      setMarkRows([]);
      setMarksError("");
      setMarksLoading(false);
      return undefined;
    }
    let current = true;
    const query = new URLSearchParams({
      term: selectedExam.term,
      academic_year: selectedTerm.academic_year,
      subject: subject.id,
      assessment_type: selectedExam.assessment_type,
      class_level: selectedExam.class_level,
      stream: streamId,
    });
    setMarksLoading(true);
    setMarksError("");
    listChecked(`/api/performance/?${query.toString()}`)
      .then((rows) => { if (current) setMarkRows(rows); })
      .catch((error) => { if (current) setMarksError(error?.message || "Could not load saved marks."); })
      .finally(() => { if (current) setMarksLoading(false); });
    return () => { current = false; };
  }, [data, selectedExam?.id, selectedTerm?.academic_year, selectedExam?.class_level,
    streamId, subject?.id, marksReload]);

  useEffect(() => {
    if (offlineMode) return undefined;
    if (!data || !selectedTerm || !subject) {
      setRegistrationRows([]);
      setRegistrationsError("");
      setRegistrationsLoading(false);
      return undefined;
    }
    let current = true;
    const query = new URLSearchParams({
      academic_year: selectedTerm.academic_year,
      subject: subject.id,
    });
    setRegistrationsLoading(true);
    setRegistrationsError("");
    listChecked(`/api/subject-registrations/?${query.toString()}`)
      .then((rows) => { if (current) setRegistrationRows(rows); })
      .catch((error) => { if (current) setRegistrationsError(error?.message || "Could not load registered learners."); })
      .finally(() => { if (current) setRegistrationsLoading(false); });
    return () => { current = false; };
  }, [data, selectedTerm?.academic_year, subject?.id, registrationsReload]);

  useEffect(() => {
    if (!preparedOffline || !offlinePassphrase) return undefined;
    const refreshCached = async () => {
      try {
        const latest = await loadOfflinePayload(offlinePassphrase, offlineIdentity?.username,
          offlineIdentity?.school?.id ?? offlineIdentity?.school_id ?? offlineIdentity?.schoolId ?? offlineIdentity?.school?.slug);
        setPreparedOffline(latest);
      } catch { /* A bad or expired cache remains visible through the next explicit save/unlock. */ }
    };
    const changed = () => refreshCached();
    window.addEventListener("marian:offline-queue-updated", changed);
    return () => window.removeEventListener("marian:offline-queue-updated", changed);
  }, [preparedOffline, offlinePassphrase, offlineIdentity]);

  const paperDefinitions = useMemo(() => {
    if (!data || !subject) return [];
    return data.papers.filter((paper) => same(paper.subject, subject.id))
      .sort((a, b) => Number(a.paper_number) - Number(b.paper_number));
  }, [data, subject]);
  const papers = paperDefinitions.length ? paperDefinitions : [{
    paper_number: 1, max_marks: "100", weight: "100",
  }];
  const tooManyPapers = papers.some((paper) => Number(paper.paper_number) > 3);
  const visiblePapers = papers.filter((paper) => Number(paper.paper_number) <= 3);
  const expectedWeight = paperDefinitions.reduce((sum, item) => sum + Number(item.weight || 0), 0);
  const badWeight = paperDefinitions.length > 0 && Math.abs(expectedWeight - 100) > 0.01;

  const registeredIds = useMemo(() => {
    if (!data || !subject || !selectedTerm) return new Set();
    return new Set(registrationRows.filter((row) => same(row.subject, subject.id)
      && same(row.academic_year, selectedTerm.academic_year)).map((row) => String(row.student)));
  }, [data, subject, selectedTerm, registrationRows]);

  const learners = useMemo(() => {
    if (!data || !selectedExam || !selectedTerm || !streamId || !subject) return [];
    return data.enrollments.filter((enrollment) => active(enrollment.is_active)
      && same(enrollment.academic_year, selectedTerm.academic_year)
      && same(enrollment.class_level, selectedExam.class_level)
      && same(enrollment.stream, streamId)
      && registeredIds.has(String(enrollment.student)))
      .map((enrollment) => data.students.find((student) => same(student.id, enrollment.student)))
      .filter(Boolean)
      .sort((a, b) => String(a.admission_number || "").localeCompare(String(b.admission_number || ""))
        || makeName(a).localeCompare(makeName(b)));
  }, [data, selectedExam, selectedTerm, streamId, subject, registeredIds]);

  const oldMark = (student, paperNumber) => {
    if (!data || !selectedExam || !subject) return null;
    return markRows.find((mark) => same(mark.student, student)
      && same(mark.subject, subject.id)
      && same(mark.term, selectedExam.term)
      && same(mark.academic_year, selectedTerm?.academic_year)
      && same(mark.assessment_type, selectedExam.assessment_type)
      && Number(mark.paper_number) === Number(paperNumber)) || null;
  };
  const markStatus = (studentId, paperNumber) => {
    const key = cellKey(studentId, Number(paperNumber));
    return dispositions[key] ?? oldMark(studentId, paperNumber)?.mark_status ?? "pending";
  };

  const selectionKey = `${selectedExam?.id || ""}:${subject?.id || ""}`;
  useEffect(() => {
    if (!data || !selectedExam || !subject) {
      setValues({});
      setSaveError("");
      return;
    }
    const initial = {};
    const initialDispositions = {};
    const numbers = paperDefinitions.length
      ? paperDefinitions.map((paper) => Number(paper.paper_number)) : [1];
    for (const learner of learners) {
      for (const number of numbers) {
        const mark = oldMark(learner.id, number);
        const key = cellKey(learner.id, number);
        initialDispositions[key] = mark?.mark_status || "";
        if (mark?.mark_status === "scored" && mark.marks !== null) {
          initial[key] = String(mark.marks);
        }
      }
    }
    setValues(initial);
    setDispositions(initialDispositions);
    setSaveError("");
  }, [data, selectionKey, learners, markRows]);

  const editable = (mark) => !mark || mark.status === "draft";
  const markValue = (studentId, paper) => values[cellKey(studentId, Number(paper.paper_number))] ?? "";
  const maxFor = (paper) => Number(paper.max_marks) > 0 ? Number(paper.max_marks) : 100;
  const weightFor = (paper) => paperDefinitions.length ? Number(paper.weight || 0) : 100;
  const cellError = (studentId, paper) => {
    const value = markValue(studentId, paper);
    if (markStatus(studentId, paper.paper_number) !== "scored") return value !== "";
    return value === "" || !(Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= maxFor(paper));
  };
  const countInvalid = learners.reduce((count, learner) => count + visiblePapers.filter((paper) =>
    editable(oldMark(learner.id, paper.paper_number)) && cellError(learner.id, paper)).length, 0);

  const pendingEntries = [];
  if (selectedExam && subject) {
    for (const learner of learners) {
      for (const paper of visiblePapers) {
        const paperNumber = Number(paper.paper_number);
        const previous = oldMark(learner.id, paperNumber);
        if (previous && previous.status !== "draft") continue;
        const next = markValue(learner.id, paper);
        const nextStatus = markStatus(learner.id, paperNumber);
        const numeric = nextStatus === "scored" ? next : null;
        const previousStatus = previous?.mark_status || "";
        const previousNumeric = previous?.marks === null || previous?.marks === undefined
          ? null : String(previous.marks);
        if (previous && nextStatus === previousStatus
          && (numeric === null ? previousNumeric === null
            : previousNumeric !== null && Number(numeric) === Number(previousNumeric))) continue;
        if (!previous && nextStatus === "") continue;
        if (!previous && nextStatus === "scored" && next === "") continue;
        pendingEntries.push({ student: learner.id, paper_number: paperNumber,
          marks: numeric, mark_status: nextStatus });
      }
    }
  }

  let hasRememberedUsername = false;
  try { hasRememberedUsername = localStorage.getItem("marian:remembered-username")?.toLowerCase() === String(offlineIdentity?.username || "").toLowerCase(); } catch { /* storage blocked */ }
  const prepareOffline = async () => {
    if (!selectedExam || !selectedTerm || !selectedStream || !selectedClass || !subject || learners.length === 0
      || !offlineIdentity?.username || cacheSchoolId == null || !navigator.onLine || pendingEntries.length > 0
      || marksLoading || registrationsLoading || marksError || registrationsError || !hasRememberedUsername || hasUnresolvedOperation) return;
    if (passphrase.length < 10) { setOfflineError("Use an offline passphrase of at least 10 characters."); return; }
    if (passphrase !== passphraseAgain) { setOfflineError("The offline passphrases do not match."); return; }
    setBusy(true); setOfflineError("");
    try {
      const roster = learners.map((learner) => ({
        id: learner.id, first_name: learner.first_name || "", middle_name: learner.middle_name || "",
        last_name: learner.last_name || "", full_name: learner.full_name || "",
        admission_number: learner.admission_number || "",
      }));
      const ids = new Set(roster.map((learner) => String(learner.id)));
      const assignmentsInScope = data.assignments.filter((assignment) => same(assignment.stream, streamId)
        && same(assignment.subject, subject.id)).map((assignment) => ({ id: assignment.id, stream: assignment.stream, subject: assignment.subject }));
      const scopedExam = { id: selectedExam.id, term: selectedExam.term, assessment_type: selectedExam.assessment_type,
        name: selectedExam.name, status: selectedExam.status, class_level: selectedExam.class_level };
      const scopedTerm = { id: selectedTerm.id, name: selectedTerm.name, academic_year: selectedTerm.academic_year,
        academic_year_name: selectedTerm.academic_year_name || "", start_date: selectedTerm.start_date || "" };
      const scopedData = {
        exams: [scopedExam], assignments: assignmentsInScope,
        enrollments: data.enrollments.filter((enrollment) => ids.has(String(enrollment.student))
          && same(enrollment.stream, selectedStream.id) && same(enrollment.class_level, selectedClass.id)
          && same(enrollment.academic_year, selectedTerm.academic_year))
          .map((enrollment) => ({ id: enrollment.id, student: enrollment.student, stream: enrollment.stream,
            class_level: enrollment.class_level, academic_year: enrollment.academic_year, is_active: enrollment.is_active })),
        students: roster, terms: [scopedTerm],
        subjects: [{ id: subject.id, name: subject.name, code: subject.code || "", is_active: subject.is_active }],
        streams: [{ id: selectedStream.id, class_level: selectedStream.class_level, name: selectedStream.name }],
        classes: [{ id: selectedClass.id, name: selectedClass.name }],
        papers: paperDefinitions.map((paper) => ({ subject: paper.subject, paper_number: paper.paper_number,
          max_marks: paper.max_marks, weight: paper.weight })),
      };
      const payload = {
        version: 1,
        identity: { username: String(offlineIdentity.username), schoolId: String(cacheSchoolId),
          schoolName: offlineIdentity.school?.name || offlineIdentity.school_name || "School", role: "teacher" },
        context: { examGroupId: selectedGroup.id, examId: selectedExam.id, classId: selectedExam.class_level,
          streamId: selectedStream.id, subjectId: subject.id, termId: selectedTerm.id, term: scopedTerm,
          className: selectedClass.name, streamName: selectedStream.name, subjectName: subject.name },
        data: scopedData,
        registrationRows: registrationRows.filter((row) => ids.has(String(row.student))
          && same(row.subject, subject.id) && same(row.academic_year, selectedTerm.academic_year)),
        markRows: markRows.filter((row) => ids.has(String(row.student)) && same(row.subject, subject.id)
          && same(row.term, selectedExam.term) && same(row.academic_year, selectedTerm.academic_year)
          && same(row.assessment_type, selectedExam.assessment_type)).map((row) => ({ id: row.id,
            student: row.student, paper_number: row.paper_number, subject: row.subject, term: row.term,
            academic_year: row.academic_year, assessment_type: row.assessment_type, marks: row.marks,
            mark_status: row.mark_status, status: row.status, updated_at: row.updated_at || null })),
        operations: [],
      };
      const metadata = await saveOfflinePayload(payload, passphrase);
      setPreparedOffline(payload); setOfflineExpiry(metadata.expiresAt);
      setOfflineStoragePersistent(metadata.persistent);
      onOfflinePrepared?.(passphrase);
      setPassphrase(""); setPassphraseAgain("");
    } catch (error) {
      setOfflineError(error?.message || "Could not prepare encrypted marks for offline use.");
    } finally { setBusy(false); }
  };

  const resumeOffline = async () => {
    if (!existingPassphrase || !offlineMetadata || offlineMetadata.expired) return;
    setBusy(true); setOfflineError("");
    try {
      const payload = await loadOfflinePayload(existingPassphrase, offlineIdentity?.username, cacheSchoolId);
      setPreparedOffline(payload);
      setOfflineExpiry(payload.offlineMetadata?.expiresAt || offlineMetadata.expiresAt);
      setOfflineStoragePersistent(offlineMetadata.storagePersistent);
      setExamGroupId(String(payload.context.examGroupId));
      setClassId(String(payload.context.classId));
      setStreamId(String(payload.context.streamId));
      setSubjectId(String(payload.context.subjectId));
      onOfflinePrepared?.(existingPassphrase);
      setExistingPassphrase("");
    } catch (error) { setOfflineError(error?.message || "Could not unlock the prepared offline copy."); }
    finally { setBusy(false); }
  };

  const saveOfflineDraft = async () => {
    const secret = offlinePassphrase || passphrase;
    if (!preparedOffline || !secret) throw new Error("Prepare this exact class, stream, and subject for offline use first.");
    if (!offlineMode && (!same(preparedOffline.context.examId, selectedExam?.id)
      || !same(preparedOffline.context.subjectId, subject?.id) || !same(preparedOffline.context.streamId, streamId))) {
      throw new Error("This marks context was not prepared for offline use. Reconnect to prepare the selected context.");
    }
    const active = (preparedOffline.operations || []).find((operation) => ["pending", "waiting", "failed", "conflict"].includes(operation.status));
    if (active) throw new Error("A draft batch for this prepared context is still unsynced. Reconnect or resolve its conflict before saving another batch.");
    if (offlineMode && (preparedOffline.operations || []).some((operation) => operation.status === "synced")) {
      throw new Error("This offline batch has already synced. Return online, sign in, refresh marks, and prepare a fresh copy before making another batch.");
    }
    const entries = pendingEntries.map((entry) => ({ ...entry,
      expected_updated_at: oldMark(entry.student, entry.paper_number)?.updated_at || null }));
    const operation = createDraftOperation({ exam: selectedExam.id, subject: subject.id, entries });
    const localRows = entries.map((entry) => {
      const previous = oldMark(entry.student, entry.paper_number) || {};
      return { ...previous, id: previous.id || `offline:${operation.offline_operation_id}:${entry.student}:${entry.paper_number}`,
        student: entry.student, paper_number: entry.paper_number, marks: entry.marks, mark_status: entry.mark_status,
        term: selectedExam.term, academic_year: selectedTerm.academic_year, subject: subject.id,
        assessment_type: selectedExam.assessment_type, status: "draft" };
    });
    const next = await updateOfflinePayload(secret, (current) => ({ ...current,
      markRows: [...(current.markRows || []).filter((mark) => !entries.some((entry) => same(mark.student, entry.student)
        && Number(mark.paper_number) === Number(entry.paper_number))), ...localRows],
      operations: [...(current.operations || []), operation],
    }), offlineIdentity?.username || preparedOffline.identity.username, cacheSchoolId || preparedOffline.identity.schoolId);
    setPreparedOffline(next); setMarkRows(next.markRows || []);
    const changedValues = { ...values }, changedDispositions = { ...dispositions };
    entries.forEach((entry) => {
      const key = cellKey(entry.student, entry.paper_number);
      changedValues[key] = entry.marks === null ? "" : String(entry.marks);
      changedDispositions[key] = entry.mark_status;
    });
    setValues(changedValues); setDispositions(changedDispositions);
    setOfflineError("");
    if (navigator.onLine) window.dispatchEvent(new CustomEvent("marian:offline-sync-request"));
  };

  const retryOfflineOperation = async (operationId) => {
    const secret = offlinePassphrase;
    if (!secret || !preparedOffline) return;
    try {
      const next = await updateOfflinePayload(secret, (current) => ({ ...current,
        operations: retryOperation(current.operations || [], operationId) }),
      offlineIdentity?.username || preparedOffline.identity.username, cacheSchoolId || preparedOffline.identity.schoolId);
      setPreparedOffline(next);
      window.dispatchEvent(new CustomEvent("marian:offline-sync-request"));
    } catch (error) { setOfflineError(error?.message || "Could not retry this saved batch."); }
  };

  const updateCell = (studentId, paperNumber, value) => {
    setValues((current) => ({ ...current, [cellKey(studentId, Number(paperNumber))]: value }));
    setSaveError("");
  };
  const updateDisposition = (studentId, paperNumber, status) => {
    const key = cellKey(studentId, Number(paperNumber));
    setDispositions((current) => ({ ...current, [key]: status }));
    if (status !== "scored") {
      setValues((current) => ({ ...current, [key]: "" }));
    }
    setSaveError("");
  };

  const save = async () => {
    if (!selectedExam || !subject || pendingEntries.length === 0 || countInvalid > 0 || busy || tooManyPapers) return;
    setBusy(true);
    setSaveError("");
    try {
      if (offlineMode || !navigator.onLine) {
        await saveOfflineDraft();
        toast("Draft batch saved on this device. It is unsynced and has not been submitted, approved, or locked.", "ok");
        return;
      }
      const response = await api("/api/performance/batch/", "POST", {
        exam: selectedExam.id,
        subject: subject.id,
        entries: pendingEntries,
      });
      if (!response.ok) {
        const message = await responseMessage(response);
        setSaveError(message);
        toast(`Could not save the batch: ${message}`, "err");
        return;
      }
      const result = await response.json();
      toast(`Drafts saved: ${result.created} new, ${result.updated} updated${result.deleted ? `, ${result.deleted} cleared` : ""}.`, "ok");
      window.dispatchEvent(new CustomEvent("marian:dashboard-refresh"));
      setMarksReload((count) => count + 1);
    } catch (error) {
      const message = error?.message || "Could not save the marks. Check your connection and try again.";
      setSaveError(message);
      toast(message, "err");
    } finally {
      setBusy(false);
    }
  };

  const submitDrafts = async () => {
    setAsk(null);
    if (!selectedExam || !subject || !streamId || pendingEntries.length) return;
    setBusy(true);
    try {
      const response = await api("/api/performance/batch/submit/", "POST", {
        exam: selectedExam.id, subject: subject.id, stream: streamId,
      });
      if (!response.ok) {
        const message = await responseMessage(response);
        toast(`Could not submit drafts: ${message}`, "err");
        return;
      }
      const result = await response.json();
      toast(result.submitted
        ? `${result.submitted} draft mark${result.submitted === 1 ? "" : "s"} submitted${result.pending ? `; ${result.pending} pending entries remain` : ""}.`
        : "No resolved draft marks to submit; pending entries remain in draft.", "ok");
      setMarksReload((count) => count + 1);
      window.dispatchEvent(new CustomEvent("marian:dashboard-refresh"));
    } catch (error) {
      toast(error?.message || "Could not submit the batch. Check your connection and try again.", "err");
    } finally {
      setBusy(false);
    }
  };

  const pasteRows = learners.map((learner) => ({
    id: learner.id,
    student: learner.id,
    name: makeName(learner),
    o: editable(oldMark(learner.id, visiblePapers[0]?.paper_number)) ? null : oldMark(learner.id, visiblePapers[0]?.paper_number),
  }));
  const pasteValues = Object.fromEntries(learners.map((learner) => [
    learner.id, markStatus(learner.id, visiblePapers[0]?.paper_number || 1) === "scored"
      ? markValue(learner.id, visiblePapers[0] || { paper_number: 1 }) : "",
  ]));
  const applyPasted = (next) => {
    setValues((current) => {
      const updated = { ...current };
      Object.entries(next).forEach(([student, value]) => {
        updated[cellKey(student, Number(visiblePapers[0]?.paper_number || 1))] = value;
      });
      return updated;
    });
    setDispositions((current) => {
      const updated = { ...current };
      Object.entries(next).forEach(([student, value]) => {
        if (value !== "") updated[cellKey(student, Number(visiblePapers[0]?.paper_number || 1))] = "scored";
      });
      return updated;
    });
    setSaveError("");
  };

  if (loadingError) return <ErrorState text={`Could not load marks-entry data: ${loadingError}`} onRetry={() => setRetry((count) => count + 1)} />;
  if (!data) return <Loading />;

  const groupLabel = (group) => `${group.term.name} — ${group.name} (${ASSESSMENTS[group.type] || group.type})`;
  const className = data.classes.find((item) => same(item.id, classId))?.name || "";
  const streamName = data.streams.find((item) => same(item.id, streamId))?.name || "";
  const rosterIds = new Set(learners.map((learner) => String(learner.id)));
  const readyDraftCount = markRows.filter((mark) =>
    rosterIds.has(String(mark.student)) && mark.status === "draft"
    && mark.mark_status !== "pending").length;
  const pendingDraftCount = markRows.filter((mark) =>
    rosterIds.has(String(mark.student)) && mark.status === "draft"
    && mark.mark_status === "pending").length;
  const queuedOperations = preparedOffline?.operations || [];
  const hasUnresolvedOperation = queuedOperations.some((operation) => operation.status !== "synced");
  const rowTotals = (learner) => {
    let total = 0, maxTotal = 0, weighted = 0, activeWeight = 0, hasValue = false;
    visiblePapers.forEach((paper) => {
      const value = markValue(learner.id, paper);
      const status = markStatus(learner.id, paper.paper_number);
      if (status === "scored" && value !== "" && !cellError(learner.id, paper)) {
        hasValue = true;
        total += Number(value);
        maxTotal += maxFor(paper);
        weighted += Number(value) / maxFor(paper) * weightFor(paper);
        activeWeight += weightFor(paper);
      } else if (status === "absent") {
        hasValue = true;
        maxTotal += maxFor(paper);
        activeWeight += weightFor(paper);
      }
    });
    return { total, maxTotal, weighted, activeWeight, hasValue,
      percentage: activeWeight ? weighted * 100 / activeWeight : null };
  };

  return (
    <div>
      <h2>Teacher marks entry</h2>
      <p>Select a draft examination, class, stream, and your assigned subject. Registered learners appear automatically. Zero is a valid scored mark; choose Absent explicitly. Blank entries remain Pending.</p>

      <Card title="Choose examination and teaching group">
        {examGroups.length === 0 ? (
          <EmptyState title="No draft examinations available" text="A school admin must create a draft examination for a class where you have an active teaching assignment." />
        ) : (
          <div style={styles.selectors}>
            <Select id="mk-exam" label="Examination" value={examGroupId} disabled={offlineMode}
              onChange={(event) => { setExamGroupId(event.target.value); setClassId(""); setStreamId(""); setSubjectId(""); setValues({}); }}>
              <option value="">Choose examination</option>
              {examGroups.map((group) => <option key={group.id} value={group.id}>{groupLabel(group)}</option>)}
            </Select>
            <Select id="mk-class" label="Class" value={classId} disabled={offlineMode || !selectedGroup}
              onChange={(event) => { setClassId(event.target.value); setStreamId(""); setSubjectId(""); setValues({}); }}>
              <option value="">{selectedGroup ? "Choose class" : "Choose an examination first"}</option>
              {classOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
            <Select id="mk-stream" label="Stream" value={streamId} disabled={offlineMode || !selectedExam}
              onChange={(event) => { setStreamId(event.target.value); setSubjectId(""); setValues({}); }}>
              <option value="">{selectedExam ? "Choose stream" : "Choose a class first"}</option>
              {streamOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </Select>
            <Select id="mk-subject" label="Assigned subject" value={subjectId} disabled={offlineMode || !streamId}
              onChange={(event) => { setSubjectId(event.target.value); setValues({}); }}>
              <option value="">{streamId ? "Choose assigned subject" : "Choose a stream first"}</option>
              {assignments.map((item) => <option key={item.id} value={item.id}>{item.code ? `${item.name} (${item.code})` : item.name}</option>)}
            </Select>
          </div>
        )}
        {selectedExam && selectedTerm && <Alert kind="info">
          Draft examination: <strong>{selectedExam.name}</strong> · {selectedTerm.name} {selectedTerm.academic_year_name || ""} · {ASSESSMENTS[selectedExam.assessment_type] || selectedExam.assessment_type}
        </Alert>}
      </Card>

      {subject && selectedExam && <Card title={`${subject.name} — ${className}${streamName ? ` / ${streamName}` : ""}`}>
        {!offlineMode && <section className="offline-prep" aria-label="Prepare marks for offline use">
          <h3>Prepare this marks context for offline</h3>
          <p>Only this examination, class, stream, assigned subject, registered roster, and currently saved marks will be encrypted on this device. Preparing is explicit; each copy expires after seven days.</p>
          {preparedOffline && <div className="offline-notice">A prepared copy is on this device{offlineExpiry ? ` until ${new Date(offlineExpiry).toLocaleString()}` : ""}. Browser storage is {offlineStoragePersistent ? "marked persistent" : "best-effort and may be evicted"}. Preparing another context will replace that copy.</div>}
          {offlineMetadata && !offlineMetadata.expired && !preparedOffline &&
            <div className="offline-resume">
              <strong>Existing encrypted copy found</strong>
              <span>Saved for {offlineMetadata.username}; expires {new Date(offlineMetadata.expiresAt).toLocaleString()}. Storage is {offlineMetadata.storagePersistent ? "marked persistent" : "best-effort and may be evicted"}. Unlock it to view its context and pending sync status.</span>
              <label htmlFor="marks-offline-existing-passphrase">Offline passphrase</label>
              <input id="marks-offline-existing-passphrase" type="password" autoComplete="current-password" minLength={10}
                value={existingPassphrase} onChange={(event) => setExistingPassphrase(event.target.value)} />
              <Button kind="secondary" busy={busy} disabled={!existingPassphrase} onClick={resumeOffline}>Unlock existing copy</Button>
            </div>}
          {offlineMetadata?.expired && <div className="offline-notice warn">The previous encrypted copy expired. Prepare a fresh copy after confirming this context and its saved marks.</div>}
          <div className="offline-prep__fields">
            <label>Offline passphrase (10+ characters)<input type="password" autoComplete="new-password" minLength={10} value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)} /></label>
            <label>Confirm offline passphrase<input type="password" autoComplete="new-password" minLength={10} value={passphraseAgain}
              onChange={(event) => setPassphraseAgain(event.target.value)} /></label>
          </div>
          <Button kind="secondary" busy={busy} disabled={!navigator.onLine || pendingEntries.length > 0 || marksLoading || registrationsLoading
            || !!marksError || !!registrationsError || !learners.length || !offlineIdentity?.username || cacheSchoolId == null
            || !hasRememberedUsername || hasUnresolvedOperation || (!!offlineMetadata && !offlineMetadata.expired && !preparedOffline)}
            onClick={prepareOffline}>Prepare offline</Button>
          {offlineMetadata && !offlineMetadata.expired && !preparedOffline && <div className="offline-notice warn">Unlock the existing encrypted copy first, or explicitly forget it before preparing another context. This prevents accidental loss of unsynced work.</div>}
          {!navigator.onLine && <div className="offline-notice warn">Connect before preparing a fresh offline copy. Existing prepared data is not replaced while offline.</div>}
          {pendingEntries.length > 0 && <div className="offline-notice warn">Save or clear online changes before preparing; offline preparation copies only currently saved marks.</div>}
          {!hasRememberedUsername && <div className="offline-notice warn">Offline boot requires this teacher’s remembered-session username. Choose “Remember me for 7 days” when signing in.</div>}
          {hasUnresolvedOperation && <div className="offline-notice conflict">An unsynced or conflicted batch is retained. Resolve or retry it before preparing a replacement context.</div>}
          {preparedOffline && onForget && <div className="offline-device-action"><button type="button" onClick={onForget}>Forget this device and sign out</button></div>}
          {offlineError && <div className="offline-alert" role="alert">{offlineError}</div>}
        </section>}
        {offlineMode && offlineExpiry && <div className="offline-notice warn">Prepared copy expiry: {new Date(offlineExpiry).toLocaleString()}. This copy is limited to the context shown here.</div>}
        {queuedOperations.length > 0 && <section aria-label="Offline draft batch status">
          {queuedOperations.map((operation) => {
            const labels = { pending: "Unsynced draft batch", waiting: "Waiting to sync", failed: "Sync failed", conflict: "Conflict — review required", synced: "Draft batch synced" };
            const message = operation.last_error || (operation.status === "synced" ? `Synced ${new Date(operation.synced_at).toLocaleString()}.` : "It has not been submitted, approved, or locked.");
            return <div className={`offline-notice ${operation.status === "conflict" || operation.status === "failed" ? "conflict" : ""}`} key={operation.offline_operation_id}>
              <strong>{labels[operation.status] || "Offline draft batch"}</strong> · {operation.body.entries.length} mark change(s). {message}
              {(operation.status === "failed" || operation.status === "conflict") && navigator.onLine && offlinePassphrase
                && <button type="button" onClick={() => retryOfflineOperation(operation.offline_operation_id)}>Retry same batch</button>}
            </div>;
          })}
        </section>}
        {tooManyPapers && <Alert kind="err">This subject has a paper numbered above Paper 3. This entry grid supports Paper 1, Paper 2, and optional Paper 3; update the subject paper setup before entering these marks.</Alert>}
        {badWeight && <Alert kind="warn">Configured paper weights total {expectedWeight.toFixed(2)}%, not 100%. Marks can be saved as drafts, but the examination cannot be published until the weights are corrected.</Alert>}
        {registrationsError && <Alert kind="err">Could not load registered learners: {registrationsError}</Alert>}
        {marksError && <Alert kind="err">Could not load saved marks: {marksError}</Alert>}
        {registrationsLoading && <Alert kind="info">Loading registered learners for this subject and academic year…</Alert>}
        {marksLoading && <Alert kind="info">Loading saved draft marks…</Alert>}
        {learners.length === 0 ? (
          registrationsError || registrationsLoading || marksError || marksLoading
            ? null
            : <EmptyState title="No registered learners in this stream" text="Subject registration is required for a learner to appear in marks entry." />
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <Badge kind="info">{learners.length} registered learner{learners.length === 1 ? "" : "s"}</Badge>
              <span>Enter 0 to each paper's maximum, or select Absent, Exempted, Not assessed, or Pending.</span>
            </div>
            {visiblePapers.length > 0 && <PasteMarks rows={pasteRows} st={learners} vals={pasteValues} setVals={applyPasted} />}
            <div style={{ overflowX: "auto", marginTop: 12, border: "1px solid #e2e8f0", borderRadius: 12 }}>
              <table className="mu-table" style={styles.table}>
                <thead><tr>
                  <th scope="col">Learner</th>
                  {visiblePapers.map((paper) => <th key={paper.paper_number} scope="col" style={styles.nowrap}>
                    Paper {paper.paper_number}<span style={styles.small}>Max {maxFor(paper)}{paperDefinitions.length ? ` · Weight ${weightFor(paper)}%` : ""}</span>
                  </th>)}
                  <th scope="col">Total</th>
                  <th scope="col">Percentage</th>
                  <th scope="col">Status</th>
                </tr></thead>
                <tbody>{learners.map((learner) => {
                  const totals = rowTotals(learner);
                  const savedStatuses = visiblePapers.map((paper) => ({
                    paper, mark: oldMark(learner.id, paper.paper_number),
                  })).filter((item) => item.mark);
                  return <tr key={learner.id}>
                    <td>
                      <strong>{makeName(learner)}</strong>
                      {learner.admission_number && <span style={styles.small}>{learner.admission_number}</span>}
                    </td>
                    {visiblePapers.map((paper) => {
                      const previous = oldMark(learner.id, paper.paper_number);
                      const canEdit = editable(previous);
                      const value = markValue(learner.id, paper);
                      const outcome = markStatus(learner.id, paper.paper_number);
                      const invalid = canEdit && cellError(learner.id, paper);
                      return <td key={paper.paper_number}>
                        {canEdit ? <>
                          <select className="mu-input" style={styles.input}
                            value={outcome} aria-label={`${makeName(learner)} Paper ${paper.paper_number} status`}
                            disabled={marksLoading || registrationsLoading || !!registrationsError || !!marksError || busy}
                            onChange={(event) => updateDisposition(learner.id, paper.paper_number, event.target.value)}>
                            <option value="">Not entered — pending</option>
                            {MARK_STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                          </select>
                          {outcome === "scored" && <input className="mu-input" style={{ ...styles.input, ...(invalid ? { borderColor: "#dc2626" } : {}) }}
                            type="number" min="0" max={maxFor(paper)} step="0.01" inputMode="decimal"
                            value={value} aria-label={`${makeName(learner)} Paper ${paper.paper_number} score`}
                            aria-invalid={invalid || undefined}
                            disabled={marksLoading || registrationsLoading || !!registrationsError || !!marksError || busy}
                            onChange={(event) => updateCell(learner.id, paper.paper_number, event.target.value)} />}
                          {invalid && <span style={{ ...styles.small, color: "#b91c1c" }}>Enter 0–{maxFor(paper)}</span>}
                        </> : <div>
                          <Badge kind={outcome === "scored" ? "info" : outcome === "absent" ? "warn" : "teal"}>
                            {MARK_STATUS_LABELS[outcome] || outcome}
                          </Badge>
                          {outcome === "scored" && <span style={styles.small}>{previous?.marks}</span>}
                        </div>}
                      </td>;
                    })}
                    <td style={styles.total}>{totals.hasValue ? `${totals.total.toFixed(2)} / ${totals.maxTotal.toFixed(2)}` : "—"}</td>
                    <td style={styles.total}>{totals.hasValue ? `${totals.weighted.toFixed(2)}%` : "—"}</td>
                    <td>
                      {savedStatuses.length > 0 ? <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {savedStatuses.map(({ paper, mark }) => <Badge key={mark.id} kind={STATUSES[mark.status] || "info"}>
                          P{paper.paper_number}: {MARK_STATUS_LABELS[mark.mark_status] || mark.mark_status} · {mark.status}
                        </Badge>)}
                      </div> : <Badge kind="info">Not saved</Badge>}
                    </td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
            <p>Totals include scored marks and count an explicit absence as zero. Exempted and not-assessed papers are excluded from the percentage denominator. Pending papers contribute nothing until resolved. A scored zero remains a scored zero.</p>
            {saveError && <Alert kind="err">{saveError}</Alert>}
            {offlineError && offlineMode && <div className="offline-alert" role="alert">{offlineError}</div>}
            {countInvalid > 0 && <Alert kind="err">Fix {countInvalid} invalid cell{countInvalid === 1 ? "" : "s"} before saving. Each paper has its own maximum mark.</Alert>}
            <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12, marginTop: 14 }}>
              <Button kind="teal" busy={busy} onClick={save}
                disabled={pendingEntries.length === 0 || countInvalid > 0 || tooManyPapers || marksLoading || registrationsLoading
                  || !!marksError || !!registrationsError || ((offlineMode || !navigator.onLine) && !preparedOffline)}>
                {offlineMode || !navigator.onLine ? "Save offline draft batch" : "Save draft batch"}{pendingEntries.length ? ` (${pendingEntries.length} cell${pendingEntries.length === 1 ? "" : "s"})` : ""}
              </Button>
              {!offlineMode && <Button kind="secondary" disabled={!navigator.onLine || busy || marksLoading || registrationsLoading || !!marksError || !!registrationsError || pendingEntries.length > 0 || readyDraftCount === 0}
                onClick={() => setAsk(true)}>
                Submit resolved drafts{readyDraftCount ? ` (${readyDraftCount})` : ""}
              </Button>}
              {!offlineMode && <Button kind="secondary" disabled={!navigator.onLine || busy} onClick={() => { setMarksReload((count) => count + 1); setRegistrationsReload((count) => count + 1); }}>Refresh saved marks</Button>}
              {pendingEntries.length > 0 && <span>{pendingEntries.length} changed mark cell{pendingEntries.length === 1 ? "" : "s"} ready to save.</span>}
              {pendingDraftCount > 0 && <span>{pendingDraftCount} explicitly pending draft cell{pendingDraftCount === 1 ? "" : "s"} will stay in draft.</span>}
            </div>
          </>
        )}
      </Card>}

      {ask && <ConfirmDialog title="Submit resolved marks for approval?" confirm="Submit batch"
        text={`This submits ${readyDraftCount} resolved draft cell${readyDraftCount === 1 ? "" : "s"} for ${subject?.name || "the selected subject"} in ${className}${streamName ? ` / ${streamName}` : ""}. Pending cells remain drafts${pendingDraftCount ? ` (${pendingDraftCount} saved as pending)` : ""}. Submitted marks can be corrected only by an administrator or returned for changes.`}
        onYes={submitDrafts} onNo={() => setAsk(null)} />}
    </div>
  );
}
