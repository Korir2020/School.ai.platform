import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Button, Loading } from "./ui";
import { takedownReasonError, takedownPayload } from "./staffLearningUtils";
import "./StaffLearning.css";

const BASE = "/api/learning/v1/";
const list = (payload) => Array.isArray(payload?.results) ? payload.results : [];

async function request(path, method = "GET", body) {
  const response = await api(`${BASE}${path}`, method, body);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload?.detail || payload?.code?.replaceAll("_", " ") || "The request could not be completed.");
    error.status = response.status;
    error.code = payload?.code;
    throw error;
  }
  return payload;
}

function StatusPill({ children }) {
  return <span className={`sl-pill sl-pill--${String(children || "draft").replaceAll("_", "-")}`}>{String(children || "draft").replaceAll("_", " ")}</span>;
}

function SectionTitle({ eyebrow, title, text, children }) {
  return <div className="sl-title"><div><p className="sl-eyebrow">{eyebrow}</p><h2>{title}</h2><p>{text}</p></div>{children}</div>;
}

function Notice({ children, kind = "info" }) {
  return <div className={`sl-notice sl-notice--${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

function PracticeQuizEditor({ quiz, onChange }) {
  const questions = Array.isArray(quiz?.questions) ? quiz.questions : [];
  function updateQuestion(index, patch) {
    onChange({ schema_version: 1, questions: questions.map((question, row) => row === index ? { ...question, ...patch } : question) });
  }
  function addQuestion() {
    let n = questions.length + 1;
    while (questions.some((question) => question.id === `q${n}`)) n += 1;
    onChange({ schema_version: 1, questions: [...questions, {
      id: `q${n}`, prompt: "", options: [{ id: "a", text: "" }, { id: "b", text: "" }],
      correct_option_id: "a", explanation: "",
    }] });
  }
  function addOption(index) {
    const question = questions[index];
    if (!question || question.options.length >= 6) return;
    let n = question.options.length + 1;
    while (question.options.some((option) => option.id === `o${n}`)) n += 1;
    updateQuestion(index, { options: [...question.options, { id: `o${n}`, text: "" }] });
  }
  function removeOption(index, optionId) {
    const question = questions[index];
    if (!question || question.options.length <= 2) return;
    const options = question.options.filter((option) => option.id !== optionId);
    updateQuestion(index, {
      options,
      correct_option_id: question.correct_option_id === optionId ? options[0].id : question.correct_option_id,
    });
  }
  return <section className="sl-quiz-editor" aria-label="Practice quiz questions">
    <div className="sl-subheading"><h3>Practice questions</h3><span>{questions.length}/20</span></div>
    <p className="sl-footnote">Write original questions in the selected resource language. Answers are checked by Marian only after submission. Drafts remain private; independent school review is required, and learner publication is still controlled by Marian’s separate policy gate.</p>
    {questions.map((question, index) => <fieldset className="sl-quiz-question" key={question.id}>
      <legend>Question {index + 1}</legend>
      <div className="sl-field"><label htmlFor={`sl-quiz-${question.id}-prompt`}>Question text</label><textarea id={`sl-quiz-${question.id}-prompt`} maxLength={500} rows={2} required value={question.prompt} onChange={(event) => updateQuestion(index, { prompt: event.target.value })} /></div>
      <div className="sl-field"><span className="sl-label">Answer options (2–6)</span>
        {question.options.map((option, optionIndex) => <div className="sl-quiz-option" key={option.id}>
          <label className="sl-sr-only" htmlFor={`sl-quiz-${question.id}-${option.id}`}>Option {optionIndex + 1} text</label>
          <input id={`sl-quiz-${question.id}-${option.id}`} maxLength={240} required value={option.text} onChange={(event) => updateQuestion(index, { options: question.options.map((row) => row.id === option.id ? { ...row, text: event.target.value } : row) })} />
          <Button kind="secondary" type="button" disabled={question.options.length <= 2} onClick={() => removeOption(index, option.id)}>Remove option</Button>
        </div>)}
        <Button kind="secondary" type="button" disabled={question.options.length >= 6} onClick={() => addOption(index)}>Add option</Button>
      </div>
      <div className="sl-field"><label htmlFor={`sl-quiz-${question.id}-correct`}>Correct option (review-only)</label><select id={`sl-quiz-${question.id}-correct`} value={question.correct_option_id} onChange={(event) => updateQuestion(index, { correct_option_id: event.target.value })}>{question.options.map((option, optionIndex) => <option key={option.id} value={option.id}>Option {optionIndex + 1}{option.text ? ` · ${option.text}` : ""}</option>)}</select></div>
      <div className="sl-field"><label htmlFor={`sl-quiz-${question.id}-explanation`}>Explanation shown after an attempt (optional)</label><textarea id={`sl-quiz-${question.id}-explanation`} maxLength={600} rows={2} value={question.explanation} onChange={(event) => updateQuestion(index, { explanation: event.target.value })} /></div>
      <Button kind="secondary" type="button" onClick={() => onChange({ schema_version: 1, questions: questions.filter((_, row) => row !== index) })}>Remove question</Button>
    </fieldset>)}
    <Button kind="secondary" type="button" disabled={questions.length >= 20} onClick={addQuestion}>Add question</Button>
  </section>;
}

const blankResource = () => ({
  title: "", summary: "", body: "", practice_quiz: {}, resource_type: "lesson", language_code: "en",
  difficulty: "beginner", age_min: "", age_max: "", source_name: "",
  license_name: "", attribution: "", rights_notes: "",
});
const blankPath = () => ({
  title: "", description: "", objectivesText: "", stepsText: "", language_code: "en",
  difficulty: "beginner", age_min: "", age_max: "", source_name: "",
  license_name: "", attribution: "", rights_notes: "",
});

function TeacherDraftWorkspace({ onNotice }) {
  const [kind, setKind] = useState("resource");
  const [resources, setResources] = useState([]);
  const [paths, setPaths] = useState([]);
  const [form, setForm] = useState(blankResource());
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [resourceRows, pathRows] = await Promise.all([
        request("studio/resources/?limit=100"), request("studio/paths/?limit=100"),
      ]);
      setResources(list(resourceRows)); setPaths(list(pathRows));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const id = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(id); }, [load]);

  function resetEditor(contentKind = kind) {
    setEditing(null);
    setForm(contentKind === "resource" ? blankResource() : blankPath());
    setError("");
  }
  function edit(row, contentKind) {
    setKind(contentKind);
    setEditing({ id: row.id, kind: contentKind });
    if (contentKind === "resource") {
      const fields = ["title", "summary", "body", "practice_quiz", "resource_type", "origin", "external_url", "language_code", "difficulty", "access_tier", "age_min", "age_max", "source_name", "license_name", "license_url", "attribution", "rights_notes"];
      setForm({ ...blankResource(), ...Object.fromEntries(fields.filter((field) => field in row).map((field) => [field, row[field]])), age_min: row.age_min ?? "", age_max: row.age_max ?? "" });
    } else {
      const fields = ["title", "description", "language_code", "difficulty", "access_tier", "age_min", "age_max", "source_name", "license_name", "license_url", "attribution", "rights_notes"];
      setForm({ ...blankPath(), ...Object.fromEntries(fields.filter((field) => field in row).map((field) => [field, row[field]])), objectivesText: Array.isArray(row.objectives) ? row.objectives.join("\n") : "", stepsText: Array.isArray(row.items) ? row.items.filter((item) => item.item_type !== "resource").map((item) => item.title).join("\n") : "", age_min: row.age_min ?? "", age_max: row.age_max ?? "" });
    }
    setError("");
  }
  function setField(field, value) { setForm((current) => ({ ...current, [field]: value })); }

  function resourcePayload() {
    const fields = { ...form };
    delete fields.objectivesText;
    delete fields.stepsText;
    return {
      ...fields,
      age_min: fields.age_min === "" ? null : Number(fields.age_min),
      age_max: fields.age_max === "" ? null : Number(fields.age_max),
    };
  }
  function pathPayload() {
    const { objectivesText, stepsText, ...fields } = form;
    const steps = String(stepsText || "").split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 100);
    return {
      ...fields,
      objectives: String(objectivesText || "").split("\n").map((item) => item.trim()).filter(Boolean).slice(0, 50),
      items: steps.map((title, index) => ({ position: index + 1, item_type: "activity", title, instructions: "", completion_rule: "view" })),
      age_min: fields.age_min === "" ? null : Number(fields.age_min),
      age_max: fields.age_max === "" ? null : Number(fields.age_max),
    };
  }
  async function save(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const payload = kind === "resource" ? resourcePayload() : pathPayload();
      const root = kind === "resource" ? "studio/resources/" : "studio/paths/";
      await request(editing ? `${root}${editing.id}/` : root, editing ? "PATCH" : "POST", payload);
      onNotice(editing ? "Your draft changes have been saved." : "A private school draft has been created.");
      setEditing(null); setForm(kind === "resource" ? blankResource() : blankPath()); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function duplicate(row) {
    setBusy(true); setError("");
    try {
      await request(`studio/resources/${row.id}/duplicate/`, "POST", {});
      onNotice("A private draft copy has been created. Licence and attribution were carried over.");
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function submitForReview(row, contentKind) {
    if (!window.confirm("Submit this draft for independent school-admin review? You can no longer edit it unless changes are requested.")) return;
    setBusy(true); setError("");
    try {
      const root = contentKind === "resource" ? "studio/resources/" : "studio/paths/";
      await request(`${root}${row.id}/submit/`, "POST", {});
      onNotice("The draft has been sent to the school learning review queue. Publication is still disabled by Marian policy.");
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  const rows = kind === "resource" ? resources : paths;

  return <div className="sl-page">
    <div className="sl-panel">
      <SectionTitle eyebrow="Teacher Studio" title="Build learning materials" text="Create and manage your own private drafts. Submission sends them to the school’s independent review queue; it does not publish or expose content to learners." />
      <div className="sl-tabs" role="tablist" aria-label="Draft content type">
        <button type="button" role="tab" aria-selected={kind === "resource"} onClick={() => { setKind("resource"); resetEditor("resource"); }}>Resources</button>
        <button type="button" role="tab" aria-selected={kind === "path"} onClick={() => { setKind("path"); resetEditor("path"); }}>Learning programmes</button>
      </div>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="sl-two-col">
        <section className="sl-subpanel" aria-label="Your drafts">
          <div className="sl-subheading"><h3>Your {kind === "resource" ? "resources" : "programmes"}</h3><span>{rows.length} shown</span></div>
          {loading ? <Loading /> : rows.length ? <div className="sl-list">{rows.map((row) => <article className="sl-row" key={row.id}>
            <div className="sl-row-main"><strong>{row.title}</strong><p>{row.updated_at ? new Date(row.updated_at).toLocaleDateString() : "Private draft"}</p><StatusPill>{row.status}</StatusPill></div>
            <div className="sl-row-actions">
{kind === 'resource' && <Button kind='secondary' busy={busy} onClick={() => duplicate(row)}>Duplicate</Button>}
              {["draft", "changes_requested"].includes(row.status) && <Button kind="secondary" onClick={() => edit(row, kind)}>Edit</Button>}
              {["draft", "changes_requested"].includes(row.status) && <Button kind="teal" busy={busy} onClick={() => submitForReview(row, kind)}>Submit</Button>}
            </div>
          </article>)}</div> : <p className="sl-empty">No school {kind === "resource" ? "resources" : "programmes"} yet. Start a draft; it remains private until reviewed.</p>}
          <Button kind="secondary" onClick={resetEditor}>New {kind === "resource" ? "resource" : "programme"}</Button>
        </section>
        <form className="sl-subpanel sl-form" onSubmit={save}>
          <div className="sl-subheading"><h3>{editing ? "Edit private draft" : `New ${kind === "resource" ? "resource" : "programme"}`}</h3>{editing && <Button kind="secondary" onClick={resetEditor}>Cancel</Button>}</div>
          <div className="sl-field"><label htmlFor="sl-title">Title</label><input id="sl-title" required maxLength={240} value={form.title} onChange={(event) => setField("title", event.target.value)} /></div>
          {kind === "resource" ? <>
            <div className="sl-field"><label htmlFor="sl-summary">Short description</label><textarea id="sl-summary" maxLength={4000} rows={3} value={form.summary} onChange={(event) => setField("summary", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-body">Learning material</label><textarea id="sl-body" maxLength={24000} rows={7} value={form.body} onChange={(event) => setField("body", event.target.value)} /></div>
            <div className="sl-field-grid">
              <div className="sl-field"><label htmlFor="sl-resource-type">Format</label><select id="sl-resource-type" value={form.resource_type} onChange={(event) => { const value = event.target.value; setField("resource_type", value); if (value !== "interactive") setField("practice_quiz", {}); else if (!form.practice_quiz?.questions) setField("practice_quiz", { schema_version: 1, questions: [] }); }}>{[["lesson", "Lesson"], ["article", "Article"], ["worksheet", "Worksheet"], ["interactive", "Practice quiz"], ["other", "Other"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
              <div className="sl-field"><label htmlFor="sl-language">Language code</label><input id="sl-language" required maxLength={20} value={form.language_code} onChange={(event) => setField("language_code", event.target.value)} /></div>
            </div>
            {form.resource_type === "interactive" && <PracticeQuizEditor quiz={form.practice_quiz} onChange={(value) => setField("practice_quiz", value)} />}
          </> : <>
            <div className="sl-field"><label htmlFor="sl-description">Programme description</label><textarea id="sl-description" maxLength={8000} rows={4} value={form.description} onChange={(event) => setField("description", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-objectives">Objectives (one per line)</label><textarea id="sl-objectives" rows={3} value={form.objectivesText} onChange={(event) => setField("objectivesText", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-steps">Guided activity steps (one title per line, optional)</label><textarea id="sl-steps" rows={3} value={form.stepsText} onChange={(event) => setField("stepsText", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-language">Language code</label><input id="sl-language" required maxLength={20} value={form.language_code} onChange={(event) => setField("language_code", event.target.value)} /></div>
          </>}
          <div className="sl-field-grid">
            <div className="sl-field"><label htmlFor="sl-difficulty">Difficulty</label><select id="sl-difficulty" value={form.difficulty} onChange={(event) => setField("difficulty", event.target.value)}>{["beginner", "intermediate", "advanced"].map((value) => <option key={value}>{value}</option>)}</select></div>
            <div className="sl-field"><label htmlFor="sl-age-min">Minimum age (optional)</label><input id="sl-age-min" type="number" min="0" max="120" value={form.age_min} onChange={(event) => setField("age_min", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-age-max">Maximum age (optional)</label><input id="sl-age-max" type="number" min="0" max="120" value={form.age_max} onChange={(event) => setField("age_max", event.target.value)} /></div>
          </div>
          <details className="sl-metadata"><summary>Source, licence and attribution (required before review)</summary>
            <div className="sl-field"><label htmlFor="sl-source">Source/provenance</label><input id="sl-source" maxLength={240} value={form.source_name} onChange={(event) => setField("source_name", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-license">Licence name (or record rights below)</label><input id="sl-license" maxLength={160} value={form.license_name} onChange={(event) => setField("license_name", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-rights">Documented rights notes</label><textarea id="sl-rights" rows={2} maxLength={5000} value={form.rights_notes} onChange={(event) => setField("rights_notes", event.target.value)} /></div>
            <div className="sl-field"><label htmlFor="sl-attribution">Attribution</label><textarea id="sl-attribution" rows={2} maxLength={4000} value={form.attribution} onChange={(event) => setField("attribution", event.target.value)} /></div>
          </details>
          <Button kind="teal" type="submit" busy={busy}>{editing ? "Save private draft" : "Create private draft"}</Button>
        </form>
      </div>
      <p className="sl-footnote">Drafts and requested changes are visible only to their author and authorised school reviewers. Attachments, external ingestion, automatic content generation and publishing are not enabled here.</p>
    </div>
  </div>;
}

function TeacherDiscovery({ onNotice }) {
  const [query, setQuery] = useState("");
  const [topics, setTopics] = useState([]);
  const [resources, setResources] = useState([]);
  const [paths, setPaths] = useState([]);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [learners, setLearners] = useState([]);
  const [learnerId, setLearnerId] = useState("");
  const [itemChoice, setItemChoice] = useState("");
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (q) => {
    setLoading(true); setError("");
    try {
      const queryString = new URLSearchParams({ lang: "en" });
      if (q.trim()) queryString.set("q", q.trim().slice(0, 100));
      const [topicPayload, resourcePayload, pathPayload, learnerPayload] = await Promise.all([
        request("teachers/catalog/topics/?lang=en"),
        request(`teachers/catalog/resources/?${queryString.toString()}`),
        request(`teachers/catalog/paths/?${queryString.toString()}`),
        request("teachers/learners/"),
      ]);
      setTopics(list(topicPayload)); setResources(list(resourcePayload)); setPaths(list(pathPayload)); setLearners(list(learnerPayload));
      setLearnerId((current) => current || String(list(learnerPayload)[0]?.student_id || ""));
      setItemChoice((current) => current || (list(resourcePayload)[0] ? `resource:${list(resourcePayload)[0].id}` : list(pathPayload)[0] ? `path:${list(pathPayload)[0].id}` : ""));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const id = window.setTimeout(() => { void load(""); }, 0); return () => window.clearTimeout(id); }, [load]);

  async function openItem(type, id) {
    setError(""); setDetail(null);
    try { setDetail({ ...await request(`teachers/catalog/${type === "path" ? "paths" : "resources"}/${id}/?lang=en`), type }); }
    catch (err) { setError(err.message); }
  }
  async function recommend(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const [type, id] = itemChoice.split(":");
      await request(`teachers/learners/${learnerId}/recommendations/`, "POST", { [`${type}_id`]: Number(id), explanation });
      onNotice(`The approved free learning ${type} has been recommended to the assigned learner.`);
      setExplanation("");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div className="sl-page">
    <div className="sl-panel">
      <SectionTitle eyebrow="Teacher Studio · Personal learning" title="Explore beyond your subject" text="Discover currently available shared and school learning resources and programmes for your own professional learning. This staff view shows catalogue data only; premium entitlements and learner access rules are not bypassed." />
      {error && <Notice kind="error">{error}</Notice>}
      <form className="sl-search" onSubmit={(event) => { event.preventDefault(); load(query); }}>
        <div className="sl-field"><label htmlFor="sl-discovery-search">Search any topic</label><input id="sl-discovery-search" maxLength={100} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try a subject, skill or idea" /></div>
        <Button kind="teal" type="submit" busy={loading}>Explore</Button>
      </form>
      <div className="sl-topic-strip" aria-label="Available learning topics">{topics.slice(0, 12).map((topic) => <span className="sl-topic" key={topic.id}>{topic.name}</span>)}</div>
      {loading ? <Loading /> : resources.length || paths.length ? <div className="sl-explore-grid">
        {[...resources.map((item) => ({ ...item, kind: "resource" })), ...paths.map((item) => ({ ...item, kind: "path" }))].map((item) => <article className="sl-resource" key={`${item.kind}-${item.id}`}>
          <div><span className="sl-eyebrow">{item.kind === "path" ? "Learning programme" : item.resource_type} · {item.difficulty || "all levels"}</span><h3>{item.title}</h3></div>
          <p>{item.summary || item.description || "No summary provided."}</p>
          <div className="sl-topic-strip">{item.topics?.slice(0, 3).map((topic) => <span className="sl-topic" key={topic.id}>{topic.name}</span>)}</div>
          <Button kind="secondary" onClick={() => openItem(item.kind, item.id)}>{item.kind === "path" ? "View programme" : "Read resource"}</Button>
        </article>)}
      </div> : <p className="sl-empty">No published free learning items currently match. Drafts remain private until school review; publishing is separately disabled until Marian policy approval.</p>}
      {detail && <article className="sl-reading"><div className="sl-subheading"><h3>{detail.title}</h3><Button kind="secondary" onClick={() => setDetail(null)}>Close</Button></div><p>{detail.summary || detail.description}</p>{detail.body && <div className="sl-reading-body">{detail.body}</div>}{detail.items?.length > 0 && <ol className="sl-programme-steps">{detail.items.map((item) => <li key={item.id}><strong>{item.title}</strong>{item.instructions && <p>{item.instructions}</p>}</li>)}</ol>}{detail.external_url && <a href={detail.external_url} target="_blank" rel="noreferrer">Open original source (new tab)</a>}</article>}
    </div>
    <form className="sl-panel sl-recommend-form" onSubmit={recommend}>
      <SectionTitle eyebrow="Assigned learners" title="Recommend a learning item" text="Recommendations are limited to active learners assigned to you and resources or programmes currently visible to that learner. Only free, reviewed and published catalogue items qualify." />
      <div className="sl-field-grid">
        <div className="sl-field"><label htmlFor="sl-rec-learner">Assigned learner</label><select id="sl-rec-learner" required value={learnerId} onChange={(event) => setLearnerId(event.target.value)}><option value="">Choose learner</option>{learners.map((item) => <option key={item.student_id} value={item.student_id}>{item.learner_name}</option>)}</select></div>
        <div className="sl-field"><label htmlFor="sl-rec-item">Published free resource or programme</label><select id="sl-rec-item" required value={itemChoice} onChange={(event) => setItemChoice(event.target.value)}><option value="">Choose learning item</option><optgroup label="Resources">{resources.map((item) => <option key={item.id} value={`resource:${item.id}`}>{item.title}</option>)}</optgroup><optgroup label="Programmes">{paths.map((item) => <option key={item.id} value={`path:${item.id}`}>{item.title}</option>)}</optgroup></select></div>
      </div>
      <div className="sl-field"><label htmlFor="sl-rec-explanation">Optional note for the learner</label><textarea id="sl-rec-explanation" rows={3} maxLength={500} value={explanation} onChange={(event) => setExplanation(event.target.value)} placeholder="A short learning-focused reason" /></div>
      <div className="sl-field-grid sl-progress-grid">{[
        ["Assigned eligible learners", learners.length],
        ["Progress summaries", "Participation only"],
        ["Assessment records", "Not accessed"],
      ].map(([label, value]) => <div className="sl-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <Button kind="teal" type="submit" busy={busy} disabled={!learnerId || !itemChoice}>Send recommendation</Button>
      {!learners.length && !loading && <p className="sl-footnote">Only active, consent-eligible students in currently assigned streams are listed.</p>}
    </form>
    <div className="sl-panel">
      <SectionTitle eyebrow="Progress boundaries" title="Support, not surveillance" text="See only the learner's name and minimal learning participation counts. No marks, attendance, report cards, fees, raw prompts or private project work are shown in this workspace." />
      {learners.length > 0 && <div className="sl-table-wrap"><table className="sl-table"><thead><tr><th>Assigned learner</th><th>Learning activity</th><th>Completed paths</th><th>Last activity</th></tr></thead><tbody>{learners.map((item) => <tr key={item.profile_id}><td>{item.learner_name}</td><td>{item.participation_count}</td><td>{item.completed_path_count}</td><td>{item.last_activity_at ? new Date(item.last_activity_at).toLocaleDateString() : "Not recorded"}</td></tr>)}</tbody></table></div>}
    </div>
  </div>;
}

export function TeacherLearningStudio() {
  const [tab, setTab] = useState("explore");
  const [notice, setNotice] = useState("");
  return <div className="sl-workspace">
    <header className="sl-banner"><div><p className="sl-eyebrow">Marian · Activity 13</p><h1>Teacher Learning Studio</h1><p>Grow your own learning, build reviewed materials and support assigned learners—within clear privacy boundaries.</p></div><span className="sl-banner-mark" aria-hidden="true">T</span></header>
    <nav className="sl-tabs" aria-label="Teacher learning sections">
      {[['explore', 'Explore'], ['drafts', 'My drafts']].map(([value, label]) => <button type="button" key={value} aria-current={tab === value ? "page" : undefined} onClick={() => { setTab(value); setNotice(""); }}>{label}</button>)}
    </nav>
    {notice && <Notice>{notice}</Notice>}
    {tab === "explore" ? <TeacherDiscovery onNotice={setNotice} /> : <TeacherDraftWorkspace onNotice={setNotice} />}
  </div>;
}

function Toggle({ label, description, checked, onChange }) {
  return <label className="sl-setting-toggle"><span><strong>{label}</strong><small>{description}</small></span><input type="checkbox" checked={Boolean(checked)} onChange={(event) => onChange(event.target.checked)} /></label>;
}

function AdminLearningCentre() {
  const [tab, setTab] = useState("overview");
  const [settings, setSettings] = useState(null);
  const [summary, setSummary] = useState(null);
  const [queue, setQueue] = useState(null);
  const [resources, setResources] = useState([]);
  const [paths, setPaths] = useState([]);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [settingData, summaryData, queueData, resourceData, pathData] = await Promise.all([
        request("admin/learning-settings/"), request("admin/learning-summary/"),
        request("studio/review-queue/"), request("studio/resources/?limit=100"), request("studio/paths/?limit=100"),
      ]);
      setSettings(settingData); setSummary(summaryData); setQueue(queueData); setResources(list(resourceData)); setPaths(list(pathData));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { const id = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(id); }, [load]);

  const queueItems = useMemo(() => [
    ...(queue?.resources || []).map((item) => ({ ...item, kind: "resource" })),
    ...(queue?.paths || []).map((item) => ({ ...item, kind: "path" })),
    ...(queue?.resource_translations || []).map((item) => ({ ...item, kind: "resource_translation", title: `${item.resource_title} · ${item.language_code}` })),
    ...(queue?.path_translations || []).map((item) => ({ ...item, kind: "path_translation", title: `${item.path_title} · ${item.language_code}` })),
  ], [queue]);
  const approvedResources = resources.filter((row) => row.status === "approved").length;
  const publishedPaths = paths.filter((row) => row.status === "published").length;
  const approvedPaths = paths.filter((row) => row.status === "approved").length;

  function changeSetting(key, value) { setSettings((current) => ({ ...current, [key]: value })); }
  async function saveSettings(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const updated = await request("admin/learning-settings/", "PATCH", {
        learning_access_enabled: settings.learning_access_enabled,
        teacher_studio_enabled: settings.teacher_studio_enabled,
        teacher_recommendations_enabled: settings.teacher_recommendations_enabled,
        minimum_learner_age: Number(settings.minimum_learner_age),
        maximum_learner_age: Number(settings.maximum_learner_age),
      });
      setSettings(updated); setMessage("School learning settings have been saved and recorded in the audit trail.");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function review(item, decision) {
    setBusy(true); setError(""); setMessage("");
    try {
      const translation = item.kind.endsWith("_translation");
      const pathItem = item.kind.startsWith("path");
      const root = pathItem ? "studio/paths/" : "studio/resources/";
      const route = translation ? `${root}${pathItem ? item.path_id : item.resource_id}/translations/${item.id}/review/` : `${root}${item.id}/review/`;
      await request(route, "POST", { decision });
      setMessage(translation
        ? (decision === "approve" ? "Translation approved for reviewed metadata; this does not publish its parent content." : "Translation changes requested; the translator can edit and resubmit.")
        : (decision === "approve" ? "Content approved for school governance. Learner publishing remains disabled by the current Marian policy." : "Changes requested; the author can edit and resubmit the draft."));
      setSelected(null); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function takedown(item) {
    const problem = takedownReasonError(reason);
    if (problem) { setError(problem); return; }
    if (!window.confirm("Take this resource down? It will be archived and removed from learners.")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await request(`studio/resources/${item.id}/takedown/`, "POST", takedownPayload(reason));
      setMessage("The resource has been taken down and the action recorded in the audit trail.");
      setReason(""); setSelected(null); await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function inspect(item) {
    setSelected({ ...item, loading: true }); setError("");
    try {
      const translation = item.kind.endsWith("_translation");
      const pathItem = item.kind.startsWith("path");
      const root = pathItem ? "studio/paths/" : "studio/resources/";
      let details;
      if (translation) {
        const parentId = pathItem ? item.path_id : item.resource_id;
        const translationRows = await request(`${root}${parentId}/translations/`);
        details = list(translationRows).find((row) => row.id === item.id);
        if (!details) throw new Error("This translation is no longer available for review.");
      } else {
        details = await request(`${root}${item.id}/`);
      }
      setSelected({ ...item, ...details, loading: false });
    } catch (err) { setSelected(null); setError(err.message); }
  }
  const switchTab = (value) => { setTab(value); setMessage(""); setError(""); setSelected(null); };

  if (loading && !settings) return <div className="sl-workspace"><Loading /></div>;
  return <div className="sl-workspace">
    <header className="sl-banner sl-banner--admin"><div><p className="sl-eyebrow">Marian · Activity 14</p><h1>Learning Administration Centre</h1><p>Control learning access, age boundaries, staff workflows and school content review. Publishing stays governed by Marian’s global content policy.</p></div><span className="sl-banner-mark" aria-hidden="true">A</span></header>
    <nav className="sl-tabs" aria-label="Learning administration sections">
      {[["overview", "Overview"], ["settings", "Access & age controls"], ["review", "Content review"], ["programmes", "Programmes"]].map(([value, label]) => <button type="button" key={value} aria-current={tab === value ? "page" : undefined} onClick={() => switchTab(value)}>{label}</button>)}
    </nav>
    {error && <Notice kind="error">{error}</Notice>}{message && <Notice>{message}</Notice>}
    {tab === "overview" && <div className="sl-page">
      <div className="sl-metric-grid">{[
        ["Learner accounts", summary?.learner_count ?? "—", "School-linked profiles only"],
        ["Active accounts", summary?.active_account_count ?? "—", "Account status, not academic standing"],
        ["Learning participations", summary?.participation_count ?? "—", "Aggregate activity count"],
        ["Completed paths", summary?.completed_path_count ?? "—", "Self-reported path status"],
      ].map(([label, value, note]) => <article className="sl-metric" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>
      <section className="sl-panel"><SectionTitle eyebrow="School content" title="Review and learning programmes" text="Approved teacher materials remain in the school catalogue workflow. The publication endpoint is intentionally disabled until rights, moderation and shared-catalogue ownership policy is approved." />
        <div className="sl-metric-grid sl-metric-grid--compact"><div className="sl-metric"><span>Items awaiting review</span><strong>{queueItems.length}</strong></div><div className="sl-metric"><span>Approved programmes</span><strong>{approvedPaths}</strong></div><div className="sl-metric"><span>Published programmes</span><strong>{publishedPaths}</strong></div></div>
        <Button kind="teal" onClick={() => switchTab("review")}>Open review queue</Button>
      </section>
      <section className="sl-panel"><h3>Oversight principles</h3><ul className="sl-principles"><li>School administrators see aggregate learning usage, not raw learner projects or messages.</li><li>Teacher progress views are restricted to assigned learners and contain participation summaries only.</li><li>Learning is isolated from marks, report cards, attendance and fee records.</li></ul></section>
    </div>}
    {tab === "settings" && settings && <form className="sl-page" onSubmit={saveSettings}>
      <section className="sl-panel"><SectionTitle eyebrow="School controls" title="Learning access" text="Changes apply to school-managed learning profiles. Turning access off blocks protected learner and staff learning endpoints; it does not delete an account or academic record." />
        <Toggle label="School-managed learning access" description="Allow eligible school learner profiles to use protected learning features." checked={settings.learning_access_enabled} onChange={(value) => changeSetting("learning_access_enabled", value)} />
        <Toggle label="Teacher Learning Studio" description="Allow teachers to explore free catalogue items, manage their own drafts and view assignment-scoped learning summaries." checked={settings.teacher_studio_enabled} onChange={(value) => changeSetting("teacher_studio_enabled", value)} />
        <Toggle label="Teacher recommendations" description="Allow teachers to recommend currently visible, reviewed and published free items to assigned learners." checked={settings.teacher_recommendations_enabled} onChange={(value) => changeSetting("teacher_recommendations_enabled", value)} />
      </section>
      <section className="sl-panel"><SectionTitle eyebrow="Age boundaries" title="School-managed learner age range" text="This additional school gate can only narrow access; it cannot override account eligibility, guardian consent, a resource’s own age band, or Marian’s approved independent-learner minimum." />
        <div className="sl-field-grid"><div className="sl-field"><label htmlFor="sl-admin-age-min">Minimum age (0–120)</label><input id="sl-admin-age-min" required type="number" min="0" max="120" value={settings.minimum_learner_age} onChange={(event) => changeSetting("minimum_learner_age", event.target.value)} /></div>
          <div className="sl-field"><label htmlFor="sl-admin-age-max">Maximum age (0–120)</label><input id="sl-admin-age-max" required type="number" min="0" max="120" value={settings.maximum_learner_age} onChange={(event) => changeSetting("maximum_learner_age", event.target.value)} /></div></div>
        <p className="sl-footnote">The learner’s date of birth is checked server-side and is never returned by these controls. Minimum must not exceed maximum.</p>
      </section>
      <Button kind="teal" type="submit" busy={busy}>Save school learning controls</Button>
    </form>}
    {tab === "review" && <div className="sl-page">
      <section className="sl-panel"><SectionTitle eyebrow="Independent review" title="Teacher-submitted content" text="Review only materials submitted within this school. Authors cannot review their own items. Approval does not publish content." />
        {!queueItems.length ? <p className="sl-empty">No resource, programme or translation submissions are waiting for review.</p> : <div className="sl-list">{queueItems.map((item) => <article className="sl-row" key={`${item.kind}-${item.id}`}>
          <div className="sl-row-main"><span className="sl-eyebrow">{item.kind.replaceAll("_", " ")} {item.language_code ? `· ${item.language_code}` : item.version ? `· version ${item.version}` : ""}</span><strong>{item.title}</strong><p>{item.translator_id ? `Translator account ID ${item.translator_id}` : `Author account ID ${item.author_id}`}</p></div>
          <div className="sl-row-actions"><Button kind="secondary" onClick={() => inspect(item)}>Inspect</Button><Button kind="teal" busy={busy} onClick={() => review(item, "approve")}>Approve</Button><Button kind="secondary" busy={busy} onClick={() => review(item, "request_changes")}>Request changes</Button></div>
        </article>)}</div>}
        {(queue?.resource_translations?.length || queue?.path_translations?.length) ? <p className="sl-footnote">Translation approval validates only that language version. It does not publish its resource or programme parent.</p> : null}
      </section>
      {(() => { const live = resources.filter((row) => ["approved", "published"].includes(row.status)); return live.length ? <section className="sl-panel"><SectionTitle eyebrow="Approved and published" title="Live school resources" text="Inspect an item to take it down if its licence or rights change." /><div className="sl-list">{live.map((row) => <article className="sl-row" key={row.id}><div className="sl-row-main"><span className="sl-eyebrow">{row.status}</span><strong>{row.title}</strong></div><div className="sl-row-actions"><Button kind="secondary" onClick={() => inspect({ ...row, kind: "resource" })}>Inspect</Button></div></article>)}</div></section> : null; })()}
        {selected && <section className="sl-panel"><div className="sl-subheading"><h3>{selected.title || "Content details"}</h3><Button kind="secondary" onClick={() => setSelected(null)}>Close</Button></div>
        {selected.loading ? <Loading /> : <><p className="sl-footnote">School-only review · {selected.kind.replaceAll("_", " ")} · {selected.version ? `version ${selected.version} · ` : ""}{selected.status || selected.review_state}</p><p>{selected.summary || selected.description || "No short description."}</p><div className="sl-reading-body">{selected.body || "No text content."}</div>
          {selected.kind.endsWith("_translation") ? <div className="sl-metadata-box"><strong>Translation provenance</strong><p>Language: {selected.language_code}</p><p>Source: {selected.translation_source || "Not recorded"}</p><p>Translator account ID: {selected.translator_id || "Not recorded"}</p>{selected.objectives?.length > 0 && <p>Objectives: {selected.objectives.join(" · ")}</p>}</div>
            : <div className="sl-metadata-box"><strong>Rights and age controls</strong><p>Source: {selected.source_name || "Not recorded"}</p><p>Licence: {selected.license_name || "Not recorded"}</p><p>Age range: {selected.age_min ?? "No minimum"}–{selected.age_max ?? "No maximum"}</p><p>Attribution: {selected.attribution || "Not recorded"}</p></div>}
          {!selected.kind.endsWith("_translation") && selected.resource_type === "interactive" && <div className="sl-metadata-box"><strong>Practice quiz · authorised reviewer preview</strong><p>Answer keys are visible only in this school content workflow; learner quiz responses omit them until an attempt is submitted.</p><ol className="sl-programme-steps">{(selected.practice_quiz?.questions || []).map((question) => <li key={question.id}><b>{question.prompt}</b><p>{question.options.map((option) => `${option.id === question.correct_option_id ? "Correct: " : ""}${option.text}`).join(" · ")}</p>{question.explanation && <p>Feedback: {question.explanation}</p>}</li>)}</ol></div>}
          {selected.author_id === null ? <p className="sl-footnote">Author information was not supplied.</p> : null}
          <div className="sl-row-actions"><Button kind="teal" busy={busy} onClick={() => review(selected, "approve")}>Approve for school governance</Button><Button kind="secondary" busy={busy} onClick={() => review(selected, "request_changes")}>Request changes</Button></div></>}
      </section>}
      {selected && !selected.kind.endsWith("_translation") && selected.kind === "resource" && ["approved", "published"].includes(selected.status) && <div className="sl-field"><label htmlFor="sl-takedown-reason">Takedown reason (required, up to 500 characters)</label><textarea id="sl-takedown-reason" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} /><Button kind="secondary" busy={busy} onClick={() => takedown(selected)}>Take down</Button></div>}
    <Notice>Publishing is disabled. Approved content is not visible to learners until the platform-wide rights, moderation and shared-catalogue policies are approved.</Notice>
    </div>}
    {tab === "programmes" && <section className="sl-panel"><SectionTitle eyebrow="School learning programmes" title="Programme lifecycle" text="Learning paths are treated as school programmes. Manage the review lifecycle without bypassing the separate publishing lock." />
      {paths.length ? <div className="sl-list">{paths.map((path) => <article className="sl-row" key={path.id}><div className="sl-row-main"><strong>{path.title}</strong><p>{path.item_count || 0} steps · {path.language_code} · version {path.version}</p></div><StatusPill>{path.status}</StatusPill></article>)}</div> : <p className="sl-empty">No school learning programmes have been created yet.</p>}
      <p className="sl-footnote">{approvedResources} school resource drafts are currently approved. Published paths: {publishedPaths}; the normal policy gate remains in effect.</p>
    </section>}
  </div>;
}

export function SchoolLearningCentre() {
  return <AdminLearningCentre />;
}
