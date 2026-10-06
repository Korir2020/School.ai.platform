import { useState } from "react";
import Logo from "./Logo";
import Ic from "./icons";
import Bell from "./Bell";
import Search from "./Search";
import { Modal, Button } from "./ui";
import "./shell.css";

const SETTINGS = ["Setup", "Admins"];

export default function Shell({ tabs, tab, go, me, out, children }) {
  const [more, setMore] = useState(false);
  const main = tabs.filter((t) => !SETTINGS.includes(t));
  const sets = tabs.filter((t) => SETTINGS.includes(t));
  const bar = tabs.slice(0, 4);
  const rest = tabs.slice(4);
  const pick = (t) => { setMore(false); go(t); };
  const user = me ? me.username : "";
  const school = me && me.school ? me.school.name : "";
  const item = (t) => (
    <button key={t} className={t === tab ? "on" : ""} onClick={() => pick(t)}
      aria-current={t === tab ? "page" : undefined}><Ic n={t} />{t}</button>);
  return (<div className="mu-app mu-shell">
    <div className="mu-top" role="banner"><Logo size={28} /><b>MARIAN</b><span>{user}</span><Search tabs={tabs} go={go} /><Bell go={go} /></div>
    <div className="mu-side" role="navigation" aria-label="Main">
      <div className="mu-brand"><Logo size={30} /><b>MARIAN</b></div>
      <div className="mu-nav">{main.map(item)}
        {sets.length > 0 && <small>Settings</small>}{sets.map(item)}</div>
      <div className="mu-user"><b>{user}</b><br />{school}<Search tabs={tabs} go={go} hotkey /><Bell go={go} />
        <Button kind="secondary" size="sm" onClick={out}>Log out</Button></div>
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
