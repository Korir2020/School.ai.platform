import { useEffect, useRef } from "react";
import { Button } from "./ui";
import "./kit.css";

export const Badge = ({ tone = "neutral", children }) => (
  <span className={`kt-badge kt-${tone}`}>{children}</span>
);

export const EmptyState = ({ title, text, action }) => (
  <div className="kt-empty"><h4>{title}</h4><p>{text}</p>{action}</div>
);

export const Skeleton = ({ rows = 5 }) => (
  <div aria-busy="true" aria-label="Loading">
    {Array.from({ length: rows }, (_, i) => <div key={i} className="kt-skel" />)}
  </div>
);

export function Dialog({ open, title, onClose, children, footer }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    if (ref.current) ref.current.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      if (prev && prev.focus) prev.focus();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="kt-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="kt-dialog" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <h3>{title}</h3>
        {children}
        {footer && <div className="kt-foot">{footer}</div>}
      </div>
    </div>
  );
}

export const ConfirmDialog = ({ open, title, text, confirmLabel = "Confirm", onConfirm, onCancel }) => (
  <Dialog open={open} title={title} onClose={onCancel} footer={<>
    <Button kind="secondary" onClick={onCancel}>Cancel</Button>
    <Button kind="teal" onClick={onConfirm}>{confirmLabel}</Button>
  </>}>
    <p>{text}</p>
  </Dialog>
);

export const Tabs = ({ tabs, value, onChange }) => (
  <div className="kt-tabs" role="tablist">
    {tabs.map((t) => (
      <button key={t} role="tab" aria-selected={t === value} className="kt-tab" onClick={() => onChange(t)}>{t}</button>
    ))}
  </div>
);
