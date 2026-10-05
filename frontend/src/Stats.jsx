import { StatCard, Card, Badge } from "./ui";

const K = ["draft", "submitted", "approved", "locked"];
const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };
const hues = { draft: "#3B82F6", submitted: "#F59E0B", approved: "#16A34A",
  locked: "#0F8B8D" };
const grid = { display: "grid", gap: "12px",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" };
const meter = { display: "flex", height: 10, borderRadius: 6,
  overflow: "hidden", background: "#E2E8F0", margin: "8px 0" };

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
      <div style={grid}>
        {cards.map(([l, v, s]) => <StatCard key={l} label={l} value={v} note={s} />)}
      </div>
      <Card title="Marks overview">
        <div style={meter}>
          {K.map((k) => (m[k] ? <i key={k} style={{ flex: m[k],
            background: hues[k] }} /> : null))}
        </div>
        <div>
          {K.map((k) => <Badge key={k} kind={kinds[k]}>{k} {m[k] || 0}</Badge>)}
        </div>
        {!tot && <p>No marks entered this term yet.</p>}
      </Card>
    </>
  );
}
