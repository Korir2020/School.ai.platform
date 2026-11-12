import { startTransition, useCallback, useEffect, useState } from "react";
import { api, listAll } from "./api";
import { Alert, Badge, Button, Card, EmptyState, Select } from "./ui";

const download = async (response, fallback) => {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fallback;
  a.click();
  URL.revokeObjectURL(url);
};

const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function allPages(path) {
  const sep = path.includes("?") ? "&" : "?";
  let url = `${path}${sep}page_size=200`;
  const out = [];
  for (let i = 0; i < 200 && url; i += 1) {
    const response = await api(url);
    if (!response.ok) {
      if (response.status === 403 && path.includes("fee-receipts")) {
        throw new Error("You do not have permission to access fee information.");
      }
      throw new Error("Could not load eligible documents.");
    }
    const data = await response.json();
    if (Array.isArray(data)) return data;
    out.push(...(data.results || data.students || data.payments || []));
    if (!data.next) break;
    const next = new URL(data.next, "http://x");
    url = `${next.pathname}${next.search}`;
  }
  return out;
}

export default function BulkDocuments({ admin = false }) {
  const [mode, setMode] = useState(admin ? "reports" : "receipts");
  const [terms, setTerms] = useState([]);
  const [term, setTerm] = useState("");
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState([]);
  const [format, setFormat] = useState("combined");
  const [busy, setBusy] = useState(false);
  const [bad, setBad] = useState("");
  const [jobProgress, setJobProgress] = useState(null);
  const endpoint = mode === "reports"
    ? "/api/documents/report-cards/"
    : "/api/documents/fee-receipts/";

  const load = useCallback(async () => {
    startTransition(() => { setBad(""); setJobProgress(null); });
    try {
      const query = mode === "reports" && term
        ? `?term_id=${encodeURIComponent(term)}`
        : "";
      const rows = await allPages(endpoint + query);
      startTransition(() => { setItems(rows); setSelected([]); });
    } catch (error) {
      startTransition(() => {
        setItems([]);
        setBad(error.message || "Could not load eligible documents.");
      });
    }
  }, [endpoint, mode, term]);

  useEffect(() => {
    if (admin) listAll("/api/terms/").then(setTerms).catch(() => {});
  }, [admin]);
  useEffect(() => {
    if (mode === "receipts" || term) void load();
  }, [load, mode, term]);

  const toggle = (id) => setSelected((current) => (
    current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
  ));

  const generate = async () => {
    setBusy(true);
    setBad("");
    setJobProgress(null);
    try {
      const payload = mode === "reports"
        ? { term_id: term, student_ids: selected, format }
        : { payment_ids: selected, format };
      const response = await api(endpoint, "POST", payload);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Generation failed.");
      }

      if (response.status === 202) {
        const queued = await response.json();
        setJobProgress({ ...queued, progress: 0, status: "queued" });
        let completed = false;
        for (let attempt = 0; attempt < 600; attempt += 1) {
          await pause(2000);
          const statusResponse = await api(queued.status_url);
          if (!statusResponse.ok) throw new Error("Could not check export progress.");
          const status = await statusResponse.json();
          setJobProgress({ ...status, status_url: queued.status_url });
          if (status.status === "failed") {
            throw new Error(status.error || "The export failed. Please try again.");
          }
          if (status.status === "completed") {
            if (!status.download_url) throw new Error("The export is complete but no file is available.");
            const file = await api(status.download_url);
            if (!file.ok) throw new Error("The export file could not be downloaded.");
            await download(file, mode === "reports" ? "report-cards.pdf" : "fee-receipts.pdf");
            completed = true;
            break;
          }
        }
        if (!completed) throw new Error("The export is still running. You can safely leave this page; check its job status with your administrator.");
      } else {
        await download(
          response,
          mode === "reports"
            ? (format === "combined" ? "report-cards.pdf" : "report-cards.zip")
            : (format === "combined" ? "fee-receipts.pdf" : "fee-receipts.zip"),
        );
      }
    } catch (error) {
      setBad(error.message || "Generation failed.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="documents-page">
    <h2>Bulk documents</h2>
    <p className="sub">Generate term-wide bulk documents from approved results and saved payments. For an authoritative report for one Opener, Mid-term, or End-term examination, use <b>Exam Reports</b> instead.</p>
    {admin && <div className="doc-switch">
      <Button kind={mode === "reports" ? "teal" : "secondary"} onClick={() => setMode("reports")}>Report cards</Button>
      <Button kind={mode === "receipts" ? "teal" : "secondary"} onClick={() => setMode("receipts")}>Fee receipts</Button>
    </div>}
    {mode === "reports" && <Card title="Term-wide report-card filters">
      <p className="sub">This legacy term-wide export is a convenience document and may aggregate approved results across the selected term; it is not the per-examination report route.</p>
      <Select label="Academic term" value={term} onChange={(event) => setTerm(event.target.value)}>
        <option value="">Select term</option>
        {terms.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.academic_year}</option>)}
      </Select>
    </Card>}
    {bad && <Alert kind="err">{bad}</Alert>}
    {jobProgress && <Alert kind={jobProgress.status === "failed" ? "err" : "info"}>
      Export {jobProgress.status}: {jobProgress.progress || 0} of {jobProgress.total || 0} documents processed.
      {jobProgress.status_url && <> <a href={jobProgress.status_url}>View job status</a></>}
    </Alert>}
    <Card title={mode === "reports" ? "Eligible students" : "Recorded payments"}>
      <div className="doc-toolbar">
        <Badge kind="teal">{selected.length} selected</Badge>
        <Button kind="ghost" onClick={() => setSelected(items.map((row) => row.id))}>Select all</Button>
        <Button kind="ghost" onClick={() => setSelected([])}>Clear</Button>
      </div>
      {items.length === 0
        ? <EmptyState title={mode === "reports" ? "No eligible report cards" : "No recorded payments"} text={mode === "reports" ? "Only students with approved or locked marks are included." : "Receipts can only be generated from saved payments."} />
        : <div className="doc-list">{items.map((row) => <label key={row.id} className="doc-row">
          <input type="checkbox" checked={selected.includes(row.id)} onChange={() => toggle(row.id)} />
          <span><b>{mode === "reports" ? row.name : row.student}</b><small>{mode === "reports" ? row.admission_number : `${row.receipt_number} · KES ${Number(row.amount).toLocaleString()}`}</small></span>
        </label>)}</div>}
    </Card>
    <Card title="Export">
      <Select label="Format" value={format} onChange={(event) => setFormat(event.target.value)}>
        <option value="combined">One combined PDF</option>
        <option value="zip">Individual PDFs in ZIP</option>
        <option value="both">Both: combined PDF + individual PDFs</option>
      </Select>
      <Button kind="teal" busy={busy} disabled={!selected.length || (mode === "reports" && !term)} onClick={generate}>
        Generate {mode === "reports" ? "report cards" : "receipts"}
      </Button>
    </Card>
  </div>;
}
