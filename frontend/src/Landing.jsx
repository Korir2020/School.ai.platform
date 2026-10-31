import "./pub.css";
import "./home.css";
import { Button } from "./ui";
import { Mark, Wordmark } from "./brand";
import "./wall.css";
import Ic from './icons';
import Demo from './Demo';
import ThemeToggle from './ThemeToggle';

const BENEFITS = [
  ["Settled results", "Marks are entered, reviewed and locked in one place."],
  ["Reports from real marks", "Report cards are built from the marks held in Marian."],
  ["The right view for each role", "Administrators, teachers and parents see what their role allows."],
  ['Analytics', 'See how your school is doing across marks and fees, so you know where to act.'],
];

const CAPS = [
  "Marks entry, review and locking",
  "Report cards",
  "Attendance",
  "Fee management",
  "Parent portal",
  "Staff and audit log",
  "CBC, 8-4-4 and Cambridge curricula",
];

const STEPS = [
  ["Register your school", "Submit your school's details."],
  ["Get reviewed", "Your application is reviewed and approved."],
  ["Set up", "Complete the setup wizard."],
  ["Invite teachers", "Teachers join with your School Code."],
];

const BENEFIT_ICONS = ['Approve', 'Reports', 'Admins', 'Analytics'];

const MIGRATE = [
  ['Upload or paste', 'Use an Excel, CSV or typed PDF file, or paste the list.'],
  ['Check the list', 'Marian shows who is ready and anyone who is blocked.'],
  ['Fix what is blocked', 'Correct mistakes on the spot, and undo a fix if you need to.'],
  ['Add the ready learners', 'Add the ones that passed the check to your school.'],
];


const YEAR = new Date().getFullYear();

export default function Landing({ onStart, onRegister, onSignIn, onStatus, onPrivacy, onTerms }) {
  return (
    <div className="mk wall">
      <header className="mk-bar">
        <span className="mk-brand">
          <Mark size={26} />
          <Wordmark height={14} />
        </span>
        <ThemeToggle />
      </header>


      <main>
        <section className="mk-hero">
          <div>
            <p className="mk-eyebrow">Marks, report cards, attendance and fees in one place.</p>
            <h1>Run your school on clear data</h1>
            <p className="mk-lead">
              Marian brings marks, report cards, attendance, fees and parents into
              one platform, so your team can see what is happening and act on it.
            </p>
            <div className="mk-act">
              <Button kind="teal" onClick={onStart}>Get Started</Button>
              <Button kind="secondary" onClick={onSignIn}>Sign In</Button>
            </div>
            <p className="mk-sub">
              New school?{" "}
              <button type="button" className="mk-link" onClick={onRegister}>Register a school</button>
              {" · "}
              <button type="button" className="mk-link" onClick={onStatus}>Check my application</button>
            </p>
            <p className="mk-note">Joining a school? Get Started, then enter its School Code.</p>
          </div>
        </section>

        <Demo />

        <section className="mk-sec">
          <h2>Why Marian</h2>
          <div className="mk-grid c4">
            {BENEFITS.map(([t, d], i) => (
              <div className="mk-card" key={t}><span className="mk-ico"><Ic n={BENEFIT_ICONS[i]} size={18} /></span><h3>{t}</h3><p>{d}</p></div>
            ))}
          </div>
        </section>

        <section className="mk-sec">
          <h2>What you can do</h2>
          <ul className="mk-chips">
            {CAPS.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </section>

        <section className="mk-sec">
          <h2>How Marian works</h2>
          <ol className="mk-steps">
            {STEPS.map(([t, d]) => (
              <li key={t}><b>{t}</b><span>{d}</span></li>
            ))}
          </ol>
        </section>

        <section className="mk-sec">
          <h2>Bring in your existing learners</h2>
          <p className="mk-mig-lead">Moving from a register, Excel or CSV? Upload or paste your learner list. Marian checks it before anything is added.</p>
          <ol className="mk-steps">
            {MIGRATE.map(([t, d]) => (
              <li key={t}><b>{t}</b><span>{d}</span></li>
            ))}
          </ol>
          <p className="mk-mig-note">Photos of paper registers are not read yet. Use an Excel, CSV or typed PDF file.</p>
        </section>

        <section className="mk-final">
          <h2>Ready to begin?</h2>
          <p>Get started, or sign in if you already have an account.</p>
          <div className="mk-act">
            <Button kind="teal" onClick={onStart}>Get Started</Button>
            <Button kind="secondary" onClick={onSignIn}>Sign In</Button>
          </div>
        </section>
      </main>
      <footer className="mk-foot2">
        <div className="mk-fcols">
          <div><h4>Support</h4><a href="mailto:korirmartin42@gmail.com">Email support</a><a href="tel:+254703702690">Call us</a><button type="button" onClick={onStatus}>Check my application</button></div>
          <div><h4>Legal</h4><button type="button" onClick={onPrivacy}>Privacy Policy</button><button type="button" onClick={onTerms}>Terms of Service</button></div>
        </div>
        <p className="mk-foot">© {YEAR} Marian. All rights reserved.</p>
      </footer>
    </div>
  );
}
