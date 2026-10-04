const A = [
  ["Approve", "Approve Marks", "Approve"],
  ["Exams", "Exams", "Exams"],
  ["Reports", "Reports", "Reports"],
  ["Students", "Students", "Students"],
  ["Analytics", "Analytics", "Analytics"],
];
export default function Quick({ go, tabs }) {
  return (
    <div className="qa">
      <h3>Quick actions</h3>
      <div className="qrow">
        {A.filter(([t]) => tabs[t]).map(([t, label]) => (
          <button key={t} onClick={() => go(t)}>{label}</button>
        ))}
      </div>
    </div>
  );
}
