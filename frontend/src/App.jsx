import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { logout } from "./api";
import { Loading } from "./ui";
import Login from "./Login";
import Landing from "./Landing";
import LegalPage from "./LegalPage";
import Join from "./Join";
import PasswordRecovery from "./PasswordRecovery";
import SchoolRegistration from "./SchoolRegistration";
import SchoolStatus from "./SchoolStatus";
import { OfflineUnlock } from "./offline/OfflineComponents";
import { clearOfflineData } from "./offline/offlineStore";
import "./app.css";
import "./light.css";

// Signed-in dashboards load on demand so the landing page stays small.
const Dash = lazy(() => import("./Dash"));

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
  if (ok) return <Suspense fallback={<Loading />}><Dash onOut={onOut} onOfflineBoot={onOfflineBoot} offlineSession={offlineSession} onForget={forgetDevice}
    onReconnect={() => { setOfflineSession(null); setOfflineRequired(false); setOk(true); }}
    onOfflinePrepared={() => {}} /></Suspense>;
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
