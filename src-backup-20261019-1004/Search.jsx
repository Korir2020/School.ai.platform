import { useState, useEffect } from "react";
import { api } from "./api";
import { Modal, Button, Input } from "./ui";
import Ic from "./icons";

const GROUPS = [["students", "Students"], ["teachers", "Teachers"],
  ["subjects", "Subjects"], ["schools", "Schools"]];
const NEXT = { Students: ["Marks"], Subjects: ["Marks", "Setup"] };

export default function Search({ tabs, go, hotkey }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(""), [res, setRes] = useState(null);
  useEffect(() => {
    if (!hotkey) return undefined;
    const key = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setOpen(true);
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [hotkey]);
  useEffect(() => {
    if (q.trim().length < 2) return undefined;
    const t = setTimeout(async () => {
      const r = await api("/api/search/?q=" + encodeURIComponent(q.trim()));
      if (r.ok) setRes(await r.json());
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const close = () => { setOpen(false); setQ(""); setRes(null); };
  const pick = (g) => {
    const to = [g, ...(NEXT[g] || [])].find((t) => tabs.includes(t));
    if (to) { close(); go(to); }
  };
  const show = q.trim().length >= 2 && res;
  const none = show && GROUPS.every(([k]) => res[k].length === 0);
  const extra = (x) => [x.admission_number, x.username, x.code]
    .filter(Boolean).join(" · ");
  return (<>
    <button type="button" className="mu-bell" aria-label="Search"
      onClick={() => setOpen(true)}><Ic n="Search" /></button>
    {open && <Modal title="Search" onClose={close}
      actions={<Button kind="secondary" onClick={close}>Close</Button>}>
      <Input id="sr-q" label="Search" value={q}
        placeholder="Name, admission number, subject"
        onChange={(e) => setQ(e.target.value)} />
      {none && <p>No matches.</p>}
      {show && GROUPS.map(([k, g]) => res[k].length > 0 && (
        <div key={k}><small>{g}</small>
          {res[k].map((x) => (
            <button type="button" key={k + x.id} className="mu-note"
              onClick={() => pick(g)}>
              {x.name}{extra(x) ? " · " + extra(x) : ""}</button>))}</div>))}
    </Modal>}
  </>);
}
