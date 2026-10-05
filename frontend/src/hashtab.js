import { useState, useEffect } from "react";

const read = () => decodeURIComponent(window.location.hash.slice(1)) || "Home";

export function useHashTab() {
  const [tab, set] = useState(read);
  useEffect(() => {
    const on = () => set(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (t) => { window.location.hash = encodeURIComponent(t); };
  return [tab, go];
}
