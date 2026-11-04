import { useEffect, useState } from "react";
import Logo from "./Logo";

const stages = ["Students", "Learning", "Assessment", "Analytics", "Insights"];

export default function Splash({ onDone }) {
  const [out, setOut] = useState(false);
  const leave = () => { setOut(true); setTimeout(onDone, 3000); };
  useEffect(() => { const t = setTimeout(leave, 3200); return () => clearTimeout(t); }, []);
  return (
    <div className={"splash" + (out ? " out" : "")} onClick={leave}>
      <div className="glow" />
      <div className="brand">
        <Logo size={96} />
        <div><h1>MARIAN</h1><p>Intelligent School Management</p></div>
      </div>
      <ol className="path">{stages.map((s, i) => <li key={s} style={{ animationDelay: 1 + i * 0.3 + "s" }}><i />{s}</li>)}</ol>
    </div>
  );
}
