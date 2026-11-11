import { useEffect } from "react";
import App from "./App";
import { ToastProvider } from "./ui";

// The opening screen (#boot) is plain HTML in index.html so the logo shows the
// moment the page opens, even on a slow phone. Once the app is ready we hold it
// for a short beat, then fade it away to reveal the landing page underneath.
const HOLD_MS = 1600;

function useBootScreen() {
  useEffect(() => {
    const el = document.getElementById("boot");
    if (!el) return;
    let seen = false;
    try { seen = !!sessionStorage.getItem("marian-boot"); } catch { /* private mode */ }
    if (seen) { el.remove(); return; }
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let gone = false;
    const leave = () => {
      if (gone) return;
      gone = true;
      try { sessionStorage.setItem("marian-boot", "1"); } catch { /* private mode */ }
      el.classList.add("out");
      setTimeout(() => el.remove(), 650);
    };
    el.addEventListener("click", leave);
    const t = setTimeout(leave, Math.max(0, (calm ? 700 : HOLD_MS) - performance.now()));
    return () => { clearTimeout(t); el.removeEventListener("click", leave); };
  }, []);
}

export default function Root() {
  useBootScreen();
  return <ToastProvider><App /></ToastProvider>;
}
