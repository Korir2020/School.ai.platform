import { useState } from "react";

export default function SetupSection({ id, title, summary, complete, children }) {
  const [openState, setOpenState] = useState({ complete, open: !complete });
  const open = openState.complete === complete ? openState.open : !complete;
  const toggleOpen = (nextOpen) => setOpenState({ complete, open: nextOpen });

  return (
    <section className="s2-sec s2-collapsible" id={id}>
      {complete && !open ? (
        <button type="button" className="s2-collapsed" onClick={() => toggleOpen(true)} aria-expanded="false">
          <span className="s2-collapsed-check" aria-hidden="true">✓</span>
          <span className="s2-collapsed-title">{title}</span>
          <span className="s2-collapsed-summary">{summary}</span>
          <span className="s2-collapsed-chevron" aria-hidden="true">⌄</span>
        </button>
      ) : (
        <>
          <div className="s2-section-head">
            <div>
              <h3>{title}</h3>
              <p>{summary}</p>
            </div>
            {complete && <button type="button" className="s2-section-close" onClick={() => toggleOpen(false)} aria-expanded="true">Collapse</button>}
          </div>
          {children}
        </>
      )}
    </section>
  );
}
