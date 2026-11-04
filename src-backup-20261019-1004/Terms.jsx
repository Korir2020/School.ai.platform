import { useState, useEffect } from "react";
import { api, listAll as list } from "./api";
import { useToast } from "./toastctx";
import { Button, Input, Select, Modal, ConfirmDialog } from "./ui";
import { Card, Badge, DataTable, Loading, ErrorState } from "./ui";

const empty = { name: "", start_date: "", end_date: "" };

export default function Terms() {
  const toast = useToast();
  const [x, setX] = useState(null), [bad, setBad] = useState(false);
  const [y, setY] = useState(empty);
  const [t, setT] = useState({ ...empty, academic_year: "" });
  const [ed, setEd] = useState(null), [ask, setAsk] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      const get = (p) => list("/api/" + p + "/");
      const [yr, tm] = await Promise.all(["academic-years", "terms"].map(get));
      setX({ yr, tm }); setBad(false);
    } catch { setBad(true); }
  };
  useEffect(() => { load(); }, []);
  const send = async (path, method, body) => {
    setBusy(true);
    const r = await api(path, method, body);
    const e = r.ok ? {} : await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) toast("Saved", "ok");
    else toast("Failed: " + (e.detail || JSON.stringify(e)), "err");
    load();
    return r.ok;
  };
  if (bad) return <ErrorState text="Could not load terms." onRetry={load} />;
  if (!x) return <Loading />;
  const yname = (id) => (x.yr.find((a) => a.id === id) || {}).name || "";
  const tpath = (m) => "/api/terms/" + m.id + "/";
  const toggle = (m) => (m.is_active ? setAsk(m)
    : send(tpath(m), "PATCH", { is_active: true }));
  const saveDates = async () => {
    const body = { start_date: ed.start_date, end_date: ed.end_date };
    if (await send(ed.path, "PATCH", body)) setEd(null);
  };
  const editBtn = (path, r) => (
    <Button kind="ghost" size="sm" onClick={() => setEd({ path,
      start_date: r.start_date, end_date: r.end_date })}>Edit dates</Button>);
  const dcols = [
    { label: "Starts", key: "start_date", sort: true },
    { label: "Ends", key: "end_date", sort: true },
  ];
  const ycols = [
    { label: "Year", key: "name", sort: true }, ...dcols,
    { label: "Actions", render: (a) => editBtn("/api/academic-years/" + a.id + "/", a) },
  ];
  const state = (m) => (m.is_active ? "Active" : "Off");
  const tcols = [
    { label: "Year", get: (m) => yname(m.academic_year), sort: true },
    { label: "Term", key: "name", sort: true }, ...dcols,
    { label: "Status", get: state, sort: true, render: (m) => (
      <Badge kind={m.is_active ? "ok" : "info"}>{state(m)}</Badge>) },
    { label: "Actions", render: (m) => (<>
      <Button kind="ghost" size="sm" onClick={() => toggle(m)}>
        {m.is_active ? "Turn off" : "Turn on"}</Button>
      {editBtn(tpath(m), m)}</>) },
  ];
  const field = (obj, set, k, label, type) => (
    <Input id={label + k} label={label} type={type || "text"} value={obj[k]}
      onChange={(e) => set({ ...obj, [k]: e.target.value })} />);
  return (
    <div>
      <h2>Academic years and terms</h2>
      <p>The active term with the latest start date is the one the app uses.</p>
      <Card title="Academic years">
        <DataTable cols={ycols} rows={x.yr} search="Search years"
          empty="No academic years yet" />
      </Card>
      <Card title="Add academic year">
        {field(y, setY, "name", "Year name, e.g. 2026")}
        {field(y, setY, "start_date", "Starts", "date")}
        {field(y, setY, "end_date", "Ends", "date")}
        <Button kind="teal" busy={busy}
          disabled={!y.name || !y.start_date || !y.end_date}
          onClick={async () => {
            if (await send("/api/academic-years/", "POST",
              { ...y, is_active: true })) setY(empty);
          }}>Add year</Button>
      </Card>
      <Card title="Terms">
        <DataTable cols={tcols} rows={x.tm} search="Search terms"
          empty="No terms yet" />
      </Card>
      <Card title="Add term">
        <Select id="tm-year" label="Academic year" value={t.academic_year}
          onChange={(e) => setT({ ...t, academic_year: e.target.value })}>
          <option value="">Select...</option>
          {x.yr.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </Select>
        {field(t, setT, "name", "Term name, e.g. Term 1")}
        {field(t, setT, "start_date", "Starts", "date")}
        {field(t, setT, "end_date", "Ends", "date")}
        <Button kind="teal" busy={busy} disabled={!t.academic_year || !t.name
          || !t.start_date || !t.end_date}
          onClick={async () => {
            if (await send("/api/terms/", "POST", { ...t, is_active: true }))
              setT({ ...empty, academic_year: t.academic_year });
          }}>Add term</Button>
      </Card>
      {ed && <Modal title="Edit dates" onClose={() => setEd(null)} actions={<>
        <Button kind="secondary" onClick={() => setEd(null)}>Cancel</Button>
        <Button kind="teal" busy={busy} onClick={saveDates}>Save dates</Button></>}>
        {field(ed, setEd, "start_date", "Starts", "date")}
        {field(ed, setEd, "end_date", "Ends", "date")}
      </Modal>}
      {ask && <ConfirmDialog title={"Turn off " + ask.name + "?"} danger
        text="The app uses the active term with the latest start date, so this may change which term is used."
        confirm="Turn off" onYes={() => {
          send(tpath(ask), "PATCH", { is_active: false }); setAsk(null); }}
        onNo={() => setAsk(null)} />}
    </div>
  );
}
