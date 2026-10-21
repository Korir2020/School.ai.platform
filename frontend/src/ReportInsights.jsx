import { useState } from "react";
import { api } from "./api";
import { Button, Card, Badge, Alert } from "./ui";

const P = "/api/report-module/";

async function errText(r) {
  try { const d = await r.json(); return d.message || d.detail || "Request failed."; }
  catch { return "Request failed (" + r.status + ")."; }
}

function Table({ head, rows }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead><tr>{head.map((h) => <th key={h} style={{ textAlign: "left", padding: "4px 8px" }}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={{ padding: "4px 8px" }}>{c ?? "-"}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export default function ReportInsights({ exam, cls, stream, prov }) {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [own, setOwn] = useState(false);

  const qs = (extra) => {
    const q = new URLSearchParams({ exam_id: exam, class_name: cls, ...extra });
    if (stream) q.set("stream", stream);
    if (prov) q.set("provisional", "1");
    return q.toString();
  };

  const load = async () => {
    setMsg(""); setData(null); setBusy(true);
    try {
      const scope = own && stream ? "stream" : "overall";
      const rs = await Promise.all([
        api(P + "analytics/?" + qs({})),
        api(P + "rankings/?" + qs({ scope })),
        api(P + "support-list/?" + qs({})),
      ]);
      const bad = rs.find((x) => !x.ok);
      if (bad) setMsg(await errText(bad));
      else setData({ a: await rs[0].json(), r: await rs[1].json(), s: await rs[2].json() });
    } catch { setMsg("Could not reach the server."); }
    finally { setBusy(false); }
  };

  const save = async (fmt) => {
    setMsg("");
    try {
      const r = await api(P + "export/" + fmt + "/?" + qs({}));
      if (!r.ok) { setMsg(await errText(r)); return; }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = "results." + fmt;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch { setMsg("Download failed."); }
  };

  const g = data && data.a, rk = data && data.r, sp = (data && data.s) || [];
  return (
    <Card title="Class insights">
      {stream && <p><label><input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} /> Rank within this stream only</label></p>}
      <p>
        <Button onClick={load} disabled={busy}>{busy ? "Loading..." : "Show insights"}</Button>{" "}
        <Button onClick={() => save("csv")}>Export CSV</Button>{" "}
        <Button onClick={() => save("xlsx")}>Export Excel</Button>
      </p>
      {msg && <Alert>{msg}</Alert>}
      {g && (
        <div>
          <p><b>{g.population}</b></p>
          <p>
            <Badge>{g.assessed} assessed</Badge> <Badge>{g.eligible} eligible</Badge> <Badge kind="warn">{g.incomplete} incomplete</Badge>
            {g.mean_grade && <> <Badge>Mean {g.mean_grade}</Badge> <Badge>{g.mean_points} pts</Badge> <Badge>{g.mean_weighted_pct}%</Badge></>}
          </p>
          <p>{Object.entries(g.grade_distribution || {}).map(([k, v]) => <Badge key={k}>{k}: {v}</Badge>)}</p>
          {g.subjects && <Table head={["Subject", "Mean %", "High", "Low", "Pass %", "Done", "Pending"]}
            rows={g.subjects.map((s) => [s.subject, s.mean_weighted_pct, s.highest, s.lowest, s.pass_rate, s.assessed, s.pending])} />}
        </div>
      )}
      {rk && (
        <div>
          <p><b>Rankings</b> ({rk.included} included, ties: {String(rk.tie_policy)})</p>
          <Table head={["#", "Adm", "Name", "Stream", "Total", "Best pts", "Mean pts", "Grade"]}
            rows={(rk.rows || []).map((x) => [x.position, x.adm_no, x.name, x.stream, x.total, x.best_points, x.mean_points, x.mean_grade])} />
        </div>
      )}
      {data && (
        <div>
          <p><b>Support list</b> (for staff review, not an automatic decision)</p>
          {sp.length === 0 ? <p>No students flagged.</p> :
            <Table head={["Adm", "Stream", "Mean pts"]} rows={sp.map((x) => [x.adm_no, x.stream, x.mean_points])} />}
        </div>
      )}
    </Card>
  );
}
