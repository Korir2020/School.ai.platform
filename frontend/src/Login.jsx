import { useState } from "react";
import { login } from "./api";
import Logo from "./Logo";
import "./backgrounds.css";
import "./login.css";

const Ic = ({ d }) => (<svg className="lic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>);
const USER = "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z";
const LOCK = "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3";
const EYE = "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z";

export default function Login({ onDone }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [see, setSee] = useState(false), [err, setErr] = useState(""), [st, setSt] = useState(""), [note, setNote] = useState("");
  const calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const go = async (e) => {
    e.preventDefault(); if (st) return; setErr(""); setSt("wait");
    const t0 = Date.now(), hold = () => new Promise((r) => setTimeout(r, Math.max(0, 1500 - (Date.now() - t0))));
    try { await login(u.trim(), p); await hold(); setSt("ok"); setTimeout(onDone, calm ? 400 : 3900); }
    catch (x) { await hold(); setP(""); setSt("bad"); setErr(x.message === "Failed to fetch" ? "Cannot reach the server. Try again." : x.message); setTimeout(() => setSt(""), 900); }
  };
  return (<div className={"lg " + st}><div className="gwrap"><i className="dog tl" /><i className="dog br" /><form className="gbox" onSubmit={go}>
    <h2>Welcome <b>Back</b></h2><p className="lsub">Enter your credentials to access your secure account</p>
    <label htmlFor="lu">Username</label>
    <div className="fld"><Ic d={USER} /><input id="lu" onFocus={(e) => setTimeout(() => e.target.scrollIntoView({ block: "center", behavior: "smooth" }), 350)} placeholder="Your username" autoCapitalize="none" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} /></div>
    <div className={"pwrow" + (u.trim() ? " show" : "")}><label htmlFor="lp">Password</label>
      <div className={"fld pwf" + (st === "wait" ? " flip" : "")}><Ic d={LOCK} />
        <input id="lp" onFocus={(e) => setTimeout(() => e.target.scrollIntoView({ block: "center", behavior: "smooth" }), 350)} placeholder="Your password" type={see ? "text" : "password"} autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} />
        <button type="button" className="eye" onClick={() => setSee(!see)} aria-label={see ? "Hide password" : "Show password"}><Ic d={EYE} /></button></div></div>
    {u.trim() && <div className="rmrow fade"><label className="rm"><input type="checkbox" defaultChecked /><span>Remember me</span></label>
      <button type="button" className="lnk" onClick={() => setNote("Forgot your password? Teachers and deputies: ask your school administrator. Administrators: contact the Marian platform owner.")}>Forgot password?</button></div>}
    {p.length >= 4 && <button className="sign fade" disabled={!!st}>{st === "wait" ? "Checking..." : "Sign In  →"}</button>}
    {err && <p className="lerr">{err}</p>}
    {p.length >= 4 && <div className="alt fade"><p className="orc">OR CONTINUE WITH</p>
      <div className="soc"><button type="button" onClick={() => setNote("Google sign-in is not available yet.")}><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.7 3.8-5.5 3.8-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.7 3.4 14.6 2.4 12 2.4 6.7 2.4 2.4 6.7 2.4 12s4.3 9.6 9.6 9.6c5.5 0 9.2-3.9 9.2-9.4 0-.6-.1-1.1-.2-1.6z"/></svg>Google</button>
      <button type="button" onClick={() => setNote("Apple sign-in is not available yet.")}><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M16.4 12.6c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9-.7 0-1.9-.8-3.1-.8-1.6 0-3.1.9-3.9 2.4-1.7 2.9-.4 7.2 1.2 9.6.8 1.2 1.8 2.5 3 2.4 1.2 0 1.7-.8 3.1-.8s1.9.8 3.1.7c1.3 0 2.1-1.2 2.9-2.3.9-1.3 1.3-2.6 1.3-2.7 0 0-2.7-1-2.7-4.1zM14.1 5.6c.6-.8 1.1-1.8.9-2.9-.9 0-2.1.6-2.7 1.4-.6.7-1.1 1.8-1 2.8 1 .1 2.1-.5 2.8-1.3z"/></svg>Apple</button></div>
      <p className="su">Don't have an account? <button type="button" className="lnk gold" onClick={() => setNote("Accounts are created by your school admin.")}>Sign Up</button></p></div>}
    {note && !err && <p className="lnote">{note}</p>}
    </form><div className="seal"><Logo size={96} /></div></div></div>);
}
