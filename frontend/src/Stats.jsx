const K = ["draft", "submitted", "approved", "locked"];
export default function Stats({ d }) {
  const adm = d.role === "school_admin", x = d.exams || {};
  const m = (adm ? d.marks_by_status : d.my_marks_by_status) || {};
  const tot = K.reduce((a, k) => a + (m[k] || 0), 0);
  const cards = adm ? [
    ["Students", d.students, "In the school"],
    ["Enrolled", d.active_enrollments, "Active enrollments"],
    ["Teachers", d.teachers, "On staff"],
    ["Streams", d.streams, "Active streams"],
    ["Subjects", d.subjects, "Active subjects"],
    ["Awaiting", d.awaiting_approval, "Marks to approve"],
    ["Exams", (x.draft || 0) + (x.published || 0), (x.published || 0) + " published"],
  ] : [["Classes", (d.assignments || []).length, "Subjects you teach"]];
  return (<>
    <div className="cards">{cards.map(([l, v, s]) => (
      <div className="kpi" key={l}><small>{l}</small><b>{v ?? 0}</b><em>{s}</em></div>))}</div>
    <div className="mo"><h3>Marks overview</h3>
      <div className="meter">{K.map((k) => m[k] ? <i key={k} className={"s-" + k} style={{ flex: m[k] }} /> : null)}</div>
      <div className="legend">{K.map((k) => <span key={k}><i className={"s-" + k} />{k} <b>{m[k] || 0}</b></span>)}</div>
      {!tot && <p className="sub">No marks entered this term yet.</p>}
    </div></>);
}
