import { useState } from "react";
import { api } from "./api";
import { Button, Card, Select, Badge, Alert } from "./ui";

const P = "/api/frameworks/";

async function errText(r) {
  try { const j = await r.json(); return j.message || j.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function FrameworkAdmin() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [ov, setOv] = useState(null);
  const [busy, setBusy] = useState("");
  const [key, setKey] = useState("");
  const [cur, setCur] = useState("");
  const [minL, setMinL] = useState("");
  const [maxL, setMaxL] = useState("");
  const [ver, setVer] = useState("");
  const [scope, setScope] = useState("");
  const [yr, setYr] = useState("");
  const [au, setAu] = useState("");
  const [ap, setAp] = useState("");

  const load = async () => {
    setBusy("ld");
    try {
      const r = await api(P);
      if (!r.ok) setMsg(await errText(r));
      else setOv(await r.json());
    } catch { setMsg("Could not load frameworks."); }
    setBusy("");
  };

  const makeVersion = async () => {
    setMsg("");
    if (!key || !cur || !minL || !maxL) { setMsg("Choose the framework, curriculum and level range first."); return; }
    setBusy("cv");
    try {
      const r = await api(P + "version/", "POST", { framework_key: key, curriculum_id: cur, min_level: minL, max_level: maxL });
      if (!r.ok) setMsg(await errText(r));
      else {
        const j = await r.json();
        setMsg("Saved " + j.framework_key + " version " + j.version + ". Now assign it below.");
        setVer(String(j.id));
        await load();
      }
    } catch { setMsg("Save failed."); }
    setBusy("");
  };

  const assignIt = async () => {
    setMsg("");
    if (!ver) { setMsg("Choose a saved version to assign."); return; }
    setBusy("as");
    try {
      const body = { version_id: ver, class_level_id: scope, year_id: yr };
      if (au.trim()) { body.approver_username = au.trim(); body.approver_password = ap; }
      const r = await api(P + "assign/", "POST", body);
      if (!r.ok) setMsg(await errText(r));
      else {
        const j = await r.json();
        setMsg("Assigned " + j.framework_key + " version " + j.version + (j.second_approval_used ? " with second approval." : "."));
        setAp("");
        await load();
      }
    } catch { setMsg("Assign failed."); }
    setBusy("");
  };

  const levels = ov ? ov.class_levels : [];
  const curs = [];
  levels.forEach((c) => {
    if (!curs.some((x) => x.id === c.curriculum_id)) curs.push({ id: c.curriculum_id, name: c.curriculum_name });
  });
  const nums = levels.filter((c) => String(c.curriculum_id) === cur).map((c) => c.level_number).sort((a, b) => a - b);
  const target = levels.find((c) => String(c.id) === scope);
  const fits = (v) => !target || (v.curriculum_id === target.curriculum_id
    && v.min_level <= target.level_number && target.level_number <= v.max_level);
  const usable = ov ? ov.versions.filter(fits) : [];
  const fwName = (k) => ((ov && ov.frameworks.find((f) => f.key === k)) || {}).name || k;
  const effOf = (c) => (ov.effective.find((e) => e.class_level_id === c.id) || {});
  const box = { width: "100%", padding: 8, boxSizing: "border-box" };

  return (
    <Card title="Admin: grading frameworks">
      <p><Button onClick={() => setOpen(!open)}>{open ? "Hide frameworks" : "Show frameworks"}</Button></p>
      {open && (
        <div>
          {msg && <Alert>{msg}</Alert>}
          <p>These rules are set by your school, not official KNEC rules.</p>
          {ov === null && <p><Button busy={busy === "ld"} onClick={load}>Load frameworks</Button></p>}
          {ov && (
            <div>
              <h4>In use now</h4>
              {levels.length === 0 && <p>No class levels found.</p>}
              {levels.map((c) => {
                const e = effOf(c);
                return (
                  <p key={c.id}>{c.curriculum_name} - {c.name}:{" "}
                    {e.framework_key
                      ? <Badge>{fwName(e.framework_key)} v{e.version}</Badge>
                      : <Badge kind="warn">Not configured</Badge>}
                  </p>
                );
              })}
              <h4>1. Save a framework version</h4>
              <p>A framework only applies to the curriculum and levels you choose. Saving never changes an old version; it makes a new one.</p>
              <Select id="fw-key" label="Framework" value={key} onChange={(e) => setKey(e.target.value)}>
                <option value="">Choose framework</option>
                {ov.frameworks.map((f) => <option key={f.key} value={f.key}>{f.name}</option>)}
              </Select>
              <Select id="fw-cur" label="Curriculum" value={cur} onChange={(e) => { setCur(e.target.value); setMinL(""); setMaxL(""); }}>
                <option value="">Choose curriculum</option>
                {curs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
              {cur && <Select id="fw-min" label="First level number" value={minL} onChange={(e) => setMinL(e.target.value)}>
                <option value="">Choose</option>
                {nums.map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>}
              {cur && <Select id="fw-max" label="Last level number" value={maxL} onChange={(e) => setMaxL(e.target.value)}>
                <option value="">Choose</option>
                {nums.map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>}
              <p><Button busy={busy === "cv"} onClick={makeVersion}>Save version</Button></p>
              <h4>2. Assign it</h4>
              <Select id="fw-scope" label="Applies to" value={scope} onChange={(e) => { setScope(e.target.value); setVer(""); }}>
                <option value="">Whole school (default)</option>
                {levels.map((c) => <option key={c.id} value={c.id}>Override: {c.curriculum_name} - {c.name}</option>)}
              </Select>
              <Select id="fw-year" label="Academic year" value={yr} onChange={(e) => setYr(e.target.value)}>
                <option value="">Every year</option>
                {ov.years.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
              </Select>
              <Select id="fw-ver" label={target ? "Saved version that fits this class level" : "Saved version"} value={ver} onChange={(e) => setVer(e.target.value)}>
                <option value="">Choose version</option>
                {usable.map((v) => (
                  <option key={v.id} value={v.id}>
                    {fwName(v.framework_key)} v{v.version} ({v.curriculum_name}, levels {v.min_level}-{v.max_level})
                  </option>
                ))}
              </Select>
              {target && usable.length === 0 && <p>No saved version fits this class level yet. Save one in step 1.</p>}
              {ov.published_results_exist && (
                <div>
                  <Alert>Published results exist. Published results are never recalculated, but a second administrator must confirm this change. They must be a different person from you.</Alert>
                  <p><input type="text" style={box} value={au} autoComplete="off" aria-label="Second administrator username"
                    placeholder="Second administrator username" onChange={(e) => setAu(e.target.value)} /></p>
                  <p><input type="password" style={box} value={ap} autoComplete="off" aria-label="Second administrator password"
                    placeholder="Second administrator password" onChange={(e) => setAp(e.target.value)} /></p>
                </div>
              )}
              <p><Button busy={busy === "as"} onClick={assignIt}>Assign framework</Button></p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
