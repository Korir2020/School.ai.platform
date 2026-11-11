import { useEffect } from "react";
import App from "./App";
import { ToastProvider } from "./ui";
import { bootDelay, BOOT_FADE_MS } from "./landing-boot";

// The opening screen (#boot) is plain HTML in index.html so the logo shows the
// moment the page opens, even on a slow phone. Once the app is ready we hold it
// for no more than half a second including the fade; slower loads add no hold.

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
      setTimeout(() => el.remove(), BOOT_FADE_MS);
    };
    el.addEventListener("click", leave);
    const t = setTimeout(leave, bootDelay(performance.now(), calm));
    return () => { clearTimeout(t); el.removeEventListener("click", leave); };
  }, []);
}

export default function Root() {
  useBootScreen();
  return <ToastProvider><App /></ToastProvider>;
}
