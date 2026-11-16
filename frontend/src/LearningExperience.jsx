import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import LearningAccountSettings from "./LearningAccountSettings";
import LearnerRecommendations from "./LearnerRecommendations";
import { MotivationPanel, OfflineLearningPanel } from "./LearningMotivationOffline";
import { Button, ErrorState, Loading } from "./ui";
import {
  buildLearningQuery,
  createLearningActivityPayload,
  LEARNING_CHECKPOINTS,
  LEARNING_VIEWS,
  normalizeLearningLanguage,
} from "./learningExperienceUtils";
import "./LearningExperience.css";
import "./activity18-19.css";

const BASE = "/api/learning/v1/";

function errorText(payload, status) {
  if (payload?.detail) return String(payload.detail);
  if (payload?.errors && typeof payload.errors === "object") {
    const messages = Object.entries(payload.errors).flatMap(([field, value]) =>
      (Array.isArray(value) ? value : [value]).map((message) => `${field}: ${String(message)}`));
    if (messages.length) return messages.join(" ");
  }
  if (payload?.code) return String(payload.code).replaceAll("_", " ");
  if (status === 403) return "Learning access is blocked by account eligibility or school-status checks.";
  if (status === 404) return "This learning item is no longer available to this account.";
  if (status === 503) return "This learning feature is temporarily unavailable.";
  return "The request could not be completed. Try again.";
}

async function requestJson(path, method = "GET", body) {
  const response = await api(`${BASE}${path}`, method, body);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(errorText(payload, response.status));
    error.status = response.status;
    error.code = payload?.code;
    throw error;
  }
  return payload;
}

const resultList = (payload) => Array.isArray(payload?.results) ? payload.results : [];
const languageLabel = (code) => {
  const key = normalizeLearningLanguage(code);
  if (key === "en") return "English";
  if (key === "sw") return "Kiswahili";
  return key;
};
const humanize = (value) => String(value || "Learning item").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const niceDate = (value) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};
const checkpointLabel = (value) => LEARNING_CHECKPOINTS.find((item) => item.value === value)?.label || "Self-reported activity";
const itemSaveKey = (type, id) => `${type}:${id}`;

function PageTitle({ eyebrow, title, text, children }) {
  return <div className="lx-title-row"><div>
    {eyebrow && <p className="lx-eyebrow">{eyebrow}</p>}
    <h1>{title}</h1>
    {text && <p className="lx-lede">{text}</p>}
  </div>{children}</div>;
}

function EmptyNotice({ title, text }) {
  return <div className="lx-empty"><strong>{title}</strong>{text}</div>;
}

function Chip({ children }) {
  if (!children) return null;
  return <span className="lx-chip">{children}</span>;
}

function useLoader(dependencies, load) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((current) => ({ ...current, loading: true, error: "" }));
    load().then((data) => {
      if (alive) setState({ loading: false, error: "", data });
    }).catch((error) => {
      if (alive) setState({ loading: false, error: error.message || "Unable to load this view.", data: null });
    });
    return () => { alive = false; };
  // `dependencies` is a stable call-site list; `attempt` triggers an explicit retry.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1), setData: (data) => setState({ loading: false, error: "", data }) };
}

function ResourceCard({ resource, saved, busy, onOpen, onToggleSave }) {
  return <article className="lx-card">
    <div className="lx-card-top"><div><p className="lx-eyebrow">{humanize(resource.resource_type)}</p><h3>{resource.title}</h3></div></div>
    <p>{resource.summary || "No summary is available for this resource."}</p>
    <div className="lx-chip-row">
      <Chip>{humanize(resource.difficulty)}</Chip>
      <Chip>{resource.display_language || resource.language_code}</Chip>
      {(resource.topics || []).slice(0, 2).map((topic) => <Chip key={topic.id}>{topic.name}</Chip>)}
    </div>
    <div className="lx-actions">
      <Button kind="teal" onClick={() => onOpen(resource.id)}>Open resource</Button>
      <Button kind="secondary" busy={busy} onClick={() => onToggleSave(resource.id, !saved)}>{saved ? "Remove saved" : "Save for later"}</Button>
    </div>
  </article>;
}

function PathCard({ path, saved, busy, onOpen, onToggleSave }) {
  return <article className="lx-card">
    <div><p className="lx-eyebrow">Learning path · {path.item_count} {path.item_count === 1 ? "step" : "steps"}</p><h3>{path.title}</h3></div>
    <p>{path.description || "A Marian learning path."}</p>
    {Array.isArray(path.objectives) && path.objectives.length > 0 && <p className="lx-small">{path.objectives.slice(0, 2).join(" · ")}</p>}
    <div className="lx-chip-row"><Chip>{humanize(path.difficulty)}</Chip><Chip>{path.language_code}</Chip>
      {(path.topics || []).slice(0, 2).map((topic) => <Chip key={topic.id}>{topic.name}</Chip>)}</div>
    <div className="lx-actions">
      <Button kind="teal" onClick={() => onOpen(path.id)}>View path</Button>
      <Button kind="secondary" busy={busy} onClick={() => onToggleSave(path.id, !saved)}>{saved ? "Remove saved" : "Save for later"}</Button>
    </div>
  </article>;
}

function CatalogueScreen({ mode, language, onOpenResource, onOpenPath }) {
  const [queryInput, setQueryInput] = useState("");
  const [filters, setFilters] = useState({ q: "", topicId: "", difficulty: "", resourceType: "" });
  const [notice, setNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [savedKeys, setSavedKeys] = useState(null);
  const [busyKey, setBusyKey] = useState("");
  const data = useLoader([mode, language, filters], async () => {
    const topicPath = `catalog/topics/${buildLearningQuery({ lang: language })}`;
    const topicRequest = requestJson(topicPath);
    const resourceRequest = mode === "paths" ? Promise.resolve({ results: [], truncated: false })
      : requestJson(`catalog/resources/${buildLearningQuery({ lang: language, ...filters })}`);
    const pathRequest = requestJson(`catalog/paths/${buildLearningQuery({
      lang: language, q: filters.q, topicId: filters.topicId, difficulty: filters.difficulty,
    })}`);
    const [topics, resources, paths] = await Promise.all([topicRequest, resourceRequest, pathRequest]);
    return { topics, resources, paths };
  });

  useEffect(() => {
    let alive = true;
    requestJson(`saved/${buildLearningQuery({ lang: language })}`).then((payload) => {
      if (alive) setSavedKeys(new Set(resultList(payload).map((item) => itemSaveKey(item.item_type, item.item_id))));
    }).catch(() => { if (alive) setSavedKeys(null); });
    return () => { alive = false; };
  }, [language]);

  async function toggleSaved(type, id, shouldSave) {
    const key = itemSaveKey(type, id);
    setBusyKey(key);
    setSaveError("");
    setNotice("");
    try {
      const body = type === "resource" ? { resource_id: Number(id) } : { path_id: Number(id) };
      await requestJson("saved/", shouldSave ? "POST" : "DELETE", body);
      setSavedKeys((current) => {
        const next = new Set(current || []);
        if (shouldSave) next.add(key); else next.delete(key);
        return next;
      });
      setNotice(shouldSave ? "Saved to your private learning list." : "Removed from your saved list.");
    } catch (error) { setSaveError(error.message); }
    finally { setBusyKey(""); }
  }

  function submitFilters(event) {
    event.preventDefault();
    setFilters((current) => ({ ...current, q: queryInput.trim().slice(0, 100) }));
  }
  function clearFilters() {
    setQueryInput("");
    setFilters({ q: "", topicId: "", difficulty: "", resourceType: "" });
  }

  const heading = mode === "paths" ? "Learning paths" : "Discover learning";
  const resources = resultList(data.data?.resources);
  const paths = resultList(data.data?.paths);
  const topics = resultList(data.data?.topics);
  const truncated = Boolean(data.data?.resources?.truncated || data.data?.paths?.truncated || data.data?.topics?.truncated);
  return <div className="lx-page">
    <PageTitle eyebrow={mode === "paths" ? "Learn step by step" : "Find your next subject"} title={heading}
      text="Search only learning resources and paths currently visible to this Marian account. Availability is checked again when an item is opened." />
    <section className="lx-panel">
      <form className="lx-filter-form" onSubmit={submitFilters}>
        <div className="lx-filter-grid">
          <div className="lx-field"><label htmlFor="lx-search">Search words</label><input id="lx-search" maxLength={100} value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="Try a topic or skill" /></div>
          <div className="lx-field"><label htmlFor="lx-topic">Topic</label><select id="lx-topic" value={filters.topicId} onChange={(event) => setFilters((current) => ({ ...current, topicId: event.target.value }))}>
            <option value="">All topics</option>{topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
          </select></div>
          <div className="lx-field"><label htmlFor="lx-difficulty">Difficulty</label><select id="lx-difficulty" value={filters.difficulty} onChange={(event) => setFilters((current) => ({ ...current, difficulty: event.target.value }))}>
            <option value="">Any level</option>{["beginner", "intermediate", "advanced"].map((item) => <option key={item} value={item}>{humanize(item)}</option>)}
          </select></div>
          {mode !== "paths" && <div className="lx-field"><label htmlFor="lx-type">Resource type</label><select id="lx-type" value={filters.resourceType} onChange={(event) => setFilters((current) => ({ ...current, resourceType: event.target.value }))}>
            <option value="">All formats</option>{["article", "video", "audio", "worksheet", "interactive", "book", "other"].map((item) => <option key={item} value={item}>{humanize(item)}</option>)}
          </select></div>}
        </div>
        <div className="lx-filter-actions"><Button kind="teal" type="submit">Apply filters</Button><Button kind="secondary" onClick={clearFilters}>Clear</Button></div>
      </form>
      {data.loading && <div style={{ marginTop: "1rem" }}><Loading /></div>}
      {data.error && <div style={{ marginTop: "1rem" }}><ErrorState text={data.error} onRetry={data.retry} /></div>}
      {truncated && <p className="lx-small" role="status">This result list is capped at 200 items. Refine your search to find other available items.</p>}
      {saveError && <div className="lx-alert" role="alert">{saveError}</div>}
      {notice && <div className="lx-notice" role="status">{notice}</div>}
    </section>
    {!data.loading && !data.error && <>
      {mode !== "paths" && <section className="lx-page" aria-labelledby="lx-resource-results">
        <div className="lx-section-heading"><h2 id="lx-resource-results">Resources</h2><span className="lx-small">{resources.length} shown</span></div>
        {resources.length ? <div className="lx-card-list">{resources.map((resource) => {
          const key = itemSaveKey("resource", resource.id);
          return <ResourceCard key={resource.id} resource={resource} saved={savedKeys?.has(key)} busy={busyKey === key}
            onOpen={onOpenResource} onToggleSave={(id, shouldSave) => toggleSaved("resource", id, shouldSave)} />;
        })}</div> : <EmptyNotice title="No resources to show" text="No currently available resources match these filters. New items appear only after Marian's publication and eligibility checks permit them." />}
      </section>}
      <section className="lx-page" aria-labelledby="lx-path-results">
        <div className="lx-section-heading"><h2 id="lx-path-results">Learning paths</h2><span className="lx-small">{paths.length} shown</span></div>
        {paths.length ? <div className="lx-card-list">{paths.map((path) => {
          const key = itemSaveKey("path", path.id);
          return <PathCard key={path.id} path={path} saved={savedKeys?.has(key)} busy={busyKey === key}
            onOpen={onOpenPath} onToggleSave={(id, shouldSave) => toggleSaved("path", id, shouldSave)} />;
        })}</div> : <EmptyNotice title="No paths to show" text="No currently available paths match these filters. Path visibility and content access are rechecked by Marian." />}
      </section>
    </>}
    <p className="lx-footer-note">School-managed learners see only public and their own school’s permitted content. Independent learners are not linked to a school by name or inferred identity.</p>
  </div>;
}

function useRecentLearning(language) {
  return useLoader([language], async () => {
    const [eventsPayload, participationPayload] = await Promise.all([
      requestJson("activity-events/?limit=20"),
      requestJson(`participation/paths/?limit=20&lang=${encodeURIComponent(language)}`),
    ]);
    const events = resultList(eventsPayload).slice(0, 10);
    const rows = await Promise.all(events.map(async (event) => {
      const target = event.target;
      if (!target) return { event, title: "Learning activity", open: null };
      try {
        if (target.type === "resource") {
          const resource = await requestJson(`catalog/resources/${target.id}/${buildLearningQuery({ lang: language })}`);
          return { event, title: resource.title, open: { type: "resource", id: target.id } };
        }
        if (target.type === "path_item" && target.path_id) {
          const path = await requestJson(`catalog/paths/${target.path_id}/${buildLearningQuery({ lang: language })}`);
          return { event, title: path.title, open: { type: "path", id: target.path_id } };
        }
      } catch { /* A hidden item is shown only as an unavailable historical event. */ }
      return { event, title: "Previously accessed learning item", open: null };
    }));
    return {
      events: rows,
      participations: resultList(participationPayload),
      eventsTruncated: Boolean(eventsPayload.truncated),
      pathsTruncated: Boolean(participationPayload.truncated),
    };
  });
}

function RecentLearning({ language, onOpenResource, onOpenPath, compact = false }) {
  const recent = useRecentLearning(language);
  const data = recent.data;
  return <section className="lx-panel">
    <div className="lx-section-heading"><h2>{compact ? "Pick up where you left off" : "Your learning activity"}</h2>
      {compact && <span className="lx-small">Your account only</span>}</div>
    {recent.loading && <Loading />}
    {recent.error && <ErrorState text={recent.error} onRetry={recent.retry} />}
    {data && <div className="lx-split">
      <div>
        <h3>Paths in progress</h3>
        {data.pathsTruncated && <p className="lx-small">Only the latest 20 visible path participations are shown.</p>}
        {data.participations.length ? <div className="lx-list">{data.participations.map((path) => <article className="lx-row" key={path.id}>
          <div className="lx-row-content"><b>{path.path_title}</b><p>{humanize(path.state)} · Last activity {niceDate(path.last_activity_at) || "not recorded"}</p></div>
          <div className="lx-row-actions"><Button kind="secondary" onClick={() => onOpenPath(path.path_id)}>Open path</Button></div>
        </article>)}</div> : <EmptyNotice title="No paths in progress" text="Starting a visible learning path will place it here. Path steps are not automatically marked complete." />}
      </div>
      <div>
        <h3>Recent activity</h3>
        {data.eventsTruncated && <p className="lx-small">Your history is capped by the service; the latest events are shown.</p>}
        {data.events.length ? <div className="lx-list">{data.events.map(({ event, title, open }) => {
          const target = event.target;
          const type = event.event_type === "started" ? "Started" : event.event_type === "progress" ? "Check-in" : event.event_type === "feedback" ? "Feedback" : humanize(event.event_type);
          const targetOpen = open?.type === "resource" ? () => onOpenResource(open.id) : open?.type === "path" ? () => onOpenPath(open.id) : null;
          return <article className="lx-row" key={event.id}>
            <div className="lx-row-content"><b>{title}</b><p>{type}{event.details?.checkpoint ? ` · ${checkpointLabel(event.details.checkpoint)}` : ""} · {niceDate(event.occurred_at) || "Date unavailable"}</p></div>
            {targetOpen && <div className="lx-row-actions"><Button kind="secondary" onClick={targetOpen}>Reopen</Button></div>}
            {!target && <span className="lx-small">Private account event</span>}
          </article>;
        })}</div> : <EmptyNotice title="No recent activity" text="Marian records only explicit starts and self-reported check-ins. It does not estimate time spent." />}
      </div>
    </div>}
  </section>;
}

function HomeScreen({ language, onDiscover, onPaths, onOpenResource, onOpenPath }) {
  return <div className="lx-page">
    <section className="lx-panel lx-hero"><div className="lx-hero-content">
      <p className="lx-eyebrow">Your Marian learning space</p>
      <h1>Learn at your pace.<br />Choose what comes next.</h1>
      <p>Explore resources and learning paths currently available to this account. Your learning activity is not public. For school-managed learners, limited progress summaries may be visible to assigned teachers. Marian checks access whenever content is opened.</p>
      <div className="lx-actions"><Button kind="teal" onClick={onDiscover}>Explore resources</Button><Button kind="secondary" onClick={onPaths}>Browse learning paths</Button></div>
    </div></section>
      <RecentLearning language={language} onOpenResource={onOpenResource} onOpenPath={onOpenPath} compact />
    <MotivationPanel language={language} />
    <OfflineLearningPanel language={language} />
    <div className="lx-footer-note">No AI tutor, time-based rewards, client-declared completion, or premium checkout is enabled by this learning screen.</div>
  </div>;
}

function ContinueScreen({ language, onOpenResource, onOpenPath }) {
  return <div className="lx-page"><PageTitle eyebrow="Your own history" title="Continue learning" text="Only activity and path participation returned for the signed-in learner are shown here." />
    <RecentLearning language={language} onOpenResource={onOpenResource} onOpenPath={onOpenPath} />
  </div>;
}

function SavedScreen({ language, onOpenResource, onOpenPath }) {
  const saved = useLoader([language], () => requestJson(`saved/${buildLearningQuery({ lang: language })}`));
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const rows = resultList(saved.data);
  async function remove(row) {
    setBusyId(String(row.id)); setActionError(""); setNotice("");
    try {
      const body = row.item_type === "resource" ? { resource_id: row.item_id } : { path_id: row.item_id };
      await requestJson("saved/", "DELETE", body);
      saved.setData({ ...saved.data, results: rows.filter((item) => item.id !== row.id) });
      setNotice("Removed from your saved list.");
    } catch (error) { setActionError(error.message); }
    finally { setBusyId(""); }
  }
  return <div className="lx-page">
    <PageTitle eyebrow="Your private shortlist" title="Saved for later" text="Saved items are private to this learner. Marian rechecks current availability before opening them." />
    {saved.loading && <Loading />}
    {saved.error && <ErrorState text={saved.error} onRetry={saved.retry} />}
    {actionError && <div className="lx-alert" role="alert">{actionError}</div>}
    {notice && <div className="lx-notice" role="status">{notice}</div>}
    {saved.data?.truncated && <div className="lx-alert">This list is capped at 200 records. Older saves may not be shown.</div>}
    {!saved.loading && !saved.error && (rows.length ? <div className="lx-card-list">{rows.map((row) => {
      const item = row.item || {};
      const pathItem = row.item_type === "path";
      return <article className="lx-card" key={row.id}>
        <p className="lx-eyebrow">{pathItem ? "Learning path" : humanize(item.resource_type)}</p>
        <h3>{item.title || "Saved learning item"}</h3>
        <p>{item.description || item.summary || "No summary is available."}</p>
        <p className="lx-small">Saved {niceDate(row.saved_at) || "date unavailable"}</p>
        <div className="lx-actions">
          <Button kind="teal" onClick={() => pathItem ? onOpenPath(row.item_id) : onOpenResource(row.item_id)}>{pathItem ? "View path" : "Open resource"}</Button>
          <Button kind="secondary" busy={busyId === String(row.id)} onClick={() => remove(row)}>Remove</Button>
        </div>
      </article>;
    })}</div> : <EmptyNotice title="Nothing saved yet" text="Save a resource or learning path from Discover to keep it here for later." />)}
  </div>;
}

function PracticeQuiz({ resourceId, language }) {
  const kiswahili = normalizeLearningLanguage(language) === "sw";
  const [loadState, setLoadState] = useState({ resourceId, language, loading: true, data: null, error: "" });
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [attemptError, setAttemptError] = useState("");
  const isCurrentRequest = loadState.resourceId === resourceId && loadState.language === language;
  const data = isCurrentRequest ? loadState.data : null;
  const loading = !isCurrentRequest || loadState.loading;
  const error = attemptError || (isCurrentRequest ? loadState.error : "");
  useEffect(() => {
    let active = true;
    requestJson(`practice/resources/${resourceId}/quiz/${buildLearningQuery({ lang: language })}`)
      .then((payload) => { if (active) setLoadState({ resourceId, language, loading: false, data: payload, error: "" }); })
      .catch((failure) => { if (active) setLoadState({ resourceId, language, loading: false, data: null, error: failure.message }); });
    return () => { active = false; };
  }, [resourceId, language]);

  async function submit(event) {
    event.preventDefault();
    if (!data || data.quiz.questions.some((question) => !answers[question.id])) return;
    setBusy(true); setAttemptError("");
    try {
      const idempotencyKey = window.crypto?.randomUUID?.();
      if (!idempotencyKey) throw new Error("Secure attempt submission is unavailable in this browser.");
      const outcome = await requestJson(`practice/resources/${resourceId}/attempts/`, "POST", {
        idempotency_key: idempotencyKey,
        resource_version: data.resource_version,
        answers,
      });
      setResult(outcome);
    } catch (failure) { setAttemptError(failure.message); }
    finally { setBusy(false); }
  }

  return <section className="lx-panel lx-practice" aria-labelledby="lx-practice-title">
    <h2 id="lx-practice-title">{kiswahili ? "Jaribio la mazoezi" : "Practice quiz"}</h2>
    <p className="lx-small">{kiswahili ? "Haya ni mazoezi ya hiari ya kujifunza, si mtihani, alama ya shule, au cheti cha umahiri. Kukamilisha kunarekodiwa tu baada ya Marian kuthibitisha majibu yako." : "This is optional learning practice, not an examination, school mark, or mastery certificate. Completion is recorded only after Marian validates your answers."}</p>
    {loading && <Loading />}
    {error && <div className="lx-alert" role="alert">{error}</div>}
    {data && <form className="lx-practice-form" onSubmit={submit}>
      <p className="lx-small">{kiswahili ? `Maswali yako kwa ${languageLabel(data.language_code)}. Jibu kila swali kabla ya kutuma.` : `Questions are in ${languageLabel(data.language_code)}. Answer every question before submitting.`}</p>
      {data.quiz.questions.map((question, index) => {
        const feedback = result?.feedback?.find((row) => row.question_id === question.id);
        return <fieldset className="lx-practice-question" key={question.id}>
          <legend>{index + 1}. {question.prompt}</legend>
          {question.options.map((option) => <label className="lx-practice-option" key={option.id}>
            <input type="radio" name={`practice-${question.id}`} value={option.id} checked={answers[question.id] === option.id} disabled={Boolean(result) || busy} onChange={() => setAnswers((current) => ({ ...current, [question.id]: option.id }))} />
            <span>{option.text}</span>
          </label>)}
          {feedback && <p className={feedback.correct ? "lx-practice-feedback lx-practice-feedback--correct" : "lx-practice-feedback lx-practice-feedback--review"}>
            {feedback.correct ? (kiswahili ? "Sahihi." : "Correct.") : `${kiswahili ? "Angalia tena" : "Review"}: ${question.options.find((option) => option.id === feedback.correct_option_id)?.text || (kiswahili ? "jibu sahihi" : "the correct option")}.`} {feedback.explanation}
          </p>}
        </fieldset>;
      })}
      {result ? <div className="lx-notice" role="status"><strong>{kiswahili ? `Majibu sahihi ${result.correct_count} kati ya ${result.question_count}.` : `${result.correct_count} of ${result.question_count} correct.`}</strong> {kiswahili ? "Jaribio hili la mazoezi limerekodiwa kwa faragha. Si alama ya mtihani wala matokeo ya kadi ya ripoti." : result.recording_policy}</div>
        : <Button kind="teal" type="submit" busy={busy} disabled={busy || data.quiz.questions.some((question) => !answers[question.id])}>{kiswahili ? "Tuma jaribio la mazoezi" : "Submit practice attempt"}</Button>}
    </form>}
  </section>;
}

function ResourceDetail({ id, language, onBack }) {
  const resource = useLoader([id, language], () => requestJson(`catalog/resources/${id}/${buildLearningQuery({ lang: language })}`));
  const [checkpoint, setCheckpoint] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [assetBusy, setAssetBusy] = useState("");
  const item = resource.data;
  async function record(eventType) {
    if (eventType === "progress" && !checkpoint) return;
    setBusy(eventType); setActionError(""); setNotice("");
    try {
      const payload = createLearningActivityPayload({
        eventType, targetField: "resource_id", targetId: id, checkpoint: eventType === "progress" ? checkpoint : undefined,
      });
      await requestJson("activity-events/", "POST", payload);
      setNotice(eventType === "started" ? "Start recorded. Marian does not track time or mark this resource complete." : "Your self-reported check-in was recorded. It does not mark the resource or a path complete.");
    } catch (error) { setActionError(error.message); }
    finally { setBusy(""); }
  }
  async function save() {
    setBusy("save"); setActionError(""); setNotice("");
    try {
      await requestJson("saved/", "POST", { resource_id: Number(id) });
      setNotice("Saved to your private learning list.");
    } catch (error) { setActionError(error.message); }
    finally { setBusy(""); }
  }
  async function downloadAsset(asset) {
    setAssetBusy(String(asset.id)); setActionError("");
    try {
      if (!String(asset.download_url || "").startsWith("/")) throw new Error("This file download is unavailable.");
      const response = await api(asset.download_url);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(errorText(payload, response.status));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const extension = String(asset.content_type || "").split("/")[1]?.replace(/[^a-z0-9]/gi, "") || "file";
      anchor.download = `marian-learning-${asset.id}.${extension}`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { setActionError(error.message); }
    finally { setAssetBusy(""); }
  }
  const externalUrl = useMemo(() => {
    try { const url = new URL(item?.external_url); return url.protocol === "https:" ? url.href : ""; }
    catch { return ""; }
  }, [item?.external_url]);
  return <div className="lx-page">
    <div className="lx-inline-actions"><Button kind="secondary" onClick={onBack}>Back</Button><span className="lx-small">Resource detail</span></div>
    {resource.loading && <Loading />}
    {resource.error && <ErrorState text={resource.error} onRetry={resource.retry} />}
    {item && <>
      <PageTitle eyebrow={humanize(item.resource_type)} title={item.title} text={item.summary} />
      <section className="lx-panel">
        <div className="lx-chip-row"><Chip>{humanize(item.difficulty)}</Chip><Chip>{item.display_language || item.language_code}</Chip>
          {(item.topics || []).map((topic) => <Chip key={topic.id}>{topic.name}</Chip>)}</div>
        <div className="lx-actions"><Button kind="secondary" busy={busy === "save"} onClick={save}>Save for later</Button>
          <Button kind="secondary" busy={busy === "started"} onClick={() => record("started")}>Record start</Button></div>
      </section>
      {actionError && <div className="lx-alert" role="alert">{actionError}</div>}
      {notice && <div className="lx-notice" role="status">{notice}</div>}
      {item.body && <section className="lx-panel"><h2>Resource</h2><div className="lx-detail-body">{item.body}</div></section>}
      {item.resource_type === "interactive" && <PracticeQuiz key={`${item.id}:${item.version}:${language}`} resourceId={item.id} language={language} />}
      {externalUrl && <section className="lx-panel"><h2>External resource</h2><p>Opens outside Marian; the external site applies its own terms and privacy practices.</p><a href={externalUrl} target="_blank" rel="noopener noreferrer">Open {item.source_name || "external resource"}</a></section>}
      {Array.isArray(item.private_assets) && item.private_assets.length > 0 && <section className="lx-panel"><h2>Files</h2><p className="lx-small">Downloads are served through Marian's protected asset endpoint.</p>
        <div className="lx-list">{item.private_assets.map((asset) => <article className="lx-row" key={asset.id}>
          <div className="lx-row-content"><b>{humanize(asset.content_type)}</b><p>{Math.max(1, Math.round((asset.size_bytes || 0) / 1024))} KB</p></div>
          <Button kind="secondary" busy={assetBusy === String(asset.id)} onClick={() => downloadAsset(asset)}>Download file</Button>
        </article>)}</div>
      </section>}
      {(item.source_name || item.license_name || item.attribution) && <section className="lx-panel"><h2>Source and use</h2>
        {item.source_name && <p><b>Source:</b> {item.source_name}</p>}{item.license_name && <p><b>License:</b> {item.license_name}</p>}{item.attribution && <p><b>Attribution:</b> {item.attribution}</p>}
      </section>}
      <section className="lx-panel"><h2>Optional progress check-in</h2><p className="lx-small">Choose a self-reported check-in. Marian records no elapsed time and does not infer mastery or completion.</p>
        <div className="lx-step-actions"><div className="lx-field"><label htmlFor="lx-resource-checkpoint">Check-in</label><select id="lx-resource-checkpoint" value={checkpoint} onChange={(event) => setCheckpoint(event.target.value)}>
          <option value="">Choose a check-in</option>{LEARNING_CHECKPOINTS.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </select></div><Button kind="teal" busy={busy === "progress"} disabled={!checkpoint} onClick={() => record("progress")}>Record check-in</Button></div>
      </section>
    </>}
  </div>;
}

function PathDetail({ id, language, onBack, onOpenResource }) {
  const pathState = useLoader([id, language], () => requestJson(`catalog/paths/${id}/${buildLearningQuery({ lang: language })}`));
  const [participation, setParticipation] = useState(null);
  const [startBusy, setStartBusy] = useState(false);
  const [checkpointByItem, setCheckpointByItem] = useState({});
  const [busyItem, setBusyItem] = useState("");
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const path = pathState.data;
  const inProgress = participation?.state === "in_progress";
  useEffect(() => {
    let alive = true;
    requestJson(`participation/paths/?limit=200&lang=${encodeURIComponent(language)}`).then((payload) => {
      if (alive) setParticipation(resultList(payload).find((item) => Number(item.path_id) === Number(id)) || null);
    }).catch(() => { if (alive) setParticipation(null); });
    return () => { alive = false; };
  }, [id, language]);
  async function startPath() {
    setStartBusy(true); setActionError(""); setNotice("");
    try {
      const result = await requestJson(`paths/${id}/start/`, "POST", {});
      setParticipation(result);
      setNotice("Path participation is in progress. Steps are not automatically marked complete.");
    } catch (error) { setActionError(error.message); }
    finally { setStartBusy(false); }
  }
  async function recordStep(itemId) {
    const checkpoint = checkpointByItem[itemId];
    if (!checkpoint) return;
    setBusyItem(String(itemId)); setActionError(""); setNotice("");
    try {
      const payload = createLearningActivityPayload({
        eventType: "progress", targetField: "path_item_id", targetId: itemId, checkpoint,
      });
      await requestJson("activity-events/", "POST", payload);
      setNotice("Your self-reported step check-in was recorded. The path remains in progress.");
    } catch (error) { setActionError(error.message); }
    finally { setBusyItem(""); }
  }
  async function savePath() {
    setStartBusy(true); setActionError(""); setNotice("");
    try { await requestJson("saved/", "POST", { path_id: Number(id) }); setNotice("Path saved to your private learning list."); }
    catch (error) { setActionError(error.message); }
    finally { setStartBusy(false); }
  }
  return <div className="lx-page">
    <div className="lx-inline-actions"><Button kind="secondary" onClick={onBack}>Back</Button><span className="lx-small">Learning path detail</span></div>
    {pathState.loading && <Loading />}
    {pathState.error && <ErrorState text={pathState.error} onRetry={pathState.retry} />}
    {path && <>
      <PageTitle eyebrow="Learning path" title={path.title} text={path.description} />
      {actionError && <div className="lx-alert" role="alert">{actionError}</div>}
      {notice && <div className="lx-notice" role="status">{notice}</div>}
      <section className="lx-panel"><div className="lx-chip-row"><Chip>{humanize(path.difficulty)}</Chip><Chip>{path.language_code}</Chip>
        {(path.topics || []).map((topic) => <Chip key={topic.id}>{topic.name}</Chip>)}</div>
        {Array.isArray(path.objectives) && path.objectives.length > 0 && <><h2>Objectives</h2><ul>{path.objectives.map((objective, index) => <li key={`${index}-${objective}`}>{objective}</li>)}</ul></>}
        <div className="lx-actions"><Button kind="teal" busy={startBusy} onClick={startPath}>{inProgress ? "Continue path" : "Start path"}</Button><Button kind="secondary" busy={startBusy} onClick={savePath}>Save for later</Button></div>
        {inProgress && <p className="lx-small">Status: in progress. Marian does not currently verify path completion.</p>}
      </section>
      <section className="lx-panel"><div className="lx-section-heading"><h2>Path steps</h2><span className="lx-small">{path.items?.length || 0} shown</span></div>
        <div className="lx-alert" role="status">Path-step instructions are not localized by the learner catalogue yet. Check the path’s listed language; the content-language selector may affect catalogue metadata only.</div>
        {path.items?.length ? path.items.map((item, index) => <article className="lx-step" key={item.id}>
          <span className="lx-step-number" aria-label={`Step ${index + 1}`}>{index + 1}</span>
          <div className="lx-step-content"><h3>{item.title}</h3>
            {item.instructions && <p>{item.instructions}</p>}
            {item.resource && <div className="lx-actions"><Button kind="secondary" onClick={() => onOpenResource(item.resource.id)}>Open linked resource</Button></div>}
            {item.completion_rule === "view" && <p className="lx-small">Viewing this step does not mark it complete.</p>}
            <div className="lx-step-actions"><div className="lx-field"><label htmlFor={`lx-checkpoint-${item.id}`}>Optional check-in</label><select id={`lx-checkpoint-${item.id}`} value={checkpointByItem[item.id] || ""} onChange={(event) => setCheckpointByItem((current) => ({ ...current, [item.id]: event.target.value }))}>
              <option value="">Choose a check-in</option>{LEARNING_CHECKPOINTS.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
            </select></div><Button kind="teal" busy={busyItem === String(item.id)} disabled={!inProgress || !checkpointByItem[item.id]} onClick={() => recordStep(item.id)}>Record check-in</Button></div>
            {!inProgress && <p className="lx-small">Start the path before recording a check-in for a step.</p>}
          </div>
        </article>) : <EmptyNotice title="No visible steps" text="This path has no currently visible steps. Marian does not allow a hidden or unavailable resource to be opened through a path." />}
      </section>
    </>}
  </div>;
}

function GoalsScreen({ language }) {
  const goals = useLoader([language], async () => {
    const [goalPayload, topicPayload, pathPayload] = await Promise.all([
      requestJson("goals/"),
      requestJson(`catalog/topics/${buildLearningQuery({ lang: language })}`),
      requestJson(`catalog/paths/${buildLearningQuery({ lang: language })}`),
    ]);
    return { goals: goalPayload, topics: topicPayload, paths: pathPayload };
  });
  const [draft, setDraft] = useState({ title: "", description: "", targetDate: "", topicId: "", pathId: "" });
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const goalRows = resultList(goals.data?.goals);
  const topics = resultList(goals.data?.topics);
  const paths = resultList(goals.data?.paths);
  function changeDraft(field, value) { setDraft((current) => ({ ...current, [field]: value })); }
  function resetForm() {
    setDraft({ title: "", description: "", targetDate: "", topicId: "", pathId: "" });
    setEditingId(null);
  }
  function editGoal(goal) {
    setEditingId(goal.id);
    setDraft({ title: goal.title || "", description: goal.description || "", targetDate: goal.target_date || "", topicId: goal.topic?.id ? String(goal.topic.id) : "", pathId: goal.path?.id ? String(goal.path.id) : "" });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setActionError(""); setNotice("");
    const body = {
      title: draft.title.trim(), description: draft.description,
      target_date: draft.targetDate || null,
      topic_id: draft.topicId ? Number(draft.topicId) : null,
      path_id: draft.pathId ? Number(draft.pathId) : null,
    };
    try {
      await requestJson(editingId ? `goals/${editingId}/` : "goals/", editingId ? "PATCH" : "POST", body);
      setNotice(editingId ? "Goal updated." : "Goal created.");
      resetForm(); goals.retry();
    } catch (error) { setActionError(error.message); }
    finally { setBusy(false); }
  }
  async function changeState(goal, state) {
    setBusy(true); setActionError(""); setNotice("");
    try { await requestJson(`goals/${goal.id}/`, "PATCH", { state }); setNotice(`Goal marked ${state}.`); goals.retry(); }
    catch (error) { setActionError(error.message); }
    finally { setBusy(false); }
  }
  async function closeGoal(goal) {
    if (!window.confirm("Close this goal? Marian retains the goal record in your learning account; this is not permanent deletion.")) return;
    setBusy(true); setActionError(""); setNotice("");
    try { await requestJson(`goals/${goal.id}/`, "DELETE"); setNotice("Goal closed. Its record is retained in your account history."); goals.retry(); }
    catch (error) { setActionError(error.message); }
    finally { setBusy(false); }
  }
  return <div className="lx-page">
    <PageTitle eyebrow="Set a direction" title="Learning goals" text="Goals are private to your learning account. Creating a goal does not claim that a resource, path, or skill is completed." />
    {goals.loading && <Loading />}{goals.error && <ErrorState text={goals.error} onRetry={goals.retry} />}
    {actionError && <div className="lx-alert" role="alert">{actionError}</div>}{notice && <div className="lx-notice" role="status">{notice}</div>}
    {!goals.loading && !goals.error && <>
      <section className="lx-panel"><h2>{editingId ? "Edit goal" : "Create a goal"}</h2>
        <form className="lx-goal-form" onSubmit={submit}>
          <div className="lx-field"><label htmlFor="lx-goal-title">Goal</label><input id="lx-goal-title" required maxLength={200} value={draft.title} onChange={(event) => changeDraft("title", event.target.value)} placeholder="For example, practise fractions" /></div>
          <div className="lx-field"><label htmlFor="lx-goal-description">Notes (optional)</label><textarea id="lx-goal-description" maxLength={5000} value={draft.description} onChange={(event) => changeDraft("description", event.target.value)} /></div>
          <div className="lx-filter-grid">
            <div className="lx-field"><label htmlFor="lx-goal-date">Target date (optional)</label><input id="lx-goal-date" type="date" value={draft.targetDate} onChange={(event) => changeDraft("targetDate", event.target.value)} /></div>
            <div className="lx-field"><label htmlFor="lx-goal-topic">Topic (optional)</label><select id="lx-goal-topic" value={draft.topicId} onChange={(event) => changeDraft("topicId", event.target.value)}><option value="">No topic</option>{topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></div>
            <div className="lx-field"><label htmlFor="lx-goal-path">Visible path (optional)</label><select id="lx-goal-path" value={draft.pathId} onChange={(event) => changeDraft("pathId", event.target.value)}><option value="">No path</option>{paths.map((path) => <option key={path.id} value={path.id}>{path.title}</option>)}</select></div>
          </div>
          <div className="lx-actions"><Button kind="teal" type="submit" busy={busy}>{editingId ? "Save goal" : "Create goal"}</Button>{editingId && <Button kind="secondary" disabled={busy} onClick={resetForm}>Cancel edit</Button>}</div>
        </form>
      </section>
      <section className="lx-panel"><div className="lx-section-heading"><h2>Your goals</h2><span className="lx-small">{goalRows.length} shown</span></div>
        {goals.data.goals?.truncated && <p className="lx-small">This list is capped at 200 goals.</p>}
        {goalRows.length ? <div className="lx-list">{goalRows.map((goal) => <article className="lx-row" key={goal.id}>
          <div className="lx-row-content"><b>{goal.title}</b><p>{humanize(goal.state)}{goal.target_date ? ` · Target ${niceDate(goal.target_date)}` : ""}</p>
            {goal.description && <p>{goal.description}</p>}
            <p className="lx-small">{goal.topic?.name ? `Topic: ${goal.topic.name}` : "No linked topic"}{goal.path?.title ? ` · Path: ${goal.path.title}` : ""}</p>
          </div>
          {goal.state !== "closed" && <div className="lx-row-actions">
            <Button kind="secondary" disabled={busy} onClick={() => editGoal(goal)}>Edit</Button>
            {goal.state === "active" && <Button kind="secondary" busy={busy} onClick={() => changeState(goal, "paused")}>Pause</Button>}
            {goal.state === "paused" && <Button kind="secondary" busy={busy} onClick={() => changeState(goal, "active")}>Resume</Button>}
            {goal.state !== "completed" && <Button kind="teal" busy={busy} onClick={() => changeState(goal, "completed")}>Mark goal complete</Button>}
            {goal.state === "completed" && <Button kind="secondary" busy={busy} onClick={() => changeState(goal, "active")}>Reopen goal</Button>}
            <Button kind="danger" busy={busy} onClick={() => closeGoal(goal)}>Close goal</Button>
          </div>}
        </article>)}</div> : <EmptyNotice title="No goals yet" text="Create a goal above. It stays a learner-set intention; Marian does not infer that it has been achieved." />}
      </section>
    </>}
  </div>;
}

export default function LearningExperience({ me, out }) {
  const [view, setView] = useState("home");
  const [detail, setDetail] = useState(null);
  const [language, setLanguage] = useState("en");
  const [profileState, setProfileState] = useState({ loading: true, profile: null, error: "" });
  const [languageBusy, setLanguageBusy] = useState(false);
  const [languageError, setLanguageError] = useState("");
  const [profileAttempt, setProfileAttempt] = useState(0);
  const [highContrast, setHighContrast] = useState(() => localStorage.getItem("marian:learning-high-contrast") === "1");
  const [reducedMotion, setReducedMotion] = useState(() => localStorage.getItem("marian:learning-reduced-motion") === "1");

  useEffect(() => {
    document.documentElement.classList.toggle("learning-high-contrast", highContrast);
    document.documentElement.classList.toggle("learning-reduced-motion", reducedMotion);
    localStorage.setItem("marian:learning-high-contrast", highContrast ? "1" : "0");
    localStorage.setItem("marian:learning-reduced-motion", reducedMotion ? "1" : "0");
  }, [highContrast, reducedMotion]);

  useEffect(() => {
    let alive = true;
    requestJson("me/").then((payload) => {
      const expected = me?.role === "public_learner" ? "public_learner" : "school_student";
      if (!payload.profile || payload.profile.account_kind !== expected) {
        throw new Error("This Marian account does not have an active learner profile for this learning space.");
      }
      if (alive) {
        const preferred = Array.isArray(payload.preferences?.preferred_languages) ? payload.preferences.preferred_languages : [];
        setLanguage(normalizeLearningLanguage(preferred[0] || payload.profile.locale || "en"));
        setProfileState({ loading: false, profile: payload, error: "" });
      }
    }).catch((error) => {
      if (alive) setProfileState({ loading: false, profile: null, error: error.message || "The learning profile could not be checked." });
    });
    return () => { alive = false; };
  }, [me?.role, profileAttempt]);

  const languageOptions = useMemo(() => {
    const profile = profileState.profile;
    const preferred = Array.isArray(profile?.preferences?.preferred_languages) ? profile.preferences.preferred_languages : [];
    const locale = profile?.profile?.locale;
    return Array.from(new Set(["en", "sw", locale, ...preferred].filter(Boolean).map(normalizeLearningLanguage)));
  }, [profileState.profile]);

  async function changeLanguage(nextValue) {
    const next = normalizeLearningLanguage(nextValue);
    const profile = profileState.profile;
    const previous = Array.isArray(profile?.preferences?.preferred_languages) ? profile.preferences.preferred_languages : [];
    const nextPreferences = [next, ...previous.filter((item) => normalizeLearningLanguage(item) !== next)].slice(0, 10);
    setLanguageBusy(true); setLanguageError("");
    try {
      const payload = await requestJson("me/", "PATCH", { preferences: { preferred_languages: nextPreferences } });
      setLanguage(next);
      setProfileState((current) => ({ ...current, profile: { ...current.profile, ...payload } }));
    } catch (error) { setLanguageError(error.message); }
    finally { setLanguageBusy(false); }
  }

  function go(next) { setDetail(null); setView(next); }
  function openResource(id, returnTo = null) { setDetail({ type: "resource", id, returnTo }); }
  function openPath(id) { setDetail({ type: "path", id }); }
  function backFromDetail() {
    if (detail?.type === "resource" && detail.returnTo) setDetail(detail.returnTo);
    else setDetail(null);
  }
  const learningProfile = profileState.profile?.profile;
  const profileReady = Boolean(learningProfile);
  const accountLabel = learningProfile?.account_kind === "school_student" ? "School-managed learner" : "Independent learner";

  let content;
  if (view === "account") content = <div className="lx-page lx-account"><LearningAccountSettings me={me} /></div>;
  else if (profileState.loading) content = <div className="lx-page"><Loading /></div>;
  else if (!profileReady) content = <div className="lx-page"><PageTitle eyebrow="Account eligibility" title="Learning access is unavailable" text="Marian checks learner age, consent, account status and (for school-managed learners) current school eligibility on every protected request." />
    <div className="lx-alert" role="alert">{profileState.error} If you think this is unexpected, ask your linked guardian or school to review the account status. No age or consent checks are bypassed here.</div>
    <section className="lx-panel"><h2>Account and sign-in</h2><p>Your existing Marian sign-in remains unchanged. Independent learner registration, provider verification and recovery are not added by this screen.</p><Button kind="secondary" onClick={() => { setProfileState((current) => ({ ...current, loading: true, error: "" })); setProfileAttempt((value) => value + 1); }}>Check access again</Button></section>
  </div>;
  else if (detail?.type === "resource") content = <ResourceDetail key={`resource-${detail.id}`} id={detail.id} language={language} onBack={backFromDetail} />;
  else if (detail?.type === "path") content = <PathDetail key={`path-${detail.id}`} id={detail.id} language={language} onBack={backFromDetail}
    onOpenResource={(id) => openResource(id, detail)} />;
  else if (view === "home") content = <HomeScreen language={language} onDiscover={() => go("discover")} onPaths={() => go("paths")} onOpenResource={openResource} onOpenPath={openPath} />;
  else if (view === "discover") content = <CatalogueScreen mode="all" language={language} onOpenResource={openResource} onOpenPath={openPath} />;
  else if (view === "recommendations") content = <LearnerRecommendations language={language} onOpenResource={openResource} onOpenPath={openPath} />;
  else if (view === "paths") content = <CatalogueScreen mode="paths" language={language} onOpenResource={openResource} onOpenPath={openPath} />;
  else if (view === "continue") content = <ContinueScreen language={language} onOpenResource={openResource} onOpenPath={openPath} />;
  else if (view === "goals") content = <GoalsScreen language={language} />;
  else if (view === "saved") content = <SavedScreen language={language} onOpenResource={openResource} onOpenPath={openPath} />;
  else content = <HomeScreen language={language} onDiscover={() => go("discover")} onPaths={() => go("paths")} onOpenResource={openResource} onOpenPath={openPath} />;

  return <div className="lx-root">
    <header className="lx-header">
      <div className="lx-brand"><span className="lx-brand-mark" aria-hidden="true">M</span><div className="lx-brand-copy"><strong>Marian Learning</strong><small>{profileReady ? accountLabel : "Your learner account"}</small></div></div>
      <div className="lx-header-actions">
        <div className="lx-accessibility" aria-label="Accessibility preferences">
          <button type="button" aria-pressed={highContrast} onClick={() => setHighContrast((value) => !value)}>Contrast</button>
          <button type="button" aria-pressed={reducedMotion} onClick={() => setReducedMotion((value) => !value)}>Reduce motion</button>
        </div>
        {profileReady && <div className="lx-language"><label htmlFor="lx-language-choice">Learning content language</label><select id="lx-language-choice" value={language} disabled={languageBusy} onChange={(event) => changeLanguage(event.target.value)}>
          {languageOptions.map((option) => <option key={option} value={option}>{languageLabel(option)}</option>)}
        </select></div>}
        <Button kind="secondary" onClick={out}>Sign out</Button>
      </div>
    </header>
    <nav className="lx-nav" aria-label="Learner navigation">
      {LEARNING_VIEWS.map((item) => <button type="button" key={item.id} aria-current={view === item.id ? "page" : undefined} onClick={() => go(item.id)}>{item.label}</button>)}
    </nav>
    <main className="lx-main">
      {languageError && <div className="lx-alert" role="alert">Learning content language was not changed: {languageError}</div>}
      {languageBusy && <p className="lx-small" role="status">Saving content language preference…</p>}
      {content}
    </main>
  </div>;
}
