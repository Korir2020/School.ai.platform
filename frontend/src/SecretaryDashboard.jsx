import { useMemo, useState } from "react";
import "./secretary-dashboard.css";

const EMPTY = Object.freeze([]);

const Icon = ({ name, size = 18 }) => {
  const drawings = {
    home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" /></>,
    connect: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 8 8 0 0 1-3.6-.85L4 20l1.4-4.1A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8.5 11.5h7" /></>,
    notice: <><path d="M4 13V8a2 2 0 0 1 2-2h3l9-3v17l-9-3H6a2 2 0 0 1-2-1v-1" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    task: <><path d="M9 5h10v16H5V5h2m2 0V3h6v2m-6 6 2 2 4-4m-6 8h6" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 5 5" /></>,
    arrow: <><path d="M5 12h14m-6-6 6 6-6 6" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">{drawings[name] || drawings.home}</svg>;
};

function Metric({ title, value, note, icon, tone, onClick }) {
  return (
    <button type="button" className="sd-metric" onClick={onClick}>
      <span className="sd-metric-top"><span>{title}</span><i className={`sd-icon sd-${tone}`}><Icon name={icon} size={15} /></i></span>
      <strong>{Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "—"}</strong>
      <span className="sd-metric-note">{note}<b>→</b></span>
    </button>
  );
}

function EmptyCard({ title, text }) {
  return <div className="sd-empty"><b>{title}</b><span>{text}</span></div>;
}

export default function SecretaryDashboard({ me, data, onNavigate = () => {}, onViewNotice = () => {} }) {
  const [query, setQuery] = useState("");
  const channels = data?.channels?.channels || data?.channels || EMPTY;
  const notices = data?.notices?.results || data?.notices?.items || EMPTY;
  const noticeUnread = Number(data?.notices?.unread);
  const unreadChannels = channels.filter((channel) => Number(channel.unread) > 0);
  const connectUnread = unreadChannels.reduce((sum, channel) => sum + Number(channel.unread || 0), 0);
  const schoolName = me?.school?.name || "School office";
  const displayName = me?.full_name || me?.username || "Secretary";
  const filteredNotices = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notices;
    return notices.filter((item) => `${item.title || ""} ${item.body || ""} ${item.author || ""}`.toLowerCase().includes(needle));
  }, [notices, query]);

  if (me?.role && me.role !== "secretary") {
    return <section className="sd-page"><EmptyCard title="Secretary workspace" text="This view is designed for the secretary role. Server-side permissions remain authoritative." /></section>;
  }

  return (
    <section className="sd-page" aria-label="Secretary home dashboard">
      <header className="sd-hero">
        <div className="sd-hero-mark"><b>M</b><small>OFFICE<br />DESK</small></div>
        <div className="sd-hero-copy">
          <span className="sd-eyebrow"><i /> SCHOOL OFFICE</span>
          <h1>Good morning, {displayName}<em>.</em></h1>
          <p>{schoolName} · Your school communications in one clear view.</p>
        </div>
        <button type="button" className="sd-primary" onClick={() => onNavigate("Connect")}><Icon name="connect" size={15} />Open Connect</button>
      </header>

      <div className="sd-current-scope"><b>Current access</b><span>Connect and messages addressed to your account. Other office workflows are not exposed to secretary accounts in the current app.</span></div>

      <div className="sd-metrics">
        <Metric title="Unread Connect posts" value={connectUnread} note={data?.channels ? `Across ${channels.length} school channels` : "Connect channel summary not loaded"} icon="connect" tone="green" onClick={() => onNavigate("Connect")} />
        <Metric title="Unread notices" value={Number.isFinite(noticeUnread) ? noticeUnread : "—"} note={data?.notices ? "Addressed to your account" : "Notice inbox not loaded"} icon="notice" tone="gold" onClick={() => onViewNotice(null)} />
      </div>

      <div className="sd-grid">
        <article className="sd-panel">
          <div className="sd-panel-head"><div><h2>Connect channels</h2><p>Unread activity returned for your school membership</p></div><button type="button" className="sd-link" onClick={() => onNavigate("Connect")}>Open inbox <Icon name="arrow" size={13} /></button></div>
          {channels.length ? <div className="sd-channel-list">{channels.map((channel) => <button type="button" key={channel.id || channel.name} className="sd-channel" onClick={() => onNavigate("Connect")}><span className="sd-channel-icon"><Icon name="connect" size={15} /></span><span className="sd-channel-text"><b>{channel.name}</b><small>{channel.description || (channel.kind === "notices" ? "Official school notices" : "School community conversation")}</small></span><strong>{Number(channel.unread || 0)}<small>unread</small></strong><Icon name="arrow" size={13} /></button>)}</div> : <EmptyCard title="Connect activity not loaded" text="Pass the response from /api/connect/channels/ to show the secretary’s school-scoped unread counts." />}
        </article>

        <article className="sd-panel">
          <div className="sd-panel-head"><div><h2>Notices addressed to you</h2><p>This list should contain only your own received notices</p></div><span className="sd-count">{Number.isFinite(noticeUnread) ? noticeUnread : "—"} unread</span></div>
          <label className="sd-search"><Icon name="search" size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search your notices" /></label>
          {filteredNotices.length ? <div className="sd-notice-list">{filteredNotices.slice(0, 5).map((notice, index) => <button type="button" key={notice.id || index} className="sd-notice" onClick={() => onViewNotice(notice)}><span className={`sd-notice-dot ${notice.read ? "read" : ""}`} /><span><b>{notice.title || "School announcement"}</b><small>{notice.sent_at ? new Date(notice.sent_at).toLocaleString() : ""}{notice.author ? ` · ${notice.author}` : ""}</small><em>{notice.body || "Open to read this announcement."}</em></span><Icon name="arrow" size={13} /></button>)}</div> : <EmptyCard title={data?.notices ? "No notices to show" : "Notice inbox not loaded"} text={data?.notices ? "Announcements shown here should be addressed to this secretary account." : "Pass the response from /api/announcements/; do not substitute school-wide private records."} />}
        </article>

      </div>
      <p className="sd-footnote">Use server-authorized, account-scoped data only. This component intentionally does not fetch the general dashboard, school-wide learner records, marks, attendance or financial details.</p>
    </section>
  );
}
