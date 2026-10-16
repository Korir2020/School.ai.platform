import { useState } from "react";
import { Mark } from "./brand";
import Ic from "./icons";
import { Modal, Button } from "./ui";
import "./shell.css";

const SETTINGS = ["Setup", "Admins"];

const KEY = "mu-side";
const read = () => { try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; } };

export default function Shell({ tabs, tab, go, me, out, children }) {
  const [more, setMore] = useState(false);
  const [min, setMin] = useState(read);
  const flip = () => {
    const v = !min;
    setMin(v);
    try { localStorage.setItem(KEY, v ? "1" : "0"); } catch (e) { /* ignore */ }
  };
  const main = tabs.filter((t) => !SETTINGS.includes(t));
  const sets = tabs.filter((t) => SETTINGS.includes(t));
  const bar = tabs.slice(0, 4);
  const rest = tabs.slice(4);
  const pick = (t) => { setMore(false); go(t); };
  const user = me ? me.username : "";
  const school = me && me.school ? me.school.name : "";
  const item = (t) => (
    <button key={t} data-tip={t} aria-label={t} className={t === tab ? "on" : ""} onClick={() => pick(t)}
      aria-current={t === tab ? "page" : undefined}><Ic n={t} size={18} /><span>{t}</span></button>);
  return (<div className={"mu-app mu-shell" + (min ? " min" : "")}>
    <div className="mu-top" role="banner"><Mark size={28} /><b>MARIAN</b><span>{user}</span></div>
    <div className="mu-side" role="navigation" aria-label="Main">
      <div className="mu-brand"><Mark size={30} /><b>MARIAN</b></div>
      <div className="mu-nav">{main.map(item)}
        {sets.length > 0 && <small>Settings</small>}{sets.map(item)}</div>
      <div className="mu-user"><span className="mu-av" aria-hidden="true">{user.charAt(0).toUpperCase()}</span><div className="mu-uname"><b>{user}</b><small>{school}</small></div><button className="mu-out" data-tip="Log out" aria-label="Log out" onClick={out}><Ic n="Out" size={18} /></button></div>
      <button className="mu-tog" data-tip={min ? "Expand" : "Collapse"} aria-expanded={!min} aria-label={min ? "Expand sidebar" : "Collapse sidebar"} onClick={flip}><Ic n={min ? "Right" : "Left"} size={18} /><span>Collapse</span></button>
    </div>
    <div className="mu-body">
      <div className="mu-content"><h1 className="mu-title">{tab}</h1>{children}</div>
    </div>
    <div className="mu-bar" role="navigation" aria-label="Main">
      {bar.map(item)}
      <button className={rest.includes(tab) ? "on" : ""} onClick={() => setMore(true)}>
        <Ic n="More" />More</button>
    </div>
    {more && <Modal title="Menu" onClose={() => setMore(false)}><div className="mu-menu">
      {rest.map((t) => <Button key={t} kind={t === tab ? "teal" : "secondary"}
        onClick={() => pick(t)}><Ic n={t} />{t}</Button>)}
      <Button kind="danger" onClick={out}>Log out</Button></div></Modal>}
  </div>);
}
