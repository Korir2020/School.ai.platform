import { useEffect, useMemo, useRef, useState } from "react";
import { api, upload } from "./api";
import { Badge, Button, Field, Input, Modal } from "./ui";
import "./migration.css";

const CHECK = "/api/students/migration/check/";
const COMMIT = "/api/students/migration/commit/";
const PHOTO = "/api/students/migration/read-photo/";
const PAGE = 60;

const FIELDS = [
  ["", "Not imported"],
  ["first_name", "First name"],
  ["last_name", "Surname"],
  ["full_name", "Full name (one column)"],
  ["other_names", "Other names"],
  ["admission_number", "Admission number"],
  ["assessment_number", "Assessment number"],
  ["upi", "UPI"],
  ["class_level", "Class"],
  ["stream", "Stream"],
];

const TONE = {
  ready: ["ok", "Ready"],
  needs_confirmation: ["warn", "Check"],
  blocked: ["err", "Needs fixing"],
  duplicate: ["info", "Already in Marian"],
};

const TIPS = {
  name_missing: "A first name and a surname are both needed.",
  name_too_long: "Shorten the name. It will not be cut short for you.",
  admission_too_long: "Admission numbers can be up to 50 characters.",
  class_missing: "Choose the class for this learner below.",
  class_not_found: "This class is not in Setup yet. Pick one of the classes that already exist.",
  class_ambiguous: "More than one class matches. Pick the exact class below.",
  class_conflict: "The class and the stream do not agree. Pick both again below.",
  class_split: "The class and stream were read from one cell.",
  stream_not_found: "This stream does not belong to that class. Pick one of the class streams.",
  assessment_missing: "Grade 10 to 12 learners need an assessment number for registration and exams.",
  missing_admission: "Without an admission number the learner gets a temporary one until the real number is known.",
  duplicate_admission_number: "Two rows in this file use the same admission number. Give one of them a different number.",
  duplicate_assessment_number: "Two rows in this file use the same assessment number.",
  duplicate_upi: "Two rows in this file use the same UPI.",
  same_name: "Another row has the same name. Accept it if they are two different learners.",
  same_name_existing: "A learner with this name is already in Marian. Accept it if this is a different learner.",
  similar_name: "The spelling is very close to another learner. Check it, then accept if they are different.",
  admission_number_exists: "This learner is already in Marian, so the row is skipped.",
  assessment_number_exists: "This assessment number is already in Marian, so the row is skipped.",
  upi_exists: "This UPI is already in Marian, so the row is skipped.",
  unreadable_cell: "This cell could not be read from the photo. Type the value below.",
  default_class_used: "This row had no class, so the class you chose for the whole file was used.",
  duplicate_row: "Already in Marian. Change the admission number if it is a different learner.",
};

const isConfirm = (issue) => issue.severity === "confirm";
const rowName = (row) => [row.first_name, row.last_name].filter(Boolean).join(" ") || "Learner " + row.row;
const confirmCodes = (row) => (row.issues || []).filter(isConfirm).map((i) => i.code);
const blockIssues = (row) => (row.issues || []).filter((i) => i.severity === "block");
const firstIssue = (row) => blockIssues(row)[0] || (row.issues || []).find(isConfirm) || null;

function newRequestId() {
  try {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
  } catch { /* older browser */ }
  return "req-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

function classOptions(classes) {
  return (classes || []).map((c) => ({ value: c.name, label: c.name, streams: c.streams || [] }));
}

function streamNames(classes, className) {
  const found = (classes || []).find((c) => c.name === className);
  return found ? found.streams || [] : [];
}

function draftFor(row, classes) {
  const level = (classes || []).find((c) => c.id === row.level_id);
  const stream = level && (level.streams || []).find((s) => s.id === row.stream_id);
  return {
    first_name: row.first_name || "",
    last_name: row.last_name || "",
    admission_number: row.provisional_admission ? "" : row.admission_number || "",
    assessment_number: row.assessment_number || "",
    class_level: level ? level.name : row.class_text || "",
    stream: stream ? stream.name : row.stream_text || "",
  };
}

function changedFields(initial, draft) {
  const out = {};
  Object.keys(draft).forEach((key) => {
    const a = String(draft[key] || "").trim();
    const b = String(initial[key] || "").trim();
    if (a !== b) out[key] = a;
  });
  return out;
}

const STEP_NAMES = ["Choose your file", "Review the learners", "Add to Marian"];

function Steps({ step }) {
  return (
    <>
      <ol className="mc-steps" aria-label="Progress">
        {STEP_NAMES.map((label, i) => {
          const n = i + 1;
          const state = step === n ? " is-current" : step > n ? " is-done" : "";
          return (
            <li key={label} className={"mc-step" + state} aria-current={step === n ? "step" : undefined}>
              <span className="mc-step-dot" aria-hidden="true">{step > n ? "✓" : n}</span>
              <span className="mc-step-label">{label}</span>
            </li>
          );
        })}
      </ol>
      <p className="mc-step-caption">
        <b>Step {step} of {STEP_NAMES.length}</b> · {STEP_NAMES[step - 1] || STEP_NAMES[0]}
      </p>
    </>
  );
}

function Summary({ s, filter, onPick }) {
  const cells = [
    ["all", "Learners found", s.total],
    ["ready", "Ready to add", s.ready],
    ["attention", "Need attention", s.needs_attention],
    ["duplicate", "Already in Marian", s.duplicates],
    ["skipped", "Will be skipped", s.skipped],
  ];
  return (
    <div className="mc-summary" role="group" aria-label="Summary of the check">
      {cells.map(([key, label, value]) => (
        <button key={key} type="button" className={"mc-sum" + (filter === key ? " is-on" : "")}
          aria-pressed={filter === key} onClick={() => onPick(key)}>
          <span className="mc-sum-n">{value}</span>
          <span className="mc-sum-l">{label}</span>
        </button>
      ))}
    </div>
  );
}

function MappingPanel({ result, open, onClose, onApply }) {
  const [map, setMap] = useState(() => {
    const next = {};
    (result.columns || []).forEach((c) => { next[c.index] = c.field || ""; });
    return next;
  });
  const [noHeader, setNoHeader] = useState(result.header_row === -1);
  const used = Object.values(map).filter(Boolean);
  const hasFirst = used.includes("first_name");
  const hasLast = used.includes("last_name");
  const hasFull = used.includes("full_name");
  const hasClass = used.includes("class_level");
  const nameOk = (hasFirst && hasLast) || hasFull;
  const missing = [];
  if (!nameOk) missing.push("a name column (first name + surname, or one full name)");
  if (!hasClass) missing.push("a class column");
  const apply = () => {
    const mapping = {};
    Object.entries(map).forEach(([index, field]) => { if (field) mapping[field] = Number(index); });
    onApply(mapping, noHeader ? -1 : null);
  };
  if (!open) return null;
  return (
    <div className="mc-panel">
      <div className="mc-panel-head">
        <div>
          <h3>Which column is which?</h3>
          <p className="mc-hint">
            We could not read every heading in this file. Match the columns below, then read the file again.
          </p>
        </div>
        <Button kind="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>
      <div className="mc-map">
        {(result.columns || []).map((c) => (
          <div className="mc-map-row" key={c.index}>
            <div className="mc-map-head">
              <b>{c.label || "Column " + (c.index + 1)}</b>
              <span className="mc-map-sample">{(c.samples || []).slice(0, 2).join(" · ") || "no values"}</span>
            </div>
            <select className="mu-input mc-map-select" aria-label={"What is in " + (c.label || "column " + (c.index + 1))}
              value={map[c.index] || ""}
              onChange={(e) => {
                const value = e.target.value;
                setMap((m) => {
                  const next = { ...m };
                  if (value) Object.keys(next).forEach((k) => { if (next[k] === value) next[k] = ""; });
                  next[c.index] = value;
                  return next;
                });
              }}>
              {FIELDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        ))}
      </div>
      <label className="mc-check-line">
        <input type="checkbox" checked={noHeader} onChange={(e) => setNoHeader(e.target.checked)} />
        The first row is a learner, not column names
      </label>
      <div className="mc-panel-foot">
        <p className={"mc-hint" + (missing.length ? " mc-hint-warn" : "")}>
          {missing.length ? "Still needed: " + missing.join(", ") + "." : "Every learner needs a name and a class."}
        </p>
        <Button onClick={apply} disabled={missing.length > 0}>Read the file with these columns</Button>
      </div>
    </div>
  );
}

function ClassPanel({ result, defaultClass, onDefault }) {
  const classes = classOptions(result.classes);
  const level = classes.find((c) => defaultClass === c.value || defaultClass.startsWith(c.value + " "));
  const stream = level ? streamNames(result.classes, level.value).find((s) => defaultClass === level.value + " " + s.name) : null;
  const hasClassColumn = (result.columns || []).some((c) => c.field === "class_level");
  return (
    <div className="mc-panel">
      <div className="mc-panel-head">
        <div>
          <h3>{hasClassColumn ? "Class for rows with no class" : "Which class are these learners in?"}</h3>
          <p className="mc-hint">
            {hasClassColumn
              ? "This file has a class column. If some rows leave the class empty, choose one class to use for them."
              : "This file has no class column. Choose the class that these learners belong to."}
          </p>
        </div>
      </div>
      <div className="mc-two">
        <Field label="Class">
          <select className="mu-input" value={level ? level.value : ""}
            onChange={(e) => onDefault(e.target.value, "")}>
            <option value="">Choose a class…</option>
            {classes.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </Field>
        <Field label="Stream" help={!level ? "" : (streamNames(result.classes, level.value).length ? "" : "This class has no streams.")}>
          <select className="mu-input" value={stream ? stream.name : ""}
            disabled={!level || !streamNames(result.classes, level.value).length}
            onChange={(e) => onDefault(level ? level.value : "", e.target.value)}>
            <option value="">No stream</option>
            {(level ? streamNames(result.classes, level.value) : []).map((s) => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
        </Field>
      </div>
    </div>
  );
}

export default function MigrationCentre({ go }) {
  const navigate = (tab) => {
    if (typeof go === "function") go(tab);
    else window.location.hash = encodeURIComponent(tab);
  };

  const input = useRef({ file: null, text: "", source: "digital", matrix: null });
  const BLANK = { mapping: {}, headerRow: null, defaultClass: "", nameOrder: "", fixes: {}, confirms: {} };
  const ctrl = useRef(BLANK);
  const seq = useRef(0);
  const timer = useRef(null);
  const requestId = useRef("");

  const [ctrlState, setCtrlState] = useState(BLANK);
  const [fileInfo, setFileInfo] = useState(null);
  const [text, setText] = useState("");
  const [source, setSource] = useState("digital");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [selected, setSelected] = useState([]);
  const [editing, setEditing] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [done, setDone] = useState(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [photoOn, setPhotoOn] = useState(null);
  const [pages, setPages] = useState([]);
  const [reading, setReading] = useState(false);

  useEffect(() => {
    let alive = true;
    api(PHOTO).then((r) => r.json()).then((d) => { if (alive) setPhotoOn(!!d.enabled); })
      .catch(() => { if (alive) setPhotoOn(false); });
    return () => { alive = false; };
  }, []);

  useEffect(() => () => clearTimeout(timer.current), []);

  const summary = result && result.summary ? result.summary : null;
  const rows = useMemo(() => (result && result.rows) || [], [result]);
  const classes = useMemo(() => (result && result.classes) || [], [result]);

  function applyCtrl(patch) {
    const next = { ...ctrl.current, ...patch };
    ctrl.current = next;
    setCtrlState(next);
    return next;
  }

  function form(state) {
    const fd = new FormData();
    const src = input.current;
    if (src.matrix) fd.append("matrix", JSON.stringify(src.matrix));
    else if (src.file) fd.append("file", src.file);
    else fd.append("text", src.text || "");
    fd.append("source", src.source || "digital");
    if (Object.keys(state.mapping || {}).length) fd.append("mapping", JSON.stringify(state.mapping));
    if (state.headerRow !== null && state.headerRow !== undefined) fd.append("header_row", String(state.headerRow));
    if (state.defaultClass) fd.append("default_class", state.defaultClass);
    if (state.nameOrder) fd.append("name_order", state.nameOrder);
    if (Object.keys(state.fixes || {}).length) fd.append("fixes", JSON.stringify(state.fixes));
    if (Object.keys(state.confirms || {}).length) fd.append("confirmations", JSON.stringify(state.confirms));
    return fd;
  }

  function hasInput() {
    const src = input.current;
    return !!(src.file || src.matrix || (src.text || "").trim());
  }

  async function runCheck(state, patch) {
    const next = patch ? applyCtrl(patch) : state || ctrl.current;
    if (!hasInput()) {
      setError({ text: "Choose a file or paste your table first." });
      return;
    }
    const id = ++seq.current;
    setBusy("check");
    setError(null);
    try {
      const r = await upload(CHECK, form(next), 120000);
      let data = null;
      try { data = await r.json(); } catch { data = null; }
      if (id !== seq.current) return;
      if (!r.ok) {
        setError({
          text: (data && data.detail) || "The check could not finish (" + r.status + "). Try again.",
          retry: () => runCheck(next),
        });
        return;
      }
      if (data.matrix) input.current = { ...input.current, matrix: data.matrix };
      setResult(data);
      setFilter("all");
      setLimit(PAGE);
      setSelected([]);
      setDone(null);
      const needsMapping = (data.needs_input || []).some((n) => n.code === "mapping");
      setMapOpen(needsMapping || !!data.mapping_uncertain);
    } catch (e) {
      if (id !== seq.current) return;
      const timeout = e && (e.name === "TimeoutError" || e.name === "AbortError");
      setError({
        text: timeout
          ? "The server took too long to answer. Your list is safe. Wait a moment and try again."
          : "We could not reach the server. Your list and corrections are kept. Check your connection, then try again.",
        retry: () => runCheck(next),
      });
    } finally {
      if (id === seq.current) setBusy("");
    }
  }

  function resetInput() {
    clearTimeout(timer.current);
    seq.current += 1;
    input.current = { file: null, text: "", source: "digital", matrix: null };
    ctrl.current = BLANK;
    setCtrlState(BLANK);
    requestId.current = "";
    setFileInfo(null);
    setText("");
    setSource("digital");
    setResult(null);
    setError(null);
    setSelected([]);
    setEditing(null);
    setDone(null);
    setFilter("all");
    setQuery("");
    setClassFilter("");
    setMapOpen(false);
  }

  function takeFile(f) {
    if (!f) return;
    const ok = /\.(csv|tsv|txt|xlsx|xlsm|pdf)$/i.test(f.name);
    const image = /^image\//.test(f.type) || /\.(jpe?g|png|webp|heic)$/i.test(f.name);
    if (image && photoOn !== true) {
      setError({ text: "Photos of a register are not switched on for this school. Use an Excel, CSV or typed PDF file, or type the list below." });
      return;
    }
    if (!ok && !image) {
      setError({ text: "'" + f.name + "' is not a file Marian can read. Use Excel (.xlsx), CSV, TSV or a typed PDF, or paste the table below." });
      return;
    }
    if (f.size > 5 * 1024 * 1024) {
      setError({ text: "This file is larger than 5 MB. Split it into smaller files, or save it as CSV." });
      return;
    }
    if (image) {
      setPages([]);
      addPage(f);
      return;
    }
    clearTimeout(timer.current);
    input.current = { file: f, text: "", source: input.current.source, matrix: null };
    ctrl.current = BLANK;
    setCtrlState(BLANK);
    requestId.current = "";
    setFileInfo({ name: f.name, size: f.size });
    setText("");
    setResult(null);
    setError(null);
    setDone(null);
    runCheck(ctrl.current);
  }

  function onText(value) {
    setText(value);
    input.current = { ...input.current, text: value, file: null, matrix: null };
    if (fileInfo) setFileInfo(null);
    setResult(null);
    setDone(null);
    applyCtrl({ mapping: {}, headerRow: null, fixes: {}, confirms: {} });
    clearTimeout(timer.current);
    if (value.trim().split(/\r?\n/).filter((l) => l.trim()).length > 1) {
      timer.current = setTimeout(() => runCheck(ctrl.current), 900);
    }
  }

  function acceptRow(row, codes) {
    const current = { ...ctrl.current.confirms };
    const set = new Set(current[row] || []);
    codes.forEach((c) => set.add(c));
    if (set.size) current[row] = [...set]; else delete current[row];
    const next = applyCtrl({ confirms: current });
    runCheck(next);
  }

  function acceptMany(list) {
    const current = { ...ctrl.current.confirms };
    list.forEach((row) => {
      const codes = confirmCodes(row);
      if (!codes.length) return;
      const set = new Set(current[row.row] || []);
      codes.forEach((c) => set.add(c));
      current[row.row] = [...set];
    });
    runCheck(applyCtrl({ confirms: current }));
  }


  function saveFix(row, values, initial) {
    const diff = changedFields(initial, values);
    const fixes = { ...ctrl.current.fixes };
    if (Object.keys(diff).length) fixes[row.row] = diff; else delete fixes[row.row];
    setEditing(null);
    runCheck(applyCtrl({ fixes }));
  }

  function clearFix(row) {
    const fixes = { ...ctrl.current.fixes };
    delete fixes[row.row];
    setEditing(null);
    runCheck(applyCtrl({ fixes }));
  }

  function bulkClass(className, streamName) {
    const fixes = { ...ctrl.current.fixes };
    selected.forEach((n) => {
      if (!rows.some((r) => r.row === n)) return;
      const diff = { ...(fixes[n] || {}) };
      diff.class_level = className;
      if (streamName) diff.stream = streamName;
      else if (diff.stream) diff.stream = "";
      fixes[n] = diff;
    });
    setBulkOpen(false);
    runCheck(applyCtrl({ fixes }));
  }

  async function commit() {
    if (!requestId.current) requestId.current = newRequestId();
    setBusy("commit");
    setError(null);
    const fd = form(ctrl.current);
    fd.append("request_id", requestId.current);
    try {
      const r = await upload(COMMIT, fd, 300000);
      let data = null;
      try { data = await r.json(); } catch { data = null; }
      if (!r.ok) {
        setConfirmOpen(false);
        setError({
          text: (data && data.detail) || "Nothing was added. Check the list and try again.",
          retry: r.status === 409 ? () => runCheck(ctrl.current) : () => commit(),
          retryLabel: r.status === 409 ? "Check the list again" : "Try again",
        });
        return;
      }
      requestId.current = "";
      setConfirmOpen(false);
      setDone(data);
      setResult(null);
      setSelected([]);
      setEditing(null);
    } catch (e) {
      setConfirmOpen(false);
      const timeout = e && (e.name === "TimeoutError" || e.name === "AbortError");
      setError({
        text: (timeout
          ? "The server did not answer in time. "
          : "The connection dropped before Marian answered. ")
          + "Your list and corrections are kept. Check the list again: anyone who was already added shows as “Already in Marian”, so nobody is added twice.",
        retry: () => runCheck(ctrl.current),
        retryLabel: "Check the list again",
      });
    } finally {
      setBusy("");
    }
  }

  async function shrink(f) {
    try {
      const url = URL.createObjectURL(f);
      const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url; });
      const k = Math.min(1, 2400 / Math.max(img.width, img.height));
      const cv = document.createElement("canvas");
      cv.width = Math.round(img.width * k);
      cv.height = Math.round(img.height * k);
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url);
      return await new Promise((ok) => cv.toBlob(ok, "image/jpeg", 0.88));
    } catch { return null; }
  }

  async function addPage(f) {
    if (pages.length >= 20) { setError({ text: "Add at most 20 pages at a time." }); return; }
    const blob = await shrink(f);
    if (!blob) { setError({ text: "This photo could not be opened. Save it as a JPG and try again." }); return; }
    setPages((p) => [...p, { name: f.name, blob, status: "waiting" }]);
  }

  async function readPages() {
    setReading(true);
    setError(null);
    const list = pages.map((p) => ({ ...p }));
    const update = () => setPages(list.map((p) => ({ ...p })));
    let headers = list[0] && list[0].status === "done" ? list[0].headers : null;
    for (let i = 0; i < list.length; i += 1) {
      if (list[i].status === "done") continue;
      list[i].status = "reading";
      update();
      try {
        const fd = new FormData();
        fd.append("photo", list[i].blob, "page.jpg");
        fd.append("page", String(i + 1));
        if (headers) fd.append("headers", JSON.stringify(headers));
        const r = await upload(PHOTO, fd, 180000);
        let d = null;
        try { d = await r.json(); } catch { d = null; }
        if (!r.ok) {
          list[i].status = "failed";
          list[i].msg = (d && d.detail) || "Page " + (i + 1) + " could not be read (" + r.status + ").";
          update(); setReading(false); return;
        }
        Object.assign(list[i], { status: "done", headers: d.headers, rows: d.rows, unreadable: d.unreadable, to_check: d.to_check, notes: d.notes || "" });
        if (!headers) headers = d.headers;
        update();
      } catch {
        list[i].status = "failed";
        list[i].msg = "Page " + (i + 1) + " could not be sent. Check your connection and retry.";
        update(); setReading(false); return;
      }
    }
    setReading(false);
    const lines = [headers.join("\t")];
    list.forEach((p) => p.rows.forEach((row) => lines.push(row.join("\t"))));
    const table = lines.join("\n");
    input.current = { file: null, text: table, source: "paper", matrix: null };
    setText(table);
    setPages([]);
    runCheck(ctrl.current);
  }

  const attentionRows = useMemo(() => rows.filter((r) => r.status === "blocked" || r.status === "needs_confirmation"), [rows]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter === "ready" && r.status !== "ready") return false;
      if (filter === "attention" && r.status !== "blocked" && r.status !== "needs_confirmation") return false;
      if (filter === "duplicate" && r.status !== "duplicate") return false;
      if (filter === "skipped" && r.status === "ready") return false;
      if (classFilter && r.class_label !== classFilter) return false;
      if (!q) return true;
      return (rowName(r) + " " + (r.admission_number || "") + " " + (r.class_label || "")).toLowerCase().includes(q);
    });
  }, [rows, filter, classFilter, query]);

  const shown = filtered.slice(0, limit);

  const groups = useMemo(() => {
    const map = new Map();
    rows.forEach((r) => (r.issues || []).forEach((i) => {
      if (i.severity === "notice") return;
      const key = i.code + "|" + i.severity;
      const g = map.get(key) || { key, code: i.code, severity: i.severity, message: i.message, rows: [] };
      if (!g.rows.includes(r.row)) g.rows.push(r.row);
      map.set(key, g);
    }));
    return [...map.values()].sort((a, b) => b.rows.length - a.rows.length);
  }, [rows]);

  const classList = useMemo(() => Object.entries((summary && summary.by_class) || {}).sort((a, b) => a[0].localeCompare(b[0])), [summary]);
  const needsDefaultClass = useMemo(() => {
    if (ctrlState.defaultClass) return true;
    if (!(result && result.columns || []).some((c) => c.field === "class_level")) return true;
    return rows.some((r) => blockIssues(r).some((i) => i.code === "class_missing"));
  }, [result, rows, ctrlState.defaultClass]);

  const pick = (key) => { setFilter(key); setLimit(PAGE); };
  const step = done ? 3 : summary ? 2 : 1;
  const ready = summary ? summary.ready : 0;
  const fileBlocked = !!((result && result.file_issues) || []).some((i) => i.severity === "block");
  const canImport = !!summary && ready > 0 && !fileBlocked;
  const busyCheck = busy === "check";
  const busyCommit = busy === "commit";

  function openEditor(row) {
    const draft = draftFor(row, classes);
    setEditing({ row, draft, initial: { ...draft } });
  }

  function nextAfter(row) {
    const list = attentionRows;
    const i = list.findIndex((r) => r.row === row.row);
    if (list.length < 2) return null;
    return list[(i + 1) % list.length];
  }

  return (
    <div className={"mc" + (editing || bulkOpen || confirmOpen || mapOpen ? " mc-dialog-open" : "")}>
      <header className="mc-head">
        <div>
          <h2>Migration Centre</h2>
          <p>Bring your existing learner list into Marian. Nothing is added until you confirm at the end.</p>
        </div>
      </header>

      <Steps step={step} />

      {error && (
        <div className="mc-error" role="alert">
          <div>
            <b>That did not work.</b> {error.text}
          </div>
          <div className="mc-error-actions">
            {error.retry && (
              <Button size="sm" onClick={error.retry} disabled={!!busy}>
                {error.retryLabel || "Try again"}
              </Button>
            )}
            <Button size="sm" kind="ghost" onClick={() => setError(null)}>Dismiss</Button>
          </div>
        </div>
      )}

      {done && (
        <div className="mc-success" role="status">
          <div className="mc-success-mark" aria-hidden="true">✓</div>
          <h3>
            {done.already_saved ? "These learners were already added" : done.created + (done.created === 1 ? " learner added" : " learners added")}
          </h3>
          <p>
            {done.already_saved
              ? "Your earlier attempt did save them. Nothing was added twice."
              : "They are in the Students list now" + (Object.keys(done.by_class || {}).length ? ", in " + Object.keys(done.by_class).join(", ") + "." : ".")}
          </p>
          {!done.already_saved && (done.skipped > 0 || done.temporary_admission > 0) && (
            <ul className="mc-success-list">
              {done.skipped > 0 && (
                <li>
                  {done.skipped} left out
                  {done.duplicates ? " · " + done.duplicates + " already in Marian" : ""}
                  {done.blocked ? " · " + done.blocked + " need fixing" : ""}
                  {done.needs_confirmation ? " · " + done.needs_confirmation + " not confirmed" : ""}
                </li>
              )}
              {done.temporary_admission > 0 && (
                <li>{done.temporary_admission} got a temporary admission number (NO-ADM-…). Add the real numbers in Students.</li>
              )}
            </ul>
          )}
          <div className="mc-success-actions">
            <Button onClick={() => navigate("Students")}>Open the Students list</Button>
            {done.skipped > 0 && (
              <Button kind="secondary" onClick={() => { setDone(null); runCheck(ctrl.current); }}>
                Review the {done.skipped} left out
              </Button>
            )}
            <Button kind="ghost" onClick={resetInput}>Import another file</Button>
          </div>
        </div>
      )}

      {!done && (
        <>
          {!result && (
          <section className="mc-card mc-upload">
            <h3>Add your learner list</h3>
            <p className="mc-hint">
              Drop your file here, or paste the table from Excel or Word. The first row should name the
              columns, for example <i>Admission number, Name, Class</i>. The order does not matter.
            </p>
            <label
              className={"mc-drop" + (dragging ? " is-over" : "")}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); takeFile(e.dataTransfer.files && e.dataTransfer.files[0]); }}
            >
              <span className="mc-drop-icon" aria-hidden="true">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
                </svg>
              </span>
              <span className="mc-drop-text">
                <b>{fileInfo ? fileInfo.name : "Choose a file"}</b>
                <span>{fileInfo ? "Reading this file…" : "Excel, CSV, TSV or a typed PDF · up to 5 MB"}</span>
              </span>
              <input type="file" accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf" className="mc-file"
                onChange={(e) => { takeFile(e.target.files && e.target.files[0]); e.target.value = ""; }} />
            </label>

            <details className="mc-more">
              <summary>Or paste the table</summary>
              <textarea
                className="mc-paste"
                value={text}
                onChange={(e) => onText(e.target.value)}
                rows={5}
                spellCheck={false}
                placeholder={"Admission No\tFirst name\tSurname\tClass\n1001\tAmina\tOtieno\tGrade 7 East"}
              />
              <p className="mc-hint">Paste straight from Excel or Word. Tabs, commas and semicolons all work.</p>
            </details>

            {photoOn && (
              <details className="mc-more">
                <summary>Use photos of a handwritten register</summary>
                <p className="mc-hint">Add one photo per page, in order. Keep the table flat and in good light. Anything unreadable is marked for you to type.</p>
                {pages.map((p, i) => (
                  <div key={i} className="mc-page-row">
                    <b>Page {i + 1}</b>
                    <span>
                      {p.status === "waiting" ? "waiting" : p.status === "reading" ? "reading…"
                        : p.status === "done" ? p.rows.length + " lines, " + p.unreadable + " unreadable, " + p.to_check + " to check"
                          : "failed"}
                    </span>
                    {p.msg && <span className="mc-page-fail" role="alert">{p.msg}</span>}
                    {!reading && <Button size="sm" kind="ghost" onClick={() => setPages((list) => list.filter((_, k) => k !== i))}>Remove</Button>}
                  </div>
                ))}
                <div className="mc-row-actions">
                  <label className="mu-btn secondary sm mc-file-btn">
                    Add a page
                    <input type="file" accept="image/*" className="mc-file" onChange={(e) => { addPage(e.target.files && e.target.files[0]); e.target.value = ""; }} />
                  </label>
                  <Button size="sm" disabled={!pages.length || reading} onClick={readPages}>
                    {reading ? "Reading…" : "Read " + pages.length + " page(s)"}
                  </Button>
                </div>
              </details>
            )}

            <div className="mc-source">
              <label htmlFor="mc-source">How was this list made?</label>
              <select id="mc-source" className="mu-input mc-source-select" value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  input.current = { ...input.current, source: e.target.value };
                  if (hasInput()) runCheck(ctrl.current);
                }}>
                <option value="digital">Typed on a computer</option>
                <option value="paper">Handwritten, then typed or photographed</option>
              </select>
            </div>
          </section>
          )}

          {result && (
            <div className="mc-filebar">
              <span className="mc-filebar-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" />
                </svg>
              </span>
              <div className="mc-filebar-text">
                <b>{fileInfo ? fileInfo.name : "Pasted table"}</b>
                <span>
                  {busyCheck
                    ? "Checking again…"
                    : summary && summary.total
                      ? summary.total + (summary.total === 1 ? " learner read" : " learners read")
                      : "Read, but the headings need a match"}
                </span>
              </div>
              <Button kind="ghost" size="sm" onClick={resetInput}>Choose a different file</Button>
            </div>
          )}

          {busyCheck && !result && (
            <div className="mc-loading" role="status" aria-live="polite">
              <span className="mc-spinner" aria-hidden="true" />
              Reading your file and checking the learners…
            </div>
          )}

          {result && summary && (
            <>
              {(result.file_issues || []).map((i, k) => (
                <div key={k} className={"mc-note-row " + (i.severity === "block" ? "is-block" : "is-info")} role={i.severity === "block" ? "alert" : "status"}>
                  <b>{i.severity === "block" ? "Problem with the file:" : "Note:"}</b> {i.message}
                </div>
              ))}

              {(result.needs_input || []).map((n) => n.code === "name_order" ? (
                <div className="mc-panel" key="name_order">
                  <div className="mc-panel-head">
                    <div>
                      <h3>Which name comes first?</h3>
                      <p className="mc-hint">{n.message} {(n.sample || []).length ? "For example: " + n.sample.slice(0, 3).join(" · ") : ""}</p>
                    </div>
                  </div>
                  <div className="mc-row-actions">
                    <Button onClick={() => runCheck(ctrl.current, { nameOrder: "first_last" })}>First name first</Button>
                    <Button kind="secondary" onClick={() => runCheck(ctrl.current, { nameOrder: "last_first" })}>Surname first</Button>
                  </div>
                </div>
              ) : null)}

              <MappingPanel
                key={"map-" + (result.columns || []).map((c) => c.field || "-").join(",") + "-" + result.header_row}
                result={result}
                open={mapOpen}
                onClose={() => setMapOpen(false)}
                onApply={(mapping, headerRow) => {
                  setMapOpen(false);
                  runCheck(ctrl.current, { mapping, headerRow });
                }}
              />

              {!mapOpen && (result.columns || []).length > 0 && (
                <div className="mc-columns-line">
                  <span>
                    Columns read: {(result.columns || []).filter((c) => c.field).map((c) => c.label).join(" · ") || "none"}
                  </span>
                  <Button kind="ghost" size="sm" onClick={() => setMapOpen(true)}>Adjust columns</Button>
                </div>
              )}

              {summary.total > 0 && !(result.needs_input || []).some((n) => n.code === "name_order" || n.code === "mapping") && (
                <>
                  {needsDefaultClass && (
                    <ClassPanel
                      result={result}
                      defaultClass={ctrlState.defaultClass}
                      onDefault={(level, stream) => {
                        const label = level ? level + (stream ? " " + stream : "") : "";
                        runCheck(ctrl.current, { defaultClass: label });
                      }}
                    />
                  )}

                  <Summary s={summary} filter={filter} onPick={pick} />

                  {busyCheck && (
                    <div className="mc-updating" role="status" aria-live="polite">
                      <span className="mc-spinner" aria-hidden="true" /> Updating the check…
                    </div>
                  )}

                  {groups.length > 0 && (
                    <div className="mc-groups">
                      {groups.map((g) => {
                        const isClass = /^class_|^stream_|^default_class/.test(g.code);
                        const list = rows.filter((r) => g.rows.includes(r.row));
                        const acceptable = list.filter((r) => r.status === "needs_confirmation");
                        return (
                          <div className={"mc-group " + (g.severity === "block" ? "is-block" : "is-warn")} key={g.key}>
                            <div className="mc-group-text">
                              <b>{g.rows.length} {g.rows.length === 1 ? "learner" : "learners"}:</b> {g.message}
                              {TIPS[g.code] && <span className="mc-group-tip">{TIPS[g.code]}</span>}
                            </div>
                            <div className="mc-group-actions">
                              {acceptable.length > 0 && (
                                <Button size="sm" kind="secondary" onClick={() => acceptMany(acceptable)}>
                                  Accept {acceptable.length === 1 ? "this learner" : "all " + acceptable.length}
                                </Button>
                              )}
                              {isClass && g.severity === "block" && (
                                <Button size="sm" kind="secondary" onClick={() => { setSelected(g.rows); setBulkOpen(true); }}>
                                  Assign class
                                </Button>
                              )}
                              {!isClass && g.severity === "block" && (
                                <Button size="sm" kind="ghost" onClick={() => { setSelected(g.rows); setFilter("attention"); }}>
                                  Show these learners
                                </Button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="mc-toolbar">
                    <input className="mu-input mc-search" type="search" placeholder="Search name, admission number or class"
                      aria-label="Search learners" value={query} onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }} />
                    <select className="mu-input mc-class-filter" aria-label="Filter by class" value={classFilter}
                      onChange={(e) => { setClassFilter(e.target.value); setLimit(PAGE); }}>
                      <option value="">All classes</option>
                      {classList.map(([name, count]) => <option key={name} value={name}>{name} ({count})</option>)}
                    </select>
                    {selected.length > 0 && (
                      <div className="mc-bulk">
                        <span>{selected.length} selected</span>
                        <Button size="sm" onClick={() => setBulkOpen(true)}>Assign class</Button>
                        <Button size="sm" kind="secondary"
                          onClick={() => acceptMany(rows.filter((r) => selected.includes(r.row)))}>Accept</Button>
                        <Button size="sm" kind="ghost" onClick={() => setSelected([])}>Clear</Button>
                      </div>
                    )}
                  </div>

                  <div className="mc-tablewrap">
                    <table className="mc-table">
                      <thead>
                        <tr>
                          <th scope="col" className="mc-col-check">
                            <input type="checkbox" aria-label="Select every learner shown"
                              checked={shown.length > 0 && shown.every((r) => selected.includes(r.row))}
                              onChange={(e) => setSelected(e.target.checked ? shown.map((r) => r.row) : [])} />
                          </th>
                          <th scope="col">Learner</th>
                          <th scope="col">Admission no.</th>
                          <th scope="col">Class</th>
                          <th scope="col">Status</th>
                          <th scope="col" className="mc-col-act"><span className="mc-sr">Actions</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((r) => {
                          const tone = TONE[r.status] || ["info", r.status];
                          const issue = firstIssue(r);
                          const blocks = blockIssues(r).length;
                          const confirms = confirmCodes(r);
                          const corrected = !!(ctrlState.fixes[r.row]);
                          return (
                            <tr key={r.row} className={"is-" + r.status}>
                              <td className="mc-col-check">
                                <input type="checkbox" aria-label={"Select " + rowName(r)}
                                  checked={selected.includes(r.row)}
                                  onChange={(e) => setSelected((s) => e.target.checked ? [...s, r.row] : s.filter((n) => n !== r.row))} />
                              </td>
                              <td className="mc-name-cell">
                                <div className="mc-name">{rowName(r)}</div>
                                <div className="mc-sub">
                                  Row {r.row}
                                  {corrected ? " · corrected" : ""}
                                  {r.provisional_admission ? " · temporary number" : ""}
                                </div>
                                {issue && (
                                  <div className={"mc-issue " + issue.severity}>
                                    {issue.message}
                                    {blocks > 1 ? " (+" + (blocks - 1) + " more)" : ""}
                                  </div>
                                )}
                              </td>
                              <td data-label="Admission no.">{r.admission_number || <span className="mc-muted">none yet</span>}</td>
                              <td data-label="Class" className="mc-class-cell">{r.class_label || <span className="mc-muted">no class</span>}</td>
                              <td data-label="Status"><Badge kind={tone[0]}>{tone[1]}</Badge></td>
                              <td className="mc-col-act">
                                <div className="mc-row-actions">
                                  {confirms.length > 0 && r.status === "needs_confirmation" && (
                                    <Button size="sm" kind="secondary" disabled={busyCheck}
                                      onClick={() => acceptRow(r.row, confirms)}>Accept</Button>
                                  )}
                                  <Button size="sm" kind="ghost" onClick={() => openEditor(r)}>
                                    {r.status === "blocked" ? "Fix" : "Edit"}
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {shown.length === 0 && (
                      <p className="mc-empty">
                        {rows.length === 0 ? "No learners were found in this file." : "No learners match this filter."}
                      </p>
                    )}
                  </div>

                  {filtered.length > shown.length && (
                    <Button kind="secondary" className="mc-more-btn" onClick={() => setLimit(limit + PAGE)}>
                      Show {Math.min(PAGE, filtered.length - shown.length)} more ({filtered.length - shown.length} left)
                    </Button>
                  )}

                  <div className="mc-bar">
                    <div className="mc-bar-text">
                      <b>{ready}</b> of {summary.total} ready to add
                      {summary.skipped > 0 && <span> · {summary.skipped} will be skipped</span>}
                    </div>
                    <Button onClick={() => setConfirmOpen(true)} disabled={!canImport || !!busy}>
                      {busyCommit ? "Adding…" : "Add " + ready + (ready === 1 ? " learner" : " learners")}
                    </Button>
                  </div>
                </>
              )}

              {summary.total === 0 && !(result.needs_input || []).length && (
                <div className="mc-panel">
                  <h3>No learners were found</h3>
                  <p className="mc-hint">
                    The file was read, but every row below the headings was empty. Check that the learners are on
                    the first sheet, then choose the file again.
                  </p>
                </div>
              )}
            </>
          )}
        </>
      )}

      {editing && (
        <Modal title={"Row " + editing.row.row + " · " + rowName(editing.row)} onClose={() => setEditing(null)}
          actions={<>
            <Button kind="secondary" onClick={() => setEditing(null)}>Cancel</Button>
            {nextAfter(editing.row) && (
              <Button kind="ghost" onClick={() => {
                saveFix(editing.row, editing.draft, editing.initial);
                const next = nextAfter(editing.row);
                if (next) setTimeout(() => openEditor(next), 60);
              }}>Save and next</Button>
            )}
            <Button onClick={() => saveFix(editing.row, editing.draft, editing.initial)}>Save</Button>
          </>}>
          <div className="mc-edit">
            {(editing.row.issues || []).filter((i) => i.severity !== "notice").map((i, k) => (
              <div className={"mc-edit-issue " + i.severity} key={k}>
                <b>{i.severity === "block" ? "Needs fixing: " : "Please check: "}</b>{i.message}
                {TIPS[i.code] && <span className="mc-edit-tip">{TIPS[i.code]}</span>}
              </div>
            ))}
            {(editing.row.suggestions && editing.row.suggestions.class_level || []).length > 0 && (
              <div className="mc-suggest">
                <span>Did you mean:</span>
                {(editing.row.suggestions.class_level || []).map((name) => (
                  <button key={name} type="button" className="mc-chip"
                    onClick={() => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, class_level: name, stream: "" } }))}>{name}</button>
                ))}
              </div>
            )}
            <div className="mc-two">
              <Input label="First name" value={editing.draft.first_name}
                onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, first_name: e.target.value } }))} />
              <Input label="Surname" value={editing.draft.last_name}
                onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, last_name: e.target.value } }))} />
            </div>
            <div className="mc-two">
              <Input label="Admission number" help="Leave empty to get a temporary number."
                value={editing.draft.admission_number}
                onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, admission_number: e.target.value } }))} />
              <Input label="Assessment number" help="Grade 10–12 only."
                value={editing.draft.assessment_number}
                onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, assessment_number: e.target.value } }))} />
            </div>
            <div className="mc-two">
              <Field label="Class">
                <select className="mu-input" value={editing.draft.class_level}
                  onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, class_level: e.target.value, stream: "" } }))}>
                  <option value="">Choose a class…</option>
                  {classOptions(classes).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </Field>
              <Field label="Stream" help={!editing.draft.class_level ? "" : (streamNames(classes, editing.draft.class_level).length ? "" : "This class has no streams.")}>
                <select className="mu-input" value={editing.draft.stream}
                  disabled={!streamNames(classes, editing.draft.class_level).length}
                  onChange={(e) => setEditing((ed) => ({ ...ed, draft: { ...ed.draft, stream: e.target.value } }))}>
                  <option value="">No stream</option>
                  {streamNames(classes, editing.draft.class_level).map((s) => (
                    <option key={s.id} value={s.name}>{s.name}</option>
                  ))}
                </select>
              </Field>
            </div>
            <p className="mc-hint">Changes apply to this import only. Your original file is not changed.</p>
            {ctrlState.fixes[editing.row.row] && (
              <Button kind="ghost" size="sm" onClick={() => clearFix(editing.row)}>Undo my correction on this row</Button>
            )}
          </div>
        </Modal>
      )}

      {bulkOpen && (
        <BulkClass
          count={selected.length}
          classes={classes}
          onClose={() => setBulkOpen(false)}
          onApply={bulkClass}
        />
      )}

      {confirmOpen && summary && (
        <Modal title={"Add " + ready + (ready === 1 ? " learner" : " learners") + " to Marian?"} onClose={() => setConfirmOpen(false)}
          actions={<>
            <Button kind="secondary" onClick={() => setConfirmOpen(false)} disabled={busyCommit}>Cancel</Button>
            <Button onClick={commit} disabled={busyCommit}>{busyCommit ? "Adding…" : "Yes, add them"}</Button>
          </>}>
          <div className="mc-confirm">
            <p>
              {ready} {ready === 1 ? "learner goes" : "learners go"} into the classes shown below.
              {summary.skipped > 0 ? " " + summary.skipped + " will be left out." : ""}
            </p>
            <div className="mc-confirm-list">
              {Object.entries(summary.by_class_ready || {}).map(([name, count]) => (
                <div key={name}><span>{name || "No class"}</span><b>{count}</b></div>
              ))}
            </div>
            {summary.skipped > 0 && (
              <ul className="mc-confirm-skip">
                {summary.duplicates > 0 && <li>{summary.duplicates} already in Marian</li>}
                {summary.blocked > 0 && <li>{summary.blocked} still need fixing</li>}
                {summary.needs_confirmation > 0 && <li>{summary.needs_confirmation} not confirmed yet</li>}
              </ul>
            )}
            {summary.temporary_admission > 0 && (
              <p className="mc-hint">{summary.temporary_admission} will get a temporary admission number (NO-ADM-…).</p>
            )}
            <p className="mc-hint">This cannot be undone from here. Nothing has been added yet.</p>
          </div>
        </Modal>
      )}
    </div>
  );
}

function BulkClass({ count, classes, onClose, onApply }) {
  const [level, setLevel] = useState("");
  const [stream, setStream] = useState("");
  const streams = streamNames(classes, level);
  return (
    <Modal title={"Assign a class to " + count + (count === 1 ? " learner" : " learners")} onClose={onClose}
      actions={<>
        <Button kind="secondary" onClick={onClose}>Cancel</Button>
        <Button disabled={!level} onClick={() => onApply(level, stream)}>Assign class</Button>
      </>}>
      <p className="mc-hint">Every learner you selected moves to this class. Nothing else about them changes.</p>
      <Field label="Class">
        <select className="mu-input" value={level} onChange={(e) => { setLevel(e.target.value); setStream(""); }}>
          <option value="">Choose a class…</option>
          {classOptions(classes).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </Field>
      <Field label="Stream" help={streams.length ? "" : "This class has no streams."}>
        <select className="mu-input" value={stream} disabled={!streams.length} onChange={(e) => setStream(e.target.value)}>
          <option value="">No stream</option>
          {streams.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      </Field>
    </Modal>
  );
}
