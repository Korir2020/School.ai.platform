import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
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
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, sj, cl, cu] = await Promise.all(paths.map(get));
      const code = (c) => (cu.find((u) => u.id === c.curriculum) || {}).code || "";
      const lab = (c) => (code(c) + " " + (c.name || "")).trim();
      const level = (s) => cl.find((c) => c.id === s.class_level) || {};
      setX({ sj, cl: cl.map((c) => ({ id: c.id, label: lab(c) })),
        sm: sm.map((s) => ({ ...s, label: lab(level(s)) + " " + s.name })) });
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
