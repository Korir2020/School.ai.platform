import { useState, useEffect } from "react";
import { login, api, logout } from "./api";
import Logo from "./Logo";
import Marks from "./Marks";
import Approvals from "./Approvals";
import Exams from "./Exams";
import ReportCards from "./ReportCards";
import Students from "./Students";
import Setup from "./Setup";
import Terms from "./Terms";
import Password from "./Password";
import Deputies from "./Deputies";
import Welcome from "./Welcome";
import Teachers from "./Teachers";
import Analytics from "./Analytics";
import "./app.css";

const flat = (o, p = "") => Object.entries(o || {}).flatMap(([k, v]) => v && typeof v === "object" ? (Array.isArray(v) || k === "active_term" ? [] : flat(v, k + " ")) : k === "role" ? [] : [[p + k, v]]);

function Login({ onDone }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [st, setSt] = useState(""), [shake, setShake] = useState(false);
  const go = async (e) => { e.preventDefault(); setBusy(true); setErr(""); setSt("show"); try { await login(u.trim(), p); setSt("show happy"); setTimeout(() => setSt("show happy open"), 500); setTimeout(onDone, 1500); return; } catch (x) { setSt("show sad"); setShake(true); setTimeout(() => { setSt(""); setShake(false); }, 1300); setErr(x.message === "Failed to fetch" ? "Cannot reach the server. Try again." : x.message); } setBusy(false); };
  return (<div className="auth"><form onSubmit={go} className={"card" + (shake ? " shake" : "")}><Logo size={72} /><h1>MARIAN</h1><p className="sub">Intelligent School Management</p>
    <input placeholder="Username" autoCapitalize="none" value={u} onChange={(e) => setU(e.target.value)} />
    <input placeholder="Password" type="password" value={p} onChange={(e) => setP(e.target.value)} />
    <button disabled={busy}>{busy ? "Signing in..." : "Log in"}</button>{err && <p className="err">{err}</p>}</form><div className={"eleph " + st} aria-hidden="true"><div className="door" /><div className="ele"><svg viewBox="0 0 60 90"><g className="arm"><path d="M46 54 L55 34" stroke="#5b3a29" strokeWidth="7" strokeLinecap="round" /><circle cx="55" cy="33" r="4.5" fill="#5b3a29" /></g><rect x="13" y="44" width="34" height="46" rx="11" fill="#2563EB" /><rect x="4" y="60" width="15" height="19" rx="2" fill="#F8FAFC" /><g className="head"><circle cx="30" cy="30" r="15" fill="#5b3a29" /><path d="M15 26 Q30 8 45 26 Q30 19 15 26Z" fill="#1b1209" /><circle cx="25" cy="30" r="1.8" fill="#111" /><circle cx="35" cy="30" r="1.8" fill="#111" /><path d="M25 36 Q30 41 35 36" stroke="#111" strokeWidth="1.7" fill="none" strokeLinecap="round" /></g></svg></div></div></div>);
}

const Home = ({ me, d }) => (<div className="plain"><h2>Welcome{me ? ", " + me.username : ""}</h2>
  <p className="sub">{me && me.school ? me.school.name + " · " : ""}{d.active_term ? d.active_term.name + " " + d.active_term.academic_year : "No active term"}</p>
  <div className="stats">{flat(d).map(([k, v]) => <div className="stat" key={k}><b>{String(v)}</b><span>{k.replace(/_/g, " ")}</span></div>)}</div></div>);

function Dash({ onOut }) {
  const [me, setMe] = useState(null), [d, setD] = useState(null), [tab, setTab] = useState("Home");
  useEffect(() => { (async () => {
    const a = await api("/api/auth/me/"); if (a.status === 401) return onOut(); setMe(await a.json());
    const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json());
  })(); }, []);
  const role = d && d.role;
  const need = (el) => (d.active_term ? el : <p className="plain">No active term yet. Create one in Setup first.</p>);
  const home = d && <><Home me={me} d={d} /><Password /></>;
  const tabs = role === "teacher" ? { Home: home, Marks: need(<Marks d={d} />) }
    : role === "school_admin" ? { Home: home, Approve: <Approvals />, Exams: need(<Exams d={d} />), Reports: need(<ReportCards d={d} />), Analytics: need(<Analytics d={d} />), People: need(<><Students d={d} /><Teachers />{me && !me.is_deputy && <Deputies />}</>), Setup: <><Terms /><Setup /></> }
    : d ? { Home: home } : {};
  return (<div className="shell"><header><Logo size={30} /><b>MARIAN</b><span>{me ? me.username : ""}</span>
    <button className="ghost" onClick={async () => { await logout(); onOut(); }}>Log out</button></header>
    <main>{d ? tabs[tab] : <p className="sub">Loading...</p>}</main>
    <nav>{Object.keys(tabs).map((t) => <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}</nav></div>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("access")), [go, setGo] = useState(false);
  return ok ? <Dash onOut={() => setOk(false)} /> : go ? <Login onDone={() => setOk(true)} /> : <Welcome onStart={() => setGo(true)} />;
}
