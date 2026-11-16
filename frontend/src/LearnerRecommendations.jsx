import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Button, ErrorState, Loading } from "./ui";
import {
  normalizeRecommendationPreferences,
  toggleRecommendationFormat,
  toggleRecommendationTopic,
} from "./learnerRecommendations";

const BASE = "/api/learning/v1/";
const FORMATS = [
  ["lesson", "Lesson"], ["article", "Article"], ["video", "Video"],
  ["audio", "Audio"], ["interactive", "Interactive"], ["worksheet", "Worksheet"],
  ["external_link", "External link"], ["other", "Other"],
];
const DIFFICULTIES = [["", "Any level"], ["beginner", "Beginner"], ["intermediate", "Intermediate"], ["advanced", "Advanced"]];
const COPY = {
  en: {
    eyebrow: "Personalized suggestions", title: "Recommended for you",
    intro: "Suggestions use your chosen interests, goals, preferences, and recent learning activity. You can change the inputs, pause personalized suggestions, or dismiss any item.",
    settings: "Tune your suggestions", settingsHelp: "Your choices stay on your learning profile. They are not used to infer academic ability.",
    topics: "Topics I’m interested in", formats: "Formats I prefer", difficulty: "Preferred difficulty",
    enabled: "Use my learning preferences for personalized suggestions",
    save: "Save preferences", refresh: "Refresh suggestions", saving: "Saving…", refreshing: "Refreshing…",
    allTopics: "No topics are available for this account right now.", topicLimit: "Select up to 10 topics.",
    starter: "A starting point", personalized: "Personalized", teacher: "Teacher suggestion",
    keep: "Keep suggestion", dismiss: "Dismiss", openResource: "Open resource", openPath: "Open programme",
    saved: "Added to your learning suggestions.", dismissed: "Recommendation dismissed.", savedPrefs: "Your recommendation preferences were saved.", refreshed: "Your suggestions are up to date.",
    paused: "Personalized suggestions are paused. Teacher-selected suggestions, if any, remain visible.",
    empty: "No recommendations yet", emptyText: "As reviewed learning content becomes available, suitable suggestions will appear here.",
    loading: "Loading preferences and suggestions…", error: "Unable to load recommendations.",
    catalogTruncated: "Showing the first 200 available topics. Use search in Discover to browse more content.",
    enFormat: "English", swFormat: "Kiswahili",
  },
  sw: {
    eyebrow: "Mapendekezo binafsi", title: "Yaliyopendekezwa kwako",
    intro: "Mapendekezo hutumia mada, malengo, mapendeleo na shughuli zako za hivi karibuni za kujifunza. Unaweza kubadilisha mapendeleo, kusitisha mapendekezo binafsi au kuondoa kipengee chochote.",
    settings: "Rekebisha mapendekezo yako", settingsHelp: "Chaguo zako huhifadhiwa kwenye wasifu wako wa kujifunza. Hazitumiki kukisia uwezo wako wa kitaaluma.",
    topics: "Mada ninazopenda", formats: "Aina za nyenzo ninazopendelea", difficulty: "Kiwango cha ugumu ninachopendelea",
    enabled: "Tumia mapendeleo yangu ya kujifunza kwa mapendekezo binafsi",
    save: "Hifadhi mapendeleo", refresh: "Onyesha mapendekezo upya", saving: "Inahifadhi…", refreshing: "Inasasisha…",
    allTopics: "Hakuna mada zinazopatikana kwa akaunti hii kwa sasa.", topicLimit: "Chagua hadi mada 10.",
    starter: "Mwanzo mzuri", personalized: "Binafsi", teacher: "Pendekezo la mwalimu",
    keep: "Hifadhi pendekezo", dismiss: "Ondoa", openResource: "Fungua nyenzo", openPath: "Fungua programu",
    saved: "Limeongezwa kwenye mapendekezo yako ya kujifunza.", dismissed: "Pendekezo limeondolewa.", savedPrefs: "Mapendeleo ya mapendekezo yamehifadhiwa.", refreshed: "Mapendekezo yako yamesasishwa.",
    paused: "Mapendekezo binafsi yamesitishwa. Mapendekezo ya walimu, ikiwa yapo, yataendelea kuonekana.",
    empty: "Bado hakuna mapendekezo", emptyText: "Mapendekezo yanayofaa yataonekana hapa kadiri nyenzo za kujifunza zilizoidhinishwa zinavyopatikana.",
    loading: "Inapakia mapendeleo na mapendekezo…", error: "Imeshindikana kupakia mapendekezo.",
    catalogTruncated: "Inaonyesha mada 200 za kwanza zinazopatikana. Tumia utafutaji kwenye Gundua kuona nyenzo zaidi.",
    enFormat: "Kiingereza", swFormat: "Kiswahili",
  },
};

function copyFor(language) {
  return COPY[(language || "en").toLowerCase().split("-")[0]] || COPY.en;
}

async function request(path, method = "GET", body) {
  const response = await api(`${BASE}${path}`, method, body);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.detail || payload?.code?.replaceAll("_", " ") || COPY.en.error);
  return payload;
}

export default function LearnerRecommendations({ language, onOpenResource, onOpenPath }) {
  const copy = copyFor(language);
  const [rows, setRows] = useState([]);
  const [topics, setTopics] = useState([]);
  const [preferences, setPreferences] = useState(normalizeRecommendationPreferences(null));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [preferenceError, setPreferenceError] = useState("");
  const [busy, setBusy] = useState(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [catalogTruncated, setCatalogTruncated] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(""); setPreferenceError("");
    try {
      const [profilePayload, topicPayload] = await Promise.all([
        request("me/"),
        request(`catalog/topics/?lang=${encodeURIComponent(language || "en")}`),
      ]);
      const currentPreferences = normalizeRecommendationPreferences(profilePayload.preferences);
      setPreferences(currentPreferences);
      setTopics(Array.isArray(topicPayload.results) ? topicPayload.results : []);
      setCatalogTruncated(Boolean(topicPayload.truncated));
      await request(`recommendations/generate/?lang=${encodeURIComponent(language || "en")}`, "POST", {});
      const recommendationPayload = await request(`recommendations/?lang=${encodeURIComponent(language || "en")}`);
      setRows(Array.isArray(recommendationPayload.results) ? recommendationPayload.results : []);
    } catch (err) {
      setError(err.message || copy.error);
      try {
        const existing = await request(`recommendations/?lang=${encodeURIComponent(language || "en")}`);
        setRows(Array.isArray(existing.results) ? existing.results : []);
      } catch { /* Keep the primary error visible. */ }
    } finally { setLoading(false); }
  }, [language, copy.error]);

  useEffect(() => {
    const id = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(id);
  }, [load]);

  async function savePreferences() {
    setSaving(true); setPreferenceError(""); setNotice("");
    try {
      const payload = await request("me/", "PATCH", {
        preferences: {
          topic_ids: preferences.topic_ids,
          preferred_formats: preferences.preferred_formats,
          preferred_difficulty: preferences.preferred_difficulty,
          recommendations_enabled: preferences.recommendations_enabled,
        },
      });
      setPreferences(normalizeRecommendationPreferences(payload.preferences));
      setNotice(copy.savedPrefs);
      await load();
    } catch (err) { setPreferenceError(err.message); }
    finally { setSaving(false); }
  }

  function toggleTopic(id) {
    setPreferences((current) => toggleRecommendationTopic(current, id));
  }

  function toggleFormat(format) {
    setPreferences((current) => toggleRecommendationFormat(current, format));
  }

  async function respond(row, state) {
    setBusy(row.id); setError(""); setNotice("");
    try {
      const updated = await request(`recommendations/${row.id}/response/`, "POST", { state });
      if (state === "dismissed") setRows((current) => current.filter((item) => item.id !== row.id));
      else setRows((current) => current.map((item) => item.id === row.id ? { ...item, state: updated.state } : item));
      setNotice(state === "accepted" ? copy.saved : copy.dismissed);
    } catch (err) { setError(err.message || copy.error); }
    finally { setBusy(null); }
  }

  async function refreshRecommendations() {
    setBusy("refresh"); setError(""); setNotice("");
    try {
      const generated = await request(`recommendations/generate/?lang=${encodeURIComponent(language || "en")}`, "POST", {});
      const current = await request(`recommendations/?lang=${encodeURIComponent(language || "en")}`);
      setRows(Array.isArray(current.results) ? current.results : []);
      setNotice(generated.enabled ? copy.refreshed : copy.paused);
    } catch (err) { setError(err.message || copy.error); }
    finally { setBusy(null); }
  }

  return <div className="lx-page">
    <div className="lx-title-row"><div><p className="lx-eyebrow">{copy.eyebrow}</p><h1>{copy.title}</h1><p className="lx-lede">{copy.intro}</p></div></div>
    {notice && <div className="lx-notice" role="status">{notice}</div>}
    {preferenceError && <div className="lx-alert" role="alert">{preferenceError}</div>}
    <section className="lx-panel lx-recommendation-preferences" aria-labelledby="lx-recommendation-preferences-title">
      <div className="lx-panel-heading"><div><h2 id="lx-recommendation-preferences-title">{copy.settings}</h2><p className="lx-small">{copy.settingsHelp}</p></div></div>
      <label className="lx-recommendation-optout"><input type="checkbox" checked={preferences.recommendations_enabled} onChange={(event) => setPreferences((current) => ({ ...current, recommendations_enabled: event.target.checked }))} /> <span>{copy.enabled}</span></label>
      <fieldset className="lx-preference-group"><legend>{copy.topics}</legend><p className="lx-small">{copy.topicLimit}</p>
        {topics.length ? <div className="lx-recommendation-topic-list">{topics.map((topic) => <label className="lx-recommendation-choice" key={topic.id}>
          <input type="checkbox" checked={preferences.topic_ids.includes(topic.id)} disabled={!preferences.topic_ids.includes(topic.id) && preferences.topic_ids.length >= 10} onChange={() => toggleTopic(topic.id)} />
          <span>{topic.name}</span>
        </label>)}</div> : <p className="lx-small">{copy.allTopics}</p>}
        {catalogTruncated && <p className="lx-small" role="note">{copy.catalogTruncated}</p>}
      </fieldset>
      <fieldset className="lx-preference-group"><legend>{copy.formats}</legend><div className="lx-recommendation-format-list">{FORMATS.map(([value, label]) => <label className="lx-recommendation-choice" key={value}>
        <input type="checkbox" checked={preferences.preferred_formats.includes(value)} onChange={() => toggleFormat(value)} /> <span>{label}</span>
      </label>)}</div></fieldset>
      <label className="lx-recommendation-difficulty">{copy.difficulty}<select value={preferences.preferred_difficulty} onChange={(event) => setPreferences((current) => ({ ...current, preferred_difficulty: event.target.value }))}>
        {DIFFICULTIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <div className="lx-actions"><Button kind="teal" busy={saving} onClick={savePreferences}>{saving ? copy.saving : copy.save}</Button></div>
    </section>
    <div className="lx-actions"><Button kind="secondary" busy={busy === "refresh"} onClick={refreshRecommendations}>{busy === "refresh" ? copy.refreshing : copy.refresh}</Button></div>
    {error && <ErrorState text={error} onRetry={load} />}
    {loading && <Loading />}
    {!loading && !error && (rows.length ? <div className="lx-card-list">{rows.map((row) => {
      const item = row.item || {};
      const isPath = row.type === "path";
      const isTeacher = row.recommendation_type === "teacher" || row.reason_code === "teacher_selected";
      return <article className="lx-card" key={row.id}>
        <div className="lx-card-top"><div><p className="lx-eyebrow">{isTeacher ? copy.teacher : copy.personalized}</p><h3>{item.title}</h3></div><span className="lx-chip">{row.state === "accepted" ? copy.saved : isTeacher ? copy.teacher : copy.personalized}</span></div>
        <p>{row.explanation || item.summary || item.description || copy.starter}</p>
        <div className="lx-chip-row"><span className="lx-chip">{item.difficulty || "Any level"}</span><span className="lx-chip">{item.display_language || item.language_code || language}</span></div>
        <div className="lx-actions">
          <Button kind="teal" onClick={() => isPath ? onOpenPath(item.id) : onOpenResource(item.id)}>{isPath ? copy.openPath : copy.openResource}</Button>
          {row.state !== "accepted" && <Button kind="secondary" busy={busy === row.id} onClick={() => respond(row, "accepted")}>{copy.keep}</Button>}
          <Button kind="secondary" busy={busy === row.id} onClick={() => respond(row, "dismissed")}>{copy.dismiss}</Button>
        </div>
      </article>;
    })}</div> : <div className="lx-empty"><strong>{preferences.recommendations_enabled ? copy.empty : copy.paused}</strong><span>{preferences.recommendations_enabled ? copy.emptyText : copy.paused}</span></div>)}
  </div>;
}
