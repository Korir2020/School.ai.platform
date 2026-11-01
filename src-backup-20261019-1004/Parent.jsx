import { useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Badge, Button, Card, EmptyState, Loading, Select } from "./ui";

const money = (n) => `KES ${Number(n || 0).toLocaleString()}`;

export default function Parent() {
  const [data, setData] = useState(null), [child, setChild] = useState(""), [term, setTerm] = useState(""), [report, setReport] = useState(null), [fees, setFees] = useState(null);
  const [bad, setBad] = useState(false);
  useEffect(() => { api("/api/parent/children/").then(async r => { if (!r.ok) throw new Error(); setData(await r.json()); }).catch(() => setBad(true)); }, []);
  const choose = async (id) => { setChild(id); setReport(null); setFees(null); if (!id) return; const r = await api(`/api/parent/children/${id}/fees/`); if (r.ok) setFees(await r.json()); };
  const openReport = async () => { if (!child || !term) return; const r = await api(`/api/report-card/${child}/${term}/`); if (r.ok) setReport(await r.json()); };
  if (bad) return <Alert kind="err">Parent information could not be loaded.</Alert>;
  if (!data) return <Loading />;
  const selected = data.children.find(x => String(x.id) === String(child));
  return <div className="parent-page">
    <Card title="My children"><Select label="Child" value={child} onChange={e => choose(e.target.value)}><option value="">Choose a child</option>{data.children.map(x => <option key={x.id} value={x.id}>{x.name} · {x.admission_number}</option>)}</Select>
      {data.children.length === 0 && <EmptyState title="No linked children" text="Please contact the school administrator." />}</Card>
    {selected && <><div className="fees-kpis"><div><small>Fee due</small><b>{money(selected.fees.due)}</b></div><div><small>Paid</small><b>{money(selected.fees.paid)}</b></div><div><small>Balance</small><b>{money(selected.fees.balance)}</b></div></div>
      <Card title="Academic report"><div className="fee-form"><Select label="Term" value={term} onChange={e => setTerm(e.target.value)}><option value="">Choose...</option>{data.terms.map(x => <option key={x.id} value={x.id}>{x.name} {x.academic_year}</option>)}</Select><Button kind="teal" disabled={!term} onClick={openReport}>View report</Button></div>
        {report && <div className="mu-tablewrap"><table className="mu-table"><thead><tr><th>Subject</th><th>Average</th></tr></thead><tbody>{report.subjects.map(x => <tr key={x.subject}><td>{x.subject}</td><td>{x.average}%</td></tr>)}</tbody></table><p><b>Overall average: {report.overall_average || "Not available"}%</b></p>{report.pending_marks > 0 && <Badge kind="warn">{report.pending_marks} marks pending</Badge>}</div>}
      </Card>
      <Card title="Fee balances">{fees && fees.length ? <div className="mu-tablewrap"><table className="mu-table"><thead><tr><th>Fee</th><th>Due</th><th>Paid</th><th>Balance</th><th>Status</th></tr></thead><tbody>{fees.map(x => <tr key={x.id}><td>{x.fee}</td><td>{money(x.amount_due)}</td><td>{money(x.amount_paid)}</td><td>{money(x.balance)}</td><td><Badge kind={x.status === "paid" ? "ok" : "warn"}>{x.status}</Badge></td></tr>)}</tbody></table></div> : <EmptyState title="No fee records" text="The school has not assigned fees yet." />}</Card>
    </>}
  </div>;
}
