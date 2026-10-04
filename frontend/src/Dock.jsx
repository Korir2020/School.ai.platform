import { useState } from "react";
const P = {
  Home: "M3 11l9-8 9 8v10h-6v-6H9v6H3z", Approve: "M5 12l5 5 9-10",
  Exams: "M6 3h9l4 4v14H6z M9 13h6 M9 17h6",
  Reports: "M8 4h8v3H8z M6 5H5v16h14V5h-1 M9 12h6 M9 16h4",
  Analytics: "M4 20V10 M10 20V4 M16 20v-7 M2 20h20",
  Marks: "M4 20l1-4L16 5l3 3L8 19z", More: "M5 12h.01 M12 12h.01 M19 12h.01",
};
const Ic = ({ n }) => <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth={n === "More" ? 3 : 1.8} strokeLinecap="round" strokeLinejoin="round"><path d={P[n] || "M12 12h.01"} /></svg>;
const MAIN = ["Home", "Approve", "Exams", "Reports", "Analytics", "Marks"];
export default function Dock({ tabs, tab, go }) {
  const [open, setOpen] = useState(false);
  const main = tabs.filter((t) => MAIN.includes(t)), rest = tabs.filter((t) => !MAIN.includes(t));
  const pick = (t) => { setOpen(false); go(t); };
  return (<>
    {open && <div className="more" onClick={() => setOpen(false)}><div onClick={(e) => e.stopPropagation()}>
      {rest.map((t) => <button key={t} className={t === tab ? "on" : ""} onClick={() => pick(t)}>{t}</button>)}</div></div>}
    <div className="dock">
      {main.map((t) => <button key={t} className={t === tab ? "on" : ""} onClick={() => pick(t)}><Ic n={t} />{t}</button>)}
      {rest.length > 0 && <button className={rest.includes(tab) || open ? "on" : ""} onClick={() => setOpen(!open)}><Ic n="More" />More</button>}
    </div></>);
}
