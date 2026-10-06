import { useState } from "react";
import { Alert, Button, Input, Select } from "./ui";
import "./pub.css";

const EMPTY = { first_name: "", last_name: "", username: "", password: "",
  role: "teacher", school_code: "" };

export default function Join({ onBack, onSignIn }) {
  const [f, setF] = useState(EMPTY), [err, setErr] = useState("");
  const [busy, setBusy] = useState(false), [done, setDone] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const send = async () => {
    setErr(""); setBusy(true);
    try {
      const r = await fetch("/api/join/register/", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...f, username: f.username.trim(),
          school_code: f.school_code.trim() }) });
      const d = await r.json().catch(() => ({}));
      if (r.status === 201) setDone(d);
      else if (r.status === 429) setErr("Too many tries. Wait a minute.");
      else setErr(d.detail || "Could not send the request.");
    } catch { setErr("Cannot reach the server. Try again."); }
    setBusy(false);
  };
  if (done) return (<div className="mu-pub"><div className="mu-pub-in">
    <div className="mu-pub-card"><h2>Request sent</h2>
      <Alert kind="ok">{done.detail}</Alert>
      <p>Next: sign in with your username and password to see when your
        school administrator approves you.</p>
      <Button kind="teal" onClick={onSignIn}>Sign In</Button></div></div></div>);
  return (<div className="mu-pub"><div className="mu-pub-in">
    <Button kind="ghost" onClick={onBack}>← Back</Button>
    <div className="mu-pub-card"><h2>Request to join a school</h2>
      <p>Your School Code only tells Marian which school. An administrator
        must approve you.</p>
      <div className="mu-pub-form">
        <Input label="First name" value={f.first_name}
          onChange={set("first_name")} />
        <Input label="Last name" value={f.last_name}
          onChange={set("last_name")} />
        <Input label="Username" autoCapitalize="none" value={f.username}
          onChange={set("username")} />
        <Input label="Password" type="password" value={f.password}
          onChange={set("password")} help="Choose a strong password." />
        <Select label="Role" value={f.role} onChange={set("role")}>
          <option value="teacher">Teacher</option>
          <option value="bursar">Bursar</option>
          <option value="secretary">Secretary</option></Select>
        <Input label="School Code" autoCapitalize="characters"
          value={f.school_code} onChange={set("school_code")} />
        {err && <Alert kind="err">{err}</Alert>}
        <Button kind="teal" busy={busy} onClick={send}>Send request</Button>
      </div></div></div></div>);
}
