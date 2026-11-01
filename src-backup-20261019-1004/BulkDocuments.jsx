import { useEffect, useState } from "react";
import { api, listAll } from "./api";
import { Alert, Badge, Button, Card, EmptyState, Loading, Select } from "./ui";

const download = async (response, fallback) => { const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = fallback; a.click(); URL.revokeObjectURL(url); };

export default function BulkDocuments({ admin = false }) {
  const [mode, setMode] = useState(admin ? "reports" : "receipts"), [terms, setTerms] = useState([]), [term, setTerm] = useState(""), [items, setItems] = useState([]), [selected, setSelected] = useState([]), [format, setFormat] = useState("combined"), [busy, setBusy] = useState(false), [bad, setBad] = useState("");
  const endpoint = mode === "reports" ? "/api/documents/report-cards/" : "/api/documents/fee-receipts/";
  const load = async () => { setBad(""); const query = mode === "reports" && term ? `?term_id=${term}` : ""; const r = await api(endpoint + query); if (!r.ok) return setBad("Could not load eligible documents."); const j = await r.json(); setItems(mode === "reports" ? j.students : j.payments); setSelected([]); };
  useEffect(() => { if (admin) listAll("/api/terms/").then(setTerms).catch(() => {}); }, [admin]);
  useEffect(() => { if (mode === "receipts" || term) load(); }, [mode, term]);
  const toggle = (id) => setSelected(x => x.includes(id) ? x.filter(y => y !== id) : [...x, id]);
  const generate = async () => { setBusy(true); setBad(""); const r = await api(endpoint, "POST", mode === "reports" ? { term_id: term, student_ids: selected, format } : { payment_ids: selected, format }); if (!r.ok) { const j = await r.json().catch(() => ({})); setBad(j.detail || "Generation failed."); setBusy(false); return; } await download(r, mode === "reports" ? (format === "combined" ? "report-cards.pdf" : "report-cards.zip") : (format === "combined" ? "fee-receipts.pdf" : "fee-receipts.zip")); setBusy(false); };
  return <div className="documents-page"><h2>Bulk documents</h2><p className="sub">Generate verified documents from approved results and saved payments. Every output remains linked to the original record.</p>
    {admin && <div className="doc-switch"><Button kind={mode === "reports" ? "teal" : "secondary"} onClick={() => setMode("reports")}>Report cards</Button><Button kind={mode === "receipts" ? "teal" : "secondary"} onClick={() => setMode("receipts")}>Fee receipts</Button></div>}
    {mode === "reports" && <Card title="Report-card filters"><Select label="Academic term" value={term} onChange={e => setTerm(e.target.value)}><option value="">Select term</option>{terms.map(t => <option key={t.id} value={t.id}>{t.name} · {t.academic_year}</option>)}</Select></Card>}
    {bad && <Alert kind="err">{bad}</Alert>}
    <Card title={mode === "reports" ? "Eligible students" : "Recorded payments"}><div className="doc-toolbar"><Badge kind="teal">{selected.length} selected</Badge><Button kind="ghost" onClick={() => setSelected(items.map(x => x.id))}>Select all</Button><Button kind="ghost" onClick={() => setSelected([])}>Clear</Button></div>{items.length === 0 ? <EmptyState title={mode === "reports" ? "No eligible report cards" : "No recorded payments"} text={mode === "reports" ? "Only students with approved or locked marks are included." : "Receipts can only be generated from saved payments."} /> : <div className="doc-list">{items.map(x => <label key={x.id} className="doc-row"><input type="checkbox" checked={selected.includes(x.id)} onChange={() => toggle(x.id)} /><span><b>{mode === "reports" ? x.name : x.student}</b><small>{mode === "reports" ? x.admission_number : `${x.receipt_number} · KES ${Number(x.amount).toLocaleString()}`}</small></span></label>)}</div>}</Card>
    <Card title="Export"><Select label="Format" value={format} onChange={e => setFormat(e.target.value)}><option value="combined">One combined PDF</option><option value="zip">Individual PDFs in ZIP</option><option value="both">Both: combined PDF + individual PDFs</option></Select><Button kind="teal" busy={busy} disabled={!selected.length || (mode === "reports" && !term)} onClick={generate}>Generate {mode === "reports" ? "report cards" : "receipts"}</Button></Card>
  </div>;
}
