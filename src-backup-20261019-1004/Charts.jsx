export function TrendChart({ data = [] }) {
  const pts = data.filter((d) => d.average != null);
  if (!pts.length) return <p className="sub">No finalized averages yet.</p>;
  const W = 320, H = 150, P = 28;
  const x = (i) => (pts.length === 1 ? W / 2 : P + (i * (W - 2 * P)) / (pts.length - 1));
  const y = (v) => H - P - (Math.min(100, Math.max(0, v)) / 100) * (H - 2 * P);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.average)}`).join(" ");
  const label = "Average by term: " + pts.map((p) => `${p.term} ${p.average}%`).join(", ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} style={{ width: "100%", height: "auto", maxWidth: 520 }}>
      {[0, 50, 100].map((g) => (
        <g key={g}>
          <line x1={P} x2={W - P} y1={y(g)} y2={y(g)} stroke="#E2E8F0" />
          <text x={P - 4} y={y(g) + 3} fontSize="9" textAnchor="end" fill="#64748B">{g}</text>
        </g>
      ))}
      <path d={path} fill="none" stroke="#0F8B8D" strokeWidth="2.5" />
      {pts.map((p, i) => (
        <g key={p.term_id ?? i}>
          <circle cx={x(i)} cy={y(p.average)} r="4" fill="#0F2747" />
          <text x={x(i)} y={y(p.average) - 8} fontSize="10" textAnchor="middle" fill="#172033" fontWeight="600">{p.average}%</text>
          <text x={x(i)} y={H - 8} fontSize="9" textAnchor="middle" fill="#64748B">{String(p.term).slice(0, 12)}</text>
        </g>
      ))}
    </svg>
  );
}

export function DistributionChart({ data = [] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((a, d) => a + d.count, 0);
  if (!total) return <p className="sub">No finalized marks to chart yet.</p>;
  return (
    <div role="img" aria-label={"Mark distribution: " + data.map((d) => `${d.label}: ${d.count}`).join(", ")}>
      {data.map((d) => (
        <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 8, margin: "6px 0" }}>
          <span style={{ width: 64, fontSize: 13 }}>{d.label}</span>
          <div style={{ flex: 1, background: "#E2E8F0", borderRadius: 6, height: 14, overflow: "hidden" }}>
            <div style={{ width: `${(d.count / max) * 100}%`, height: "100%", background: "#0F8B8D" }} />
          </div>
          <b style={{ width: 36, textAlign: "right", fontSize: 13 }}>{d.count}</b>
        </div>
      ))}
    </div>
  );
}
