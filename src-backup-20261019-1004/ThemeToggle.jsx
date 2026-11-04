import { useState } from "react";
import { getTheme, setTheme } from "./theme";
const OPTS = [["light", "Light"], ["auto", "Auto"], ["dark", "Dark"]];
export default function ThemeToggle() {
  const [t, setT] = useState(getTheme());
  return (
    <div className="m-theme" role="group" aria-label="Colour theme">
      {OPTS.map(([v, l]) => (
        <button key={v} type="button" className="m-theme-b" aria-pressed={t === v}
          onClick={() => { setTheme(v); setT(v); }}>{l}</button>
      ))}
    </div>
  );
}
