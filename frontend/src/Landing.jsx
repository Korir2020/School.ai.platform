import "./pub.css";
import "./home.css";
import { Button } from "./ui";
import { Mark, Wordmark } from "./brand";
import "./wall.css";
import Ic from './icons';
import ThemeToggle from './ThemeToggle';

const NAV = ["Home", "Students", "Exams", "Reports", "Analytics", "Fees"];

const BENEFITS = [
  ["Settled results", "Marks are entered, reviewed and locked in one place."],
  ["Reports from real marks", "Report cards are built from the marks held in Marian."],
  ["The right view for each role", "Administrators, teachers and parents see what their role allows."],
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

const BENEFIT_ICONS = ['Approve', 'Reports', 'Admins'];

function Preview() {
  return (
    <div>
      <div className="mk-pv" role="img" aria-label="Illustration of the Marian dashboard">
        <aside>
          {NAV.map((n, i) => (
            <span key={n} className={i === 4 ? "on" : ""}>{n}</span>
          ))}
        </aside>
        <div className="mk-pv-main">
          <div className="mk-pv-top"><b>Analytics</b><i /></div>
          <div className="mk-pv-cards">
            {["Students", "Exams", "Reports"].map((n) => (
              <div key={n}><small>{n}</small><span /></div>
            ))}
          </div>
          <div className="mk-pv-chart">
            {[40, 62, 48, 75, 58, 84, 70].map((h, i) => (
              <span key={i} style={{ height: h + "%" }} />
            ))}
          </div>
        </div>
      </div>
      <p className="mk-cap">Illustration, not real data</p>
    </div>
  );
}

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
            <p className="mk-eyebrow">Turning School Data Into Better Decisions.</p>
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
          <Preview />
        </section>

        <section className="mk-sec">
          <h2>Why Marian</h2>
          <div className="mk-grid c3">
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

        <section className="mk-final">
          <h2>Ready to begin?</h2>
          <p>Register your school, or sign in if you already have an account.</p>
          <div className="mk-act">
            <Button kind="teal" onClick={onRegister}>Register a school</Button>
            <Button kind="secondary" onClick={onSignIn}>Sign In</Button>
          </div>
        </section>
      </main>
      <footer className="mk-foot2">
        <div className="mk-fcols">
          <div><h4>Platform</h4><span>Academic analytics</span><span>School management</span><span>Parent access</span></div>
          <div><h4>Access</h4><button type="button" onClick={onSignIn}>Sign In</button><button type="button" onClick={onRegister}>Register a school</button><button type="button" onClick={onStart}>Join a school</button></div>
          <div><h4>Support</h4><a href="mailto:korirmartin42@gmail.com">Email support</a><a href="tel:+254703702690">Call us</a><button type="button" onClick={onStatus}>Check my application</button></div><div><h4>Legal</h4><button type="button" onClick={onPrivacy}>Privacy Policy</button><button type="button" onClick={onTerms}>Terms of Service</button></div>
        </div>
        <p className="mk-foot">Marian · Turning School Data Into Better Decisions.</p>
      </footer>
    </div>
  );
}
