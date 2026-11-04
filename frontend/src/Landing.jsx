import { useEffect, useState } from "react";
import "./site.css";
import { Mark, Wordmark } from "./brand";
import Ic from "./icons";
import Demo from "./Demo";
import DemoRequestForm from "./DemoRequestForm";
import { TrendChart, DistributionChart } from "./Charts";

// Only capabilities that exist in Marian today are listed here.
const PLATFORM = [
  ["Students", "Student management", "Admission numbers, class placement, guardians, photos and a full student record. Import learners from Excel, CSV or a typed PDF."],
  ["Teachers", "Teacher management", "Teacher accounts, subject and class assignments, class teachers, deputies and teacher transfers between schools."],
  ["Admins", "School administration", "Setup wizard, school profile, academic years and terms, staff roles and a full audit log."],
  ["Students", "Classes and streams", "Class levels and streams for CBC, 8-4-4 and Cambridge, with enrolments per term."],
  ["Reports", "Subjects and papers", "Subjects, papers and maximum marks set per level, with versioned grading scales."],
  ["Approve", "Attendance", "Daily class attendance taken by teachers and visible to administrators."],
  ["Approve", "Assessments and exams", "Marks entry, paste-in marks, review, approval and locking. Exams are published only when ready."],
  ["Analytics", "Performance tracking", "Term averages, subject results and progress over time for every learner."],
  ["Analytics", "Rankings and comparisons", "Class and stream rankings, with clear handling of learners who did not sit."],
  ["Teachers", "Parent portal", "Parents see their children's results and fee balances with their own secure account."],
  ["Reports", "Fees and finance", "Fee structures, invoices, payments, waivers, arrears carry-forward, statements and verifiable receipts."],
  ["Reports", "Reports and documents", "Report cards built from approved marks, bulk report card and receipt printing, with school branding."],
  ["Announcements", "Announcements and alerts", "Send a notice to staff, all parents or one class. It arrives in the app and by email, and by SMS once the school's SMS service is switched on."],
  ["Connect", "Marian Connect", "Moderated school channels for staff and parents, with photos, documents and voice notes."],
  ["Calendar", "School calendar", "Term dates, events and closing days in one shared calendar."],
];

const INSIGHTS = [
  ["Academic performance analysis", "Term summaries by class, stream and subject from finalized marks."],
  ["Student rankings", "Positions within class and stream for each published exam."],
  ["Subject comparisons", "See which subjects lift or pull down a class average."],
  ["Performance trends", "A learner's averages charted term by term."],
  ["School analytics", "Marks and fee collection side by side for the active term."],
  ["Early-warning list", "Rule-based flags for learners whose results are dropping, with recorded interventions."],
];

const SOLUTIONS = [
  ["School administrators", ["Register and set up the school in one guided flow", "Approve marks before they reach report cards", "Track fee billing, collection and arrears"]],
  ["Headteachers and principals", ["Term-wide performance and rankings at a glance", "Early-warning list of learners who need support", "Audit log of every mark change"]],
  ["Teachers", ["Enter or paste marks for assigned classes only", "Take daily attendance", "Class teachers write report card comments"]],
  ["Students", ["Accurate report cards built from approved marks", "Progress tracked across terms", "Fair, consistent rankings"]],
  ["Parents and guardians", ["Secure parent account for each family", "Children's results and report cards", "Fee balances and payment history", "School announcements in the app, by email or SMS"]],
];

const STEPS = [
  ["Register your school", "Submit the school's details and verify your email address."],
  ["Get approved", "The Marian team reviews and approves the application. You can check its status at any time."],
  ["Complete setup", "The setup wizard walks you through the profile, terms, classes, streams and subjects."],
  ["Bring in your people", "Import learners. Teachers and staff join with your School Code and you approve them."],
  ["Run the term", "Teachers enter marks and attendance. You approve, publish and print report cards."],
];

const FAQ = [
  ["Who can register a school?", "A school administrator or headteacher registers the school. The application is reviewed before the school becomes active."],
  ["How do teachers get accounts?", "Teachers choose Get Started, enter the School Code and submit a request. A school administrator approves it. Teachers never choose their own permissions."],
  ["Which curricula are supported?", "CBC, 8-4-4 and Cambridge class levels and subjects are supported, with grading scales your school controls."],
  ["Can we bring our existing learner records?", "Yes. Upload an Excel, CSV or typed PDF file, or paste a list. Marian checks every row before anything is added. Photos of paper registers are not read yet."],
  ["Can one school see another school's data?", "No. Every account belongs to one school and every request is checked against that school on the server."],
  ["Is there a student login?", "Not yet. Students receive report cards through the school, and parents see results through the parent portal."],
  ["I forgot my password. What do I do?", "Choose Forgot password on the sign-in page. If your account has an email address, you will receive a reset link that expires after one hour."],
  ["Is our data backed up?", "Yes. The platform takes checksummed backups that are verified before they are ever restored, and your school administrator can download a full export of your school's records at any time."],
  ["Can the school send SMS to parents?", "Yes, once SMS is switched on for your school. Every announcement shows how many people will get it by app, email and SMS before you send, and parents can turn SMS or email alerts off."],
  ["How much does Marian cost?", "Pricing is agreed with each school. Request a demo and we will share a quote for your school."],
];

const SAMPLE_TREND = [
  { term_id: 1, term: "Term 1", average: 54 }, { term_id: 2, term: "Term 2", average: 58 },
  { term_id: 3, term: "Term 3", average: 61 }, { term_id: 4, term: "Term 1", average: 64 },
];
const SAMPLE_DIST = [
  { label: "80-100", count: 18 }, { label: "60-79", count: 46 }, { label: "40-59", count: 39 },
  { label: "20-39", count: 12 }, { label: "0-19", count: 3 },
];

const NAV = [["platform", "Platform"], ["features", "Features"], ["solutions", "Solutions"], ["pricing", "Pricing"], ["about", "About"], ["contact", "Contact"]];
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
            <Mark size={28} /><Wordmark height={14} />
          </a>
          <nav className="mw-nav" aria-label="Main">
            {NAV.map(([id, t]) => <a key={id} href={"#" + id} onClick={nav(id)}>{t}</a>)}
          </nav>
          <div className="mw-bar-act">
            <button type="button" className="mw-btn ghost" onClick={onSignIn}>Sign In</button>
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
        <section id="top" className="mw-hero">
          <div className="mw-wrap mw-hero-in">
            <div className="mw-hero-copy">
              <p className="mw-eyebrow">School management for Kenyan schools</p>
              <h1>One trusted record for every learner, mark and fee</h1>
              <p className="mw-lead">
                Marks scattered across spreadsheets, report cards typed by hand and fee balances nobody can confirm.
                Marian brings students, teachers, exams, report cards, attendance, fees and parents into one secure
                platform, so your school works from approved, consistent data.
              </p>
              <div className="mw-act">
                <button type="button" className="mw-btn lg" onClick={() => go("demo")}>Request a Demo</button>
                <button type="button" className="mw-btn lg ghost" onClick={onStart}>Get Started</button>
              </div>
              <p className="mw-sub">
                New school? <button type="button" className="mw-link" onClick={onRegister}>Register your school</button>
                {" · "}<button type="button" className="mw-link" onClick={onStatus}>Check my application</button>
              </p>
            </div>
            <div className="mw-hero-shot" aria-label="Marian product preview">
              <Demo />
            </div>
          </div>
        </section>

        <section id="platform" className="mw-sec">
          <div className="mw-wrap">
            <header className="mw-head">
              <p className="mw-eyebrow">Platform</p>
              <h2>Everything a school runs on, in one place</h2>
              <p>Each module works on the same school record, so a mark entered once flows to rankings, analytics and report cards.</p>
            </header>
            <div className="mw-grid c3">
              {PLATFORM.map(([icon, t, d]) => (
                <article className="mw-card" key={t}>
                  <span className="mw-ico" aria-hidden="true"><Ic n={icon} size={18} /></span>
                  <h3>{t}</h3><p>{d}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="features" className="mw-sec alt">
          <div className="mw-wrap mw-split">
            <div>
              <header className="mw-head left">
                <p className="mw-eyebrow">Intelligence and analytics</p>
                <h2>See how your school is really doing</h2>
                <p>Analytics are calculated from finalized marks only. Suggestions are rule-based and explained, and never change official records.</p>
              </header>
              <ul className="mw-list">
                {INSIGHTS.map(([t, d]) => <li key={t}><b>{t}</b><span>{d}</span></li>)}
              </ul>
            </div>
            <div className="mw-panel" aria-label="Analytics preview with sample data">
              <div className="mw-panel-top"><span>Analytics</span><span className="mw-tag">Sample data</span></div>
              <div className="mw-panel-body">
                <h4>School average by term</h4>
                <TrendChart data={SAMPLE_TREND} />
                <h4>Mark distribution, Grade 8</h4>
                <DistributionChart data={SAMPLE_DIST} />
              </div>
            </div>
          </div>
        </section>

        <section id="solutions" className="mw-sec">
          <div className="mw-wrap">
            <header className="mw-head">
              <p className="mw-eyebrow">Solutions</p>
              <h2>The right view for every role</h2>
              <p>Each person sees only what their assigned role allows, inside their own school.</p>
            </header>
            <div className="mw-grid c3">
              {SOLUTIONS.map(([t, pts]) => (
                <article className="mw-card" key={t}>
                  <h3>{t}</h3>
                  <ul className="mw-ticks">{pts.map((p) => <li key={p}>{p}</li>)}</ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="mw-sec alt">
          <div className="mw-wrap">
            <header className="mw-head">
              <p className="mw-eyebrow">How Marian works</p>
              <h2>From registration to report cards</h2>
            </header>
            <ol className="mw-steps">
              {STEPS.map(([t, d], i) => (
                <li key={t}><span className="mw-num">{i + 1}</span><div><h3>{t}</h3><p>{d}</p></div></li>
              ))}
            </ol>
          </div>
        </section>

        <section id="pricing" className="mw-sec">
          <div className="mw-wrap">
            <header className="mw-head">
              <p className="mw-eyebrow">Pricing</p>
              <h2>Pricing agreed with your school</h2>
              <p>Marian does not publish fixed price plans. We prepare a quote based on your school's size and needs after a short demo.</p>
            </header>
            <div className="mw-price">
              <div>
                <h3>What every school receives</h3>
                <ul className="mw-ticks">
                  <li>All modules listed on this page</li>
                  <li>Accounts for administrators, teachers, staff and parents</li>
                  <li>Guided setup and learner import</li>
                  <li>Email and phone support</li>
                </ul>
              </div>
              <div className="mw-price-cta">
                <p>Tell us about your school and we will send a quote.</p>
                <button type="button" className="mw-btn lg" onClick={() => go("demo")}>Request a quote</button>
              </div>
            </div>
          </div>
        </section>

        <section id="demo" className="mw-sec alt">
          <div className="mw-wrap mw-split">
            <header className="mw-head left">
              <p className="mw-eyebrow">Request a demo</p>
              <h2>See Marian with your own school in mind</h2>
              <p>Share a few details. A member of the Marian team will contact you to arrange a walkthrough and answer questions about pricing and setup.</p>
              <p className="mw-small">We use these details only to contact you about Marian. See our <button type="button" className="mw-link" onClick={onPrivacy}>Privacy Policy</button>.</p>
            </header>
            <DemoRequestForm />
          </div>
        </section>

        <section id="faq" className="mw-sec">
          <div className="mw-wrap mw-narrow">
            <header className="mw-head">
              <p className="mw-eyebrow">FAQ</p>
              <h2>Common questions</h2>
            </header>
            <div className="mw-faq">
              {FAQ.map(([q, a]) => (
                <details key={q}><summary>{q}</summary><p>{a}</p></details>
              ))}
            </div>
          </div>
        </section>

        <section id="about" className="mw-sec alt">
          <div className="mw-wrap mw-narrow mw-center">
            <p className="mw-eyebrow">About Marian</p>
            <h2>Built for schools, security first</h2>
            <p className="mw-lead">
              Marian is a school management platform built in Kenya. It is designed around a few firm principles:
              official records change only with human confirmation, every school's data is kept separate,
              and the core system works without AI.
            </p>
          </div>
        </section>

        <section className="mw-final">
          <div className="mw-wrap mw-center">
            <h2>Ready to begin?</h2>
            <p>Register your school, join one with a School Code, or sign in.</p>
            <div className="mw-act center">
              <button type="button" className="mw-btn lg" onClick={onRegister}>Register your school</button>
              <button type="button" className="mw-btn lg ghost" onClick={onSignIn}>Sign In</button>
            </div>
          </div>
        </section>
      </main>

      <footer id="contact" className="mw-foot">
        <div className="mw-wrap mw-foot-in">
          <div className="mw-foot-brand">
            <span className="mw-brand"><Mark size={26} /><Wordmark height={13} /></span>
            <p>School management for marks, report cards, attendance, fees, announcements and parents.</p>
          </div>
          <div>
            <h4>Platform</h4>
            <a href="#platform" onClick={nav("platform")}>Platform</a>
            <a href="#features" onClick={nav("features")}>Analytics</a>
            <a href="#solutions" onClick={nav("solutions")}>Solutions</a>
            <a href="#pricing" onClick={nav("pricing")}>Pricing</a>
          </div>
          <div>
            <h4>Get started</h4>
            <button type="button" onClick={onRegister}>Register your school</button>
            <button type="button" onClick={onStart}>Join a school</button>
            <button type="button" onClick={onStatus}>Check my application</button>
            <button type="button" onClick={onSignIn}>Sign In</button>
          </div>
          <div>
            <h4>Contact and support</h4>
            <a href="mailto:korirmartin42@gmail.com">korirmartin42@gmail.com</a>
            <a href="tel:+254703702690">+254 703 702 690</a>
            <a href="#faq" onClick={nav("faq")}>Help and FAQ</a>
            <a href="#demo" onClick={nav("demo")}>Request a demo</a>
          </div>
          <div>
            <h4>Company</h4>
            <a href="#about" onClick={nav("about")}>About Marian</a>
            <button type="button" onClick={onPrivacy}>Privacy Policy</button>
            <button type="button" onClick={onTerms}>Terms of Service</button>
          </div>
        </div>
        <p className="mw-wrap mw-copy">© {YEAR} Marian. All rights reserved.</p>
      </footer>
    </div>
  );
}
