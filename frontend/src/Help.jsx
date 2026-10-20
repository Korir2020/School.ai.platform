import Ic from "./icons";
import "./dash2.css";

const LINKS = [
  ["Call us", "+254 703 702 690", "tel:+254703702690", "blue", "Help", false],
  ["WhatsApp", "+254 703 702 690", "https://wa.me/254703702690", "green", "Help", true],
  ["Email", "foundwithin2026@gmail.com", "mailto:foundwithin2026@gmail.com", "orange", "Help", false],
  ["Instagram", "@marian.school.ke", "https://instagram.com/marian.school.ke", "pink", "Help", true],
];

export default function Help() {
  return (
    <div className="dash2">
      <article className="d2-panel">
        <div className="d2-head"><h3>Help &amp; Support</h3></div>
        <p className="d2-muted">Need help with Marian? Reach us any of these ways.</p>
        <div className="d2-help">
          {LINKS.map(([label, text, href, tint, icon, ext]) => (
            <a key={label} href={href} className="d2-stat"
              {...(ext ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
              <span className={"d2-ico t-" + tint}><Ic n={icon} size={22} /></span>
              <span>
                <small>{label}</small>
                <b style={{ fontSize: "1rem", overflowWrap: "anywhere" }}>{text}</b>
              </span>
            </a>
          ))}
        </div>
      </article>
    </div>
  );
}
