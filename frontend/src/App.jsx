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
import Attention from "./Attention";
import TeacherTodo from "./TeacherTodo";
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
import { useHashTab } from "./hashtab";
import "./app.css";

const Home = ({ me, d }) => (<div className="plain"><Hero me={me} d={d} />
  <Stats d={d} /></div>);

function Dash({ onOut }) {
  const [me, setMe] = useState(null), [d, setD] = useState(null), [tab, setTab] = useHashTab();
  useEffect(() => { (async () => {
    const a = await api("/api/auth/me/"); if (a.status === 401) return onOut(); setMe(await a.json());
    const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json());
  })(); }, []);
  const role = d && d.role;
  const need = (el) => (d.active_term ? el : <p className="plain">No active term yet. Create one in Setup first.</p>);
  const home = d && <><Home me={me} d={d} />{role === "teacher" && <TeacherTodo d={d} go={setTab} />}{role === "teacher" && <Mine d={d} />}{role === "school_admin" && <Attention d={d} go={setTab} />}{role === "school_admin" && <Quick go={setTab} tabs={{ Approve: 1, Exams: 1, Reports: 1, Students: 1, Analytics: 1 }} />}{role === "school_admin" && <Activity />}<Password /></>;
  const tabs = role === "teacher" ? { Home: home, Marks: need(<Marks d={d} />) }
    : role === "school_admin" ? { Home: home, Approve: <Approvals />, Exams: need(<Exams d={d} />), Reports: need(<ReportCards d={d} />), Analytics: need(<Analytics d={d} />), Students: need(<Students d={d} />), Teachers: need(<><Teachers />{me && !me.is_deputy && <Deputies />}</>), Setup: <><Terms /><Setup /></> }
    : role === "superadmin" ? { Home: home, Schools: <Platform d={d} />, Admins: <Accounts /> }
    : d ? { Home: home } : {};
  const out = async () => { await logout(); onOut(); };
  const cur = tabs[tab] ? tab : "Home";
  return (<Shell tabs={Object.keys(tabs)} tab={cur} go={setTab} me={me} out={out}>
    {d ? tabs[cur] : <Loading />}</Shell>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("in")), [go, setGo] = useState(false);
  return ok ? <Dash onOut={() => setOk(false)} /> : go ? <Login onDone={() => setOk(true)} /> : <Intro onStart={() => setGo(true)} />;
}
