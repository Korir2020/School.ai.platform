import { useEffect, useRef, useState } from "react";
import { ToastCtx } from "./toastctx";
import "./ui.css";

const cx = (...a) => a.filter(Boolean).join(" ");

export function Button({ kind, size, busy, children, className, ...p }) {
  return (<button type="button" className={cx("mu-btn", kind, size, className)}
    {...p} disabled={p.disabled || busy}>{busy ? "Working..." : children}</button>);
}

export function Field({ label, help, error, id, children }) {
  return (<div className="mu-field">
    {label && <label className="mu-label" htmlFor={id}>{label}</label>}
    {children}
    {help && !error && <span className="mu-help">{help}</span>}
    {error && <span className="mu-error" id={id + "-e"} role="alert">{error}</span>}
  </div>);
}

const fid = (id, label, name) => id || "f-" + String(label || name || "x").replace(/\W/g, "");

export function Input({ label, help, error, id, ...p }) {
  const i = fid(id, label, p.name);
  return (<Field label={label} help={help} error={error} id={i}>
    <input id={i} className="mu-input" aria-invalid={!!error}
      aria-describedby={error ? i + "-e" : undefined} {...p} /></Field>);
}

export function Select({ label, help, error, id, children, ...p }) {
  const i = fid(id, label, p.name);
  return (<Field label={label} help={help} error={error} id={i}>
    <select id={i} className="mu-input" aria-invalid={!!error}
      aria-describedby={error ? i + "-e" : undefined} {...p}>{children}</select></Field>);
}

export function Modal({ title, onClose, children, actions }) {
  const ref = useRef(null), cb = useRef(onClose);
  useEffect(() => { cb.current = onClose; });
  useEffect(() => {
    const prev = document.activeElement;
    if (ref.current) ref.current.focus();
    const key = (e) => { if (e.key === "Escape") cb.current(); };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      if (prev && prev.focus) prev.focus();
    };
  }, []);
  return (<div className="mu-overlay" onClick={onClose}>
    <div className="mu-modal" role="dialog" aria-modal="true" aria-label={title}
      tabIndex={-1} ref={ref} onClick={(e) => e.stopPropagation()}>
      <h3>{title}</h3>{children}
      {actions && <div className="mu-modal-actions">{actions}</div>}
    </div></div>);
}

export function ConfirmDialog({ title, text, confirm = "Confirm", danger, onYes, onNo }) {
  return (<Modal title={title} onClose={onNo} actions={<>
    <Button kind="secondary" onClick={onNo}>Cancel</Button>
    <Button kind={danger ? "danger" : "teal"} onClick={onYes}>{confirm}</Button></>}>
    <p>{text}</p></Modal>);
}

export function ToastProvider({ children }) {
  const [list, setList] = useState([]);
  const push = (text, kind) => {
    const id = Date.now() + Math.random();
    setList((l) => [...l, { id, text, kind }]);
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 4000);
  };
  return (<ToastCtx.Provider value={push}>{children}
    <div className="mu-toasts" role="status" aria-live="polite">
      {list.map((t) => <div key={t.id} className={cx("mu-toast", t.kind)}>{t.text}</div>)}
    </div></ToastCtx.Provider>);
}

export const Card = ({ title, children, className }) => (
  <div className={cx("mu-card", className)}>{title && <h3>{title}</h3>}{children}</div>);
export const Badge = ({ kind, children }) => (
  <span className={cx("mu-badge", kind)}>{children}</span>);
export const Alert = ({ kind = "info", children }) => (
  <div className={cx("mu-alert", kind)} role={kind === "err" ? "alert" : "status"}>
    {children}</div>);
export const EmptyState = ({ title, text }) => (
  <div className="mu-empty"><b>{title}</b>{text}</div>);
export const Loading = () => (<div aria-busy="true"><div className="mu-skel" />
  <div className="mu-skel" style={{ width: "70%" }} /></div>);
export const ErrorState = ({ text, onRetry }) => (
  <Alert kind="err">{text || "Something went wrong."}{" "}
    {onRetry && <Button kind="secondary" size="sm" onClick={onRetry}>Try again</Button>}</Alert>);

export const StatCard = ({ label, value, note }) => (
  <div className="mu-stat"><small>{label}</small><b>{value ?? 0}</b>
    {note && <em>{note}</em>}</div>);

export function DataTable({ cols, rows, search, empty = "Nothing here yet." }) {
  const [q, setQ] = useState(""), [sk, setSk] = useState(null), [dir, setDir] = useState(1);
  const val = (r, c) => (c.get ? c.get(r) : r[c.key]);
  const low = q.toLowerCase();
  const has = (r) => cols.some((c) =>
    String(val(r, c) ?? "").toLowerCase().includes(low));
  let list = (rows || []).filter((r) => !q || has(r));
  const cmp = (a, b) => {
    const x = val(a, sk), y = val(b, sk);
    return (x > y ? 1 : x < y ? -1 : 0) * dir;
  };
  if (sk) list = [...list].sort(cmp);
  const sortBy = (c) => {
    if (sk === c) setDir(-dir); else { setSk(c); setDir(1); }
  };
  const arrow = (c) => (sk === c ? (dir > 0 ? " ▲" : " ▼") : "");
  const aria = (c) => (sk === c ? (dir > 0 ? "ascending" : "descending") : undefined);
  const head = (c) => (c.sort
    ? <button type="button" className="mu-btn ghost sm"
        onClick={() => sortBy(c)}>{c.label}{arrow(c)}</button>
    : c.label);
  return (<div>
    {search && <Input placeholder={search} aria-label={search} value={q}
      onChange={(e) => setQ(e.target.value)} />}
    <div className="mu-tablewrap"><table className="mu-table">
      <thead><tr>{cols.map((c) => (
        <th key={c.label} scope="col" aria-sort={aria(c)}>{head(c)}</th>))}</tr></thead>
      <tbody>{list.map((r, i) => (
        <tr key={r.id ?? i}>{cols.map((c) => (
          <td key={c.label}>{c.render ? c.render(r) : val(r, c)}</td>))}</tr>))}</tbody>
    </table></div>
    {list.length === 0 && <EmptyState title={empty} />}
  </div>);
}
