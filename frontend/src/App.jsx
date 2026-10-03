import { useState, useEffect } from "react";
import { login, api, logout } from "./api";
import Teachers from "./Teachers";
import Setup from "./Setup";
import Students from "./Students";
import ReportCards from "./ReportCards";
import Exams from "./Exams";
import Approvals from "./Approvals";
import Marks from "./Marks";

const Show = ({ v }) => v && typeof v === "object"
  ? <ul>{Object.entries(v).map(([k, x]) => <li key={k}><b>{k.replace(/_/g, " ")}</b>: <Show v={x} /></li>)}</ul>
  : <span>{String(v)}</span>;

function Login({ onDone }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState("");
  const go = async (e) => { e.preventDefault(); try { await login(u, p); onDone(); } catch (x) { setErr(x.message); } };
  return (<form onSubmit={go} className="card"><h1>Marian</h1>
    <input placeholder="Username" value={u} onChange={(e) => setU(e.target.value)} />
    <input placeholder="Password" type="password" value={p} onChange={(e) => setP(e.target.value)} />
    <button>Log in</button>{err && <p className="err">{err}</p>}</form>);
}

function Dash({ onOut }) {
  const [me, setMe] = useState(null), [d, setD] = useState(null);
  useEffect(() => { (async () => {
    const a = await api("/api/auth/me/"); if (a.status === 401) return onOut(); setMe(await a.json());
    const b = await api("/api/dashboard/"); if (b.ok) setD(await b.json());
  })(); }, []);
  return (<div className="card"><h1>Marian</h1>
    {me && <p>{me.username} ({me.role}){me.school ? " - " + me.school.name : ""}</p>}
    {d ? <Show v={d} /> : <p>Loading...</p>}
    {d && d.role === "teacher" && <Marks d={d} />}
    {d && d.role === "school_admin" && <Approvals />}
    {d && d.role === "school_admin" && <Exams d={d} />}
    {d && d.role === "school_admin" && <ReportCards d={d} />}
    {d && d.role === "school_admin" && <Students d={d} />}
    {d && d.role === "school_admin" && <Setup />}
    {d && d.role === "school_admin" && <Teachers />}
    <button onClick={async () => { await logout(); onOut(); }}>Log out</button></div>);
}

export default function App() {
  const [ok, setOk] = useState(!!localStorage.getItem("access"));
  return ok ? <Dash onOut={() => setOk(false)} /> : <Login onDone={() => setOk(true)} />;
}
