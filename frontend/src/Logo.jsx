import { useId } from "react";

const BARS = [
  ["M560 624 L598 608 V672 L560 645 Z", "#0a9b5c"],
  ["M610 598 L655 585 V690 L632 712 L610 690 Z", "#0b6fa8"],
  ["M668 572 L716 548 V650 L668 672 Z", "#0a9b5c"],
];

export default function Logo({ size = 64, full = false }) {
  const u = useId().replace(/:/g, "");
  const vb = full ? "130 100 1000 1020" : "280 130 690 640";
  const ratio = full ? 1.02 : 0.93;
  return (
    <svg width={size} height={size * ratio} viewBox={vb} role="img" aria-label="Marian">
      <defs>
        <linearGradient id={`m${u}`} x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#0a3585" /><stop offset=".55" stopColor="#0b5bc4" /><stop offset="1" stopColor="#0a86f0" /></linearGradient>
        <linearGradient id={`b${u}`} x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#0a3f9e" /><stop offset="1" stopColor="#0a86f0" /></linearGradient>
        <linearGradient id={`g${u}`} x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#0a9b5c" /><stop offset="1" stopColor="#6fd04a" /></linearGradient>
        <linearGradient id={`a${u}`} x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#0a9b5c" /><stop offset="1" stopColor="#4fc24a" /></linearGradient>
        <g id={`w${u}`}>
          <path d="M335 630 L352 590 C500 598 580 660 627 722 C560 665 460 636 335 630 Z" />
          <path d="M288 708 L310 652 C470 652 580 700 640 745 L627 752 C560 700 430 684 288 708 Z" />
        </g>
      </defs>
      <path fill={`url(#m${u})`} d="M355 248 C440 252 510 295 580 360 L627 405 L674 360 C744 295 814 252 900 248 V572 L785 597 V392 L627 525 L470 392 V597 L355 572 Z" />
      <use href={`#w${u}`} fill={`url(#b${u})`} />
      <use href={`#w${u}`} fill={`url(#g${u})`} transform="translate(1255 0) scale(-1 1)" />
      {BARS.map(([d, c], i) => (
        <path key={i} className="bar" d={d} fill={c} style={{ animationDelay: 0.15 * i + "s", transformBox: "fill-box", transformOrigin: "50% 100%" }} />
      ))}
      <path d="M540 608 Q645 590 720 508" fill="none" stroke={`url(#a${u})`} strokeWidth="16" strokeLinecap="round" />
      <path fill="#3db54a" d="M744 472 L695 492 L737 525 Z" />
      <g stroke="#fff" strokeWidth="10" strokeLinejoin="round">
        <path fill="#0a3d99" d="M440 212 L627 138 L815 212 L627 290 Z" />
        <path fill="#0a2a73" d="M517 260 L627 292 L737 260 V305 L627 360 L517 305 Z" />
        <rect x="777" y="300" width="26" height="42" rx="10" fill="#0a2a73" />
      </g>
      <path d="M790 228 V305" stroke="#0a2a73" strokeWidth="8" strokeLinecap="round" />
      {full && (
        <>
          <text x="627" y="985" textAnchor="middle" fontSize="285" fontWeight="900" fill="#0b2f66" textLength="955" lengthAdjust="spacingAndGlyphs">Marian</text>
          <text x="627" y="1075" textAnchor="middle" fontSize="56" fontWeight="500" fill="#1b3a66" textLength="955" lengthAdjust="spacingAndGlyphs">Smarter Schools. Brighter Futures.</text>
        </>
      )}
    </svg>
  );
}
