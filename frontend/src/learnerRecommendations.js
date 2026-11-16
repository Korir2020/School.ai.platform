export const RECOMMENDATION_FORMATS = [
  "lesson", "article", "video", "audio", "interactive", "worksheet", "external_link", "other",
];
export const RECOMMENDATION_DIFFICULTIES = ["", "beginner", "intermediate", "advanced"];
export const MAX_RECOMMENDATION_TOPICS = 10;

export function normalizeRecommendationPreferences(value) {
  const topicIds = Array.isArray(value?.topic_ids)
    ? [...new Set(value.topic_ids.filter((id) => Number.isSafeInteger(id) && id > 0))].slice(0, MAX_RECOMMENDATION_TOPICS)
    : [];
  const formats = Array.isArray(value?.preferred_formats)
    ? [...new Set(value.preferred_formats.filter((format) => RECOMMENDATION_FORMATS.includes(format)))]
    : [];
  const difficulty = RECOMMENDATION_DIFFICULTIES.includes(value?.preferred_difficulty)
    ? value.preferred_difficulty
    : "";
  return {
    topic_ids: topicIds,
    preferred_formats: formats,
    preferred_difficulty: difficulty,
    recommendations_enabled: value?.recommendations_enabled !== false,
  };
}

export function toggleRecommendationTopic(preferences, topicId) {
  if (!Number.isSafeInteger(topicId) || topicId <= 0) return preferences;
  const selected = new Set(preferences.topic_ids);
  if (selected.has(topicId)) selected.delete(topicId);
  else if (selected.size < MAX_RECOMMENDATION_TOPICS) selected.add(topicId);
  return { ...preferences, topic_ids: [...selected] };
}

export function toggleRecommendationFormat(preferences, format) {
  if (!RECOMMENDATION_FORMATS.includes(format)) return preferences;
  const selected = new Set(preferences.preferred_formats);
  if (selected.has(format)) selected.delete(format);
  else selected.add(format);
  return { ...preferences, preferred_formats: [...selected] };
}
