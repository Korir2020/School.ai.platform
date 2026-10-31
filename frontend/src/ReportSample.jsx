const WHO = [
  ["LEARNER", "Grace Wanjiku Otieno"],
  ["ADM NO", "2417"],
  ["CLASS", "Form 3 East"],
  ["GENDER", "F"],
  ["KCPE SCORE", "371"],
];

const BOXES = [
  ["MEAN", "71.6 (B)"],
  ["TOTAL MARKS", "573/800"],
  ["TOTAL POINTS", "26/32"],
  ["STREAM POS", "5 / 42"],
  ["GENDER POS", "2 / 24"],
  ["OVERALL POS", "9 / 118"],
];

const SUBJECTS = [
  ["English", 64, 69, 72, "B", 6, "Good"],
  ["Kiswahili", 62, 65, 68, "B", 11, "Good"],
  ["Mathematics", 74, 78, 81, "A", 3, "Excellent"],
  ["Biology", 70, 74, 77, "A", 4, "Excellent"],
  ["Chemistry", 55, 60, 63, "B", 9, "Good"],
  ["Physics", 52, 55, 58, "C", 14, "Fair"],
  ["Geography", 66, 68, 70, "B", 8, "Good"],
  ["C.R.E.", 80, 82, 84, "A", 2, "Excellent"],
];

const KEY = [
  ["A", "75–100"],
  ["B", "60–74"],
  ["C", "50–59"],
  ["D", "0–49"],
];

const TREND = [
  ["Opener", 65.4, 30, 36.9],
  ["Mid-term", 68.9, 100, 27.1],
  ["End term", 71.6, 170, 19.5],
];

function Chart() {
  const pts = TREND.map(([, , x, y]) => x + "," + y).join(" ");
  return (
    <svg viewBox="0 0 200 64" aria-hidden="true">
      {[10, 24, 38, 52].map((y) => (
        <line key={y} x1="10" x2="190" y1={y} y2={y} stroke="#E3EAE6" strokeWidth="0.6" />
      ))}
      <polyline points={pts} fill="none" stroke="#0B5D44" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {TREND.map(([name, v, x, y]) => (
        <g key={name}>
          <circle cx={x} cy={y} r="3" fill="#BEEC61" stroke="#062219" strokeWidth="1" />
          <text x={x} y={y - 6} textAnchor="middle" fontSize="7" fontWeight="700" fill="#062219">{v}</text>
          <text x={x} y="62" textAnchor="middle" fontSize="6.5" fill="#52615A">{name}</text>
        </g>
      ))}
    </svg>
  );
}

function Stamp() {
  return (
    <svg viewBox="0 0 60 60" width="58" height="58" aria-hidden="true" style={{ transform: "rotate(-12deg)" }}>
      <circle cx="30" cy="30" r="27" fill="none" stroke="#0B5D44" strokeWidth="1.6" />
      <circle cx="30" cy="30" r="22" fill="none" stroke="#0B5D44" strokeWidth="0.8" strokeDasharray="2 2" />
      <text x="30" y="28" textAnchor="middle" fontSize="6.5" fontWeight="700" fill="#0B5D44">SAMPLE</text>
      <text x="30" y="37" textAnchor="middle" fontSize="5.5" fill="#0B5D44">SCHOOL STAMP</text>
    </svg>
  );
}

function Qr() {
  const cells = [];
  for (let y = 0; y < 21; y += 1) {
    for (let x = 0; x < 21; x += 1) {
      const finder = (x < 8 && y < 8) || (x > 12 && y < 8) || (x < 8 && y > 12);
      if (!finder && (x * 7 + y * 13 + x * y) % 3 === 0) cells.push({ x, y, k: x + "-" + y });
    }
  }
  const finders = [[0, 0], [14, 0], [0, 14]];
  return (
    <svg viewBox="0 0 21 21" width="56" height="56" shapeRendering="crispEdges" aria-hidden="true">
      <rect width="21" height="21" fill="#fff" />
      {cells.map((c) => (
        <rect key={c.k} x={c.x} y={c.y} width="1" height="1" fill="#0E1A15" />
      ))}
      {finders.map(([fx, fy]) => (
        <g key={fx + "-" + fy}>
          <rect x={fx} y={fy} width="7" height="7" fill="#0E1A15" />
          <rect x={fx + 1} y={fy + 1} width="5" height="5" fill="#fff" />
          <rect x={fx + 2} y={fy + 2} width="3" height="3" fill="#0E1A15" />
        </g>
      ))}
    </svg>
  );
}

export default function ReportSample() {
  return (
    <div className="rs">
      <span className="rs-tag">SAMPLE</span>
      <header className="rs-head">
        <span className="rs-logo">SS</span>
        <div className="rs-sch">
          <b>Sample Secondary School</b>
          <small>P.O. Box 0000, Sample Town · Tel 0700 000 000</small>
          <i>“Learning for life”</i>
        </div>
        <div className="rs-ex">
          <b>REPORT CARD</b>
          <small>End of Term 2 · 2026</small>
        </div>
      </header>

      <div className="rs-who">
        {WHO.map(([k, v]) => (
          <div key={k}>
            <small>{k}</small>
            <b>{v}</b>
          </div>
        ))}
      </div>

      <div className="rs-kp">
        {BOXES.map(([k, v]) => (
          <div key={k}>
            <small>{k}</small>
            <b>{v}</b>
          </div>
        ))}
      </div>

      <table className="rs-tb">
        <thead>
          <tr>
            <th className="l">SUBJECT</th>
            <th>OPENER</th>
            <th>MID-TERM</th>
            <th>END TERM</th>
            <th>GRADE</th>
            <th>POS</th>
            <th className="l">REMARK</th>
          </tr>
        </thead>
        <tbody>
          {SUBJECTS.map(([n, a, b, c, g, p, r]) => (
            <tr key={n}>
              <td className="l">{n}</td>
              <td>{a}</td>
              <td>{b}</td>
              <td><b>{c}</b></td>
              <td>{g}</td>
              <td>{p}</td>
              <td className="l">{r}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="l">MEAN</td>
            <td>65.4</td>
            <td>68.9</td>
            <td>71.6</td>
            <td>B</td>
            <td>5</td>
            <td className="l" />
          </tr>
        </tfoot>
      </table>

      <div className="rs-mid">
        <div className="rs-box">
          <small>PERFORMANCE</small>
          <Chart />
        </div>
        <div className="rs-box">
          <small>INSIGHT</small>
          <p>Mean has risen in each of the last 3 exams.</p>
          <p>Strongest: C.R.E. (84). Focus area: Physics (58).</p>
        </div>
      </div>

      <div className="rs-rem">
        <small>CLASS TEACHER’S REMARK:</small>
        <p>Grace has worked steadily and her mean has improved. More practice in Physics will lift her further.</p>
      </div>
      <div className="rs-rem">
        <small>PRINCIPAL’S REMARK:</small>
        <p>A pleasing result. Keep up the effort.</p>
      </div>

      <div className="rs-dates">
        <span><small>CLOSING:</small>Fri 20 Nov 2026</span>
        <span><small>NEXT TERM OPENS:</small>Mon 4 Jan 2027</span>
      </div>

      <div className="rs-key">
        <small>GRADING KEY</small>
        {KEY.map(([g, r]) => (
          <span key={g}><b>{g}</b>{r}</span>
        ))}
      </div>

      <div className="rs-sign">
        <div><i /><small>CLASS TEACHER</small></div>
        <div><i /><small>PRINCIPAL</small><b>Mr. J. Sample</b></div>
        <div><Stamp /></div>
        <div><Qr /><small>VERIFY</small></div>
      </div>

      <footer className="rs-foot">
        <span>Kindly clear any school fees balance before or on the opening date.</span>
        <span>1/1</span>
      </footer>
    </div>
  );
}
