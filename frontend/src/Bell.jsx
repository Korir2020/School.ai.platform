import { useState, useEffect } from "react";
import { api } from "./api";
import { Modal, Button } from "./ui";
import Ic from "./icons";

const TAB = { join_requested: "Staff", join_completed: "Staff",
  marks_awaiting_approval: "Approve" };

export default function Bell({ go }) {
  const [d, setD] = useState({ unread: 0, results: [] });
  const [open, setOpen] = useState(false);
  const load = async () => {
    const r = await api("/api/notifications/");
    if (r.ok) setD(await r.json());
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);
  const markAll = async () => {
    await api("/api/notifications/read-all/", "POST"); load();
  };
  const tap = async (n) => {
    if (n.id && !n.read) {
      await api("/api/notifications/" + n.id + "/read/", "POST"); load();
    }
    if (TAB[n.kind]) { setOpen(false); go(TAB[n.kind]); }
  };
  const label = "Notifications, " + d.unread + " unread";
  const cls = (n) => "mu-note" + (n.id && !n.read ? " new" : "");
  return (<>
    <button type="button" className="mu-bell" aria-label={label}
      onClick={() => { setOpen(true); load(); }}>
      <Ic n="Bell" />{d.unread > 0 && <i>{d.unread}</i>}</button>
    {open && <Modal title="Notifications" onClose={() => setOpen(false)}
      actions={<>
        {d.unread > 0 && <Button kind="secondary"
          onClick={markAll}>Mark all read</Button>}
        <Button kind="teal" onClick={() => setOpen(false)}>Close</Button></>}>
      {d.results.length === 0 && <p>Nothing new.</p>}
      {d.results.map((n, i) => (
        <button type="button" key={n.id || "c" + i} className={cls(n)}
          onClick={() => tap(n)}>{n.message}</button>))}
    </Modal>}
  </>);
}
