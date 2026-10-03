import "./welcome.css";

function Kid({ x, skin, shirt, i = 0, girl, cls = "", look = 0, children }) {
  return (<g transform={`translate(${x} 612)`} className={cls}><g className="kid" style={{ animationDelay: i * 0.4 + "s" }}>
    <rect x="-17" y="-46" width="34" height="46" rx="11" fill={shirt} />
    <g className="hd">
      <circle cx="0" cy="-60" r="15" fill={skin} />
      {girl && <><circle cx="-14" cy="-70" r="6" fill="#1b1209" /><circle cx="14" cy="-70" r="6" fill="#1b1209" /></>}
      <path d="M-15 -64 Q0 -82 15 -64 Q0 -71 -15 -64Z" fill="#1b1209" />
      <circle cx={-5 + look} cy="-60" r="1.8" fill="#111" /><circle cx={5 + look} cy="-60" r="1.8" fill="#111" />
      <path d="M-5 -54 Q0 -49 5 -54" stroke="#111" strokeWidth="1.7" fill="none" strokeLinecap="round" />
    </g>
    {children}
  </g></g>);
}

export default function Scene({ stage = "" }) {
  return (<svg className={"bg scene " + stage} viewBox="28 0 310 640" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#020b24" /><stop offset=".55" stopColor="#0b2a6b" /><stop offset=".85" stopColor="#0e7490" /><stop offset="1" stopColor="#f59e0b" /></linearGradient>
      <radialGradient id="lt" cx=".5" cy=".75" r=".8"><stop offset="0" stopColor="#fffbe0" /><stop offset=".55" stopColor="#ffd45a" /><stop offset="1" stopColor="#f59e0b" /></radialGradient>
      <linearGradient id="spill" x1="1" y1="0" x2="0" y2="0"><stop offset="0" stopColor="#ffd27a" stopOpacity=".55" /><stop offset="1" stopColor="#ffd27a" stopOpacity="0" /></linearGradient>
      <radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#ffd45a" stopOpacity=".5" /><stop offset="1" stopColor="#ffd45a" stopOpacity="0" /></radialGradient>
    </defs>
    <rect width="360" height="640" fill="url(#sky)" />
    <g fill="#fff">{[[40, 70], [326, 110], [44, 200], [322, 260], [38, 330], [328, 400]].map(([a, b]) => <circle key={a} cx={a} cy={b} r="1.2" opacity=".7" />)}</g>
    <circle cx="92" cy="548" r="44" fill="#fbbf24" opacity=".9" />
    <path d="M0 560 Q90 520 180 555 T360 540 L360 640 L0 640Z" fill="#0b3b4a" />
    <path d="M0 596 Q120 572 240 598 T360 590 L360 640 L0 640Z" fill="#06202b" />
    <circle className="halo" cx="296" cy="565" r="78" fill="url(#halo)" />
    <rect x="262" y="480" width="68" height="134" rx="5" fill="#0b2f3d" stroke="#1e3a78" />
    <rect x="266" y="487" width="60" height="19" rx="4" fill="#0b1d46" stroke="#e0b17a" />
    <text x="296" y="500.5" textAnchor="middle" fontSize="10.5" fontWeight="800" letterSpacing="2.4" fill="#fff4d1" fontFamily="system-ui,sans-serif">MARIAN</text>
    <path d="M274 612 V534 Q274 514 296 514 Q318 514 318 534 V612Z" fill="#2a1a0c" />
    <path className="lgt" d="M274 612 V534 Q274 514 296 514 Q318 514 318 534 V612Z" fill="url(#lt)" />
    <path className="flare" d="M274 612 V534 Q274 514 296 514 Q318 514 318 534 V612Z" fill="#fffbe0" />
    <path d="M274 612 V534 Q274 516 281 515 L270 522 V609Z" fill="#6e381e" stroke="#e0b17a" strokeWidth="1.5" />
    <path className="beam" d="M274 612 L318 612 L300 640 L170 640Z" fill="url(#spill)" />
    <path className="beam" d="M276 524 L180 566 L180 612 L276 612Z" fill="url(#spill)" />
    <Kid x={54} skin="#5b3a29" shirt="#8b5cf6" i={0}><path d="M-15 -34 L0 -30 L15 -34 L15 -15 L0 -11 L-15 -15Z" fill="#F8FAFC" /><path d="M0 -30 V-11" stroke="#94a3b8" /></Kid>
    <Kid x={100} skin="#7a4e34" shirt="#22C55E" i={1} girl><path d="M12 -38 L24 -32" stroke="#7a4e34" strokeWidth="6" strokeLinecap="round" /><path d="M23 -38 h6 v8 l6 13 h-18 l6 -13z" fill="#34d399" /><circle className="bub" cx="26" cy="-44" r="2" fill="#a7f3d0" /><circle className="bub b2" cx="30" cy="-46" r="1.5" fill="#a7f3d0" /></Kid>
    <Kid x={148} skin="#3f2a1e" shirt="#06B6D4" i={2}><rect x="-15" y="-43" width="30" height="19" rx="2" fill="#0f172a" stroke="#22d3ee" /><path d="M-9 -37 h18 M-9 -31 h12" stroke="#22d3ee" strokeWidth="1.5" /><rect x="-18" y="-24" width="36" height="4" rx="1.5" fill="#64748b" /></Kid>
    <Kid x={196} skin="#6b4430" shirt="#f59e0b" i={3} girl><circle className="ball" cx="24" cy="-9" r="7.5" fill="#F8FAFC" stroke="#334155" /><path className="ball" d="M18 -9 h12 M24 -16 v14" stroke="#334155" strokeWidth="1" /></Kid>
    <Kid x={238} skin="#5b3a29" shirt="#2563EB" cls="me"><path className="arm" d="M13 -38 L24 -54" stroke="#5b3a29" strokeWidth="6" strokeLinecap="round" /></Kid>
  </svg>);
}
