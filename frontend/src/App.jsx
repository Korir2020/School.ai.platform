import { useState, useEffect, useRef, useCallback } from "react";
import { api, logout } from "./api";
import Hero from "./Hero";
import Stats from "./Stats";
import Mine from "./Mine";
import Shell from "./Shell";
import { Loading } from "./ui";
import Login from "./Login";
import Marks from "./Marks";
import SubjectRegistration from "./SubjectRegistration";
import LevelEntry from "./LevelEntry";
import Approvals from "./Approvals";
import Exams from "./Exams";
import ReportCards from "./ReportCards";
import ReportModule from "./ReportModule";
import MigrationCentre from "./MigrationCentre";
import TeacherTodo from "./TeacherTodo";
import Students from "./Students";
import Password from "./Password";
import Deputies from "./Deputies";
import Landing from "./Landing";
import LegalPage from "./LegalPage";
import Join from "./Join";
import JoinStatus from "./JoinStatus";
import Teachers from "./Teachers";
import Staff from "./Staff";
import Analytics from "./Analytics";
import Platform from "./Platform";
import AuditLog from "./AuditLog";
import Accounts from "./Accounts";
import Fees from "./Fees";
import BursarDashboard from "./BursarDashboard";
import Connect from "./Connect";
import Feedback from "./Feedback";
import Calendar from "./Calendar";
import Parent from "./Parent";
import BulkDocuments from "./BulkDocuments";
import Attendance from "./Attendance";
import ParentAccounts from "./ParentAccounts";
import RegistrationReview from "./RegistrationReview";
import TeacherTransfers from "./TeacherTransfers";
import Promotion from "./Promotion";
import PasswordRecovery from "./PasswordRecovery";
import SchoolRegistration from "./SchoolRegistration";
import SchoolStatus from "./SchoolStatus";
import Dash2Top from "./Dash2Top";
import Dash2Mid from "./Dash2Mid";
import Dash2Low from "./Dash2Low";
import Dash2Act from "./Dash2Act";
import Help from "./Help";
import SuperHome from "./SuperHome";
import TeacherHome from "./TeacherHome";
import SecretaryHome from "./SecretaryHome";
import SetupPage from "./SetupPage";
import Announcements from "./Announcements";
import Backups from "./Backups";
import { OfflineUnlock } from "./offline/OfflineComponents";
import { clearOfflineData, getOfflineMetadata, loadOfflinePayload, updateOfflinePayload } from "./offline/offlineStore";
import { replayOperations } from "./offline/operationQueue";
import { useHashTab } from "./hashtab";
import "./app.css";
import "./light.css";

const Home = ({ me, d }) => (<div className="plain"><Hero me={me} d={d} />
  <Stats d={d} /></div>);

function schoolIdFor(me) {
  return me?.school?.id ?? me?.school_id ?? me?.schoolId ?? me?.school?.slug ?? null;
}

function Dash({ onOut, onOfflineBoot, offlineSession, onForget, onOfflinePrepared, onReconnect }) {
  const initialTerm = offlineSession?.payload?.context?.term || null;
  const [me, setMe] = useState(offlineSession?.payload?.identity || null);
  const [d, setD] = useState(offlineSession ? { role: "teacher", active_term: initialTerm } : null);
  const [tab, setTab] = useHashTab();
  const [syncPassphrase, setSyncPassphrase] = useState(offlineSession?.passphrase || "");
  const [offlineVaultNotice, setOfflineVaultNotice] = useState("");
  const syncing = useRef(false);
  useEffect(() => { if (offlineSession) return undefined; let alive = true; (async () => {
    try {
      const a = await api("/api/auth/me/");
      if (a.status === 401) return onOut();
      if (!a.ok) return;
      const m = await a.json(); if (!alive) return; setMe(m);
      if (m.username) {
        try {
          if (localStorage.getItem("keep") === "0") localStorage.removeItem("marian:remembered-username");
          else localStorage.setItem("marian:remembered-username", String(m.username));
        } catch { /* storage blocked */ }
      }
      const saved = await getOfflineMetadata().catch(() => null);
      if (saved && !saved.expired && (saved.username.toLowerCase() !== String(m.username || "").toLowerCase()
        || (schoolIdFor(m) != null && String(saved.schoolId) !== String(schoolIdFor(m))))) {
        setOfflineVaultNotice(`This device also contains an encrypted marks copy for ${saved.username} in a different account or school. It was not opened or deleted.`);
      } else setOfflineVaultNotice("");
      if (m.role === "school_admin" && m.setup_complete === false && !m.is_deputy && !window.location.hash) setTab("Setup");
      if (m.role === "none") return;
      if (m.role === "secretary") { setD({ role: m.role }); return; }
      if (m.role === "parent") { setD({ role: "parent" }); return; }
      const b = await api("/api/dashboard/"); if (b.ok && alive) setD(await b.json());
    } catch {
      if (alive) onOfflineBoot();
    }
  })(); return () => { alive = false; }; }, [offlineSession, onOut, onOfflineBoot, setTab]);
  useEffect(() => {
    if (!syncPassphrase || !me?.username || me.role !== "teacher") return undefined;
    let alive = true;
    let retryTimer = null;
    const sync = async () => {
      if (!navigator.onLine || syncing.current) return;
      syncing.current = true;
      try {
        const metadata = await getOfflineMetadata();
        if (!metadata || metadata.expired || metadata.username.toLowerCase() !== String(me.username).toLowerCase()
          || (schoolIdFor(me) != null && String(metadata.schoolId) !== String(schoolIdFor(me)))) return;
        const payload = await loadOfflinePayload(syncPassphrase, me.username, schoolIdFor(me));
        const next = await replayOperations(payload.operations || [], (body) => api("/api/performance/batch/", "POST", body));
        if (alive && next.some((item, index) => item.status !== payload.operations?.[index]?.status
          || item.attempts !== payload.operations?.[index]?.attempts
          || item.retry_after !== payload.operations?.[index]?.retry_after)) {
          await updateOfflinePayload(syncPassphrase, (current) => ({ ...current, operations: next }), me.username, schoolIdFor(me));
          window.dispatchEvent(new CustomEvent("marian:offline-queue-updated"));
        }
        if (retryTimer) window.clearTimeout(retryTimer);
        const retryAt = next.filter((item) => item.status === "waiting" && Number(item.retry_after) > Date.now())
          .reduce((earliest, item) => Math.min(earliest, Number(item.retry_after)), Infinity);
        if (Number.isFinite(retryAt)) retryTimer = window.setTimeout(sync, Math.max(0, retryAt - Date.now()));
      } catch { /* Keep encrypted operations visible for a later explicit retry. */ }
      finally { syncing.current = false; }
    };
    window.addEventListener("online", sync);
    window.addEventListener("marian:offline-sync-request", sync);
    if (navigator.onLine) sync();
    return () => { alive = false; if (retryTimer) window.clearTimeout(retryTimer); window.removeEventListener("online", sync); window.removeEventListener("marian:offline-sync-request", sync); };
  }, [syncPassphrase, me]);
  useEffect(() => { if (offlineSession) return undefined; const h = async () => { if (!d || !["school_admin", "teacher"].includes(d.role)) return; const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json()); }; window.addEventListener("marian:dashboard-refresh", h); return () => window.removeEventListener("marian:dashboard-refresh", h); }, [d, offlineSession]);
  const role = d && d.role;
  const need = (el) => (d.active_term ? el : <p className="plain">No active term yet. Create one in Setup first.</p>);
  const home = d && <>{role === "school_admin" ? <Dash2Top me={me} d={d} go={setTab} tabs={{ Students: 1, Teachers: 1, Exams: 1, Approve: 1, Fees: 1 }}><Dash2Low d={d} go={setTab} tabs={{ Approve: 1, Exams: 1, Reports: 1, Students: 1, Analytics: 1, Fees: 1 }} /><Dash2Mid d={d} go={setTab} /></Dash2Top> : role === "superadmin" ? <SuperHome me={me} d={d} go={setTab} /> : <Home me={me} d={d} />}{role === "teacher" && <TeacherTodo d={d} go={setTab} />}{role === "teacher" && <Mine d={d} />}{role === "school_admin" && <Dash2Act go={setTab} />}<Password /></>;
  const forgetFromWorkspace = () => {
    if (window.confirm("Forget this device? The encrypted offline marks copy and remembered username will be removed, and you will be signed out locally.")) onForget?.();
  };
  const markProps = { d, offlineIdentity: me, offlinePassphrase: syncPassphrase,
    onOfflinePrepared: (passphrase) => { setSyncPassphrase(passphrase); onOfflinePrepared?.(passphrase); }, onForget: forgetFromWorkspace };
  const baseTabs = role === "teacher" ? { Home: home, Announcements: <Announcements />, Connect: <Connect />, Feedback: <Feedback />, Calendar: <Calendar />, Marks: need(<Marks {...markProps} />), Levels: need(<LevelEntry d={d} />), Attendance: <Attendance />, ...(me && me.is_class_teacher ? { 'Report Cards': <ReportModule /> } : {}) }
    : role === "school_admin" ? { Home: home, Announcements: <Announcements />, Connect: <Connect />, Feedback: <Feedback />, Calendar: <Calendar />, Approve: <Approvals />, Exams: need(<Exams d={d} />), 'Subject Registration': <SubjectRegistration />, Reports: need(<ReportCards d={d} />), 'Report Cards': <ReportModule />, Analytics: need(<Analytics d={d} />), Attendance: <Attendance />, Fees: <Fees admin />, Documents: <BulkDocuments admin />, 'Migration Centre': <MigrationCentre />, Students: need(<Students d={d} />), Parents: <ParentAccounts />, Promotion: <Promotion />, Transfers: <TeacherTransfers />, Teachers: need(<><Teachers />{me && !me.is_deputy && <Deputies />}</>), Staff: <Staff />, Audit: <AuditLog />, Setup: <SetupPage me={me} d={d} go={setTab} /> }
    : role === "bursar" ? { Home: <BursarDashboard me={me} data={d} />, Fees: <Fees admin />, Announcements: <Announcements />, Connect: <Connect />, Documents: <BulkDocuments />, Calendar: <Calendar /> }
    : role === "parent" ? { Home: <Parent />, Announcements: <Announcements />, Connect: <Connect />, Feedback: <Feedback /> }
    : role === "secretary" ? { Home: <SecretaryHome me={me} onNavigate={setTab} />, Connect: <Connect /> }
    : role === "superadmin" ? { Home: home, Schools: <Platform d={d} />, Registrations: <RegistrationReview />, Transfers: <TeacherTransfers />, Admins: <Accounts />, Backups: <Backups />, Audit: <AuditLog />, Feedback: <Feedback owner /> }
    : d ? { Home: home } : {};
  const tabs = d ? { ...baseTabs, Help: <Help /> } : baseTabs;
  if (offlineSession) {
    return <div className="offline-workspace">
      <header className="offline-workspace__header"><div><strong>Marian · Teacher marks</strong><span>{me?.username} · {offlineSession.payload.identity.schoolName || "School"}</span></div>
        <div className="offline-workspace__actions"><button type="button" disabled={!navigator.onLine} onClick={onReconnect}>Return online to sign in / sync</button>
          <button type="button" onClick={forgetFromWorkspace}>Forget this device</button></div></header>
      <div className="offline-notice">Offline access is limited to the teacher marks context explicitly prepared on this device. Other areas are unavailable offline. Draft changes are not submitted, approved, or locked.</div>
      <Marks {...markProps} offlineMode offlinePayload={offlineSession.payload} />
    </div>;
  }
  const out = async () => {
    const saved = await getOfflineMetadata().catch(() => null);
    if (saved && !saved.expired && !window.confirm(
      "Signing out will delete this device's encrypted offline marks copy and any unsynced batches. Continue?"
    )) return;
    await clearOfflineData().catch(() => {}); await logout(); onOut();
  };
  if (me && me.role === "none") {
    return <JoinStatus me={me} out={out} />;
  }
  const cur = tabs[tab] ? tab : "Home";
  return (<Shell tabs={Object.keys(tabs)} tab={cur} go={setTab} me={me} out={out} term={d && d.active_term ? d.active_term.name : null}>
    {offlineVaultNotice && <div className="offline-notice" role="status">{offlineVaultNotice} <button type="button" onClick={async () => {
      if (window.confirm("Permanently delete the encrypted offline marks copy and any unsynced batches?")) {
        await clearOfflineData(); setOfflineVaultNotice("");
      }
    }}>Forget saved offline copy</button></div>}
    {d ? tabs[cur] : <Loading />}</Shell>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("in"));
  const [scr, setScr] = useState(() => window.location.search.includes("recovery=1") ? "recovery" : "landing");
  const [blocked, setBlocked] = useState(null);
  const [offlineRequired, setOfflineRequired] = useState(false);
  const [offlineSession, setOfflineSession] = useState(null);
  const onOut = useCallback(() => { setOk(false); setOfflineRequired(false); setOfflineSession(null); setScr("landing"); }, []);
  const onOfflineBoot = useCallback(() => setOfflineRequired(true), []);
  const forgetDevice = useCallback(async () => {
    await clearOfflineData().catch(() => {});
    try { localStorage.removeItem("marian:remembered-username"); localStorage.removeItem("in"); } catch { /* storage blocked */ }
    await logout(); onOut();
  }, [onOut]);
  useEffect(() => {
    const h = (e) => setBlocked(e.detail || "This school account is suspended.");
    window.addEventListener("marian:suspended", h);
    return () => window.removeEventListener("marian:suspended", h);
  }, []);
  const to = (x) => () => setScr(x);
  if (offlineRequired && !offlineSession) return <OfflineUnlock onUnlock={(payload, passphrase) => { setOfflineSession({ payload, passphrase }); setOfflineRequired(false); }} onForget={forgetDevice} />;
  if (blocked) return (
    <div role="alert" style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, marginBottom: 12, color: "inherit" }}>School account suspended</h1>
        <p style={{ marginBottom: 20 }}>{blocked}</p>
        <button onClick={async () => { await clearOfflineData().catch(() => {}); await logout(); setBlocked(null); onOut(); }} style={{ padding: "12px 20px", fontSize: 16 }}>Sign out</button>
      </div>
    </div>
  );
  if (ok) return <Dash onOut={onOut} onOfflineBoot={onOfflineBoot} offlineSession={offlineSession} onForget={forgetDevice}
    onReconnect={() => { setOfflineSession(null); setOfflineRequired(false); setOk(true); }}
    onOfflinePrepared={() => {}} />;
  if (scr === "login") return <Login onDone={() => { if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search); setOk(true); }} onForgot={to("recovery")} onBack={to("landing")} onJoin={to("join")} onRegister={to("school-register")} />;
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
  if (scr === "privacy") return <LegalPage kind="privacy" onBack={to("landing")} />;
  if (scr === "terms-of-service") return <LegalPage kind="terms" onBack={to("landing")} />;
  return <Landing onPrivacy={to("privacy")} onTerms={to("terms-of-service")} onStatus={to("school-status")} onStart={to("join")} onRegister={to("school-register")} onSignIn={to("login")} />;
}
