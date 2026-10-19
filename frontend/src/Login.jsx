import { useState, useEffect, useRef } from "react";
import { login } from "./api";
import { Mark as Logo } from "./brand";
import ThemeToggle from "./ThemeToggle";
import "./backgrounds.css";
import "./login.css";
import "./login-pro.css";

const SUSPENDED = "This school's account is suspended. Contact Marian support.";
const WRONG = "The username or password is incorrect. Check both and try again.";
const NETWORK = "We could not reach Marian. Check your connection and try again.";
const LOCKED = "Too many sign-in attempts. Wait a minute, then try again.";
const LOCK_MS = 60000;
const USER = "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z";
const LOCK = "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3";
const EYE = "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z";
const ARROW = "M5 12h14M13 6l6 6-6 6";
const calm = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const Icon = ({ d }) => (
  <svg className="lp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);

function explain(err) {
  const m = (err && err.message) || "";
  if (/suspended/i.test(m)) return ["suspended", SUSPENDED];
  if (/too many/i.test(m)) return ["locked", LOCKED];
  if (m === "Failed to fetch") return ["error", NETWORK];
  return ["error", m || WRONG];
}

export default function Login({ onDone, onForgot }) {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [see, setSee] = useState(false);
  const [st, setSt] = useState("idle"); // idle | loading | success | error | locked | suspended
  const [msg, setMsg] = useState("");
  const timer = useRef(null);

  useEffect(() => {
    const on = () => { setSt("suspended"); setMsg(SUSPENDED); };
    window.addEventListener("marian:suspended", on);
    return () => { window.removeEventListener("marian:suspended", on); clearTimeout(timer.current); };
  }, []);

  const blocked = ["loading", "success", "locked", "suspended"].includes(st);
  const ready = u.trim() && p.length >= 4;
  const look = (e) => setTimeout(() => e.target.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" }), 350);

  const submit = async (e) => {
    e.preventDefault();
    if (blocked || !ready) return;
    setMsg(""); setSt("loading");
    try {
      await login(u.trim(), p);
      setSt("success");
      setTimeout(onDone, 350);
    } catch (x) {
      const [kind, text] = explain(x);
      setP(""); setMsg(text); setSt(kind);
      if (kind === "locked") timer.current = setTimeout(() => { setSt("idle"); setMsg(""); }, LOCK_MS);
    }
  };

  return (
    <main className="lp">
      <section className="lp-aside" aria-label="About Marian">
        <div className="lp-brand lp-brand-d"><Logo size={42} /><span>Marian</span></div>
        <div>
          <h1>Smarter Schools. Brighter Futures.</h1>
          <p>One secure workspace for your school.</p>
          <ul className="lp-list">
            <li>Marks and analytics</li><li>Classes and teachers</li>
            <li>Report cards</li><li>Parent access</li>
          </ul>
        </div>
        <span />
      </section>
      <section className="lp-panel">
        <div className="lp-card">
          <div className="lp-brand lp-brand-m"><Logo size={42} /><span>Marian</span></div>
          <h2>Sign in to Marian</h2>
          <p className="lp-intro">Use your school account to continue.</p>
          <form onSubmit={submit} noValidate>
            <label htmlFor="lp-u">Username or email</label>
            <div className="lp-field">
              <Icon d={USER} />
              <input id="lp-u" value={u} onChange={(e) => setU(e.target.value)} onFocus={look} autoComplete="username" autoCapitalize="none" disabled={blocked} />
            </div>
            <label htmlFor="lp-p">Password</label>
            <div className="lp-field">
              <Icon d={LOCK} />
              <input id="lp-p" type={see ? "text" : "password"} value={p} onChange={(e) => setP(e.target.value)} onFocus={look} autoComplete="current-password" disabled={blocked} />
              <button type="button" className="lp-eye" onClick={() => setSee(!see)} aria-pressed={see} aria-label={see ? "Hide password" : "Show password"}><Icon d={EYE} /></button>
            </div>
            <div className="lp-row"><button type="button" className="lp-link" onClick={onForgot}>Forgot password?</button></div>
            {msg && <div className={"lp-alert " + (st === "locked" ? "warn" : "err")} role="alert">{msg}</div>}
            {st === "success" && <div className="lp-alert ok" role="status">Signed in. Loading your workspace…</div>}
            <button className="lp-btn" type="submit" disabled={blocked || !ready}>
              <span>{st === "loading" ? "Checking account…" : st === "success" ? "Signed in" : "Sign in"}</span>
              {st === "idle" || st === "error" ? <Icon d={ARROW} /> : null}
            </button>
          </form>
          <p className="lp-help">Need access to a school? <span>Ask your school administrator for an invitation.</span></p>
        </div>
        <div className="lp-theme"><ThemeToggle /></div>
        <footer className="lp-foot">© Marian · Smarter Schools. Brighter Futures.</footer>
      </section>
    </main>
  );
}
