import { useEffect, useState } from "react";
import "./intro.css";
export default function Intro({ onStart }) {
  const [out, setOut] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const a = setTimeout(() => setOut(true), q ? 900 : 5400);
    const b = setTimeout(onStart, q ? 1300 : 6000);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, []);
  const skip = () => { setOut(true); setTimeout(onStart, 400); };
  return (
    <div className={"intro" + (out ? " out" : "")} onClick={skip}>
      <svg className="ilogo" viewBox="0 0 120 108" width="230" height="207" aria-label="Marian">
        <defs><linearGradient id="ib1" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#2563EB" /><stop offset=".55" stopColor="#06B6D4" /><stop offset="1" stopColor="#22C55E" /></linearGradient><linearGradient id="ib2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#fff3b0" /><stop offset=".45" stopColor="#facc15" /><stop offset="1" stopColor="#a16207" /></linearGradient></defs>
        <g className="ibook"><path d="M6 10 L46 30 L46 86 Q26 82 6 90 Z" fill="url(#ib1)" /><path d="M18 52 L46 66 L60 98 Q36 88 18 92 Z" fill="#06B6D4" opacity=".85" /></g>
        {[[70, 52, 44], [86, 40, 56], [102, 28, 68]].map(([x, y, h], i) => <rect key={x} className="ibar" style={{ animationDelay: 1.3 + i * 0.2 + "s" }} x={x} y={y} width="10" height={h} rx="1.5" fill="url(#ib2)" stroke="#000" strokeWidth="1.2" />)}
        <path className="iline" d="M62 56 L108 14" stroke="#facc15" strokeWidth="3" strokeLinecap="round" />
        {[[72, 48, 5], [88, 33, 5.5], [108, 14, 6.5]].map(([x, y, r], i) => <circle key={x} className="idot" style={{ animationDelay: 2.2 + i * 0.25 + "s" }} cx={x} cy={y} r={r} fill="#facc15" stroke="#000" strokeWidth="1.2" />)}
      </svg>
      <h1>MARIAN</h1>
      <p className="itag">Intelligent School Management</p>
      <div className="icards"><div className="ic c1"><b>92%</b><small>Pass rate</small></div><div className="ic c2"><b>+14%</b><small>Improvement</small></div></div>
    </div>
  );
}
