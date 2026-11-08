import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Alert, Button, ErrorState, Input, Loading, Select } from "./ui";
import SetupSection from "./SetupSection";

const STEPS = [
  ["profile", "School profile", "setup-progress"],
  ["academic_year", "Academic year", "setup-terms"],
  ["term", "Term", "setup-add-term"],
  ["stream", "Class stream", "setup-classes"],
  ["subject", "Subject", "setup-classes"],
];
const TYPES = ["primary", "junior", "combined", "senior"];
const TYPE_ALIASES = { secondary: "senior", "secondary school": "senior", "senior school": "senior" };

export default function SetupWizard({ go }) {
  const toast = useToast();
  const [st, setSt] = useState(null);
  const [bad, setBad] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ location: "", county: "", school_type: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const load = async () => {
    try {
      const [s, p] = await Promise.all([api("/api/setup/"), api("/api/school/profile/")]);
      if (!s.ok || !p.ok) throw new Error("load");
      setSt(await s.json());
      const pj = await p.json();
      const raw = String(pj.school_type || "").trim().toLowerCase();
      const t = TYPE_ALIASES[raw] || raw;
      setF({ location: pj.location || "", county: pj.county || "", school_type: TYPES.includes(t) ? t : "" });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => {
    // This effect initiates async API reads; state updates happen after the requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    load();
  }, []);
  useEffect(() => {
    const h = () => load();
    window.addEventListener("marian:dashboard-refresh", h);
    return () => window.removeEventListener("marian:dashboard-refresh", h);
  }, []);

  const call = async (path, method, body) => {
    setErr(""); setBusy(true);
    const r = await api(path, method, body);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (!r.ok) setErr(j.errors ? Object.values(j.errors).join(" ") : (j.detail || "Could not save."));
    return r.ok;
  };
  const saveProfile = async () => {
    if (await call("/api/school/profile/", "PATCH", f)) { toast("Profile saved", "ok"); load(); }
  };
  const finish = async () => {
    if (await call("/api/setup/complete/", "POST", {})) { toast("Setup complete", "ok"); load(); }
  };

  if (bad) return <ErrorState text="Could not load setup." onRetry={load} />;
  if (!st) return <Loading />;
  const done = STEPS.filter(([k]) => st.checklist[k]).length;
  const pct = Math.round((done / STEPS.length) * 100);

  return (
    <SetupSection id="setup-progress" title="Setup progress" summary={`${done} of ${STEPS.length} complete · ${pct}%`} complete={done === STEPS.length}>
      <div className="s2-cols">
        <div className="s2-panel">
          <div className="s2-ph"><h4>Setup progress</h4><span className="s2-mut">{done} of {STEPS.length} · {pct}%</span></div>
          <div className="s2-prog"><i style={{ width: pct + "%" }} /></div>
          <ol className="s2-steps">
            {STEPS.map(([k, label, target], i) => (
              <li key={k} className={st.checklist[k] ? "ok" : ""}>
                <span className="s2-num">{st.checklist[k] ? "✓" : i + 1}</span>
                <b>{label}</b>
                {!st.checklist[k] && go && <button type="button" className="s2-chip" onClick={() => go(target)}>Go</button>}
              </li>
            ))}
          </ol>
          {st.setup_complete
            ? <Alert kind="ok">Setup is complete.</Alert>
            : <>
              <Button kind="teal" busy={busy} disabled={st.missing.length > 0} onClick={finish}>Finish setup</Button>
              {st.missing.length > 0 && <p className="s2-hint">Still missing: {st.missing.join(", ")}</p>}
            </>}
        </div>
        <div className="s2-panel">
          <h4>School profile</h4>
          <div className="s2-two">
            <Input label="Location" value={f.location} onChange={set("location")} />
            <Input label="County" value={f.county} onChange={set("county")} />
          </div>
          <Select label="School type" value={f.school_type} onChange={set("school_type")}>
            <option value="">Select school type...</option>
            <option value="primary">Primary school</option>
            <option value="junior">Junior school</option>
            <option value="combined">Combined (junior and primary)</option>
            <option value="senior">Senior school</option>
          </Select>
          {err && <Alert kind="err">{err}</Alert>}
          <Button kind="teal" busy={busy} onClick={saveProfile}>Save profile</Button>
        </div>
      </div>
    </SetupSection>
  );
}
