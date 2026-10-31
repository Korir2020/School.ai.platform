import { useState, useRef } from 'react';
import { Mark as Logo, Wordmark } from "./brand";
import ThemeToggle from "./ThemeToggle.jsx";
import Ic from "./icons";
import Bell from "./Bell";
import Search from './Search';
import { Modal, Button } from "./ui";
import './shell.css';

const GROUPS = [
  ['Main', ['Home', 'Calendar', 'Approve', 'Registrations']],
  ['Academics', ['Students', 'Teachers', 'Marks', 'Attendance', 'Exams', 'Reports', 'Report Cards', 'Analytics']],
  ['Manage', ['Parents', 'Staff', 'Fees', 'Documents', 'Transfers', 'Schools', 'Migration Centre']],
  ['Settings', ['Audit', 'Setup', 'Admins']],
];
const rd = (k) => { try { return localStorage.getItem(k) || ''; } catch { return ''; } };
const wr = (k, v) => { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch { /* storage blocked */ } };

export default function Shell({ tabs, tab, go, me, out, term, children }) {
  const [more, setMore] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [small, setSmall] = useState(rd('mu-small') === '1');
  const [menu, setMenu] = useState(false);
  const user = me ? me.username : '';
  const pk = 'mu-pic-' + user;
  const [pic, setPic] = useState(rd(pk));
  const fileRef = useRef(null);
  const groups = GROUPS.map(([n, l]) => [n, l.filter((t) => tabs.includes(t))]).filter((g) => g[1].length);
  const other = tabs.filter((t) => !GROUPS.some((g) => g[1].includes(t)));
  if (other.length) groups.push(['Other', other]);
  const bar = tabs.slice(0, 4);
  const rest = tabs.slice(4);
  const pick = (t) => { setMore(false); setDrawer(false); go(t); };
  const school = me && me.school ? me.school.name : "";
  const toggle = () => { const v = !small; setSmall(v); wr('mu-small', v ? '1' : ''); };
  const dropPic = () => { setPic(''); wr(pk, ''); setMenu(false); };
  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    setMenu(false);
    if (!f || !f.type.startsWith('image/')) return;
    const img = new Image();
    const url = URL.createObjectURL(f);
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = 96; c.height = 96;
      const s = Math.min(img.width, img.height);
      c.getContext('2d').drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, 96, 96);
      const d = c.toDataURL('image/jpeg', 0.8);
      URL.revokeObjectURL(url);
      setPic(d); wr(pk, d);
    };
    img.src = url;
  };
  const item = (t) => (
    <button key={t} className={t === tab ? 'on' : ''} onClick={() => pick(t)}
      data-tip={t} aria-label={t}
      aria-current={t === tab ? 'page' : undefined}><Ic n={t} /><span>{t}</span></button>);
  const avatar = <span className="mu-av">{pic ? <img src={pic} alt="" /> : (user || '?').slice(0, 2).toUpperCase()}</span>;
  const profile = (
    <div className="mu-dt-p">
      <button className="mu-dt-who" onClick={() => setMenu(!menu)} aria-haspopup="menu"
        aria-expanded={menu} aria-label="Profile menu">{avatar}<b>{user}</b></button>
      {menu && <div className="mu-shade" onClick={() => setMenu(false)} />}
      {menu && <div className="mu-dt-m" role="menu">
        <button role="menuitem" onClick={() => fileRef.current && fileRef.current.click()}>Change photo</button>
        {pic && <button role="menuitem" onClick={dropPic}>Remove photo</button>}
        <button role="menuitem" onClick={out}>Log out</button>
      </div>}
    </div>);
  return (<div className={'mu-app mu-shell' + (small ? ' small' : '')}>
    <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFile} />
    <div className="mu-top" role="banner">
      <button className="mu-burger" onClick={() => setDrawer(true)} aria-label="Open menu" aria-expanded={drawer}>☰</button>
      <h1>{tab}</h1>
      <Search tabs={tabs} go={go} /><Bell go={go} /><ThemeToggle />{profile}
    </div>
    {drawer && <div className="mu-back" onClick={() => setDrawer(false)} />}
    <div className={'mu-side' + (drawer ? ' open' : '')} role="navigation" aria-label="Main"
      onKeyDown={(e) => { if (e.key === 'Escape') setDrawer(false); }}>
      <div className="mu-brand"><Logo size={22} /><b><Wordmark height={12} /></b>
        <button className="mu-x" onClick={() => setDrawer(false)} aria-label="Close menu">✕</button>
        <button className="mu-tog" onClick={toggle} aria-expanded={!small}
          aria-label={small ? 'Expand menu' : 'Collapse menu'} data-tip={small ? 'Expand' : 'Collapse'}>{small ? '›' : '‹'}</button></div>
      <div className="mu-nav">
        {groups.map(([name, list]) => (
          <div className="mu-grp" key={name}><small>{name}</small>{list.map(item)}</div>))}
      </div>
      <div className="mu-sf">{avatar}
        <span className="mu-nm"><b>{user}</b><small>{school}</small></span>
        <button onClick={out}>Log out</button></div>
    </div>
    <div className="mu-body">
      <div className="mu-dt">
        <h1 className="mu-dt-t">{tab}</h1>
        {school && <span className="mu-dt-s">{school}</span>}
        <div className="mu-dt-r"><Search tabs={tabs} go={go} hotkey /><Bell go={go} /><ThemeToggle />{profile}</div>
      </div>
      <div className="mu-content"><nav className="mu-crumb" aria-label="Breadcrumb"><span>{school || "Platform"}</span><span aria-hidden="true"> › </span><span aria-current="page">{tab}</span></nav><h1 className="mu-title">{tab}</h1>{term && tab !== "Home" ? <p className="mu-ctx">Active term: {term}</p> : null}{children}</div>
    </div>
    <div className="mu-bar" role="navigation" aria-label="Main">
      {bar.map(item)}
      <button className={rest.includes(tab) ? 'on' : ''} onClick={() => setMore(true)}>
        <Ic n="More" /><span>More</span></button>
    </div>
    {more && <Modal title="Menu" onClose={() => setMore(false)}><div className="mu-menu">
      {rest.map((t) => <Button key={t} kind={t === tab ? 'teal' : 'secondary'}
        onClick={() => pick(t)}><Ic n={t} />{t}</Button>)}
      <Button kind="danger" onClick={out}>Log out</Button></div></Modal>}
  </div>);
}
