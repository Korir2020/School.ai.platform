import { useEffect, useState } from "react";
import "./intro.css";
import { Mark, Wordmark } from "./brand";
export default function Intro({ onStart }) {
  const [out, setOut] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const a = setTimeout(() => setOut(true), q ? 900 : 5400);
    const b = setTimeout(onStart, q ? 1300 : 6000);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, []);
  const skip = () => { setOut(true); setTimeout(onStart, 400); };
  return (
    <div className={"intro" + (out ? " out" : "")} onClick={skip}>
        <Mark size={110} />
        <h1><Wordmark height={26} /></h1>
      <p className="itag">Marks, report cards, attendance and fees in one place.</p>
    </div>
  );
}
