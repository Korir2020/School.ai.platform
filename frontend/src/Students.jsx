import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Card, StatCard, DataTable } from "./ui";
import { Loading, ErrorState } from "./ui";

const blank = (stream) => ({ first: "", last: "", adm: "", stream });
const paths = ["streams", "class-levels", "terms", "students"];

const cols = [
  { label: "Name", sort: true, get: (r) => r.first_name + " " + r.last_name },
  { label: "Admission no.", key: "admission_number", sort: true },
];

export default function Students({ d }) {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [f, setF] = useState(blank("")), [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [sm, cl, tm, st] = await Promise.all(paths.map(get));
      const lab = (s) => ((cl.find((c) => c.id === s.class_level) || {}).name || "")
        + " " + s.name;
      const term = tm.find((t) => t.id === d.active_term.id) || {};
      setX({ sm: sm.map((s) => ({ ...s, label: lab(s) })),
        year: term.academic_year, count: st.length, list: st });
      setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const add = async () => {
    setBusy(true);
    const r = await api("/api/students/", "POST", { first_name: f.first,
      last_name: f.last, admission_number: f.adm });
    const s = await r.json().catch(() => ({}));
    if (!r.ok) {
      setBusy(false);
      return toast("Failed: " + (s.detail || JSON.stringify(s)), "err");
    }
    const q = x.sm.find((z) => String(z.id) === f.stream);
    const e = await api("/api/enrollments/", "POST", { student: s.id,
      academic_year: x.year, class_level: q.class_level, stream: q.id,
      is_active: true });
    setBusy(false);
    if (e.ok) toast("Added " + f.first, "ok");
    else toast("Student saved but enrolment failed: "
      + JSON.stringify(await e.json().catch(() => ({}))), "err");
    setF(blank(f.stream)); load();
  };
  if (bad) return <ErrorState text="Could not load students." onRetry={load} />;
  if (!x) return <Loading />;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <div>
      <h2>Students</h2>
      <StatCard label="Total students" value={x.count} />
      <Card title="Add student">
        <Input id="st-first" label="First name" value={f.first} onChange={set("first")} />
        <Input id="st-last" label="Last name" value={f.last} onChange={set("last")} />
        <Input id="st-adm" label="Admission number" value={f.adm} onChange={set("adm")} />
        <Select id="st-stream" label="Class / stream" value={f.stream}
          onChange={set("stream")}>
          <option value="">Select...</option>
          {x.sm.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </Select>
        <Button kind="teal" busy={busy} onClick={add}
          disabled={!f.first || !f.last || !f.adm || !f.stream}>Add student</Button>
      </Card>
        <Card title="All students">
          <DataTable search="Search students" rows={x.list} cols={cols}
            empty="No students yet. Add the first one above." />
        </Card>
    </div>
  );
}
