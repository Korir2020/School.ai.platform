export default function Hero({ me, d }) {
  const t = d.active_term;
  const name = me ? me.username : "";
  const school = me && me.school ? me.school.name : "";
  return (
    <div className="plain hero">
      <h2>Welcome{name ? ", " + name : ""}</h2>
      <p className="sub">{school}</p>
      <span className={"term" + (t ? " live" : "")}>
        <i className="dot" />
        {t ? t.name + " " + t.academic_year : "No active term"}
      </span>
    </div>
  );
}
