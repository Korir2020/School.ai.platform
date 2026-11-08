import { StatCard, Card } from "./ui";
import "./dashboard.css";

const K = ["draft", "submitted", "approved", "locked"];
const hues = { draft: "#8FB5A0", submitted: "#E0B84A", approved: "#1F7A55",
  locked: "#0A3326" };
const meter = { display: "flex", height: 10, borderRadius: 0,
  overflow: "hidden", background: "#E2DFA8", margin: "8px 0" };

export default function Stats({ d }) {
  const adm = d.role === "school_admin", x = d.exams || {};
  const m = (adm ? d.marks_by_status : d.my_marks_by_status) || {};
  const tot = K.reduce((a, k) => a + (m[k] || 0), 0);
  const pub = x.published || 0;
  const cards = adm ? [
    ["Students", d.students, "In the school"],
    ["Enrolled", d.active_enrollments, "Active enrollments"],
    ["Teachers", d.teachers, "On staff"],
    ["Streams", d.streams, "Active streams"],
    ["Subjects", d.subjects, "Active subjects"],
    ["Awaiting", d.awaiting_approval, "Marks to approve"],
    ["Exams", (x.draft || 0) + pub, pub + " published"],
  ] : [["Classes", (d.assignments || []).length, "Subjects you teach"]];
  return (
    <>
      <div className="dash-kpis">
        {cards.map(([l, v, s]) => <StatCard key={l} label={l} value={v} note={s} />)}
      </div>
      <Card title="Marks overview">
        <div style={meter}>
          {K.map((k) => (m[k] ? <i key={k} style={{ flex: m[k],
            background: hues[k] }} /> : null))}
        </div>
        <div>
          <div className="st-grid">{K.map((k) => { const n = m[k] || 0; const done = (k === "approved" || k === "locked") && n > 0; return (<div key={k} className={"st-box st-" + k + (done ? " done" : "")}><span className="st-tick"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.8" /></svg></span><b>{n}</b><small>{k}</small></div>); })}</div>
        </div>
        {!tot && <p>No marks entered this term yet.</p>}
      </Card>
    </>
  );
}
