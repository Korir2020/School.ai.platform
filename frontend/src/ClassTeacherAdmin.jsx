import { useState } from "react";
import { api } from "./api";
import { Button, Card, Select, Badge, Alert } from "./ui";

const P = "/api/records/class-teachers/";

async function errText(r) {
  try { const j = await r.json(); return j.message || j.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function ClassTeacherAdmin() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [data, setData] = useState(null);
  const [yr, setYr] = useState("");
  const [pick, setPick] = useState({});
  const [busy, setBusy] = useState("");

  const load = async () => {
    setBusy("ld");
    try {
      const r = await api(P);
      if (!r.ok) setMsg(await errText(r));
      else {
        const j = await r.json();
        setData(j);
        if (!yr && j.options.years.length) setYr(String(j.options.years[0].id));
      }
    } catch { setMsg("Could not load class teachers."); }
    setBusy("");
  };

  const save = async (sid) => {
    const tid = pick[sid];
    if (!yr || !tid) { setMsg("Choose the year and the teacher first."); return; }
    setMsg("");
    setBusy("s" + sid);
    try {
      const r = await api(P, "POST", { stream_id: sid, year_id: yr, teacher_id: tid });
      if (!r.ok) setMsg(await errText(r));
      else { setMsg("Saved."); setPick({ ...pick, [sid]: "" }); await load(); }
    } catch { setMsg("Save failed."); }
    setBusy("");
  };

  const current = (sid) => data.class_teachers.find(
    (c) => String(c.stream_id) === String(sid) && String(c.year_id) === yr);

  return (
    <Card title="Admin: class teachers">
      <p><Button onClick={() => setOpen(!open)}>{open ? "Hide class teachers" : "Show class teachers"}</Button></p>
      {open && (
        <div>
          {msg && <Alert>{msg}</Alert>}
          <p>The class teacher of a stream can open that stream's report cards after they are published.</p>
          {data === null && <p><Button busy={busy === "ld"} onClick={load}>Load class teachers</Button></p>}
          {data && (
            <div>
              <Select id="ct-year" label="Academic year" value={yr} onChange={(e) => setYr(e.target.value)}>
                <option value="">Choose year</option>
                {data.options.years.map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
              </Select>
              {data.options.streams.length === 0 && <p>No streams found.</p>}
              {data.options.streams.map((s) => {
                const cur = yr ? current(s.id) : null;
                return (
                  <Card key={s.id} title={s.name}>
                    <p>{cur ? <Badge>{cur.teacher_name}</Badge> : <Badge kind="warn">Not set</Badge>}</p>
                    <Select id={"ct-t-" + s.id} label="Class teacher" value={pick[s.id] || ""}
                      onChange={(e) => setPick({ ...pick, [s.id]: e.target.value })}>
                      <option value="">Choose teacher</option>
                      {data.options.teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </Select>
                    <p><Button busy={busy === "s" + s.id} onClick={() => save(s.id)}>Save class teacher</Button></p>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
