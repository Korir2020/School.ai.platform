import { useEffect, useState } from "react";
import { Icon } from "./icons";
import "./site.css";

// `go` is the App.jsx screen setter. Existing screens are reused:
// login, join, school-register, privacy, terms.
const LINKS = [
  ["site-school", "School Management"],
  ["site-learning", "Personalized Learning"],
];

export function LogoMark({ inverted }) {
  return (
    <svg viewBox="0 0 40 40" className={"mw-lm" + (inverted ? " is-ring" : "")} aria-hidden="true">
      <rect width="40" height="40" rx="12" className="mw-lm-bg" />
      <path d="M9 29V12l11 10 11-10v17" fill="none" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" className="mw-lm-line" />
      <circle cx="9" cy="12" r="3.2" className="mw-lm-a" />
      <circle cx="31" cy="12" r="3.2" className="mw-lm-b" />
    </svg>
  );
}

export function Logo({ go, inverted }) {
  return (
    <button type="button" className="mw-logo" onClick={() => go("site-home")} aria-label="MARIAN home">
      <LogoMark inverted={inverted} />
      <span className={"mw-logo-text" + (inverted ? " is-inv" : "")}>MARIAN</span>
    </button>
  );
}

export function SiteHeader({ go, active }) {
  const [open, setOpen] = useState(false);
  const nav = (to) => { setOpen(false); go(to); };
  return (
    <header className="mw-header">
      <div className="mw-container mw-header-row">
        <Logo go={go} />
        <nav className="mw-nav" aria-label="Main">
          {LINKS.map(([to, label]) => (
            <button key={to} type="button" className={"mw-navlink" + (active === to ? " is-active" : "")} onClick={() => nav(to)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="mw-header-cta">
          <button type="button" className="mw-btn mw-btn--ghost mw-btn--sm" onClick={() => nav("login")}>Sign in</button>
          <button type="button" className="mw-btn mw-btn--ink mw-btn--sm mw-pill" onClick={() => nav("join")}>Get started</button>
        </div>
        <button type="button" className="mw-burger" onClick={() => setOpen((o) => !o)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
          <Icon name={open ? "close" : "menu"} s={20} />
        </button>
      </div>
      {open && (
        <div className="mw-mobile">
          <nav className="mw-container mw-mobile-nav" aria-label="Mobile">
            {LINKS.map(([to, label]) => (
              <button key={to} type="button" className="mw-mobile-link" onClick={() => nav(to)}>{label}</button>
            ))}
            <div className="mw-mobile-cta">
              <button type="button" className="mw-btn mw-btn--quiet mw-btn--lg mw-pill" onClick={() => nav("login")}>Sign in</button>
              <button type="button" className="mw-btn mw-btn--ink mw-btn--lg mw-pill" onClick={() => nav("join")}>Get started</button>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

export function SiteFooter({ go }) {
  return (
    <footer className="mw-footer">
      <div className="mw-container mw-footer-grid">
        <div className="mw-footer-brand">
          <Logo go={go} inverted />
          <p>School Management and Personalized Learning on one platform — for CBC and everything beyond it.</p>
        </div>
        <div>
          <h3 className="mw-eyebrow mw-gold">Platform</h3>
          <ul className="mw-footer-list">
            <li><button type="button" onClick={() => go("site-school")}>School Management</button></li>
            <li><button type="button" onClick={() => go("site-learning")}>Personalized Learning</button></li>
            <li><button type="button" onClick={() => go("school-register")}>Register a school</button></li>
          </ul>
        </div>
        <div>
          <h3 className="mw-eyebrow mw-gold">Learning</h3>
          <ul className="mw-footer-list mw-footer-plain">
            <li>CBC (Grades 1–12)</li>
            <li>Computer Science</li>
            <li>Life Skills</li>
            <li>Languages &amp; Arts</li>
          </ul>
        </div>
      </div>
      <div className="mw-footer-bar">
        <div className="mw-container mw-footer-bar-row">
          <p>© 2026 MARIAN. All rights reserved.</p>
          <p>
            <button type="button" onClick={() => go("privacy")}>Privacy</button>
            {" · "}
            <button type="button" onClick={() => go("terms-of-service")}>Terms</button>
          </p>
        </div>
      </div>
    </footer>
  );
}

export function PageShell({ go, active, children }) {
  useEffect(() => { window.scrollTo(0, 0); }, [active]);
  return (
    <div className="mw">
      <SiteHeader go={go} active={active} />
      <main className="mw-main">{children}</main>
      <SiteFooter go={go} />
    </div>
  );
}
