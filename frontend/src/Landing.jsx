import { useEffect, useState } from "react";
import "./site.css";
import { Mark, Wordmark } from "./brand";
import Ic from "./icons";
import Demo from "./Demo";
import DemoRequestForm from "./DemoRequestForm";
import { TrendChart } from "./Charts";

// Only capabilities that exist in Marian today are described on this page.
const NAV = [["migration", "Migration Centre"], ["platform", "Platform"], ["analytics", "Analytics"], ["demo", "Request a demo"]];

const FORMATS = ["Excel", "CSV", "TSV", "TXT", "Typed PDF", "Pasted records"];

const MIGRATE_STEPS = [
  ["Upload or paste", "Bring the learner list you already have, from another system or a spreadsheet."],
  ["Check every row", "Marian matches your columns and flags anything missing or duplicated."],
  ["Confirm and import", "Nothing is saved until you approve. Learners land in the right class."],
];

const PREVIEW_ROWS = [
  ["Grace Otieno", "2417", "Grade 7 East", "ok"],
  ["Brian Mwangi", "2402", "Grade 7 East", "ok"],
  ["Amina Hassan", "—", "Grade 7 West", "warn"],
  ["Kevin Kiprop", "2411", "Grade 7 West", "ok"],
  ["Faith Njeri", "2402", "Grade 7 East", "dup"],
];

const MODULES = [
  ["Students", "Learners and classes", "Admissions, streams, guardians and a complete learner record."],
  ["Marks", "Exams and marks", "Teachers enter or paste marks; you review, approve and lock."],
  ["Reports", "Report cards", "Branded report cards built only from approved marks, printed in bulk."],
  ["Fees", "Fees and receipts", "Invoices, payments, arrears, statements and verifiable receipts."],
  ["Attendance", "Attendance", "Daily class registers taken by teachers, visible to administrators."],
  ["Parents", "Parents and notices", "A secure parent portal, with announcements by app, email or SMS."],
];

const INSIGHTS = [
  ["Performance by class, stream and subject", "Calculated from finalized marks only."],
  ["Fair rankings", "Class and stream positions, with learners who did not sit handled clearly."],
  ["Progress over time", "Every learner's average charted term by term."],
  ["Early-warning list", "Rule-based flags for learners whose results are dropping."],
];

const SUBJECTS = [["Mathematics", 71], ["English", 66], ["Integrated Science", 62], ["Kiswahili", 58]];
const SAMPLE_TREND = [
  { term_id: 1, term: "Term 1", average: 54 }, { term_id: 2, term: "Term 2", average: 58 },
  { term_id: 3, term: "Term 3", average: 61 }, { term_id: 4, term: "Term 1", average: 64 },
];

const YEAR = new Date().getFullYear();

function go(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  history.replaceState(null, "", "#" + id);
}

export default function Landing({ onStart, onRegister, onSignIn, onStatus, onPrivacy, onTerms }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id && document.getElementById(id)) setTimeout(() => go(id), 50);
  }, []);
  useEffect(() => {
    if (!open) return;
    const k = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);
  const nav = (id) => (e) => { e.preventDefault(); setOpen(false); go(id); };

  return (
    <div className="mw">
      <a className="mw-skip" href="#main">Skip to content</a>

      <header className="mw-bar">
        <div className="mw-wrap mw-bar-in">
          <a href="#top" className="mw-brand" onClick={nav("top")} aria-label="Marian home">
            <Mark size={30} /><Wordmark height={14} />
          </a>
          <nav className="mw-nav" aria-label="Main">
            {NAV.map(([id, t]) => <a key={id} href={"#" + id} onClick={nav(id)}>{t}</a>)}
          </nav>
          <div className="mw-bar-act">
            <button type="button" className="mw-btn text" onClick={onSignIn}>Sign In</button>
            <button type="button" className="mw-btn" onClick={onStart}>Get Started</button>
          </div>
          <button type="button" className="mw-burger" aria-expanded={open} aria-controls="mw-menu" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            <span /><span /><span />
          </button>
        </div>
        <div id="mw-menu" className={"mw-menu" + (open ? " on" : "")} hidden={!open}>
          {NAV.map(([id, t]) => <a key={id} href={"#" + id} onClick={nav(id)}>{t}</a>)}
          <div className="mw-menu-act">
            <button type="button" className="mw-btn ghost" onClick={onSignIn}>Sign In</button>
            <button type="button" className="mw-btn" onClick={onStart}>Get Started</button>
          </div>
        </div>
      </header>

      <main id="main">
        {/* Hero */}
        <section id="top" className="mw-hero">
          <div className="mw-wrap mw-hero-in">
            <div className="mw-hero-copy">
              <p className="mw-eyebrow">School management for Kenyan schools</p>
              <h1>The trusted record for every learner, mark and fee.</h1>
              <p className="mw-lead">
                Marks, report cards, attendance, fees and parents in one secure platform,
                built for CBC, 8-4-4 and Cambridge.
              </p>
              <div className="mw-act">
                <button type="button" className="mw-btn lg" onClick={onRegister}>Register your school</button>
                <button type="button" className="mw-btn lg ghost" onClick={() => go("demo")}>Request a demo</button>
              </div>
              <p className="mw-sub">
                Joining a school? <button type="button" className="mw-link" onClick={onStart}>Use your School Code</button>
                <span aria-hidden="true"> · </span>
                <button type="button" className="mw-link" onClick={onStatus}>Check my application</button>
              </p>
            </div>
            <div className="mw-hero-shot" aria-label="Marian product preview: generating report cards for a class">
              <Demo />
            </div>
          </div>
          <div className="mw-wrap">
            <ul className="mw-trust" aria-label="Why schools trust Marian">
              <li><Ic n="Admins" size={18} /><span>Each school's data kept separate</span></li>
              <li><Ic n="Approve" size={18} /><span>Marks approved before report cards</span></li>
              <li><Ic n="Audit" size={18} /><span>Every change recorded in an audit log</span></li>
              <li><Ic n="Backups" size={18} /><span>Verified backups and full data export</span></li>
            </ul>
          </div>
        </section>

        {/* Migration Centre */}
        <section id="migration" className="mw-sec mw-migrate">
          <div className="mw-wrap mw-split mid">
            <div className="mw-migrate-copy">
              <p className="mw-eyebrow">Migration Centre</p>
              <h2>Switch to Marian without retyping a single learner.</h2>
              <p className="mw-lead">
                Already on another system, or keeping records in spreadsheets? Bring your existing learner
                list straight into Marian, checked row by row before anything is saved.
              </p>
              <ul className="mw-formats" aria-label="Supported formats">
                {FORMATS.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <ol className="mw-msteps">
                {MIGRATE_STEPS.map(([t, d], i) => (
                  <li key={t}><span className="mw-num">{i + 1}</span><div><h3>{t}</h3><p>{d}</p></div></li>
                ))}
              </ol>
              <p className="mw-note">The Migration Centre imports learner records. Other school history is set up in Marian as you go.</p>
            </div>

            <div className="mw-window mw-mc" aria-label="Migration Centre preview with sample data">
              <div className="mw-window-top">
                <span className="mw-dots" aria-hidden="true"><i /><i /><i /></span>
                <span>Migration Centre</span>
                <span className="mw-tag">Sample</span>
              </div>
              <div className="mw-mc-body">
                <div className="mw-mc-file">
                  <span className="mw-mc-ext">XLSX</span>
                  <div><b>Grade7_register.xlsx</b><small>218 rows · 5 columns matched</small></div>
                  <span className="mw-pill ok">Checked</span>
                </div>
                <table className="mw-mc-table">
                  <thead><tr><th>Name</th><th>Adm. no.</th><th className="hide-sm">Class</th><th><span className="sr">Status</span></th></tr></thead>
                  <tbody>
                    {PREVIEW_ROWS.map(([n, a, c, s]) => (
                      <tr key={n} className={s}>
                        <td>{n}</td><td>{a}</td><td className="hide-sm">{c}</td>
                        <td>{s === "ok" ? <span className="mw-pill ok">Ready</span> : s === "warn" ? <span className="mw-pill warn">Missing no.</span> : <span className="mw-pill err">Duplicate</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mw-mc-foot">
                  <p><b>214 ready</b> · 4 need your attention</p>
                  <span className="mw-mc-btn">Import 214 learners</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Platform */}
        <section id="platform" className="mw-sec">
          <div className="mw-wrap">
            <div className="mw-head">
              <p className="mw-eyebrow">The platform</p>
              <h2>Everything your school runs on, connected.</h2>
              <p>A mark entered once flows to rankings, analytics and report cards — no copying between systems.</p>
            </div>
            <div className="mw-modules">
              {MODULES.map(([icon, t, d]) => (
                <article key={t}>
                  <span className="mw-ico" aria-hidden="true"><Ic n={icon} size={20} /></span>
                  <h3>{t}</h3><p>{d}</p>
                </article>
              ))}
            </div>
            <p className="mw-also">Also included: school calendar, Marian Connect channels, staff roles and teacher transfers.</p>
          </div>
        </section>

        {/* Analytics */}
        <section id="analytics" className="mw-sec mw-alt">
          <div className="mw-wrap mw-split mid">
            <div>
              <p className="mw-eyebrow">Analytics and reporting</p>
              <h2>Know how every class is really doing.</h2>
              <p className="mw-lead">
                Exams are reviewed, approved and locked before results are published, so every report and chart
                rests on marks you trust.
              </p>
              <ul className="mw-list">
                {INSIGHTS.map(([t, d]) => (
                  <li key={t}><span className="mw-check" aria-hidden="true"><Ic n="Approve" size={14} /></span><div><b>{t}</b><span>{d}</span></div></li>
                ))}
              </ul>
            </div>
            <div className="mw-window" aria-label="Analytics preview with sample data">
              <div className="mw-window-top">
                <span className="mw-dots" aria-hidden="true"><i /><i /><i /></span>
                <span>Grade 8 · Term 1 analysis</span>
                <span className="mw-tag">Sample</span>
              </div>
              <div className="mw-an">
                <div className="mw-kpis">
                  <div><small>Mean score</small><b>64.2%</b><em>+3.1 on last term</em></div>
                  <div><small>Learners</small><b>118</b><em>3 streams</em></div>
                  <div><small>Flagged</small><b>7</b><em>Early warning</em></div>
                </div>
                <div className="mw-an-grid">
                  <div className="mw-an-card">
                    <h4>School average by term</h4>
                    <TrendChart data={SAMPLE_TREND} />
                  </div>
                  <div className="mw-an-card">
                    <h4>Subject means</h4>
                    <ul className="mw-bars">
                      {SUBJECTS.map(([s, v]) => (
                        <li key={s}><span>{s}</span><i style={{ "--v": v + "%" }} /><b>{v}</b></li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Demo + final call to action */}
        <section id="demo" className="mw-sec mw-cta">
          <div className="mw-wrap mw-split">
            <div className="mw-cta-copy">
              <p className="mw-eyebrow">Get started</p>
              <h2>See Marian with your school in mind.</h2>
              <p className="mw-lead">
                Tell us about your school. We'll arrange a walkthrough, help you plan your migration and share a
                quote — pricing is agreed with each school.
              </p>
              <div className="mw-act">
                <button type="button" className="mw-btn lg" onClick={onRegister}>Register your school</button>
                <button type="button" className="mw-btn lg ghost" onClick={onStatus}>Check application status</button>
              </div>
              <dl className="mw-contact">
                <div><dt>Email</dt><dd><a href="mailto:korirmartin42@gmail.com">korirmartin42@gmail.com</a></dd></div>
                <div><dt>Phone</dt><dd><a href="tel:+254703702690">+254 703 702 690</a></dd></div>
              </dl>
              <p className="mw-small">We use these details only to contact you about Marian. See our <button type="button" className="mw-link" onClick={onPrivacy}>Privacy Policy</button>.</p>
            </div>
            <DemoRequestForm />
          </div>
        </section>
      </main>

      <footer id="contact" className="mw-foot">
        <div className="mw-wrap mw-foot-in">
          <div className="mw-foot-brand">
            <span className="mw-brand"><Mark size={28} /><Wordmark height={13} /></span>
            <p>School management for learners, marks, report cards, attendance, fees and parents.</p>
          </div>
          <div>
            <h4>Product</h4>
            <a href="#migration" onClick={nav("migration")}>Migration Centre</a>
            <a href="#platform" onClick={nav("platform")}>Platform</a>
            <a href="#analytics" onClick={nav("analytics")}>Analytics</a>
            <a href="#demo" onClick={nav("demo")}>Request a demo</a>
          </div>
          <div>
            <h4>Get started</h4>
            <button type="button" onClick={onRegister}>Register your school</button>
            <button type="button" onClick={onStart}>Join a school</button>
            <button type="button" onClick={onStatus}>Check my application</button>
            <button type="button" onClick={onSignIn}>Sign In</button>
          </div>
          <div>
            <h4>Contact</h4>
            <a href="mailto:korirmartin42@gmail.com">korirmartin42@gmail.com</a>
            <a href="tel:+254703702690">+254 703 702 690</a>
          </div>
          <div>
            <h4>Legal</h4>
            <button type="button" onClick={onPrivacy}>Privacy Policy</button>
            <button type="button" onClick={onTerms}>Terms of Service</button>
          </div>
        </div>
        <p className="mw-wrap mw-copy">© {YEAR} Marian. All rights reserved.</p>
      </footer>
    </div>
  );
}
