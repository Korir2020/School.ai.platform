export default function Mine({ d }) {
  const a = d.assignments || [];
  return (
    <div className="act">
      <h3>My classes</h3>
      {!a.length && <p className="sub">No classes assigned yet. Ask the administrator.</p>}
      {a.map((x) => (
        <div className="arow" key={x.id}>
          <span><b>{x.subject}</b></span>
          <em>{x.class_level} {x.stream}</em>
        </div>))}
    </div>
  );
}
