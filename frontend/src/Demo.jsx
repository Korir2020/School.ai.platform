import { useEffect, useRef, useState } from "react";
import ReportSample from "./ReportSample";
import "./demo.css";

const PLAN = [
  [600, 1],
  [2300, 2],
  [2800, 3],
  [4400, 4],
  [8000, 5],
  [15300, 6],
];
const END = 16000;
const CAPS = [
  "Choose the class and the exam",
  "Choose the class and the exam",
  "One tap to generate",
  "Building every report card…",
  "Printing the whole class",
  "A complete report for every learner",
];
const LEARNERS = [
  ["Grace Otieno", "2417"],
  ["Brian Mwangi", "2402"],
  ["Amina Hassan", "2419"],
  ["Kevin Kiprop", "2411"],
  ["Faith Njeri", "2425"],
  ["Daniel Wafula", "2408"],
  ["Mercy Achieng", "2421"],
  ["Peter Kamau", "2414"],
];
const SHEETS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13];
const STEPS = [1, 2, 3, 4, 5, 6];

export default function Demo() {
  const [step, setStep] = useState(0);
  const [vis, setVis] = useState(false);
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(0.5);
  const [calm] = useState(
    () =>
      typeof window === "undefined" ||
      !("IntersectionObserver" in window) ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  const stage = useRef(null);
  const pageRef = useRef(null);
  const closeBtn = useRef(null);

  useEffect(() => {
    const el = stage.current;
    if (calm || !el) return undefined;
    const io = new IntersectionObserver(([e]) => setVis(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, [calm]);

  useEffect(() => {
    if (calm || !vis) return undefined;
    let ids = [];
    const run = () => {
      setStep(0);
      ids = PLAN.map(([t, s]) => setTimeout(() => setStep(s), t));
      ids.push(setTimeout(run, END));
    };
    run();
    return () => ids.forEach((id) => clearTimeout(id));
  }, [calm, vis]);

  useEffect(() => {
    const el = pageRef.current;
    if (!el || !("ResizeObserver" in window)) return undefined;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / 595));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    if (closeBtn.current) closeBtn.current.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const cur = calm ? 5 : step;
  const cls = "dm" + STEPS.filter((n) => cur >= n).map((n) => " s" + n).join("");

  return (
    <section className="mk-sec dm-sec">
      <h2>See Marian in action</h2>
      <p className="dm-lead">From marks to a printed report card for every learner, in a few taps.</p>

      <div className={cls} ref={stage} role="img" aria-label="Animated demo: generating and printing report cards for a whole class">
        <div className="dm-win" aria-hidden="true">
          <div className="dm-bar">
            <i />
            <i />
            <i />
            <span>Report Cards</span>
          </div>
          <div className="dm-body">
            <div className="dm-head">
              <div>
                <b>Form 3 East</b>
                <small>End of Term 2</small>
              </div>
              <span className="dm-btnwrap">
                <span className="dm-btn">{cur >= 3 ? "Generating…" : "Generate reports"}</span>
                <span className="dm-ripple" />
                <span className="dm-cur">
                  <svg viewBox="0 0 24 24" width="24" height="24">
                    <path d="M4 2l15 9-6.5 1.6L9 19z" fill="#fff" stroke="#111" strokeWidth="1.4" strokeLinejoin="round" />
                  </svg>
                </span>
              </span>
            </div>
            <ul className="dm-rows">
              {LEARNERS.map(([n, a]) => (
                <li key={a}>
                  <span>{n}</span>
                  <small>{a}</small>
                  <em>Ready</em>
                </li>
              ))}
            </ul>
            <div className="dm-prog"><i /></div>
          </div>
        </div>

        <div className="dm-print" aria-hidden="true">
          <div className="dm-printer">
            <svg viewBox="0 0 240 100">
              <rect x="72" y="0" width="96" height="26" rx="3" fill="#e7efe9" />
              <rect x="10" y="18" width="220" height="82" rx="14" fill="#0B2E22" stroke="rgba(190,236,97,.28)" />
              <rect x="26" y="34" width="64" height="9" rx="4.5" fill="rgba(255,255,255,.14)" />
              <circle cx="206" cy="39" r="4" fill="#BEEC61" />
              <rect x="42" y="91" width="156" height="9" rx="3" fill="#03140E" />
            </svg>
          </div>
          <div className="dm-pile">
            {SHEETS.map((n) => (
              <span
                key={n}
                className="dm-sheet"
                style={{ "--i": n, "--dx": ((n * 37) % 17) - 8, "--r": ((n * 53) % 9) - 4 }}
              />
            ))}
          </div>
        </div>

        <div className="dm-shade" />
        <div className="dm-page" ref={pageRef} aria-hidden="true">
          <div className="dm-scale" style={{ transform: `scale(${scale})` }}>
            <ReportSample />
          </div>
        </div>
      </div>

      <p className="dm-cap">{CAPS[Math.min(cur, 5)]}</p>
      <div className="dm-act">
        <button type="button" className="dm-view" onClick={() => setOpen(true)}>
          View the sample report full size
        </button>
      </div>
      <p className="dm-note">Sample data for demonstration. Not a real school or learner.</p>

      {open && (
        <div className="dm-modal" role="dialog" aria-modal="true" aria-label="Sample report card">
          <div className="dm-modal-top">
            <span>Sample report card</span>
            <button type="button" className="dm-close" ref={closeBtn} onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <div className="dm-modal-scroll">
            <div className="dm-modal-page">
              <ReportSample />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
