import { useState } from "react";
import { Alert, Button, Input } from "./ui";
import "./pub.css";

export default function SchoolStatus({ onBack, onSignIn }) {
  const [reference, setReference] = useState("");
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const check = async () => {
    setError(""); setResult(null); setBusy(true);
    const r = await fetch("/api/school-registration/status/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference: reference.trim(), username: username.trim() }),
    }).catch(() => null);
    setBusy(false);
    if (!r) return setError("Could not reach the server. Try again.");
    const j = await r.json().catch(() => ({}));
    if (r.status === 429) return setError("Too many tries. Wait a minute and try again.");
    if (!r.ok) return setError(j.detail || "Could not check the application.");
    setResult(j);
  };

  return (
    <div className="mu-pub"><div className="mu-pub-in">
      <Button kind="ghost" onClick={onBack}>← Back</Button>
      <div className="mu-pub-card">
        <h2>Check my application</h2>
        <p>Enter the reference you received and the administrator username.</p>
        <Input label="Reference" value={reference} onChange={(e) => setReference(e.target.value)} />
        <Input label="Administrator username" autoCapitalize="none" value={username} onChange={(e) => setUsername(e.target.value)} />
        {error && <Alert kind="err">{error}</Alert>}
        <Button kind="teal" busy={busy} disabled={!reference.trim() || !username.trim()} onClick={check}>Check status</Button>
        {result && (
          <Alert kind={result.status === "approved" ? "ok" : result.status === "rejected" ? "err" : "info"}>
            <b>{result.school_name}</b>: {result.status_text}
            {result.rejection_reason ? " Reason: " + result.rejection_reason : ""}
            {result.info_request_message ? " " + result.info_request_message : ""}
          </Alert>
        )}
        {result && result.status === "approved" && <Button kind="teal" onClick={onSignIn}>Sign in</Button>}
      </div>
    </div></div>
  );
}
