import { useEffect, useRef, useState } from "react";
import { api, upload } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card } from "./ui";
import "./announce.css";

async function download(path, fallback) {
  const r = await api(path);
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.detail || "Download failed");
  }
  const cd = r.headers.get("Content-Disposition") || "";
  const m = /filename="([^"]+)"/.exec(cd);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = m ? m[1] : fallback;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// School administrator: download everything the school owns, for safekeeping.
export function SchoolExport() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await download("/api/school/export/", "school-export.json"); toast("Export downloaded", "ok"); }
    catch (e) { toast(e.message, "err"); }
    setBusy(false);
  };
  return (<Card title="Export school data">
    <p className="sub">Download every record that belongs to your school: learners, guardians, staff, classes, marks, exams, report cards, attendance, fees and messages. Passwords are never included.</p>
    <Alert kind="warn">The file holds private learner records. Store it somewhere safe and do not share it.</Alert>
    <Button kind="teal" busy={busy} onClick={run}>Download export</Button>
  </Card>);
}

// Platform administrator: full backups and file checks.
export default function Backups() {
  const toast = useToast();
  const [st, setSt] = useState(null), [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null), [checking, setChecking] = useState(false);
  const pick = useRef(null);
  const load = () => api("/api/backups/status/").then(async (r) => r.ok && setSt(await r.json()));
  useEffect(() => { load(); }, []);

  const take = async () => {
    setBusy(true);
    try { await download("/api/backups/full/", "marian-backup.json.gz"); toast("Backup downloaded", "ok"); load(); }
    catch (e) { toast(e.message, "err"); }
    setBusy(false);
  };
  const check = async (file) => {
    if (!file) return;
    setChecking(true); setReport(null);
    const fd = new FormData(); fd.append("file", file, file.name);
    try {
      const r = await upload("/api/backups/validate/", fd, 120000);
      const j = await r.json().catch(() => ({}));
      setReport(r.ok ? j : { ok: false, problems: [j.detail || "Could not check the file."], warnings: [] });
    } catch { setReport({ ok: false, problems: ["The upload failed. Check your connection."], warnings: [] }); }
    setChecking(false);
  };
  const days = st && st.last_backup ? Math.floor((Date.now() - new Date(st.last_backup)) / 86400000) : null;

  return (<div className="an">
    <Card title="Full backup">
      <p className="sub">One file with every school, account and record on the platform, protected by a checksum. Download one before every update and at least weekly, and keep copies off this server.</p>
      {st && (st.last_backup
        ? <p>Last backup: <b>{new Date(st.last_backup).toLocaleString()}</b>{st.last_backup_by ? " by " + st.last_backup_by : ""} {days > 7 ? <Badge kind="warn">{days} days ago</Badge> : <Badge kind="ok">Recent</Badge>}</p>
        : <Alert kind="warn">No backup has been taken yet.</Alert>)}
      <Button kind="teal" busy={busy} onClick={take}>Download full backup</Button>
    </Card>

    <Card title="Check a backup file">
      <p className="sub">Confirm a backup is complete and undamaged before you rely on it. Checking never changes any data.</p>
      <input ref={pick} type="file" hidden accept=".gz,.json,application/gzip,application/json" onChange={(e) => { check(e.target.files[0]); e.target.value = ""; }} />
      <Button kind="secondary" busy={checking} onClick={() => pick.current && pick.current.click()}>Choose backup file</Button>
      {report && <div className="an-report">
        {report.ok ? <Alert kind="ok">The file is a valid Marian backup{report.meta ? ` from ${new Date(report.meta.created_at).toLocaleString()} with ${report.meta.total} records` : ""}.</Alert>
          : <Alert kind="err">{report.problems.join(" ")}</Alert>}
        {report.warnings && report.warnings.map((w) => <Alert key={w} kind="warn">{w}</Alert>)}
      </div>}
    </Card>

    <Card title="Restoring">
      <p className="sub">Restoring replaces data, so it is never done from a web page. A technical person runs it on the server, which checks the file first and changes nothing if any check fails:</p>
      <pre className="an-pre">python manage.py restore_data FILE            (check only)
python manage.py restore_data FILE --yes      (into an empty database)
python manage.py restore_data FILE --yes --replace</pre>
    </Card>
  </div>);
}
