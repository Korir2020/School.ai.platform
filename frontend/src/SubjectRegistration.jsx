import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Card, Select, Button, Alert, EmptyState, Loading, ErrorState } from "./ui";

const YEARS = "/api/academic-years/";
const ENROLLMENTS = "/api/enrollments/";
const STUDENTS = "/api/students/";
const SUBJECTS = "/api/subjects/";
const REGISTRATIONS = "/api/subject-registrations/";
const PATHWAYS = "/api/curriculum-pathways/";

const refId = (value) => value && typeof value === "object" ? value.id : value;
const sameId = (a, b) => String(refId(a) ?? "") === String(refId(b) ?? "");
const isActive = (value) => value === true || value === 1 || value === "1" || value === "true";

async function listChecked(path) {
  const sep = path.includes("?") ? "&" : "?";
  let url = `${path}${sep}page_size=200`;
  const rows = [];
  for (let page = 0; page < 200 && url; page += 1) {
    const response = await api(url);
    if (!response.ok) throw new Error(await errorMessage(response));
    const body = await response.json();
    if (Array.isArray(body)) return body;
    rows.push(...(body.results || []));
    if (!body.next) break;
    const next = new URL(body.next, window.location.origin);
    url = `${next.pathname}${next.search}`;
  }
  return rows;
}

function studentName(student, fallbackId) {
  if (!student || typeof student !== "object") return `Learner ${fallbackId ?? student ?? ""}`;
  const full = student.full_name || student.name || [student.first_name, student.middle_name, student.last_name]
    .filter(Boolean).join(" ");
  return full || student.admission_number || student.admission_no || `Learner ${student.id ?? fallbackId ?? ""}`;
}

function describeEnrollment(enrollment, students) {
  const studentId = refId(enrollment.student);
  const student = students.find((item) => sameId(item.id, studentId)) || enrollment.student;
  const name = studentName(student, studentId);
  const className = enrollment.class_level && typeof enrollment.class_level === "object"
    ? (enrollment.class_level.name || enrollment.class_level.title || "")
    : "";
  const streamName = enrollment.stream && typeof enrollment.stream === "object"
    ? (enrollment.stream.name || enrollment.stream.title || "")
    : "";
  const detail = [className, streamName].filter(Boolean).join(" · ");
  return detail ? `${name} — ${detail}` : name;
}

async function errorMessage(response) {
  const fallback = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body === "string" && body.trim()) return body;
    if (!body || typeof body !== "object") return fallback;
    for (const key of ["detail", "message", "error"]) {
      if (typeof body[key] === "string" && body[key].trim()) return body[key];
    }
    const details = Object.entries(body).map(([field, value]) => {
      const text = Array.isArray(value) ? value.join(" ")
        : typeof value === "string" ? value
          : value && typeof value === "object" ? JSON.stringify(value) : String(value ?? "");
      return text ? `${field}: ${text}` : "";
    }).filter(Boolean);
    return details.length ? details.join(" ") : fallback;
  } catch {
    return fallback;
  }
}

const styles = {
  selectors: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))", gap: 12 },
  summary: { display: "flex", flexWrap: "wrap", gap: 8, margin: "12px 0" },
  summaryItem: { padding: "6px 10px", borderRadius: 999, background: "#f1f5f9", fontSize: 14 },
  subjectGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))", gap: 10 },
  subject: { border: "1px solid #dbe3ea", borderRadius: 10, padding: 12, minWidth: 0 },
  subjectTop: { display: "flex", alignItems: "flex-start", gap: 10 },
  checkbox: { width: 18, height: 18, marginTop: 2, flex: "0 0 auto" },
  subjectName: { fontWeight: 600, overflowWrap: "anywhere" },
  subjectCode: { color: "#64748b", fontSize: 13, marginTop: 3 },
  category: { marginTop: 10 },
  actions: { display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, marginTop: 16 },
};

export default function SubjectRegistration() {
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  const [yearId, setYearId] = useState("");
  const [enrollmentId, setEnrollmentId] = useState("");
  const [pathwayId, setPathwayId] = useState("");
  const [categories, setCategories] = useState({});
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    let live = true;
    setData(null);
    setLoadError("");
    Promise.all([
      listChecked(YEARS),
      listChecked(ENROLLMENTS),
      listChecked(STUDENTS),
      listChecked(SUBJECTS),
      listChecked(REGISTRATIONS),
      listChecked(PATHWAYS),
    ]).then(([years, enrollments, students, subjects, registrations, pathways]) => {
      if (live) {
        setData({ years, enrollments, students, subjects, registrations, pathways });
        setYearId((current) => current || String(years.find((year) => isActive(year.is_active))?.id || ""));
      }
    }).catch(() => {
      if (live) setLoadError("Could not load the subject registration data. Check your connection and try again.");
    });
    return () => { live = false; };
  }, [retry]);

  const years = useMemo(() => data ? data.years : [], [data]);
  const activeSubjects = useMemo(() => data ? data.subjects.filter((subject) => isActive(subject.is_active)) : [], [data]);
  const activeEnrollments = useMemo(() => {
    if (!data || !yearId) return [];
    return data.enrollments.filter((enrollment) => isActive(enrollment.is_active)
      && sameId(enrollment.academic_year, yearId));
  }, [data, yearId]);
  const enrollment = activeEnrollments.find((item) => String(item.id) === enrollmentId);
  const isSenior = !!enrollment && enrollment.curriculum_code === "CBC"
    && Number(enrollment.class_level_number) >= 10 && Number(enrollment.class_level_number) <= 12;
  const availablePathways = useMemo(() => {
    if (!data || !enrollment || !isSenior) return [];
    const classLevelId = refId(enrollment.class_level);
    return data.pathways.filter((pathway) => pathway.curriculum_code === "CBC"
      && (pathway.class_levels || []).some((id) => sameId(id, classLevelId)));
  }, [data, enrollment, isSenior]);
  const availableSubjects = useMemo(() => {
    if (!enrollment) return activeSubjects;
    const classLevelId = refId(enrollment.class_level);
    return activeSubjects.filter((subject) => {
      const levels = subject.definition_class_levels || [];
      if (levels.length && !levels.some((id) => sameId(id, classLevelId))) return false;
      if (isSenior) {
        if (subject.definition && subject.curriculum_code !== "CBC") return false;
        const tagged = subject.definition_pathways || [];
        return tagged.length === 0 || (!!pathwayId && tagged.some((pathway) => sameId(pathway.id, pathwayId)));
      }
      return true;
    });
  }, [activeSubjects, enrollment, isSenior, pathwayId]);
  const learnerId = enrollment ? refId(enrollment.student) : "";
  const selectedIds = Object.keys(categories).filter((id) => categories[id] !== undefined);
  const compulsoryCount = selectedIds.filter((id) => categories[id] === "compulsory").length;
  const optionalCount = selectedIds.filter((id) => categories[id] === "optional").length;
  const classifiedCount = compulsoryCount + optionalCount;
  const allClassified = selectedIds.length > 0 && classifiedCount === selectedIds.length;

  useEffect(() => {
    setPathwayId(enrollment && enrollment.pathway ? String(refId(enrollment.pathway)) : "");
  }, [enrollmentId]);

  useEffect(() => {
    if (!data || !yearId || !enrollment) {
      setCategories({});
      return;
    }
    const existing = {};
    data.registrations.forEach((row) => {
      if (sameId(row.student, learnerId) && sameId(row.academic_year, yearId)) {
        const subjectId = refId(row.subject);
        if (subjectId != null && availableSubjects.some((subject) => sameId(subject.id, subjectId))) {
          existing[String(subjectId)] = row.category;
        }
      }
    });
    setCategories(existing);
  }, [data, yearId, enrollmentId, availableSubjects]);

  const chooseYear = (value) => {
    setYearId(value);
    setEnrollmentId("");
    setCategories({});
    setSaveError("");
  };

  const chooseEnrollment = (value) => {
    setEnrollmentId(value);
    const selected = activeEnrollments.find((item) => String(item.id) === String(value));
    setPathwayId(selected?.pathway ? String(refId(selected.pathway)) : "");
    setCategories({});
    setSaveError("");
  };

  const toggleSubject = (subjectId, checked) => {
    setCategories((current) => {
      const next = { ...current };
      if (checked) next[String(subjectId)] = "";
      else delete next[String(subjectId)];
      return next;
    });
    setSaveError("");
  };

  const setCategory = (subjectId, category) => {
    setCategories((current) => ({ ...current, [String(subjectId)]: category }));
    setSaveError("");
  };

  const save = async () => {
    if (!enrollment || selectedIds.length === 0 || !allClassified || busy) return;
    setBusy(true);
    setSaveError("");
    const selectedSubjects = availableSubjects.filter((subject) => selectedIds.includes(String(subject.id)));
    const payload = {
      student: learnerId,
      academic_year: refId(yearId),
      ...(isSenior ? { pathway: Number(pathwayId) } : {}),
      subjects: selectedSubjects.map((subject) => ({
        subject: subject.id,
        category: categories[String(subject.id)],
      })),
    };
    try {
      const response = await api(REGISTRATIONS, "POST", payload);
      if (!response.ok) {
        const message = await errorMessage(response);
        setSaveError(message);
        toast(`Could not save subject registrations: ${message}`, "err");
        return;
      }
      setData((current) => ({
        ...current,
        enrollments: current.enrollments.map((row) => String(row.id) === String(enrollment.id)
          ? { ...row, pathway: isSenior ? Number(pathwayId) : row.pathway,
            pathway_name: availablePathways.find((path) => String(path.id) === String(pathwayId))?.name || row.pathway_name }
          : row),
        registrations: [
          ...current.registrations.filter((row) => !(sameId(row.student, learnerId)
            && sameId(row.academic_year, yearId))),
          ...payload.subjects.map((row) => ({
            student: payload.student,
            academic_year: payload.academic_year,
            subject: row.subject,
            category: row.category,
          })),
        ],
      }));
      toast(`Saved ${payload.subjects.length} subject${payload.subjects.length === 1 ? "" : "s"} for ${studentName(
        data.students.find((item) => sameId(item.id, learnerId)) || enrollment.student, learnerId,
      )}.`, "ok");
    } catch {
      const message = "Could not save subject registrations. Check your connection and try again.";
      setSaveError(message);
      toast(message, "err");
    } finally {
      setBusy(false);
    }
  };

  if (loadError) return <ErrorState text={loadError} onRetry={() => setRetry((count) => count + 1)} />;
  if (!data) return <Loading />;

  return (
    <div>
      <h2>Register learner subjects</h2>
      <p>Choose an academic year and an active learner enrollment, then set the subjects for that learner.</p>

      <Card title="Learner and academic year">
        {years.length === 0 ? (
          <EmptyState title="No academic years" text="Create an academic year before registering subjects." />
        ) : (
          <div style={styles.selectors}>
            <Select id="subject-registration-year" label="Academic year" value={yearId}
              onChange={(event) => chooseYear(event.target.value)}>
              <option value="">Choose an academic year</option>
              {years.map((year) => <option key={year.id} value={year.id}>
                {year.name || `Academic year ${year.id}`}{isActive(year.is_active) ? " (Active)" : ""}
              </option>)}
            </Select>
            <Select id="subject-registration-enrollment" label="Active learner enrollment" value={enrollmentId}
              disabled={!yearId || activeEnrollments.length === 0}
              onChange={(event) => chooseEnrollment(event.target.value)}>
              <option value="">{yearId ? "Choose an enrolled learner" : "Choose an academic year first"}</option>
              {activeEnrollments.map((item) => <option key={item.id} value={item.id}>
                {describeEnrollment(item, data.students)}
              </option>)}
            </Select>
          </div>
        )}
        {yearId && activeEnrollments.length === 0 && (
          <EmptyState title="No active learner enrollments" text="There are no active learner enrollments for this academic year." />
        )}
        {enrollment && <Alert kind="info">
          Selected learner: <strong>{describeEnrollment(enrollment, data.students)}</strong>
        </Alert>}
        {enrollment && isSenior && <div style={{ marginTop: 12 }}>
          <Select id="subject-registration-pathway" label="CBC Senior pathway for this academic year" value={pathwayId}
            onChange={(event) => { setPathwayId(event.target.value); setCategories({}); setSaveError(""); }}>
            <option value="">Choose a pathway</option>
            {availablePathways.map((pathway) => <option key={pathway.id} value={pathway.id}>{pathway.name}</option>)}
          </Select>
          {availablePathways.length === 0 && <p>No active pathway is configured for this CBC Senior grade.</p>}
          {enrollment.pathway_name && <p>Current pathway: {enrollment.pathway_name}. Saving a different path replaces the learner’s registered subject combination as one audited change.</p>}
        </div>}
      </Card>

      {enrollment && (!isSenior || pathwayId) && <Card title={isSenior ? "Senior pathway subjects" : "Subjects"}>
        <div style={styles.summary} aria-live="polite">
          <span style={styles.summaryItem}>{selectedIds.length} selected of {availableSubjects.length} available for this class</span>
          <span style={styles.summaryItem}>{compulsoryCount} compulsory</span>
          <span style={styles.summaryItem}>{optionalCount} optional</span>
          {selectedIds.length > classifiedCount &&
            <span style={styles.summaryItem}>{selectedIds.length - classifiedCount} need a category</span>}
        </div>
        {availableSubjects.length === 0 ? (
          <EmptyState title="No subjects for this class" text="There are no active subjects defined for this learner’s class level." />
        ) : (
          <>
            <div style={styles.subjectGrid}>
              {availableSubjects.map((subject) => {
                const id = String(subject.id);
                const selected = Object.prototype.hasOwnProperty.call(categories, id);
                return <div key={subject.id} style={styles.subject}>
                  <div style={styles.subjectTop}>
                    <input id={`subject-registration-${id}`} type="checkbox" checked={selected}
                      style={styles.checkbox} onChange={(event) => toggleSubject(subject.id, event.target.checked)}
                      aria-label={`Register ${subject.name || `subject ${subject.id}`}`} />
                    <label htmlFor={`subject-registration-${id}`} style={styles.subjectName}>
                      {subject.name || `Subject ${subject.id}`}
                      {subject.code && <div style={styles.subjectCode}>{subject.code}</div>}
                    </label>
                  </div>
                  {selected && <div style={styles.category}>
                    <Select id={`subject-category-${id}`} label={`Category for ${subject.name || `subject ${id}`}`}
                      value={categories[id] || ""} onChange={(event) => setCategory(subject.id, event.target.value)}>
                      <option value="">Choose a category</option>
                      <option value="compulsory">Compulsory</option>
                      <option value="optional">Optional</option>
                    </Select>
                  </div>}
                </div>;
              })}
            </div>
            {saveError && <p><Alert kind="err">{saveError}</Alert></p>}
            <div style={styles.actions}>
              <Button kind="teal" busy={busy} disabled={selectedIds.length === 0 || !allClassified || (isSenior && !availablePathways.some((path) => String(path.id) === String(pathwayId)))}
                onClick={save}>Save subject registrations</Button>
              {selectedIds.length === 0 && <span>Select at least one subject to save.</span>}
              {selectedIds.length > 0 && !allClassified && <span>Choose compulsory or optional for each selected subject.</span>}
            </div>
          </>
        )}
      </Card>}
    </div>
  );
}
