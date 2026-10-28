import { useEffect, useState } from "react";
import { api, listAll } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card, DataTable, Input, Loading, Select } from "./ui";
import Receipt from './Receipt';

const money = (n) => `KES ${Number(n || 0).toLocaleString()}`;
const statusKind = { pending: "warn", partial: "info", paid: "ok", waived: "teal" };

export default function Fees({ admin = false }) {
  const toast = useToast();
  const [data, setData] = useState(null), [rows, setRows] = useState(null);
  const [years, setYears] = useState([]), [structures, setStructures] = useState([]), [students, setStudents] = useState([]), [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", amount: "", academic_year: "", due_date: "", term: "", category: "", from_grade: "", to_grade: "" });
  const [invoice, setInvoice] = useState({ student: "", fee_structure: "", amount_due: "" });
  const [history, setHistory] = useState(null), [report, setReport] = useState([]);
  const [pay, setPay] = useState(null), [payment, setPayment] = useState({ amount: "", method: "mpesa", reference: "" });
  const ITEMS = ["Tuition", "Lunch", "Activity", "Transport"];
  const [receiptId, setReceiptId] = useState(null);
  const [edit, setEdit] = useState(null);
  const [terms, setTerms] = useState([]), [billed, setBilled] = useState(null);
  const load = async () => {
    const [s, i] = await Promise.all([api("/api/fees/summary/"), listAll("/api/fees/invoices/")]);
    if (!s.ok) { setData({ error: true }); return; }
    setData(await s.json()); setRows(i);
    if (admin) {
      const [y, f, st, rp] = await Promise.all([listAll("/api/academic-years/"), listAll("/api/fees/structures/"), listAll("/api/students/"), listAll("/api/fees/report/")]);
      setYears(y); listAll("/api/terms/").then(setTerms).catch(() => {}); setStructures(f); setStudents(st);
      setReport(rp);
    }
  };
  useEffect(() => { load(); }, []);
  const createStructure = async () => {
    setBusy(true); const r = await api("/api/fees/structures/", "POST", form);
    const j = await r.json().catch(() => ({})); setBusy(false);
    toast(r.ok ? "Fee structure created" : j.detail || "Could not create fee structure", r.ok ? "ok" : "err");
    if (r.ok) setBilled(j.students_billed ?? 0);
    if (r.ok) setForm({ name: "", amount: "", academic_year: "", due_date: "", term: "", category: "", from_grade: "", to_grade: "" });
  };
  const saveEdit = async () => {
    setBusy(true);
    const r = await api(`/api/fees/structures/${edit.id}/`, "PATCH", { amount: edit.amount, category: edit.category, from_grade: edit.from_grade, to_grade: edit.to_grade });
    const j = await r.json().catch(() => ({})); setBusy(false);
    toast(r.ok ? `Saved. ${j.students_billed} new learners billed, ${j.students_updated} updated` : j.detail || "Could not save fee item", r.ok ? "ok" : "err");
    if (r.ok) { setEdit(null); load(); }
  };
  const createInvoice = async () => {
    setBusy(true); const r = await api("/api/fees/invoices/", "POST", invoice);
    const j = await r.json().catch(() => ({})); setBusy(false);
    toast(r.ok ? "Invoice assigned" : j.detail || "Could not assign fee", r.ok ? "ok" : "err");
    if (r.ok) { setInvoice({ student: "", fee_structure: "", amount_due: "" }); load(); }
  };
  const recordPayment = async () => {
    setBusy(true); const r = await api("/api/fees/payments/", "POST", { ...payment, student_fee: pay.id });
    const j = await r.json().catch(() => ({})); setBusy(false);
    toast(r.ok ? "Payment recorded" : j.detail || "Could not record payment", r.ok ? "ok" : "err");
    if (r.ok) { setPay(null); load(); }
  };
  const openHistory = async (x) => {
    const r = await api(`/api/fees/payment-history/?student_fee=${x.id}`);
    setHistory({ invoice: x, rows: r.ok ? await r.json() : [] });
  };
  const waive = async (x) => {
    if (!window.confirm(`Waive ${x.fee_name} for ${x.student_name}?`)) return;
    const r = await api(`/api/fees/invoices/${x.id}/waive/`, "POST", { reason: "Admin waiver" });
    const j = await r.json().catch(() => ({}));
    toast(r.ok ? "Fee waived" : j.detail || "Could not waive fee", r.ok ? "ok" : "err");
    if (r.ok) load();
  };
  if (!data) return <Loading />;
  if (data.error) return <Alert kind="err">Fees are not available for this account.</Alert>;
  const cols = [
    { label: "Student", get: (x) => x.student_name, sort: true },
    { label: "Fee", key: "fee_name" },
    { label: "Due", render: (x) => money(x.amount_due) },
    { label: "Balance", render: (x) => <b>{money(x.balance)}</b> },
    { label: "Status", render: (x) => <Badge kind={statusKind[x.status] || "info"}>{x.status}</Badge> },
    { label: "Action", render: (x) => <><Button size="sm" kind="ghost" onClick={() => openHistory(x)}>History</Button>{Number(x.balance) > 0 && <Button size="sm" kind="teal" onClick={() => { setPay(x); setPayment({ amount: x.balance, method: "mpesa", reference: "" }); }}>Payment</Button>}{admin && x.status !== "paid" && x.status !== "waived" && <Button size="sm" kind="danger" onClick={() => waive(x)}>Waive</Button>}</> },
  ];
  return <div className="fees-page">
    <div className="fees-kpis">
      <div><small>Collected</small><b>{money(data.amount_paid)}</b></div>
      <div><small>Outstanding</small><b>{money(data.balance)}</b></div>
      <div><small>Invoices</small><b>{data.invoices}</b><span>{data.overdue} overdue</span></div>
    </div>
    {admin && <Card title="Create fee structure">
      <div className="fee-form"><Select label="Fee item" value={ITEMS.includes(form.name) ? form.name : (form.name === "" ? "" : "__other")} onChange={e => setForm({ ...form, name: e.target.value === "__other" ? " " : e.target.value })}><option value="">Select...</option>{ITEMS.map(i => <option key={i} value={i}>{i}</option>)}<option value="__other">Other (type new)</option></Select>
      {form.name !== "" && !ITEMS.includes(form.name) && <Input label="New fee item name" placeholder="e.g. Library" value={form.name.trim() === "" ? "" : form.name} onChange={e => setForm({ ...form, name: e.target.value || " " })} />}
        <Input label="Amount (KES)" type="number" min="0" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} />
        <Select label="Academic year" value={form.academic_year} onChange={e => setForm({ ...form, academic_year: e.target.value })}><option value="">Select...</option>{years.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}</Select>
        <Input label="Due date" type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
      <Select label="Term" value={form.term} onChange={e => setForm({ ...form, term: e.target.value })}><option value="">All terms</option>{terms.filter(t => String(t.academic_year) === String(form.academic_year)).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
        <Select label="Category" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}><option value="">Everyone</option><option value="day">Day scholars</option><option value="boarder">Boarders</option></Select>
        <Input label="From grade" type="number" min="1" placeholder="All" value={form.from_grade} onChange={e => setForm({ ...form, from_grade: e.target.value })} />
        <Input label="To grade" type="number" min="1" placeholder="All" value={form.to_grade} onChange={e => setForm({ ...form, to_grade: e.target.value })} />
      </div><Button kind="teal" busy={busy} disabled={!form.name || !form.amount || !form.academic_year} onClick={createStructure}>Create structure</Button>
      {billed !== null && <p>Billed {billed} learners</p>}
    </Card>}
    {admin && <Card title="Fee items">
      {structures.length === 0 ? <p>No fee items yet.</p> : structures.map(f => <div key={f.id} className="fee-form">
        <div><b>{f.name}</b> · {money(f.amount)}{f.term_name ? ` · ${f.term_name}` : ""}{f.category ? ` · ${f.category}` : " · everyone"} · grades {f.from_grade ?? "all"} to {f.to_grade ?? "all"}</div>
        {edit && edit.id === f.id ? <>
          <Input label="Amount (KES)" type="number" min="0" value={edit.amount} onChange={e => setEdit({ ...edit, amount: e.target.value })} />
          <Select label="Category" value={edit.category} onChange={e => setEdit({ ...edit, category: e.target.value })}><option value="">Everyone</option><option value="day">Day scholars</option><option value="boarder">Boarders</option></Select>
          <Input label="From grade" type="number" min="1" placeholder="All" value={edit.from_grade} onChange={e => setEdit({ ...edit, from_grade: e.target.value })} />
          <Input label="To grade" type="number" min="1" placeholder="All" value={edit.to_grade} onChange={e => setEdit({ ...edit, to_grade: e.target.value })} />
          <Button kind="teal" busy={busy} disabled={!edit.amount} onClick={saveEdit}>Save and re-bill</Button>
          <Button kind="teal" onClick={() => setEdit(null)}>Cancel</Button>
        </> : <Button kind="teal" onClick={() => setEdit({ id: f.id, amount: f.amount, category: f.category || "", from_grade: f.from_grade ?? "", to_grade: f.to_grade ?? "" })}>Edit</Button>}
      </div>)}
    </Card>}
    {admin && <Card title="Assign fee to student">
      <div className="fee-form"><Select label="Student" value={invoice.student} onChange={e => setInvoice({ ...invoice, student: e.target.value })}><option value="">Select...</option>{students.map(s => <option key={s.id} value={s.id}>{s.first_name} {s.last_name} · {s.admission_number}</option>)}</Select>
        <Select label="Fee structure" value={invoice.fee_structure} onChange={e => { const f = structures.find(x => String(x.id) === e.target.value); setInvoice({ ...invoice, fee_structure: e.target.value, amount_due: f ? f.amount : "" }); }}><option value="">Select...</option>{structures.map(f => <option key={f.id} value={f.id}>{f.name} · {money(f.amount)}</option>)}</Select>
        <Input label="Amount due (KES)" type="number" min="0" value={invoice.amount_due} onChange={e => setInvoice({ ...invoice, amount_due: e.target.value })} />
      </div><Button kind="teal" busy={busy} disabled={!invoice.student || !invoice.fee_structure || !invoice.amount_due} onClick={createInvoice}>Assign fee</Button>
    </Card>}
    <Card title="Student fee balances"><DataTable cols={cols} rows={rows || []} search="Search student or fee" empty="No fee invoices yet" /></Card>
    {admin && <Card title="Fee report"><div className="mu-tablewrap"><table className="mu-table"><thead><tr><th>Fee</th><th>Invoices</th><th>Due</th><th>Paid</th><th>Balance</th></tr></thead><tbody>{report.map(x => <tr key={x.fee_structure}><td>{x.name}</td><td>{x.invoices}</td><td>{money(x.due)}</td><td>{money(x.paid)}</td><td><b>{money(x.balance)}</b></td></tr>)}</tbody></table></div></Card>}
    {receiptId && <Receipt paymentId={receiptId} onClose={() => setReceiptId(null)} />}{history && <div className="mu-overlay" onClick={() => setHistory(null)}><div className="mu-modal" onClick={e => e.stopPropagation()}><h3>Payment history</h3><p><b>{history.invoice.student_name}</b> · {history.invoice.fee_name}</p>{history.rows.length === 0 ? <p>No payments recorded.</p> : <div className="mu-tablewrap"><table className="mu-table"><thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Reference</th><th></th></tr></thead><tbody>{history.rows.map(x => <tr key={x.id}><td>{new Date(x.paid_at).toLocaleDateString()}</td><td>{money(x.amount)}</td><td>{x.method}</td><td>{x.reference || "—"}</td><td><Button size="sm" kind="ghost" onClick={() => setReceiptId(x.id)}>Receipt</Button></td></tr>)}</tbody></table></div>}<div className="mu-modal-actions"><Button kind="secondary" onClick={() => setHistory(null)}>Close</Button><Button kind="teal" onClick={() => window.print()}>Print</Button></div></div></div>}
    {pay && <div className="mu-overlay" onClick={() => setPay(null)}><div className="mu-modal" onClick={e => e.stopPropagation()}><h3>Record payment</h3><p><b>{pay.student_name}</b> · {pay.fee_name}<br />Balance: {money(pay.balance)}</p>
      <Input label="Amount (KES)" type="number" min="0.01" value={payment.amount} onChange={e => setPayment({ ...payment, amount: e.target.value })} />
      <Select label="Method" value={payment.method} onChange={e => setPayment({ ...payment, method: e.target.value })}><option value="mpesa">M-Pesa</option><option value="cash">Cash</option><option value="bank">Bank</option><option value="other">Other</option></Select>
      <Input label="Reference" placeholder="e.g. M-Pesa receipt" value={payment.reference} onChange={e => setPayment({ ...payment, reference: e.target.value })} />
      <div className="mu-modal-actions"><Button kind="secondary" onClick={() => setPay(null)}>Cancel</Button><Button kind="teal" busy={busy} onClick={recordPayment}>Save payment</Button></div>
    </div></div>}
  </div>;
}
