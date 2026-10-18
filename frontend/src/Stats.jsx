import { StatCard, Card, Badge } from "./ui";
import "./dashboard.css";

const K = ["draft", "submitted", "approved", "locked"];
const kinds = { draft: "info", submitted: "warn", approved: "ok", locked: "teal" };
const hues = { draft: "#3B82F6", submitted: "#F59E0B", approved: "#16A34A",
  locked: "#0F8B8D" };
const meter = { display: "flex", height: 10, borderRadius: 6,
  overflow: "hidden", background: "#E2E8F0", margin: "8px 0" };

export default function Stats({ d }) {
  const adm = d.role === "school_admin", x = d.exams || {};
  const fees = d.fees || {};
  const billed = Number(fees.invoices || 0) > 0;
  const money = (v) => "KES " + Number(v || 0).toLocaleString();
  const outstanding = Math.max(0, Number(fees.balance || 0));
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
    ["Balance", money(outstanding), billed ? `${fees.collection_percentage || 0}% collected` : "No fees billed yet"],
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
          {K.map((k) => <Badge key={k} kind={kinds[k]}>{k} {m[k] || 0}</Badge>)}
        </div>
        {!tot && <p>No marks entered this term yet.</p>}
      </Card>
      {adm && <Card title="Fee collection">
        {!billed ? <p>No fees billed yet.</p> : <>
          <div className="dash-fee">
            <div><small>Billed</small><b>{money(fees.amount_due)}</b></div>
            <div><small>Collected</small><b>{money(fees.amount_paid)}</b></div>
            <div><small>Outstanding</small><b>{money(outstanding)}</b></div>
          </div>
          <p><b>{fees.collection_percentage || 0}%</b> collected · <b>{money(fees.overdue_amount)}</b> overdue</p>
        </>}
        {billed && ((fees.recent_payments || []).length === 0 ? <p>No payments recorded yet.</p> : (fees.recent_payments || []).map((p, i) => (
          <div key={i} className="dash-payment"><span><b>{p.student}</b><small>{p.method}{p.reference ? ` · ${p.reference}` : ""}</small></span><strong>KES {Number(p.amount || 0).toLocaleString()}</strong></div>
        )))}
      </Card>}
    </>
  );
}
