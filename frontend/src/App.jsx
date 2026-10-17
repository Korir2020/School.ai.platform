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
import SetupWizard from "./SetupWizard";
import Terms from "./Terms";
import Password from "./Password";
import Deputies from "./Deputies";
import Intro from "./Intro";
import Landing from "./Landing";
import Join from "./Join";
import JoinStatus from "./JoinStatus";
import Teachers from "./Teachers";
import Staff from "./Staff";
import Analytics from "./Analytics";
import Platform from "./Platform";
import AuditLog from "./AuditLog";
import Accounts from "./Accounts";
import Fees from "./Fees";
import Parent from "./Parent";
import BulkDocuments from "./BulkDocuments";
import Attendance from "./Attendance";
import ParentAccounts from "./ParentAccounts";
import RegistrationReview from "./RegistrationReview";
import TeacherTransfers from "./TeacherTransfers";
import PasswordRecovery from "./PasswordRecovery";
import SchoolRegistration from "./SchoolRegistration";
import SchoolStatus from "./SchoolStatus";
import { useHashTab } from "./hashtab";
import "./app.css";
import "./light.css";

const Home = ({ me, d }) => (<div className="plain"><Hero me={me} d={d} />
  <Stats d={d} /></div>);

function Dash({ onOut }) {
  const [me, setMe] = useState(null), [d, setD] = useState(null), [tab, setTab] = useHashTab();
  useEffect(() => { (async () => {
    const a = await api("/api/auth/me/"); if (a.status === 401) return onOut(); const m = await a.json(); setMe(m); if (m.role === "school_admin" && m.setup_complete === false && !m.is_deputy && !window.location.hash) setTab("Setup");
    if (["none", "secretary"].includes(m.role)) return;
    if (m.role === "bursar") { setD({ role: "bursar" }); return; }
    if (m.role === "parent") { setD({ role: "parent" }); return; }
    const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json());
  })(); }, []);
  const role = d && d.role;
  const need = (el) => (d.active_term ? el : <p className="plain">No active term yet. Create one in Setup first.</p>);
  const home = d && <><Home me={me} d={d} />{role === "teacher" && <TeacherTodo d={d} go={setTab} />}{role === "teacher" && <Mine d={d} />}{role === "school_admin" && <Attention d={d} go={setTab} />}{role === "school_admin" && <Quick go={setTab} tabs={{ Approve: 1, Exams: 1, Reports: 1, Students: 1, Analytics: 1, Fees: 1 }} />}{role === "school_admin" && <Activity />}<Password /></>;
  const tabs = role === "teacher" ? { Home: home, Marks: need(<Marks d={d} />), Attendance: <Attendance /> }
    : role === "school_admin" ? { Home: home, Approve: <Approvals />, Exams: need(<Exams d={d} />), Reports: need(<ReportCards d={d} />), Analytics: need(<Analytics d={d} />), Attendance: <Attendance />, Fees: <Fees admin />, Documents: <BulkDocuments admin />, Students: need(<Students d={d} />), Parents: <ParentAccounts />, Transfers: <TeacherTransfers />, Teachers: need(<><Teachers />{me && !me.is_deputy && <Deputies />}</>), Staff: <Staff />, Audit: <AuditLog />, Setup: <><SetupWizard /><Terms /><Setup /></> }
    : role === "bursar" ? { Fees: <Fees />, Documents: <BulkDocuments /> }
    : role === "parent" ? { Home: <Parent /> }
    : role === "superadmin" ? { Home: home, Schools: <Platform d={d} />, Registrations: <RegistrationReview />, Transfers: <TeacherTransfers />, Admins: <Accounts />, Audit: <AuditLog /> }
    : d ? { Home: home } : {};
  const out = async () => { await logout(); onOut(); };
  if (me && ["none", "secretary"].includes(me.role)) {
    return <JoinStatus me={me} out={out} />;
  }
  const cur = tabs[tab] ? tab : "Home";
  return (<Shell tabs={Object.keys(tabs)} tab={cur} go={setTab} me={me} out={out} term={d && d.active_term ? d.active_term.name : null}>
    {d ? tabs[cur] : <Loading />}</Shell>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("in"));
  const [scr, setScr] = useState(() => window.location.search.includes("recovery=1") ? "recovery" : "intro");
  const [blocked, setBlocked] = useState(null);
  useEffect(() => {
    const h = (e) => setBlocked(e.detail || "This school account is suspended.");
    window.addEventListener("marian:suspended", h);
    return () => window.removeEventListener("marian:suspended", h);
  }, []);
  const to = (x) => () => setScr(x);
  if (blocked) return (
    <div role="alert" style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, marginBottom: 12, color: "inherit" }}>School account suspended</h1>
        <p style={{ marginBottom: 20 }}>{blocked}</p>
        <button onClick={async () => { await logout(); setBlocked(null); setOk(false); setScr("landing"); }} style={{ padding: "12px 20px", fontSize: 16 }}>Sign out</button>
      </div>
    </div>
  );
  if (ok) return <Dash onOut={() => { setOk(false); setScr("landing"); }} />;
  if (scr === "login") return <Login onDone={() => setOk(true)} onForgot={to("recovery")} />;
  if (scr === "recovery") return <PasswordRecovery onBack={to("login")} />;
  if (scr === "join") {
    return <Join onBack={to("landing")} onSignIn={to("login")} />;
  }
  if (scr === "school-register") {
    return <SchoolRegistration onBack={to("landing")} onSignIn={to("login")} />;
  }
  if (scr === "school-status") {
    return <SchoolStatus onBack={to("landing")} onSignIn={to("login")} />;
  }
  if (scr === "landing") {
    return <Landing onStatus={to("school-status")} onStart={to("join")} onRegister={to("school-register")} onSignIn={to("login")} />;
  }
  return <Intro onStart={to("landing")} />;
}
