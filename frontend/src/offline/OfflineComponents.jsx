import { useEffect, useState } from "react";
import { clearOfflineData, getOfflineMetadata, loadOfflinePayload } from "./offlineStore";
import "./offline.css";

function rememberedUsername() {
  try { return localStorage.getItem("marian:remembered-username") || ""; } catch { return ""; }
}

export function OfflineStatus() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" || navigator.onLine);
  const [reconnected, setReconnected] = useState(false);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    if (import.meta.env.PROD && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    }
    const wentOnline = () => { setOnline(true); setReconnected(true); window.setTimeout(() => setReconnected(false), 7000); };
    const wentOffline = () => { setOnline(false); setReconnected(false); };
    const beforeInstall = (event) => { event.preventDefault(); setInstallPrompt(event); };
    const appInstalled = () => { setInstalled(true); setInstallPrompt(null); };
    window.addEventListener("online", wentOnline);
    window.addEventListener("offline", wentOffline);
    window.addEventListener("beforeinstallprompt", beforeInstall);
    window.addEventListener("appinstalled", appInstalled);
    return () => {
      window.removeEventListener("online", wentOnline);
      window.removeEventListener("offline", wentOffline);
      window.removeEventListener("beforeinstallprompt", beforeInstall);
      window.removeEventListener("appinstalled", appInstalled);
    };
  }, []);

  const install = async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    setInstallPrompt(null);
  };
  return <div className={`offline-status ${online ? "is-online" : "is-offline"}`} role="status" aria-live="polite">
    <span className="offline-status__dot" aria-hidden="true" />
    <span>{online ? (reconnected ? "Back online — saved draft batches can sync." : "Online") : "Offline — only prepared teacher marks drafts are available."}</span>
    {!online && <span className="offline-status__note">No attendance, reports, receipts, attachments, or other records are available offline.</span>}
    {installPrompt && !installed && <button type="button" onClick={install}>Install app</button>}
    {installed && <span>App installed</span>}
  </div>;
}

export function OfflineUnlock({ onUnlock, onForget }) {
  const [username, setUsername] = useState(rememberedUsername);
  const [meta, setMeta] = useState(undefined);
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmForget, setConfirmForget] = useState(false);

  useEffect(() => {
    let current = true;
    getOfflineMetadata().then((value) => { if (current) setMeta(value); })
      .catch(() => { if (current) setMeta(null); });
    return () => { current = false; };
  }, []);

  const unlock = async (event) => {
    event.preventDefault();
    if (!meta || meta.expired || !username || !passphrase || busy) return;
    setBusy(true); setError("");
    try {
      const payload = await loadOfflinePayload(passphrase, username);
      onUnlock(payload, passphrase);
    } catch (cause) {
      setError(cause?.message || "Could not unlock the offline marks copy.");
    } finally { setBusy(false); }
  };

  const forget = async () => {
    await clearOfflineData();
    try { localStorage.removeItem("marian:remembered-username"); localStorage.removeItem("in"); } catch { /* storage blocked */ }
    onForget?.();
  };
  const expired = meta?.expired;
  return <main className="offline-screen">
    <section className="offline-unlock" aria-labelledby="offline-title">
      <span className="offline-kicker">Offline workspace</span>
      <h1 id="offline-title">Unlock prepared teacher marks</h1>
      <p>Use the username remembered on this device and the offline passphrase you created. Your saved copy is encrypted and available for up to seven days.</p>
      {meta === undefined ? <p role="status">Checking this device…</p> : expired ? <div className="offline-alert" role="alert">This device’s prepared marks copy has expired. Connect, sign in, and prepare it again.</div>
        : !meta ? <div className="offline-alert" role="alert">No prepared teacher marks copy was found on this device. Offline attendance, reports, receipts, attachments, and other records are not supported.</div>
          : <>
            <p className="offline-expiry">Prepared for <strong>{meta.username}</strong> · expires {new Date(meta.expiresAt).toLocaleString()}</p>
            <form onSubmit={unlock} className="offline-form">
              <label htmlFor="offline-username">Remembered username</label>
              <input id="offline-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
              <label htmlFor="offline-passphrase">Offline passphrase</label>
              <input id="offline-passphrase" type="password" autoComplete="current-password" value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)} required />
              {error && <div className="offline-alert" role="alert">{error}</div>}
              <button type="submit" disabled={busy || !passphrase || !username}>{busy ? "Unlocking…" : "Unlock offline marks"}</button>
            </form>
          </>}
      <p className="offline-security-note">This device does not store your account password, authentication token, or encryption key.</p>
      <div className="offline-forget">
        {!confirmForget ? <button className="offline-link-danger" type="button" onClick={() => setConfirmForget(true)}>Forget this device</button>
          : <div role="group" aria-label="Confirm forget this device"><p>This removes the encrypted offline copy and remembered username from this device.</p>
            <button className="offline-danger" type="button" onClick={forget}>Delete offline copy</button>
            <button type="button" onClick={() => setConfirmForget(false)}>Cancel</button></div>}
      </div>
    </section>
  </main>;
}
