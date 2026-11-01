import { useState, useEffect } from "react";
import { api, listAll as list, upload } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, DataTable } from "./ui";
import { Loading, ErrorState } from "./ui";

const paths = ["streams", "subjects", "class-levels", "curriculums"];

export default function Setup() {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [lvl, setLvl] = useState(""), [sn, setSn] = useState("");
  const [bn, setBn] = useState(""), [bc, setBc] = useState("");
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState(null), [logo, setLogo] = useState(null);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, sj, cl, cu, br] = await Promise.all([...paths.map(get), api("/api/school/branding/")]);
      const code = (c) => (cu.find((u) => u.id === c.curriculum) || {}).code || "";
      const lab = (c) => (code(c) + " " + (c.name || "")).trim();
      const level = (s) => cl.find((c) => c.id === s.class_level) || {};
      setX({ sj, cl: cl.map((c) => ({ id: c.id, label: lab(c) })),
        sm: sm.map((s) => ({ ...s, label: lab(level(s)) + " " + s.name })) });
      if (br.ok) setBranding(await br.json());
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
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
  ];
  return (
    <div>
      <Card title="School identity">
        <p className="sub">Upload a PNG, JPG, JPEG, or WEBP logo up to 2 MB. It will appear on report cards and fee receipts.</p>
        {branding && <div className="branding-preview">{branding.logo_url ? <img src={branding.logo_url} alt={`${branding.name} logo`} /> : <span>No logo uploaded</span>}<b>{branding.name}</b></div>}
        <Input id="su-logo" label="School logo" type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setLogo(e.target.files[0] || null)} />
        <Button kind="teal" busy={busy} disabled={!logo} onClick={async () => { setBusy(true); const fd = new FormData(); fd.append("logo", logo); const r = await upload("/api/school/branding/", fd); setBusy(false); if (r.ok) { toast("Logo uploaded", "ok"); load(); setLogo(null); } else toast("Logo upload failed", "err"); }}>Upload logo</Button>
      </Card>
      <h2>Classes and subjects</h2>
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
      </Card>
      <Card title="Subjects">
        <DataTable cols={jcols} rows={x.sj} search="Search subjects"
          empty="No subjects yet" />
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
    </div>
  );
}
