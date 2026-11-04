import { useCallback, useEffect, useState } from "react";
import { api, listAll } from "./api";
import { useToast } from "./toastctx";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, Input, Loading, Modal, Select } from "./ui";
import AlertSettings from "./AlertSettings";
import "./announce.css";

const AUDIENCES = [
  ["everyone", "Everyone (staff and parents)"],
  ["staff", "All staff"],
  ["teachers", "Teachers"],
  ["admins", "Administrators"],
  ["parents", "Parents"],
];
const STATUS = {
  draft: ["info", "Draft"], sending: ["warn", "Sending"], sent: ["ok", "Sent"],
  partial: ["warn", "Sent with problems"], failed: ["err", "Failed"],
};
const DELIVERY = {
  failed: "Failed", no_contact: "No contact", over_limit: "Over SMS limit",
  not_configured: "Not set up", opted_out: "Turned off", sent: "Sent", queued: "Queued", "": "-",
};
const read = async (r) => r.json().catch(() => ({}));
const when = (d) => (d ? new Date(d).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
const blank = { title: "", body: "", audience: "everyone", class_level: "", stream: "", priority: "normal", send_email: false, send_sms: false, sms_text: "" };

function Composer({ channels, onDone }) {
  const toast = useToast();
  const [f, setF] = useState(blank);
  const [streams, setStreams] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false), [ask, setAsk] = useState(false), [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  useEffect(() => { listAll("/api/streams/").then((r) => setStreams(r || [])).catch(() => setStreams([])); }, []);
  const levels = [...new Map(streams.map((s) => [s.class_level, s.class_level_name || ("Class " + s.class_level)])).entries()];
  const scoped = f.audience === "parents";
  const payload = { ...f, class_level: scoped && !f.stream ? f.class_level : "", stream: scoped ? f.stream : "" };

  useEffect(() => {
    const t = setTimeout(async () => {
      const r = await api("/api/announcements/preview/", "POST", payload);
      setPreview(r.ok ? await read(r) : null);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.audience, f.class_level, f.stream, f.send_email, f.send_sms]);

  const smsDefault = (f.title + ". " + f.body).trim();
  const smsLen = (f.sms_text || smsDefault).length;
  const smsParts = Math.max(1, Math.ceil(smsLen / 153));
  const valid = f.title.trim().length >= 3 && f.body.trim().length > 0;

  const submit = async (draft) => {
    setAsk(false); setBusy(true); setErr("");
    const r = await api("/api/announcements/", "POST", { ...payload, draft });
    const j = await read(r); setBusy(false);
    if (!r.ok) { setErr(j.detail || "Could not send the announcement."); return; }
    toast(draft ? "Draft saved" : `Announcement sent to ${j.total} ${j.total === 1 ? "person" : "people"}`, "ok");
    setF(blank); onDone();
  };

  return (<Card title="New announcement" className="an-compose">
    {err && <Alert kind="err">{err}</Alert>}
    <Input label="Title" maxLength={120} value={f.title} onChange={set("title")} placeholder="For example: Closing day moved to Friday" />
    <label className="mu-label" htmlFor="an-body">Message</label>
    <textarea id="an-body" className="mu-input an-body" rows={5} maxLength={2000} value={f.body} onChange={set("body")} />
    <span className="mu-help">{f.body.length} / 2000</span>
    <div className="an-grid">
      <Select label="Send to" value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value, class_level: "", stream: "" })}>
        {AUDIENCES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </Select>
      {scoped && <Select label="Class (optional)" value={f.class_level} onChange={(e) => setF({ ...f, class_level: e.target.value, stream: "" })}>
        <option value="">All classes</option>
        {levels.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
      </Select>}
      {scoped && <Select label="Stream (optional)" value={f.stream} onChange={set("stream")}>
        <option value="">All streams</option>
        {streams.filter((s) => !f.class_level || String(s.class_level) === String(f.class_level)).map((s) => <option key={s.id} value={s.id}>{(s.class_level_name ? s.class_level_name + " " : "") + s.name}</option>)}
      </Select>}
      <Select label="Priority" value={f.priority} onChange={set("priority")}>
        <option value="normal">Normal</option>
        <option value="urgent">Urgent</option>
      </Select>
    </div>

    <fieldset className="an-channels">
      <legend>How to deliver</legend>
      <label className="an-check"><input type="checkbox" checked disabled /> In the app (always)</label>
      <label className="an-check"><input type="checkbox" checked={f.send_email} onChange={set("send_email")} disabled={!channels.email_ready} /> Email{!channels.email_ready && <small> (email is not set up on the server)</small>}</label>
      <label className="an-check"><input type="checkbox" checked={f.send_sms} onChange={set("send_sms")} disabled={!channels.sms_ready} /> SMS{!channels.sms_ready && <small> (no SMS provider is set up yet)</small>}</label>
    </fieldset>

    {f.send_sms && <>
      <label className="mu-label" htmlFor="an-sms">SMS text (optional, shorter version)</label>
      <textarea id="an-sms" className="mu-input" rows={3} maxLength={channels.sms_max_length || 459} value={f.sms_text} onChange={set("sms_text")} placeholder={smsDefault.slice(0, 160)} />
      <span className="mu-help">{smsLen} characters, about {smsParts} SMS per person{smsLen > (channels.sms_max_length || 459) ? ". Long messages are shortened." : ""}</span>
    </>}

    {preview && <div className="an-preview" aria-live="polite">
      <b>{preview.recipients} {preview.recipients === 1 ? "person" : "people"}</b> will see this in the app
      {f.send_email && <>, <b>{preview.email.will_send}</b> by email{preview.email.no_email ? ` (${preview.email.no_email} have no email)` : ""}</>}
      {f.send_sms && <>, <b>{preview.sms.will_send}</b> by SMS{preview.sms.no_phone ? ` (${preview.sms.no_phone} have no valid phone)` : ""}{preview.sms.over_limit ? `, ${preview.sms.over_limit} over the limit` : ""}</>}.
    </div>}

    <div className="an-actions">
      <Button kind="secondary" busy={busy} disabled={!valid} onClick={() => submit(true)}>Save draft</Button>
      <Button kind="teal" busy={busy} disabled={!valid || (preview && !preview.recipients)} onClick={() => setAsk(true)}>Send now</Button>
    </div>
    {ask && <ConfirmDialog title="Send this announcement?" confirm="Send"
      text={`It goes to ${preview ? preview.recipients : "everyone in the audience"} people now and cannot be unsent.${f.send_sms && preview ? ` About ${preview.sms.will_send * smsParts} SMS will be charged to the school.` : ""}`}
      onYes={() => submit(false)} onNo={() => setAsk(false)} />}
  </Card>);
}

function Details({ id, onClose, onChanged }) {
  const toast = useToast();
  const [d, setD] = useState(null), [busy, setBusy] = useState(false);
  const load = useCallback(async () => { const r = await api(`/api/announcements/${id}/`); setD(r.ok ? await read(r) : { error: true }); }, [id]);
  useEffect(() => { load(); }, [load]);
  const act = async (path, method = "POST") => {
    setBusy(true);
    const r = await api(`/api/announcements/${id}/${path}`, method);
    const j = await read(r); setBusy(false);
    if (!r.ok && r.status !== 204) return toast(j.detail || "That did not work", "err");
    toast(path === "retry/" ? "Failed deliveries queued again" : path === "send/" ? "Announcement sent" : "Draft deleted", "ok");
    onChanged();
    if (method === "DELETE") onClose(); else load();
  };
  return (<Modal title={d && d.title ? d.title : "Announcement"} onClose={onClose}
    actions={d && !d.error && <>
      {d.status === "draft" && <Button kind="secondary" busy={busy} onClick={() => act("", "DELETE")}>Delete draft</Button>}
      {d.status === "draft" && <Button kind="teal" busy={busy} onClick={() => act("send/")}>Send now</Button>}
      {(d.email_failed > 0 || d.sms_failed > 0) && <Button kind="teal" busy={busy} onClick={() => act("retry/")}>Retry failed</Button>}
    </>}>
    {!d ? <Loading /> : d.error ? <Alert kind="err">Could not load this announcement.</Alert> : <>
      <p className="an-meta">{d.audience_label} · {d.sent_at ? "Sent " + when(d.sent_at) : "Not sent yet"}{d.author ? " · by " + d.author : ""}</p>
      <p className="an-text">{d.body}</p>
      {d.status !== "draft" && <div className="an-stats">
        <div><small>Reached in app</small><b>{d.total}</b><em>{d.read} read</em></div>
        {d.send_email && <div><small>Email</small><b>{d.email_sent}</b><em>{d.email_failed} failed{d.email_queued ? `, ${d.email_queued} sending` : ""}</em></div>}
        {d.send_sms && <div><small>SMS</small><b>{d.sms_sent}</b><em>{d.sms_failed} failed{d.sms_queued ? `, ${d.sms_queued} sending` : ""}</em></div>}
      </div>}
      {d.problems && d.problems.length > 0 && <>
        <h4 className="an-h4">Not delivered</h4>
        <ul className="an-problems">
          {d.problems.map((p, i) => <li key={i}><b>{p.name}</b> <small>{p.role}</small>
            <span>{d.send_email && p.email && p.email !== "sent" ? "Email: " + DELIVERY[p.email] : ""}{d.send_sms && p.sms && p.sms !== "sent" ? " SMS: " + DELIVERY[p.sms] : ""}</span></li>)}
        </ul>
      </>}
    </>}
  </Modal>);
}

function AdminView({ data, reload }) {
  const [open, setOpen] = useState(null);
  const ch = data.channels || {};
  return (<>
    {(!ch.sms_ready || !ch.email_ready) && <Alert kind="info">
      {!ch.sms_ready && "SMS is not switched on yet. Ask the Marian team to connect an SMS provider for your school. "}
      {!ch.email_ready && "Email sending is not set up on the server yet."}
    </Alert>}
    <Composer channels={ch} onDone={reload} />
    <Card title="Sent and drafts">
      {!data.results.length ? <EmptyState title="No announcements yet" text="Announcements you send appear here with delivery results." /> :
        <ul className="an-list">{data.results.map((a) => {
          const [k, t] = STATUS[a.status] || ["info", a.status];
          return (<li key={a.id}><button type="button" className="an-item" onClick={() => setOpen(a.id)}>
            <span className="an-row"><b>{a.title}</b><Badge kind={k}>{t}</Badge>{a.priority === "urgent" && <Badge kind="err">Urgent</Badge>}</span>
            <small>{a.audience_label} · {a.sent_at ? when(a.sent_at) : "Draft"}{a.status !== "draft" ? ` · ${a.read}/${a.total} read` : ""}</small>
          </button></li>);
        })}</ul>}
    </Card>
    {open && <Details id={open} onClose={() => setOpen(null)} onChanged={reload} />}
  </>);
}

function Feed({ data, reload }) {
  const [open, setOpen] = useState(null);
  const view = async (a) => {
    setOpen(a);
    if (!a.read) { await api(`/api/announcements/${a.id}/read/`, "POST"); reload(); }
  };
  return (<Card title="School announcements">
    {!data.results.length ? <EmptyState title="No announcements" text="Announcements from your school will appear here." /> :
      <ul className="an-list">{data.results.map((a) => (
        <li key={a.id}><button type="button" className={"an-item" + (a.read ? "" : " unread")} onClick={() => view(a)}>
          <span className="an-row">{!a.read && <span className="an-dot" aria-label="Unread" />}<b>{a.title}</b>{a.priority === "urgent" && <Badge kind="err">Urgent</Badge>}</span>
          <small>{when(a.sent_at)}{a.author ? " · " + a.author : ""}</small>
          <span className="an-snip">{a.body}</span>
        </button></li>))}</ul>}
    {open && <Modal title={open.title} onClose={() => setOpen(null)}>
      <p className="an-meta">{when(open.sent_at)}{open.author ? " · " + open.author : ""}</p>
      <p className="an-text">{open.body}</p>
    </Modal>}
  </Card>);
}

export default function Announcements() {
  const [data, setData] = useState(null), [err, setErr] = useState(false);
  const load = useCallback(async () => {
    const r = await api("/api/announcements/");
    if (r.ok) { setData(await read(r)); setErr(false); } else setErr(true);
  }, []);
  useEffect(() => { load(); }, [load]);
  if (err) return <Alert kind="err">Could not load announcements. <Button kind="secondary" size="sm" onClick={load}>Try again</Button></Alert>;
  if (!data) return <Loading />;
  return <div className="an">{data.is_admin ? <AdminView data={data} reload={load} /> : <Feed data={data} reload={load} />}<AlertSettings /></div>;
}
