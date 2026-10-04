import { useState, useEffect } from "react";
import { api, logout } from "./api";
import Logo from "./Logo";
import Hero from "./Hero";
import Stats from "./Stats";
import Quick from "./Quick";
import Login from "./Login";
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

const Home = ({ me, d }) => (<div className="plain"><Hero me={me} d={d} />
  <Stats d={d} /></div>);

function Dash({ onOut }) {
  const [me, setMe] = useState(null), [d, setD] = useState(null), [tab, setTab] = useState("Home");
  useEffect(() => { (async () => {
    const a = await api("/api/auth/me/"); if (a.status === 401) return onOut(); setMe(await a.json());
    const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json());
  })(); }, []);
  const role = d && d.role;
  const need = (el) => (d.active_term ? el : <p className="plain">No active term yet. Create one in Setup first.</p>);
  const home = d && <><Home me={me} d={d} />{role === "school_admin" && <Quick go={setTab} tabs={{ Approve: 1, Exams: 1, Reports: 1, People: 1, Analytics: 1 }} />}<Password /></>;
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
