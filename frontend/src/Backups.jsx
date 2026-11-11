import { useCallback, useEffect, useRef, useState } from "react";
import { api, upload } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card, Loading } from "./ui";
import "./announce.css";
import "./backups.css";

async function download(path, fallback) {
  const response = await api(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Download failed");
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = match ? match[1] : fallback;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function responseError(response, fallback) {
  const body = await response.json().catch(() => ({}));
  return body.detail || body.error || fallback;
}

function formatDate(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "Not reported";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = bytes / 1024, unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toFixed(amount >= 10 ? 0 : 1)} ${units[unit]}`;
}

function stateKind(status) {
  const value = String(status || "").toLowerCase();
  if (value === "succeeded") return "ok";
  if (value === "failed") return "err";
  if (["queued", "running"].includes(value)) return "info";
  return "warn";
}

function statusLabel(status) {
  return String(status || "Unknown").replaceAll("_", " ");
}

// School administrator: a separate privacy-redacted school export.
export function SchoolExport() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      await download("/api/school/export/", "school-export.json");
      toast("Export downloaded", "ok");
    } catch (error) { toast(error.message, "err"); }
    finally { setBusy(false); }
  };
  return <Card title="Export school data">
    <p className="sub">Download every record that belongs to your school: learners, guardians, staff, classes, marks, exams, report cards, attendance, fees and messages. Passwords are never included.</p>
    <Alert kind="warn">The file holds private learner records. Store it somewhere safe and do not share it.</Alert>
    <Button kind="teal" busy={busy} onClick={run}>Download export</Button>
  </Card>;
}

// Platform administrator: encrypted off-site backup queue plus separate legacy tools.
export default function Backups() {
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState("");
  const [report, setReport] = useState(null);
  const [checking, setChecking] = useState(false);
  const picker = useRef(null);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [statusResponse, historyResponse] = await Promise.all([
        api("/api/backups/offsite/status/"),
        api("/api/backups/offsite/history/?limit=50"),
      ]);
      if (!statusResponse.ok) throw new Error(await responseError(statusResponse, "Backup status could not be loaded."));
      if (!historyResponse.ok) throw new Error(await responseError(historyResponse, "Backup history could not be loaded."));
      const [nextStatus, nextHistory] = await Promise.all([statusResponse.json(), historyResponse.json()]);
      setStatus(nextStatus);
      setHistory(Array.isArray(nextHistory) ? nextHistory : (nextHistory.results || []));
    } catch (error) { setLoadError(error.message || "Backup information could not be loaded."); }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const queueRun = async () => {
    setBusy(true);
    try {
      const response = await api("/api/backups/offsite/trigger/", "POST", {});
      if (!response.ok) throw new Error(await responseError(response, "The backup could not be queued."));
      toast("Encrypted backup queued. The worker must be running to process it.", "ok");
      await load();
    } catch (error) { toast(error.message, "err"); }
    finally { setBusy(false); }
  };

  const retry = async (id) => {
    setRetrying(id);
    try {
      const response = await api(`/api/backups/offsite/${encodeURIComponent(id)}/retry/`, "POST", {});
      if (!response.ok) throw new Error(await responseError(response, "The backup retry could not be queued."));
      toast("Backup retry queued", "ok");
      await load();
    } catch (error) { toast(error.message, "err"); }
    finally { setRetrying(""); }
  };

  const takeLegacy = async () => {
    setBusy(true);
    try { await download("/api/backups/full/", "marian-backup.json.gz"); toast("Legacy export downloaded", "ok"); }
    catch (error) { toast(error.message, "err"); }
    finally { setBusy(false); }
  };

  const checkLegacy = async (file) => {
    if (!file) return;
    setChecking(true);
    setReport(null);
    const form = new FormData();
    form.append("file", file, file.name);
    try {
      const response = await upload("/api/backups/validate/", form, 120000);
      const body = await response.json().catch(() => ({}));
      setReport(response.ok ? body : { ok: false, problems: [body.detail || "Could not check the file."], warnings: [] });
    } catch { setReport({ ok: false, problems: ["The upload failed. Check your connection."], warnings: [] }); }
    finally { setChecking(false); }
  };

  const latest = status?.latest || null;
  const lastVerified = status?.last_remote_readback_verified_at || null;
  const failedCount = history.filter((item) => item.status === "failed").length;
  const configured = status?.configured === true;
  const scheduled = status?.automatic_schedule_configured === true;
  const ready = status?.operational === true;

  return <div className="bkp-page">
    <header className="bkp-header">
      <div><span className="bkp-eyebrow">PLATFORM OPERATIONS</span><h2>Backup &amp; recovery</h2>
        <p>Encrypted off-site snapshots, integrity verification, and operator-controlled recovery.</p></div>
      <div className="bkp-header-actions">
        <Button kind="secondary" onClick={load}>Refresh status</Button>
        <Button kind="teal" busy={busy} disabled={!configured} onClick={queueRun}>Run backup now</Button>
      </div>
    </header>

    {loadError && <Alert kind="err">{loadError} <Button kind="secondary" size="sm" onClick={load}>Try again</Button></Alert>}
    {!status ? (loadError ? null : <Card title="Loading backup status"><Loading /></Card>) : <>
      {!ready && <Alert kind="warn"><b>Automated protection is not yet verified as operational.</b>{" "}
        {!configured ? "Off-site storage or encryption keys are not configured, so the worker cannot create a verified backup. " : !scheduled ? "No external scheduler is declared. " : !status.last_success ? "No successful remote-verified backup is recorded. " : "A successful restore drill has not been recorded. "}
        Queueing a run only creates a job; configure and supervise the worker/scheduler before relying on scheduled protection.</Alert>}
      {(status.setup_warnings || []).map((warning, index) => <Alert key={`${index}-${warning}`} kind="warn">{warning}</Alert>)}
      {status.latest?.status === "failed" && <Alert kind="err"><b>Latest backup run failed.</b>{status.latest.error ? ` ${status.latest.error}` : " Review the failed run and retry after correcting the cause."}</Alert>}
      <div className="bkp-stats" aria-label="Backup status summary">
        <div className={`bkp-stat ${ready ? "is-good" : "is-bad"}`}>
          <span>Backup service</span><strong>{ready ? "Operational" : "Not verified"}</strong>
          <small>{configured ? "Storage and keys configured" : "Storage or keys not configured"}</small>
        </div>
        <div className="bkp-stat"><span>Last verified backup</span><strong>{formatDate(status.last_success || lastVerified)}</strong>
          <small>Remote read-back and integrity check</small></div>
        <div className="bkp-stat"><span>Scheduled runs</span><strong>{scheduled ? "Declared" : "Not configured"}</strong>
          <small>{scheduled ? `Next: ${formatDate(status.next_scheduled_at)}` : "No next run is available"}</small></div>
        <div className="bkp-stat"><span>Storage usage</span><strong>{formatBytes(status.storage_usage_bytes)}</strong><small>Object bytes under the configured backup prefix</small></div>
        <div className="bkp-stat"><span>Retention</span><strong>{status.retention_days ? `${status.retention_days} days` : "Not reported"}</strong>
          <small>BACKUP_RETENTION_DAYS; see operator guide</small></div>
        <div className="bkp-stat"><span>Restore drill</span><strong>{formatDate(status.last_restore_drill)}</strong><small>Operator-declared last staging restore drill</small></div>
      </div>
      <div className="bkp-current-run"><span>Most recent run</span>
        {latest ? <><Badge kind={stateKind(latest.status)}>{statusLabel(latest.status)}</Badge>
          <span>{formatDate(latest.finished_at || latest.created_at)}</span>
          <span>{latest.result?.remote_readback_verified ? "Remote verified" : "Not verified"}</span>
          <span>{latest.result?.database_engine || "Database engine not reported"}</span></>
          : <span>No run has been recorded.</span>}
      </div>
    </>}

    <Card title="Automated backup history" className="bkp-history-card">
      <div className="bkp-section-head"><p>Jobs and their outcomes. Failed runs can be queued for retry.</p>
        <span className="bkp-failure-count">{failedCount} failed</span></div>
      {history.length === 0 ? <div className="bkp-empty"><b>No automated runs recorded</b><span>Queued and processed runs will appear here.</span></div> :
        <div className="bkp-history-list">{history.map((item) => {
          const verified = item.status === "succeeded" && item.result?.remote_readback_verified === true;
          return <article className={`bkp-run ${item.status === "failed" ? "bkp-run-failed" : ""}`} key={item.id}>
            <div className="bkp-run-main">
              <div className="bkp-run-title"><Badge kind={stateKind(item.status)}>{statusLabel(item.status)}</Badge>
                <span className="bkp-trigger">{item.requested_by ? `On-demand · requested by user ${item.requested_by}` : "Worker-created run"}</span>
                {verified && <Badge kind="ok">Remote verified</Badge>}</div>
              <div className="bkp-run-meta"><span>Created <b>{formatDate(item.created_at)}</b></span>
                <span>Started <b>{formatDate(item.started_at)}</b></span>
                <span>Finished <b>{formatDate(item.finished_at)}</b></span>
                <span>Attempts <b>{item.attempts ?? 0}</b></span>
                {item.result?.database_engine && <span>Format <b>{item.result.database_engine}</b></span>}</div>
              {item.error && <p className="bkp-run-error">{item.error}</p>}
              {item.manifest_key && <details className="bkp-checksum"><summary>Off-site manifest locator</summary><code>{item.manifest_key}</code></details>}
              {item.result?.manifest_sha256 && <details className="bkp-checksum"><summary>Manifest SHA-256</summary><code>{item.result.manifest_sha256}</code></details>}
              {item.result?.ciphertext_bytes != null && <div className="bkp-run-meta"><span>Encrypted objects <b>{formatBytes(item.result.ciphertext_bytes)}</b></span></div>}
            </div>
            {item.status === "failed" && <Button kind="secondary" size="sm" busy={retrying === item.id}
              disabled={!!retrying || !configured} onClick={() => retry(item.id)}>Retry</Button>}
          </article>;
        })}</div>}
    </Card>

    <Card title="Recovery guidance" className="bkp-recovery">
      <p>Restores are intentionally restricted to a technical operator using the server-side CLI in a staging environment. The browser dashboard cannot overwrite production or another school.</p>
      <div className="bkp-guidance-note"><b>Before recovery</b><span>Verify the backup and checksums, use a newly created empty database and a new media staging directory, rehearse the full process, and record the drill. School-only restore is not supported.</span></div>
    </Card>

    <Card title="Legacy manual export" className="bkp-legacy">
      <div className="bkp-legacy-label"><Badge kind="warn">Legacy export</Badge><span>Separate from automated encrypted backups</span></div>
      <p className="sub">Download the existing privacy-redacted JSON export. It does not represent disaster-recovery completeness, encryption, scheduling, or retention.</p>
      <Button kind="secondary" busy={busy} onClick={takeLegacy}>Download legacy full export</Button>
    </Card>

    <Card title="Validate a legacy backup file" className="bkp-legacy">
      <p className="sub">Check an existing export file for integrity. Validation is read-only and does not restore data.</p>
      <input ref={picker} type="file" hidden accept=".gz,.json,application/gzip,application/json"
        onChange={(event) => { checkLegacy(event.target.files[0]); event.target.value = ""; }} />
      <Button kind="secondary" busy={checking} onClick={() => picker.current?.click()}>Choose file to validate</Button>
      {report && <div className="an-report">
        {report.ok ? <Alert kind="ok">{`The legacy export is valid${report.meta?.created_at ? ` from ${formatDate(report.meta.created_at)}` : ""}${Number.isFinite(Number(report.meta?.total)) ? ` with ${report.meta.total} records` : ""}.`}</Alert>
          : <Alert kind="err">{(report.problems || ["The file could not be validated."]).join(" ")}</Alert>}
        {report.warnings?.map((warning, index) => <Alert key={`${index}-${warning}`} kind="warn">{warning}</Alert>)}
      </div>}
    </Card>
  </div>;
}
