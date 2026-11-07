import { useState, useEffect } from "react";
import { api, listAll as list, upload } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, DataTable } from "./ui";
import { Loading, ErrorState } from "./ui";
import PaperSetup from "./PaperSetup";

const paths = ["streams", "subjects", "class-levels", "curriculums"];

export default function Setup() {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [lvl, setLvl] = useState(""), [sn, setSn] = useState("");
  const [bn, setBn] = useState(""), [bc, setBc] = useState("");
  const [subjectLevel, setSubjectLevel] = useState("");
  const [primaryDefs, setPrimaryDefs] = useState([]);
  const [definitionId, setDefinitionId] = useState("");
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState(null), [logo, setLogo] = useState(null);
  const [idt, setIdt] = useState({});
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, sj, cl, cu, br] = await Promise.all([...paths.map(get), api("/api/school/branding/")]);
      const code = (c) => (cu.find((u) => u.id === c.curriculum) || {}).code || "";
      const lab = (c) => (code(c) + " " + (c.name || "")).trim();
      const level = (s) => cl.find((c) => c.id === s.class_level) || {};
      setX({ sj, cl: cl.map((c) => ({ ...c, curriculum_code: code(c.curriculum), label: lab(c) })),
        sm: sm.map((s) => ({ ...s, label: lab(level(s)) + " " + s.name })) });
      if (br.ok) setBranding(await br.json());
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let live = true;
    const selected = x && x.cl.find((row) => String(row.id) === String(subjectLevel));
    if (!selected || selected.curriculum_code !== "CBC" || selected.level_number < 1 || selected.level_number > 6) {
      setPrimaryDefs([]); setDefinitionId("");
      return undefined;
    }
    api("/api/subject-definitions/primary/?class_level=" + selected.id)
      .then(async (r) => {
        if (!r.ok) throw new Error("Could not load CBC Primary learning areas.");
        const rows = await r.json();
        if (live) setPrimaryDefs(rows);
      }).catch(() => { if (live) setPrimaryDefs([]); });
    return () => { live = false; };
  }, [x, subjectLevel]);
  const post = async (path, body, ok) => {
    setBusy(true);
    const r = await api(path, "POST", body);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) { toast(ok, "ok"); load(); }
    else toast("Failed: " + (j.detail || JSON.stringify(j)), "err");
    return r.ok;
  };
  if (bad) return <ErrorState text="Could not load setup." onRetry={load} />;
  if (!x) return <Loading />;
  const scols = [{ label: "Class / stream", key: "label", sort: true }];
  const jcols = [
    { label: "Subject", key: "name", sort: true },
    { label: "Code", key: "code", sort: true },
    { label: "Curriculum learning area", key: "definition_name", render: (row) => row.definition_name || "School-created" },
  ];
  const saveIdentity = async () => {
    setBusy(true);
    const fd = new FormData();
    Object.entries(idt).forEach(([k, v]) => fd.append(k, v));
    const r = await upload("/api/school/branding/", fd);
    setBusy(false);
    if (r.ok) { setIdt({}); toast("Saved", "ok"); load(); }
    else { const j = await r.json().catch(() => ({})); toast(j.detail || "Not saved", "err"); }
  };
  return (
    <div className="s2-wrap">
      <section className="s2-sec" id="setup-identity"><div className="s2-sh"><div><h3>School identity</h3><p>Shown on report cards and fee receipts.</p></div></div><div className="s2-panel s2-ident"><div>
        <Input id="su-motto" label="School motto" value={idt.motto ?? (branding && branding.motto) ?? ""} onChange={(e) => setIdt({ ...idt, motto: e.target.value })} />
        <Input id="su-principal" label="Principal's name" value={idt.principal_name ?? (branding && branding.principal_name) ?? ""} onChange={(e) => setIdt({ ...idt, principal_name: e.target.value })} />
        <p><Button kind="teal" busy={busy} disabled={busy || !Object.keys(idt).length} onClick={saveIdentity}>Save motto and principal</Button></p>
        </div><div>
        <p className="sub">Upload a PNG, JPG, JPEG, or WEBP logo up to 2 MB. It will appear on report cards and fee receipts.</p>
        {branding && <div className="branding-preview">{branding.logo_url ? <img src={branding.logo_url} alt={`${branding.name} logo`} /> : <span>No logo uploaded</span>}<b>{branding.name}</b></div>}
        <Input id="su-logo" label="School logo" type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setLogo(e.target.files[0] || null)} />
        <Button kind="teal" busy={busy} disabled={!logo} onClick={async () => { setBusy(true); const fd = new FormData(); fd.append("logo", logo); const r = await upload("/api/school/branding/", fd); setBusy(false); if (r.ok) { toast("Logo uploaded", "ok"); load(); setLogo(null); } else toast("Logo upload failed", "err"); }}>Upload logo</Button>
      </div></div></section>
      <section className="s2-sec" id="setup-classes"><div className="s2-sh"><div><h3>Classes and subjects</h3><p>{x.sm.length} streams · {x.sj.length} subjects</p></div></div>
      <div className="s2-cols even"><div className="s2-stack">
      <Card title="Streams">
        <DataTable cols={scols} rows={x.sm} search="Search streams"
          empty="No streams yet" />
      </Card>
      <Card title="Add stream">
        <Select id="su-lvl" label="Class level" value={lvl}
          onChange={(e) => setLvl(e.target.value)}>
          <option value="">Select...</option>
          {x.cl.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
        </Select>
        <Input id="su-sn" label="Stream name" value={sn}
          onChange={(e) => setSn(e.target.value)} />
        <Button kind="teal" busy={busy} disabled={!lvl || !sn}
          onClick={async () => {
            const b = { class_level: lvl, name: sn, is_active: true };
            if (await post("/api/streams/", b, "Stream added")) setSn("");
          }}>Add stream</Button>
      </Card></div><div className="s2-stack">
      <Card title="Subjects">
        <DataTable cols={jcols} rows={x.sj} search="Search subjects"
          empty="No subjects yet" />
      </Card>
      <Card title="Add CBC Primary learning area by grade">
        <p>Select a grade and a school-curriculum learning-area definition. The grade-specific subject record lets paper maxima and weights be set separately for each grade.</p>
        <Select id="su-primary-grade" label="CBC Primary grade" value={subjectLevel}
          onChange={(e) => { setSubjectLevel(e.target.value); setDefinitionId(""); }}>
          <option value="">Choose Grade 1–6</option>
          {x.cl.filter((c) => c.curriculum_code === "CBC" && c.level_number >= 1 && c.level_number <= 6)
            .map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        {subjectLevel && <Select id="su-primary-definition" label="Learning area" value={definitionId}
          onChange={(e) => {
            const item = primaryDefs.find((row) => String(row.id) === e.target.value);
            setDefinitionId(e.target.value);
            if (item) {
              const level = x.cl.find((row) => String(row.id) === String(subjectLevel));
              setBn(`${item.name} — ${level.name}`);
              setBc(`${item.code}-G${level.level_number}`.slice(0, 20));
            }
          }}>
          <option value="">Choose learning area</option>
          {primaryDefs.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>}
        {subjectLevel && primaryDefs.length === 0 && <p>No catalogued learning areas were found for this grade.</p>}
        {subjectLevel && definitionId && <>
          <Input id="su-primary-name" label="Grade-specific subject name" value={bn} onChange={(e) => setBn(e.target.value)} />
          <Input id="su-primary-code" label="Grade-specific subject code" value={bc} onChange={(e) => setBc(e.target.value)} />
          <Button kind="teal" busy={busy} disabled={!bn || !bc || x.sj.some((s) => s.definition === Number(definitionId) && s.code === bc)}
            onClick={async () => {
              const b = { name: bn, code: bc, definition: Number(definitionId), is_active: true };
              if (await post("/api/subjects/", b, "CBC Primary learning area added")) {
                setBn(""); setBc(""); setDefinitionId("");
              }
            }}>Add learning area for this grade</Button>
        </>}
      </Card>
      <Card title="Add subject">
        <Input id="su-bn" label="Subject name" value={bn}
          onChange={(e) => setBn(e.target.value)} />
        <Input id="su-bc" label="Code" value={bc}
          onChange={(e) => setBc(e.target.value)} />
        <Button kind="teal" busy={busy} disabled={!bn || !bc}
          onClick={async () => {
            const b = { name: bn, code: bc, is_active: true };
            if (await post("/api/subjects/", b, "Subject added")) {
              setBn(""); setBc("");
            }
          }}>Add subject</Button>
      </Card>
      </div></div></section>
      <section className="s2-sec" id="setup-papers"><PaperSetup /></section>
    </div>
  );
}
