import { useState, useEffect } from "react";
import { api, logout } from "./api";
import Hero from "./Hero";
import Stats from "./Stats";
import Quick from "./Quick";
import Mine from "./Mine";
import Shell from "./Shell";
import { Loading } from "./ui";
import Activity from "./Activity";
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
import Intro from "./Intro";
import Teachers from "./Teachers";
import Analytics from "./Analytics";
import Platform from "./Platform";
import Accounts from "./Accounts";
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
  const home = d && <><Home me={me} d={d} />{role === "teacher" && <Mine d={d} />}{role === "school_admin" && <Quick go={setTab} tabs={{ Approve: 1, Exams: 1, Reports: 1, Students: 1, Analytics: 1 }} />}{role === "school_admin" && <Activity />}<Password /></>;
  const tabs = role === "teacher" ? { Home: home, Marks: need(<Marks d={d} />) }
    : role === "school_admin" ? { Home: home, Approve: <Approvals />, Exams: need(<Exams d={d} />), Reports: need(<ReportCards d={d} />), Analytics: need(<Analytics d={d} />), Students: need(<Students d={d} />), Teachers: need(<><Teachers />{me && !me.is_deputy && <Deputies />}</>), Setup: <><Terms /><Setup /></> }
    : role === "superadmin" ? { Home: home, Schools: <Platform d={d} />, Admins: <Accounts /> }
    : d ? { Home: home } : {};
  const out = async () => { await logout(); onOut(); };
  return (<Shell tabs={Object.keys(tabs)} tab={tab} go={setTab} me={me} out={out}>
    {d ? tabs[tab] : <Loading />}</Shell>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("in")), [go, setGo] = useState(false);
  return ok ? <Dash onOut={() => setOk(false)} /> : go ? <Login onDone={() => setOk(true)} /> : <Intro onStart={() => setGo(true)} />;
}
