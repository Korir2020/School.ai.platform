import Ic from "./icons";
import "./dash2.css";

const num = (v) => (v === undefined || v === null ? "\u2014" : v);

export default function Dash2Top({ me, d, go, tabs, children }) {
  const t = d.active_term;
  const name = me ? me.username : "";
  const school = me && me.school ? me.school.name : "";
  const x = d.exams || {};
  const canViewFeeData = me && me.role === "school_admin" && !me.is_deputy;
  const hasFeeData = canViewFeeData && Object.prototype.hasOwnProperty.call(d, "fees")
    && d.fees !== null && typeof d.fees === "object";
  const fees = hasFeeData ? d.fees : {};
  const examTotal =
    x.draft === undefined && x.published === undefined
      ? "\u2014"
      : (x.draft || 0) + (x.published || 0);
  const feePct =
    fees.collection_percentage === undefined || fees.collection_percentage === null
      ? "\u2014"
      : fees.collection_percentage + "%";

  // [label, value, note, tint, icon, tab]
  const cards = [
    ["Students", num(d.students), "In the school", "blue", "Students", "Students"],
    ["Enrolments", num(d.active_enrollments), "Active enrolments", "green", "Enrollments", null],
    ["Teachers", num(d.teachers), "On staff", "purple", "Teachers", "Teachers"],
    ["Streams", num(d.streams), "Active streams", "orange", "Streams", null],
    ["Subjects", num(d.subjects), "Active subjects", "pink", "Subjects", null],
    ["Examinations", examTotal, "Total examinations", "teal", "Exams", "Exams"],
    ["Marks Approval", num(d.awaiting_approval), "Pending approval", "cyan", "Approve", "Approve"],
  ];
  if (hasFeeData) cards.push(["Fee Collection", feePct, "Collected", "violet", "Fees", "Fees"]);

  return (
    <div className="dash2">
      <header className="d2-header" aria-label="Welcome">
        <div>
          <p className="d2-eyebrow">{school || "School overview"}</p>
          <h1>Welcome back, {name}</h1>
        </div>
        <div className="d2-period">
          <span>Academic year <b>{t ? t.academic_year : "\u2014"}</b></span>
          <span>Term <b>{t ? t.name : "No active term"}</b></span>
        </div>
      </header>
      <section className="d2-stats" aria-label="School statistics">
        {cards.map(([label, value, note, tint, icon, tab]) => {
          const inner = (
            <>
              <span className={"d2-ico t-" + tint}><Ic n={icon} size={22} /></span>
              <span>
                <small>{label}</small>
                <b>{value}</b>
                <em>{note}</em>
              </span>
            </>
          );
          return tab && tabs && tabs[tab] ? (
            <button type="button" key={label} className="d2-stat" onClick={() => go(tab)}>{inner}</button>
          ) : (
            <div key={label} className="d2-stat" style={{ cursor: "default" }}>{inner}</div>
          );
        })}
      </section>
      {children}
    </div>
  );
}
