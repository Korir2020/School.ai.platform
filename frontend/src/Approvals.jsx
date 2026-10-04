import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";


export default function Approvals() {
  const [d, setD] = useState(null), [msg, setMsg] = useState("");
  const load = async () => {
    const [pf, st, sj] = await Promise.all(["performance", "students", "subjects"].map((x) => list("/api/" + x + "/")));
    setD({ pf, st, sj });
  };
  useEffect(() => { load(); }, []);
  if (!d) return <p>Loading approvals...</p>;
  const nm = (id) => { const s = d.st.find((x) => x.id === id); return s ? s.first_name + " " + s.last_name : "Student " + id; };
  const sb = (id) => { const s = d.sj.find((x) => x.id === id); return s ? s.name : "Subject " + id; };
  const act = async (p, a) => { const r = await api("/api/performance/" + p.id + "/" + a + "/", "POST"); setMsg(r.ok ? "Done: " + a : "Failed: " + a); load(); };
  const rows = d.pf.filter((p) => p.status === "submitted" || p.status === "approved");
  return (<div><h3>Marks awaiting action</h3>{rows.length === 0 && <p>Nothing waiting.</p>}
    {rows.map((p) => (<p key={p.id}>{nm(p.student)} - {sb(p.subject)}: {p.marks} ({p.status}){" "}
      {p.status === "submitted" && <><button onClick={() => act(p, "approve")}>Approve</button> <button onClick={() => act(p, "reject")}>Reject</button></>}
      {p.status === "approved" && <button onClick={() => act(p, "lock")}>Lock</button>}</p>))}
    <p>{msg}</p></div>);
}
