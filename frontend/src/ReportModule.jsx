import { useState, useEffect } from "react";
import { api } from "./api";
import { Button, Card, Select, Badge, Alert, EmptyState, Loading, ErrorState } from "./ui";
import GradingScale from "./GradingScale";
import ReportInsights from "./ReportInsights";
import ReportComments from "./ReportComments";
import ReportAdmin from "./ReportAdmin";
import FrameworkAdmin from "./FrameworkAdmin";
import ClassTeacherAdmin from "./ClassTeacherAdmin";

const P = "/api/report-module/";

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

export default function ReportModule() {
  const [meta, setMeta] = useState(null);
  const [bad, setBad] = useState("");
  const [needScale, setNeedScale] = useState(false);
  const [tries, setTries] = useState(0);
  const [exam, setExam] = useState("");
  const [cls, setCls] = useState("");
  const [stream, setStream] = useState("");
  const [prov, setProv] = useState(false);
  const [sel, setSel] = useState(null);
  const [msg, setMsg] = useState("");
  const [busyId, setBusyId] = useState("");
  const [bulk, setBulk] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [brand, setBrand] = useState(null);
  const [skip, setSkip] = useState(false);
  useEffect(() => {
    api("/api/school/branding/").then(async (r) => { if (r.ok) setBrand(await r.json()); }).catch(() => {});
  }, []);
  const warn = brand ? [
    !brand.logo_url && "school logo",
    !brand.motto && "school motto",
    !brand.principal_name && "principal's name",
  ].filter(Boolean) : [];

  useEffect(() => {
    api(P + "meta/").then(async (r) => {
      if (!r.ok) {
        let d = null;
        try { d = await r.clone().json(); } catch { d = null; }
        if (d && d.error === "no_grading_scale") return setNeedScale(true);
        return setBad(await errText(r));
      }
      setMeta(await r.json());
    }).catch(() => setBad("Could not reach the server."));
  }, [tries]);

  const qs = (extra) => {
    const q = new URLSearchParams({ exam_id: exam, ...extra });
    if (prov) q.set("provisional", "1");
    return q.toString();
  };

  const check = async () => {
    setMsg(""); setSel(null);
    const extra = { class_name: cls };
    if (stream) extra.stream = stream;
    const r = await api(P + "selection/?" + qs(extra));
    if (!r.ok) return setMsg(await errText(r));
    setSel(await r.json());
  };

  const download = async (s) => {
    setMsg(""); setBusyId(s.id);
    try {
      const r = await api(P + "student/" + s.id + "/pdf/?" + qs({ download: "1" }));
      if (!r.ok) { setMsg(await errText(r)); }
      else {
        const url = URL.createObjectURL(await r.blob());
        const a = document.createElement("a");
        a.href = url; a.download = (s.adm_no || s.id) + ".pdf";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      }
    } catch { setMsg("Download failed."); }
    setBusyId("");
  };

  if (needScale) return <GradingScale onSaved={() => { setNeedScale(false); setTries(tries + 1); }} />;
  if (bad) return <ErrorState text={bad} onRetry={() => { setBad(""); setTries(tries + 1); }} />;
  if (!meta) return <Loading />;

  const students = meta.students.filter((s) => s.class_name === cls && (!stream || s.stream === stream));
  const why = {};
  ((sel && sel.excluded) || []).forEach((x) => { why[x.student_id] = x.reason; });
  const ready = students.filter((s) => !why[s.id]);

  const preview = async (s) => {
    const w = window.open("", "_blank");
    setMsg("");
    try {
      const r = await api(P + "student/" + s.id + "/pdf/?" + qs({}));
      if (!r.ok) { if (w) w.close(); setMsg(await errText(r)); return; }
      const url = URL.createObjectURL(await r.blob());
      if (w) { w.location.href = url; } else { setMsg("Allow pop-ups for this site to preview."); }
    } catch { if (w) w.close(); setMsg("Preview failed."); }
  };

  const downloadAll = async () => {
    setBulk(""); setMsg(""); setBulkBusy(true);
    let ok = 0; const failed = [];
    for (let i = 0; i < ready.length; i++) {
      const s = ready[i];
      setBulk("Downloading " + (i + 1) + " of " + ready.length + "...");
      try {
        const r = await api(P + "student/" + s.id + "/pdf/?" + qs({ download: "1" }));
        if (!r.ok) { failed.push(s.adm_no || s.id); }
        else {
          const url = URL.createObjectURL(await r.blob());
          const a = document.createElement("a");
          a.href = url; a.download = (s.adm_no || s.id) + ".pdf";
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 5000);
          ok += 1;
        }
      } catch { failed.push(s.adm_no || s.id); }
      await new Promise((res) => setTimeout(res, 700));
    }
    setBulk("Done: " + ok + " downloaded" + (failed.length ? ", failed: " + failed.join(", ") : "") + ".");
    setBulkBusy(false);
  };

  return (
    <div>
      <Card title="Report cards">
        <Select id="rm-exam" label="Exam" value={exam} onChange={(e) => { setExam(e.target.value); setSel(null); }}>
          <option value="">Choose exam</option>
          {meta.exams.map((x) => <option key={x.id} value={x.id}>{x.name}{x.published ? "" : " (not published)"}</option>)}
        </Select>
        <Select id="rm-class" label="Class" value={cls} onChange={(e) => { setCls(e.target.value); setSel(null); }}>
          <option value="">Choose class</option>
          {meta.classes.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select id="rm-stream" label="Stream" value={stream} onChange={(e) => { setStream(e.target.value); setSel(null); }}>
          <option value="">All streams</option>
          {meta.streams.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        {meta.config.allow_provisional && meta.role !== "teacher" && (
          <p><label><input type="checkbox" checked={prov} onChange={(e) => { setProv(e.target.checked); setSel(null); }} /> Allow provisional reports</label></p>
        )}
        <p><Button onClick={check} disabled={!exam || !cls}>Check readiness</Button></p>
      </Card>
      {warn.length > 0 && !skip && (
        <Card title="Before you print">
          <p>Your report cards will look better with: <b>{warn.join(", ")}</b>. Add them under Setup, School identity. You can still print without them.</p>
          <p><Button kind="ghost" size="sm" onClick={() => setSkip(true)}>Skip anyway</Button></p>
        </Card>
      )}
      {msg && <Alert>{msg}</Alert>}
      {sel && (
        <Card title={sel.population}>
          <p><Badge>{sel.selected} selected</Badge> <Badge>{sel.eligible} ready</Badge> <Badge kind="warn">{sel.pending} pending</Badge></p>
          {sel.excluded.length > 0 && <p>{sel.excluded.length} student(s) cannot be printed yet. The reason is shown beside each name.</p>}
        </Card>
      )}
      {sel && ready.length > 0 && (warn.length === 0 || skip) && (
          <Card title="Download all">
            <p>{ready.length} report(s) ready. They download one after another; keep this page open.</p>
            <p><Button busy={bulkBusy} onClick={downloadAll}>Download all ({ready.length})</Button></p>
            {bulk && <p>{bulk}</p>}
          </Card>
        )}
        {exam && cls && meta.role !== "teacher" && <ReportInsights exam={exam} cls={cls} stream={stream} prov={prov} />}
        {exam && cls && meta.role !== "teacher" && <ReportComments key={exam + "|" + cls} exam={exam} cls={cls} students={students} />}
        {meta.role !== "teacher" && <ReportAdmin />}
        {meta.role !== "teacher" && <FrameworkAdmin />}
        {meta.role !== "teacher" && <ClassTeacherAdmin />}
    {cls && students.length === 0 && <EmptyState title="No students" text="No students in this class." />}
      {exam && students.map((s) => (
        <Card key={s.id} title={s.name + " (Adm " + s.adm_no + ")"}>
          {why[s.id] && <p>{why[s.id]}</p>}
          <Button onClick={() => preview(s)}>Preview</Button> <Button busy={busyId === s.id} onClick={() => download(s)}>Download PDF</Button>
        </Card>
      ))}
    </div>
  );
}
