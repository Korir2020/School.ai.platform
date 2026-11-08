import { useEffect, useState } from "react";
import { api } from "./api";
import { Button, Card, Input, Select, Alert, Loading } from "./ui";

const blank = (n) => ({ key: `senior_level_${n}`, label: "", description: "" });

export default function SeniorAchievementSettings() {
  const [meta, setMeta] = useState(null);
  const [scales, setScales] = useState([]);
  const [curriculum, setCurriculum] = useState("");
  const [minLevel, setMinLevel] = useState("10");
  const [maxLevel, setMaxLevel] = useState("12");
  const [levels, setLevels] = useState([blank(1), blank(2), blank(3), blank(4)]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      const [frameworkResponse, scaleResponse] = await Promise.all([
        api("/api/frameworks/"), api("/api/levels/scales/"),
      ]);
      if (!frameworkResponse.ok || !scaleResponse.ok) throw new Error("Could not load Senior settings.");
      const [frameworks, saved] = await Promise.all([frameworkResponse.json(), scaleResponse.json()]);
      const senior = frameworks.class_levels.filter((row) =>
        row.curriculum_code === "CBC" && row.level_number >= 10 && row.level_number <= 12);
      const curriculumRows = [...new Map(senior.map((row) => [String(row.curriculum_id), {
        id: row.curriculum_id, name: row.curriculum_name,
      }])).values()];
      setMeta({ senior, curricula: curriculumRows });
      setScales((saved.scales || []).filter((scale) => curriculumRows.some((c) => c.id === scale.curriculum_id)
        && scale.min_level >= 10 && scale.max_level <= 12));
      if (!curriculum && curriculumRows.length) setCurriculum(String(curriculumRows[0].id));
    } catch (e) { setError(e.message || "Could not load Senior settings."); }
  };

  useEffect(() => { if (open && !meta) load(); }, [open]);

  const changeLevel = (index, key, value) => setLevels((rows) => rows.map((row, i) =>
    i === index ? { ...row, [key]: value } : row));

  const save = async () => {
    const keys = levels.map((row) => row.key.trim().toLowerCase());
    const labels = levels.map((row) => row.label.trim().toLowerCase());
    if (!curriculum) return setError("No CBC Senior curriculum is available. Load the school curriculum catalogue first.");
    if (levels.length < 2 || levels.some((row) => !row.key.trim() || !row.label.trim())) {
      return setError("Enter a distinct key and a school-defined label for at least two achievement levels.");
    }
    if (new Set(keys).size !== keys.length || new Set(labels).size !== labels.length) {
      return setError("Achievement level keys and labels must each be unique.");
    }
    const lo = Number(minLevel), hi = Number(maxLevel);
    if (!Number.isInteger(lo) || !Number.isInteger(hi) || lo < 10 || hi > 12 || lo > hi) {
      return setError("Choose a valid Grade 10–12 range.");
    }
    setError(""); setBusy(true);
    try {
      const response = await api("/api/levels/scales/", "POST", {
        curriculum_id: Number(curriculum), min_level: lo, max_level: hi,
        levels: levels.map((row) => ({ key: row.key.trim().toLowerCase(),
          label: row.label.trim(), description: row.description.trim() })),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.message || body.detail || "Could not save Senior achievement descriptors.");
      }
      setLevels([blank(1), blank(2), blank(3), blank(4)]);
      await load();
    } catch (e) { setError(e.message || "Could not save Senior achievement descriptors."); }
    setBusy(false);
  };

  return (
    <Card title="CBC Senior achievement descriptors">
      <p>Configure school-authored achievement-level names and explanations for Grades 10–12. Marian supplies no national percentage thresholds or official KNEC descriptors.</p>
      <p><Button kind="ghost" onClick={() => { const next = !open; setOpen(next); if (next && !meta) load(); }}>{open ? "Hide Senior settings" : "Configure Senior descriptors"}</Button></p>
      {open && !meta && !error && <Loading />}
      {open && error && <Alert>{error}</Alert>}
      {open && meta && (
        <div>
          {meta.curricula.length === 0 ? <p>No CBC Grade 10–12 class levels were found.</p> : <>
            <Select id="senior-cur" label="Curriculum" value={curriculum} onChange={(e) => setCurriculum(e.target.value)}>
              {meta.curricula.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
            <Select id="senior-min" label="From grade number" value={minLevel} onChange={(e) => setMinLevel(e.target.value)}>
              {[10, 11, 12].map((n) => <option key={n} value={n}>Grade {n}</option>)}
            </Select>
            <Select id="senior-max" label="Through grade number" value={maxLevel} onChange={(e) => setMaxLevel(e.target.value)}>
              {[10, 11, 12].map((n) => <option key={n} value={n}>Grade {n}</option>)}
            </Select>
            <p>Use wording adopted by your school; do not treat these as KNEC labels.</p>
            {levels.map((row, i) => <div key={i}>
              <Input id={`senior-key-${i}`} label={`Internal key ${i + 1}`} value={row.key} onChange={(e) => changeLevel(i, "key", e.target.value)} />
              <Input id={`senior-label-${i}`} label={`School achievement label ${i + 1}`} value={row.label} onChange={(e) => changeLevel(i, "label", e.target.value)} />
              <Input id={`senior-desc-${i}`} label={`School descriptor ${i + 1}`} value={row.description} onChange={(e) => changeLevel(i, "description", e.target.value)} />
              {levels.length > 2 && <p><Button kind="ghost" size="sm" onClick={() => setLevels((rows) => rows.filter((_, j) => j !== i))}>Remove level</Button></p>}
            </div>)}
            {levels.length < 10 && <p><Button kind="ghost" onClick={() => setLevels((rows) => [...rows, blank(rows.length + 1)])}>Add achievement level</Button></p>}
            <p><Button kind="teal" busy={busy} onClick={save}>Save new Senior descriptor version</Button></p>
            <hr />
            <h4>Saved Senior scales</h4>
            {scales.length === 0 ? <p>No Senior descriptor scales saved yet.</p> : scales.map((scale) => (
              <p key={scale.id}><b>Grades {scale.min_level}–{scale.max_level}, version {scale.version}:</b>{" "}
                {scale.levels.map((item) => item.label).join(" · ")}</p>
            ))}
          </>}
        </div>
      )}
    </Card>
  );
}
