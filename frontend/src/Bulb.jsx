import "./bulb.css";

/* Fixed wall + bulb. Sits behind the page; only the writing scrolls. */
export default function Bulb() {
  return (
    <div className="bulb-scene" aria-hidden="true">
      <div className="ambient-light" />
      <div className="bulb-container">
        <div className="bulb-cord" />
        <div className="bulb-glow" />
        <div className="light-beam" />
        <div className="bulb-art">
          <svg viewBox="0 0 170 250" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <defs>
              <linearGradient id="mkb-metal" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#171719" />
                <stop offset="18%" stopColor="#49494b" />
                <stop offset="36%" stopColor="#222225" />
                <stop offset="65%" stopColor="#555458" />
                <stop offset="85%" stopColor="#252528" />
                <stop offset="100%" stopColor="#101113" />
              </linearGradient>
              <linearGradient id="mkb-glass" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#fff5ce" stopOpacity=".48" />
                <stop offset="25%" stopColor="#ffe7a1" stopOpacity=".12" />
                <stop offset="55%" stopColor="#ffffff" stopOpacity=".04" />
                <stop offset="82%" stopColor="#ffc86a" stopOpacity=".12" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity=".25" />
              </linearGradient>
              <radialGradient id="mkb-fg">
                <stop offset="0%" stopColor="#fffef0" />
                <stop offset="35%" stopColor="#fff1a5" />
                <stop offset="75%" stopColor="#ffb62e" />
                <stop offset="100%" stopColor="#ff9c16" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="mkb-il">
                <stop offset="0%" stopColor="#fff5c0" stopOpacity=".88" />
                <stop offset="45%" stopColor="#ffd66e" stopOpacity=".25" />
                <stop offset="100%" stopColor="#ffc45c" stopOpacity="0" />
              </radialGradient>
              <filter id="mkb-fb"><feGaussianBlur stdDeviation="5" /></filter>
              <filter id="mkb-sg"><feGaussianBlur stdDeviation="2.5" /></filter>
            </defs>

            <path d="M69 17 L101 17 L101 34 L105 42 L65 42 L69 34 Z" fill="url(#mkb-metal)" stroke="#111214" strokeWidth="1.5" />
            <path d="M63 38 Q60 38 60 43 L60 86 Q60 91 66 91 L104 91 Q110 91 110 86 L110 43 Q110 38 104 38 Z" fill="url(#mkb-metal)" stroke="#090a0b" strokeWidth="2" />

            <g fill="none" strokeLinecap="round">
              <path d="M62 46 H108" stroke="#77767a" strokeWidth="1.3" />
              <path d="M61 52 H109" stroke="#090a0b" strokeWidth="2" />
              <path d="M61 59 H109" stroke="#6c6b70" strokeWidth="1.1" />
              <path d="M61 65 H109" stroke="#08090a" strokeWidth="2" />
              <path d="M61 72 H109" stroke="#5b5a5e" strokeWidth="1.1" />
              <path d="M62 79 H108" stroke="#09090a" strokeWidth="2" />
              <path d="M64 85 H106" stroke="#68676b" strokeWidth="1" />
            </g>

            <path
              d="M70 88 C69 98 64 104 55 113 C41 127 34 145 36 165 C38 188 53 207 70 214 C76 217 94 217 100 214 C117 207 132 188 134 165 C136 145 129 127 115 113 C106 104 101 98 100 88 Z"
              fill="url(#mkb-glass)" stroke="#f4dca7" strokeOpacity=".72" strokeWidth="1.5"
            />

            <ellipse cx="85" cy="164" rx="47" ry="51" fill="url(#mkb-il)" />
            <g filter="url(#mkb-fb)" opacity=".95"><ellipse cx="85" cy="160" rx="20" ry="24" fill="#ffb52e" /></g>

            <path d="M81 93 L81 140 L85 153 L89 140 L89 93" fill="#fff4c6" fillOpacity=".35" stroke="#ffdfa0" strokeOpacity=".65" strokeWidth="1" />

            <g fill="none" stroke="#ffe8a8" strokeWidth="1.1" strokeLinecap="round">
              <path d="M81 134 L76 158" />
              <path d="M89 134 L94 158" />
              <path d="M85 146 L85 169" />
            </g>

            <path d="M76 158 L79 153 L82 158 L85 153 L88 158 L91 153 L94 158" fill="none" stroke="#ffbc3c" strokeWidth="6" opacity=".9" filter="url(#mkb-sg)" />
            <path d="M76 158 L79 153 L82 158 L85 153 L88 158 L91 153 L94 158" fill="none" stroke="#fff4b0" strokeWidth="1.8" strokeLinejoin="round" />

            <circle cx="85" cy="156" r="13" fill="url(#mkb-fg)" />
            <ellipse cx="85" cy="156" rx="6" ry="4" fill="#fffde8" />

            <path d="M53 126 Q42 145 46 163" fill="none" stroke="#ffffff" strokeOpacity=".55" strokeWidth="2" strokeLinecap="round" />
            <path d="M58 120 Q54 125 52 132" fill="none" stroke="#ffffff" strokeOpacity=".4" strokeWidth="1.2" strokeLinecap="round" />
            <path d="M116 130 Q126 146 122 160" fill="none" stroke="#fff4d0" strokeOpacity=".5" strokeWidth="2" strokeLinecap="round" />
            <path d="M62 197 Q85 210 108 197" fill="none" stroke="#ffe9bd" strokeOpacity=".55" strokeWidth="1.3" />

            <ellipse cx="47" cy="174" rx="2" ry="4" fill="#fff7e2" opacity=".55" />
            <ellipse cx="121" cy="175" rx="1.5" ry="3" fill="#fff5dc" opacity=".45" />
          </svg>
        </div>
      </div>
    </div>
  );
}
