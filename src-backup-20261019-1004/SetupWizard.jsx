import { useState, useEffect } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card, ErrorState, Input, Loading, Select } from "./ui";

const STEPS = [
  ["profile", "School profile"],
  ["academic_year", "Academic year"],
  ["term", "Term"],
  ["stream", "Class stream"],
  ["subject", "Subject"],
];
const TYPES = ["primary", "junior", "secondary", "combined"];

export default function SetupWizard({ go }) {
  const toast = useToast();
  const [st, setSt] = useState(null);
  const [bad, setBad] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ location: "", county: "", school_type: "secondary" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const load = async () => {
    try {
      const [s, p] = await Promise.all([api("/api/setup/"), api("/api/school/profile/")]);
      if (!s.ok || !p.ok) throw new Error("load");
      setSt(await s.json());
      const pj = await p.json();
      const t = (pj.school_type || "").toLowerCase();
      setF({ location: pj.location || "", county: pj.county || "", school_type: TYPES.includes(t) ? t : "secondary" });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);

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

  return (
    <div>
      <Card title="Set up your school">
        {st.setup_complete
          ? <Alert kind="ok">Setup is complete.</Alert>
          : <Alert kind="info">Finish the steps below, then press Finish setup.</Alert>}
        {STEPS.map(([k, label]) => (
          <p key={k}>
            <Badge kind={st.checklist[k] ? "ok" : "warn"}>{st.checklist[k] ? "Done" : "To do"}</Badge> {label}
            {!st.checklist[k] && k !== "profile" && go && (
              <> <Button size="sm" kind="ghost" onClick={() => go("Setup")}>Open Setup</Button></>
            )}
          </p>
        ))}
      </Card>
      <Card title="School profile">
        <Input label="Location" value={f.location} onChange={set("location")} />
        <Input label="County" value={f.county} onChange={set("county")} />
        <Select label="School type" value={f.school_type} onChange={set("school_type")}>
          <option value="primary">Primary</option>
          <option value="junior">Junior school</option>
          <option value="secondary">Senior / Secondary</option>
          <option value="combined">Combined</option>
        </Select>
        {err && <Alert kind="err">{err}</Alert>}
        <Button kind="teal" busy={busy} onClick={saveProfile}>Save profile</Button>
      </Card>
      {!st.setup_complete && (
        <Card title="Finish">
          <Button kind="teal" busy={busy} disabled={st.missing.length > 0} onClick={finish}>Finish setup</Button>
          {st.missing.length > 0 && <p className="sub">Still missing: {st.missing.join(", ")}</p>}
        </Card>
      )}
    </div>
  );
}
