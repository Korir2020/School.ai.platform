import { useMemo, useState } from "react";
import { api } from "./api";
import { Button, Input, Alert } from "./ui";
import Logo from "./Logo";

export default function PasswordRecovery({ onBack }) {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const [identifier, setIdentifier] = useState(""), [password, setPassword] = useState(""), [confirm, setConfirm] = useState(""), [msg, setMsg] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const token = params.get("token"), uid = params.get("uid");
  const submit = async (e) => { e.preventDefault(); setErr(""); setMsg(""); setBusy(true); const body = token ? { uid, token, new_password: password } : { identifier }; const r = await api(token ? "/api/auth/password-reset/confirm/" : "/api/auth/password-reset/", "POST", body); const j = await r.json().catch(() => ({})); setBusy(false); if (!r.ok) return setErr(j.detail || "Unable to complete recovery."); setMsg(j.detail); if (token) { setTimeout(() => { window.history.replaceState({}, "", window.location.pathname); onBack(); }, 1600); } };
  const valid = token ? password && password === confirm : identifier.trim();
  return <div className="recovery-page"><div className="recovery-card"><Logo size={72} /><h2>{token ? "Set a new password" : "Recover your account"}</h2><p className="sub">{token ? "Choose a strong password you have not used before." : "Enter your username or account email. We will respond safely without revealing whether an account exists."}</p><form onSubmit={submit}>{token ? <><Input label="New password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /><Input label="Confirm password" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} />{password && confirm && password !== confirm && <Alert kind="err">Passwords do not match.</Alert>}</> : <Input label="Username or email" autoComplete="username" value={identifier} onChange={e => setIdentifier(e.target.value)} />}{err && <Alert kind="err">{err}</Alert>}{msg && <Alert kind="ok">{msg}</Alert>}<Button kind="teal" busy={busy} disabled={!valid || (token && password !== confirm)}>{token ? "Reset password" : "Send recovery instructions"}</Button></form><button className="lnk recovery-back" type="button" onClick={onBack}>Back to sign in</button></div></div>;
}
