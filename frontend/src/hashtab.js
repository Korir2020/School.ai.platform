import { useCallback, useState, useEffect } from "react";

const read = () => decodeURIComponent(window.location.hash.slice(1)) || "Home";

export function useHashTab() {
  const [tab, set] = useState(read);
  useEffect(() => {
    const on = () => set(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  // Stable identity: Dash keeps this in an effect dependency list, and a new
  // function on every render made that effect re-run without end.
  const go = useCallback((t) => { window.location.hash = encodeURIComponent(t); }, []);
  return [tab, go];
}
