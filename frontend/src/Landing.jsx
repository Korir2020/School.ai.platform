import { useEffect } from "react";
import Logo from "./Logo";
import { Button } from "./ui";
import "./pub.css";
import "./landing.css";

const I = {
  book: ["M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z",
    "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"],
  up: ["M23 6l-9.5 9.5-5-5L1 18", "M17 6h6v6"],
  check: ["M22 11.08V12a10 10 0 1 1-5.93-9.14", "M22 4L12 14.01l-3-3"],
  smile: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
    "M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"],
  award: ["M12 15a7 7 0 1 0 0-14 7 7 0 0 0 0 14z",
    "M8.21 13.89L7 23l5-3 5 3-1.21-9.12"],
  flag: ["M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z",
    "M4 22v-7"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"],
  zap: ["M13 2L3 14h9l-1 8 10-12h-9l1-8z"],
  star: ["M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88" +
    "L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"],
  users: ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2",
    "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "M23 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
};

const CH = [
  ["Learning", "Discover. Explore. Understand.", "book", "#0F8B8D"],
  ["Academic Excellence", "Learn. Improve. Excel.", "up", "#2563EB"],
  ["Assessment", "Measure. Understand. Improve.", "check", "#4F46E5"],
  ["Student Development", "Knowledge. Character. Confidence.", "smile", "#16A34A"],
  ["Talent & Sports", "Discover Talent. Build Teamwork.", "award", "#EA580C"],
  ["Leadership", "Inspire. Lead. Serve.", "flag", "#7C3AED"],
  ["Character", "Discipline. Integrity. Responsibility.", "shield", "#0F2747"],
  ["Innovation", "Imagine. Create. Transform.", "zap", "#0891B2"],
  ["Achievement", "Dream. Work. Achieve.", "star", "#CA8A04"],
  ["Community", "Together We Grow.", "users", "#0F8B8D"],
];

function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll(".mu-ld-ch");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm || !("IntersectionObserver" in window)) {
      els.forEach((e) => e.classList.add("in"));
      return undefined;
    }
    const io = new IntersectionObserver((rows) => rows.forEach((r) => {
      if (r.isIntersecting) { r.target.classList.add("in"); io.unobserve(r.target); }
    }), { threshold: 0.2 });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
}

export default function Landing({ onStart, onSignIn }) {
  useReveal();
  return (<div className="mu-ld">
    <div className="mu-ld-hero"><Logo size={76} />
      <h1>MARIAN</h1>
      <p>More than academics. We grow the whole student.</p>
      <b>Learn. Lead. Achieve.</b></div>
    <div className="mu-ld-story">
      {CH.map(([t, p, ic, c], n) => (
        <section key={t} className="mu-ld-ch" style={{ "--c": c }}>
          <svg className="mu-ld-ic" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
            strokeLinejoin="round" aria-hidden="true">
            {I[ic].map((d) => <path key={d} d={d} />)}</svg>
          <small>{String(n + 1).padStart(2, "0")} · {t.toUpperCase()}</small>
          <h2>{p}</h2></section>))}
    </div>
    <p className="mu-pub-note">Joining a school? You need its School Code.</p>
    <div className="mu-ld-bar">
      <Button kind="teal" onClick={onStart}>Get Started</Button>
      <Button kind="secondary" onClick={onSignIn}>Sign In</Button></div>
  </div>);
}
