import { useState } from "react";
import { login } from "./api";
import Logo from "./Logo";
import "./backgrounds.css";
import "./login.css";

const Ic = ({ d }) => (<svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>);
const USER = "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z";
const LOCK = "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3";
const EYE = "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z";

export default function Login({ onDone }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [see, setSee] = useState(false), [err, setErr] = useState(""), [st, setSt] = useState("");
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
    <div className="fld"><Ic d={USER} /><input id="lu" placeholder="Your username" autoCapitalize="none" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} /></div>
    <div className={"pwrow" + (u.trim() ? " show" : "")}><label htmlFor="lp">Password</label>
      <div className={"fld pwf" + (st === "wait" ? " flip" : "")}><Ic d={LOCK} />
        <input id="lp" placeholder="Your password" type={see ? "text" : "password"} autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} />
        <button type="button" className="eye" onClick={() => setSee(!see)} aria-label={see ? "Hide password" : "Show password"}><Ic d={EYE} /></button></div></div>
    {p.length >= 4 && <button className="sign fade" disabled={!!st}>{st === "wait" ? "Checking..." : "Sign In  →"}</button>}
    {err && <p className="lerr">{err}</p>}
    </form><div className="seal"><Logo size={96} /></div></div></div>);
}
