import Logo from "./Logo";
import "./welcome.css";

const acts = ["Mark entry", "Approvals", "Exams and ranks", "Report cards", "Analytics", "Student progress"];
const kids = [[70, "#5b3a29", "#2563EB"], [180, "#7a4e34", "#22C55E"], [290, "#3f2a1e", "#06B6D4"]];

function Kid({ x, skin, shirt, i }) {
  return (<g transform={`translate(${x} 610)`}><g className="kid" style={{ animationDelay: i * 0.4 + "s" }}>
    <rect x="-17" y="-46" width="34" height="46" rx="11" fill={shirt} />
    <circle cx="0" cy="-60" r="15" fill={skin} />
    <path d="M-15 -64 Q0 -82 15 -64 Q0 -71 -15 -64Z" fill="#1b1209" />
    <circle cx="-5" cy="-60" r="1.8" fill="#111" /><circle cx="5" cy="-60" r="1.8" fill="#111" />
    <path d="M-5 -54 Q0 -49 5 -54" stroke="#111" strokeWidth="1.7" fill="none" strokeLinecap="round" />
    <rect x="12" y="-34" width="15" height="19" rx="2" fill="#F8FAFC" />
  </g></g>);
}

function Scene() {
  return (<svg className="bg" viewBox="0 0 360 640" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#020b24" /><stop offset=".55" stopColor="#0b2a6b" /><stop offset=".85" stopColor="#0e7490" /><stop offset="1" stopColor="#f59e0b" />
    </linearGradient></defs>
    <rect width="360" height="640" fill="url(#sky)" />
    <circle cx="260" cy="520" r="46" fill="#fbbf24" opacity=".85" />
    <path d="M0 560 Q90 520 180 555 T360 540 L360 640 L0 640Z" fill="#0b3b4a" />
    <path d="M0 595 Q120 570 240 598 T360 590 L360 640 L0 640Z" fill="#06202b" />
    <g fill="#06202b"><rect x="38" y="470" width="6" height="90" /><ellipse cx="41" cy="468" rx="44" ry="11" /><ellipse cx="62" cy="456" rx="30" ry="8" /></g>
    {kids.map(([x, skin, shirt], i) => <Kid key={x} x={x} skin={skin} shirt={shirt} i={i} />)}
  </svg>);
}

export default function Welcome({ onStart }) {
  return (<div className="welcome"><Scene />
    <div className="wc"><Logo size={92} /><h1>MARIAN</h1><p className="tag">Intelligent School Management</p>
      <ul className="acts">{acts.map((a, i) => <li key={a} style={{ animationDelay: 0.3 + i * 0.15 + "s" }}>{a}</li>)}</ul>
      <button className="go" onClick={onStart}>Log in</button></div></div>);
}
