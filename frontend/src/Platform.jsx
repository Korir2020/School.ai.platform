import { useState } from "react";
import { api } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Card, DataTable, Alert, StatCard } from "./ui";
import { Dialog } from "./kit";

const blank = { name: "", code: "", admin_username: "", admin_password: "",
  admin_first_name: "", admin_last_name: "" };
const labels = { name: "School name", code: "School code",
  admin_username: "Admin username", admin_password: "Admin password",
  admin_first_name: "Admin first name", admin_last_name: "Admin last name" };

export default function Platform({ d }) {
  const toast = useToast();
  const [f, setF] = useState(blank), [made, setMade] = useState([]);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState(null);
  const add = async () => {
    setBusy(true);
    const r = await api("/api/schools/", "POST", f);
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) {
      toast("School created: " + j.name, "ok");
      setMade([...made, j]); setF(blank);
    } else toast("Failed: " + (j.detail || JSON.stringify(j)), "err");
  };
  const scols = [
    { label: "School", key: "name", sort: true },
    { label: "Students", key: "students", sort: true },
    { label: "Teachers", key: "teachers", sort: true },
    { label: "Profile", render: (r) => <Button kind="secondary" size="sm" onClick={() => setPick(r)}>View</Button> },
  ];
  const mcols = [
    { label: "New school", key: "name" },
    { label: "Admin username", key: "admin_username" },
  ];
  return (
    <div>
      <h2>Schools</h2>
      <StatCard label="Registered schools" value={(d.schools || []).length} />
      <StatCard label="Students on the platform" value={(d.schools || []).reduce((a, s) => a + (Number(s.students) || 0), 0)} />
      <StatCard label="Teachers on the platform" value={(d.schools || []).reduce((a, s) => a + (Number(s.teachers) || 0), 0)} />
      <Card>
        <DataTable cols={scols} rows={d.schools || []} search="Search schools"
          empty="No schools yet" />
      </Card>
      {made.length > 0 && <Card title="Created in this session">
        <DataTable cols={mcols} rows={made} />
      </Card>}
      <Dialog open={!!pick} title={pick ? pick.name : ""} onClose={() => setPick(null)}
        footer={<Button kind="secondary" onClick={() => setPick(null)}>Close</Button>}>
        {pick && <div>
          <p>Students enrolled: <b>{pick.students}</b></p>
          <p>Teachers: <b>{pick.teachers}</b></p>
          <p className="sub">Platform-level counts only. Each school's student and teacher records stay private to that school.</p>
        </div>}
      </Dialog>
      <Card title="Create school">
        <Alert kind="info">
          Create a school and its first administrator, then give that person
          the login.</Alert>
        {Object.keys(blank).map((k) => (
          <Input key={k} id={"pl-" + k} label={labels[k]}
            type={k === "admin_password" ? "password" : "text"} value={f[k]}
            onChange={(e) => setF({ ...f, [k]: e.target.value })} />
        ))}
        <Button kind="teal" busy={busy} onClick={add}
          disabled={!f.name || !f.code || !f.admin_username
            || !f.admin_password}>Create school</Button>
      </Card>
    </div>
  );
}
