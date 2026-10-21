import { useState } from "react";
import { api } from "./api";
import { Button, Card, Badge, Alert, EmptyState, Loading } from "./ui";

const P = "/api/report-module/";

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

function nice(k) { return k.replace(/_/g, " "); }

export default function ReportAdmin() {
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [secs, setSecs] = useState(null);
  const [busy, setBusy] = useState("");
  const [entries, setEntries] = useState(null);
  const [action, setAction] = useState("");

  const loadSections = async () => {
    setMsg(""); setBusy("ls");
    try {
      const r = await api(P + "section-config/");
      if (!r.ok) setMsg(await errText(r));
      else setSecs((await r.json()).sections || {});
    } catch { setMsg("Could not load sections."); }
    setBusy("");
  };

  const saveSections = async () => {
    setMsg(""); setBusy("ss");
    try {
      const r = await api(P + "section-config/", "PUT", { sections: secs });
      if (!r.ok) setMsg(await errText(r));
      else {
        const d = await r.json();
        setSecs(d.sections || secs);
        const n = d.changed ? Object.keys(d.changed).length : 0;
        setMsg(n ? "Saved. " + n + " section(s) changed." : "No changes to save.");
      }
    } catch { setMsg("Save failed."); }
    setBusy("");
  };

  const loadAudit = async () => {
    setMsg(""); setBusy("au");
    try {
      const q = new URLSearchParams({ limit: "50" });
      if (action.trim()) q.set("action", action.trim());
      const r = await api(P + "audit/?" + q.toString());
      if (!r.ok) { setMsg(await errText(r)); setEntries(null); }
      else setEntries((await r.json()).entries || []);
    } catch { setMsg("Could not load activity."); }
    setBusy("");
  };

  const toggle = (k) => setSecs({ ...secs, [k]: !secs[k] });

  return (
    <Card title="Admin: report settings">
      <p><Button onClick={() => setOpen(!open)}>{open ? "Hide settings" : "Show settings"}</Button></p>
      {open && (
        <div>
          {msg && <Alert>{msg}</Alert>}
          <h4>Report sections</h4>
          <p>Choose which sections appear on report cards. This only changes visibility, not grading.</p>
          {secs === null && <p><Button busy={busy === "ls"} onClick={loadSections}>Load sections</Button></p>}
          {secs && (
            <div>
              {Object.keys(secs).sort().map((k) => (
                <p key={k}><label><input type="checkbox" checked={!!secs[k]} onChange={() => toggle(k)} /> {nice(k)}</label></p>
              ))}
              <p><Button busy={busy === "ss"} onClick={saveSections}>Save sections</Button></p>
            </div>
          )}
          <h4>Recent activity</h4>
          <p><input type="text" value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter by action, e.g. comment.approved (optional)" style={{ width: "100%", padding: 8, boxSizing: "border-box" }} /></p>
          <p><Button busy={busy === "au"} onClick={loadAudit}>Show recent activity</Button></p>
          {busy === "au" && <Loading />}
          {entries && entries.length === 0 && <EmptyState title="No activity" text="Nothing recorded for this filter yet." />}
          {entries && entries.map((e) => (
            <Card key={e.id} title={e.action}>
              <p><Badge>{e.role}</Badge> {new Date(e.at * 1000).toLocaleString()}</p>
              {e.target && <p>Target: {e.target}</p>}
              <p>{JSON.stringify(e.detail || {})}</p>
            </Card>
          ))}
        </div>
      )}
    </Card>
  );
}
