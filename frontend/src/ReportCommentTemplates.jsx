import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Button, Card, Select, Alert, Loading } from "./ui";

const P = "/api/report-module/comment-templates/";
const FIELD_LABELS = {
  subject: "Subject comment",
  class_teacher: "Class-teacher comment",
  principal: "Headteacher / principal comment",
};
const PLACEHOLDER_HELP = "Available placeholders: {level}, {subject}, {scale}, {levels}, {stage}. Keep wording neutral and do not assert personal observations unless verified by the teacher.";

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function ReportCommentTemplates() {
  const [scales, setScales] = useState(null);
  const [scaleKey, setScaleKey] = useState("");
  const [draft, setDraft] = useState({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api(P).then(async (r) => {
      if (!live) return;
      if (!r.ok) { setMsg(await errText(r)); setScales([]); return; }
      const rows = (await r.json()).templates || [];
      if (!live) return;
      setScales(rows);
      if (rows.length) setScaleKey(rows[0].key);
    }).catch(() => { if (live) { setMsg("Could not load comment defaults."); setScales([]); } });
    return () => { live = false; };
  }, []);

  const selected = useMemo(() => (scales || []).find((row) => row.key === scaleKey) || null,
    [scales, scaleKey]);
  useEffect(() => { setDraft(selected ? selected.templates : {}); }, [selected]);

  const change = (entry, field, value) => setDraft((old) => ({
    ...old,
    [entry]: { ...(old[entry] || {}), [field]: value },
  }));

  const save = async () => {
    if (!selected) return;
    setMsg(""); setBusy(true);
    try {
      const r = await api(P, "PUT", { scale_key: selected.key, templates: draft });
      if (!r.ok) { setMsg(await errText(r)); }
      else {
        const result = (await r.json()).template;
        setScales((rows) => rows.map((row) => row.key === result.key ? result : row));
        setMsg("Comment defaults saved. They remain editable before approval.");
      }
    } catch { setMsg("Could not save comment defaults."); }
    setBusy(false);
  };

  return (
    <Card title="School comment defaults">
      <p>These editable starting points are tied to the selected school scale and describe recorded results, not personal observations. Subject feedback appears with the recorded school result; level-entry teachers can edit it before submitting the result for approval. Class-teacher and headteacher/principal wording is only a suggestion: an authorized staff member must save a learner-specific draft and an administrator must approve it before it prints.</p>
      {msg && <Alert>{msg}</Alert>}
      {scales === null && <Loading />}
      {scales && scales.length === 0 && <p>No grading or achievement scale is available yet. Configure a school scale first.</p>}
      {selected && (
        <div>
          <Select id="rct-scale" label="School scale" value={scaleKey} onChange={(e) => setScaleKey(e.target.value)}>
            {scales.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}
          </Select>
          <p><small>{PLACEHOLDER_HELP}</small></p>
          {selected.entries.map((entry) => (
            <section key={entry.key} style={{ borderTop: "1px solid rgba(128,128,128,.25)", paddingTop: 8, marginTop: 12 }}>
              <h4>{entry.label}</h4>
              {entry.fields.map((field) => (
                <label key={field} style={{ display: "block", margin: "10px 0", fontWeight: 600 }}>
                  {FIELD_LABELS[field] || field}
                  <textarea
                    aria-label={entry.label + " — " + (FIELD_LABELS[field] || field)}
                    value={(draft[entry.key] || {})[field] || ""}
                    onChange={(e) => change(entry.key, field, e.target.value)}
                    maxLength={400}
                    rows={3}
                    style={{ display: "block", width: "100%", boxSizing: "border-box", marginTop: 5, padding: 8 }}
                  />
                </label>
              ))}
            </section>
          ))}
          <p><Button kind="teal" busy={busy} onClick={save}>Save defaults</Button></p>
        </div>
      )}
    </Card>
  );
}
