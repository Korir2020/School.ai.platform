import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Alert, Button, ConfirmDialog, EmptyState, ErrorState, Loading, Select } from "./ui";
import "./connect.css";

const MAX = 2000;
const POLL_MS = 20000;
const ROLE_TEXT = { admin: "School admin", teacher: "Teacher" };

async function call(path, method = "GET", body) {
  const r = await api(path, method, body);
  let data = null;
  if (r.status !== 204) {
    try {
      data = await r.json();
    } catch {
      data = null;
    }
  }
  if (!r.ok) throw new Error((data && data.message) || "Something went wrong. Please try again.");
  return data;
}

function when(iso) {
  return new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function day(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

function mergeFeed(prev, d) {
  if (!d.has_more) return { posts: d.posts, hasMore: false };
  const floor = d.posts.length ? d.posts[d.posts.length - 1].id : 0;
  const older = prev.posts.filter((p) => p.id < floor);
  return { posts: d.posts.concat(older), hasMore: older.length ? prev.hasMore : true };
}

function PostCard({ post, me, kind, acts }) {
  const [open, setOpen] = useState(false);
  const admin = me.is_admin;
  const roleText = ROLE_TEXT[post.author_role];
  const cls = "cn-post" + (post.is_urgent ? " urgent" : "") + (post.hidden ? " hidden" : "");
  return (
    <article className={cls}>
      <header className="cn-ph">
        <b>{post.author}</b>
        {roleText && <span className="cn-tag">{roleText}</span>}
        {post.is_urgent && <span className="cn-tag cn-urgent">Urgent</span>}
        {post.is_pinned && <span className="cn-tag">Pinned</span>}
        {post.hidden && <span className="cn-tag cn-urgent">Hidden</span>}
        <time className="cn-time" dateTime={post.created_at}>{when(post.created_at)}</time>
      </header>
      <p className="cn-body">{post.body}</p>
      {post.event && (
        <p className="cn-event">
          <b>{post.event.title}</b> {day(post.event.start_date)}
          {post.event.end_date ? " to " + day(post.event.end_date) : ""}
        </p>
      )}
      <div className="cn-pa">
        {kind === "notices" && (post.acknowledged
          ? <span className="cn-ok">Acknowledged</span>
          : <Button kind="secondary" size="sm" onClick={() => acts.ack(post)}>Acknowledge</Button>)}
        {admin && kind === "notices" && <span className="cn-meta">Acknowledged by {post.ack_count}</span>}
        {admin && post.report_count > 0 && (
          <span className="cn-tag cn-urgent">{post.report_count + (post.report_count === 1 ? " report" : " reports")}</span>
        )}
        {!post.mine && <button type="button" className="cn-link" onClick={() => acts.report(post)}>Report</button>}
        {post.can_delete && <button type="button" className="cn-link" onClick={() => acts.remove(post)}>Delete</button>}
        {admin && (
          <button type="button" className="cn-link" aria-expanded={open} onClick={() => setOpen(!open)}>Manage</button>
        )}
      </div>
      {admin && open && (
        <div className="cn-pa">
          <button type="button" className="cn-link" onClick={() => acts.patch(post, { is_pinned: !post.is_pinned })}>
            {post.is_pinned ? "Unpin" : "Pin"}
          </button>
          <button type="button" className="cn-link" onClick={() => acts.patch(post, { is_urgent: !post.is_urgent })}>
            {post.is_urgent ? "Clear urgent" : "Mark urgent"}
          </button>
          <button type="button" className="cn-link" onClick={() => acts.patch(post, { hidden: !post.hidden })}>
            {post.hidden ? "Show again" : "Hide from members"}
          </button>
        </div>
      )}
    </article>
  );
}

function Composer({ me, events, onSend, onDone }) {
  const [text, setText] = useState("");
  const [urgent, setUrgent] = useState(false);
  const [pin, setPin] = useState(false);
  const [eventId, setEventId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const send = async () => {
    setBusy(true);
    setErr("");
    const payload = { body: text };
    if (me.is_admin) {
      payload.is_urgent = urgent;
      payload.is_pinned = pin;
      payload.event_id = eventId || null;
    }
    try {
      await onSend(payload);
      onDone();
    } catch (e) {
      setErr(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="cn-compose">
      <label className="mu-label" htmlFor="cn-text">Your post</label>
      <textarea
        id="cn-text"
        className="cn-text"
        rows={4}
        maxLength={MAX}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="cn-hint">
        {text.length + "/" + MAX}. Please do not share phone numbers, emails or admission numbers.
        {me.role === "parent" ? " You may mention your own child by name." : ""}
      </p>
      {me.is_admin && (
        <>
          <label className="cn-check">
            <input type="checkbox" checked={urgent} onChange={(e) => setUrgent(e.target.checked)} />
            Mark as urgent
          </label>
          <label className="cn-check">
            <input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} />
            Pin to the top
          </label>
          <Select label="Attach a calendar event" value={eventId} onChange={(e) => setEventId(e.target.value)}>
            <option value="">None</option>
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>{ev.title + " (" + day(ev.start_date) + ")"}</option>
            ))}
          </Select>
        </>
      )}
      {err && <Alert kind="err">{err}</Alert>}
      <div className="cn-pa">
        <Button kind="teal" busy={busy} onClick={send}>Post</Button>
        <Button kind="secondary" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}

function ChatPanel({ channel, me, onSeen }) {
  const [feed, setFeed] = useState({ posts: [], hasMore: false });
  const [pinned, setPinned] = useState([]);
  const [canPost, setCanPost] = useState(false);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState("");
  const [note, setNote] = useState(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState([]);
  const [pending, setPending] = useState(null);
  const [writing, setWriting] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const base = "/api/connect/channels/" + channel.id + "/posts/";

  const refresh = useCallback(async () => {
    const qs = new URLSearchParams({ limit: "30" });
    if (query) qs.set("q", query);
    try {
      const d = await call(base + "?" + qs);
      setFeed((prev) => mergeFeed(prev, d));
      setPinned(d.pinned);
      setCanPost(d.can_post);
      setErr("");
      setReady(true);
      if (!query) onSeen();
    } catch (e) {
      setErr(e.message);
    }
  }, [base, query, onSeen]);

  useEffect(() => {
    const first = setTimeout(() => {
      refresh();
    }, 0);
    const t = setInterval(() => {
      if (!document.hidden) refresh();
    }, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [refresh]);

  useEffect(() => {
    if (!me.is_admin) return undefined;
    let alive = true;
    const from = new Date();
    const to = new Date(from.getTime() + 90 * 86400000);
    const iso = (x) => x.toISOString().slice(0, 10);
    call("/api/calendar/events/?from=" + iso(from) + "&to=" + iso(to))
      .then((d) => {
        if (alive) setEvents(d.events);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [me.is_admin]);

  const act = async (fn, okText) => {
    setNote(null);
    try {
      await fn();
      if (okText) setNote({ kind: "info", text: okText });
      await refresh();
    } catch (e) {
      setNote({ kind: "err", text: e.message });
    }
  };

  const runPending = async () => {
    const c = pending;
    setPending(null);
    if (c) await act(c.run, c.ok);
  };

  const acts = {
    ack: (p) => act(() => call("/api/connect/posts/" + p.id + "/ack/", "POST")),
    patch: (p, body) => act(() => call("/api/connect/posts/" + p.id + "/", "PATCH", body)),
    report: (p) =>
      setPending({
        title: "Report this post?",
        text: "The school administrators will review it. Your name is not shown to them.",
        confirm: "Report",
        ok: "Reported. Thank you.",
        run: () => call("/api/connect/posts/" + p.id + "/report/", "POST", {}),
      }),
    remove: (p) =>
      setPending({
        title: "Delete this post?",
        text: "It will no longer be shown to members.",
        confirm: "Delete",
        danger: true,
        run: () => call("/api/connect/posts/" + p.id + "/", "DELETE"),
      }),
  };

  const startSearch = (e) => {
    e.preventDefault();
    setFeed({ posts: [], hasMore: false });
    setReady(false);
    setQuery(draft.trim());
  };

  const clearSearch = () => {
    setDraft("");
    setFeed({ posts: [], hasMore: false });
    setReady(false);
    setQuery("");
  };

  const loadEarlier = async () => {
    const last = feed.posts[feed.posts.length - 1];
    if (!last) return;
    setLoadingMore(true);
    try {
      const qs = new URLSearchParams({ limit: "30", before: String(last.id) });
      if (query) qs.set("q", query);
      const d = await call(base + "?" + qs);
      setFeed((prev) => ({ posts: prev.posts.concat(d.posts), hasMore: d.has_more }));
    } catch (e) {
      setNote({ kind: "err", text: e.message });
    }
    setLoadingMore(false);
  };

  if (!ready && !err) return <Loading />;
  const pinIds = new Set(query ? [] : pinned.map((p) => p.id));
  const shown = feed.posts.filter((p) => !pinIds.has(p.id));

  return (
    <div className="cn-chat">
      {err && <ErrorState text={err} onRetry={refresh} />}
      <form className="cn-search" onSubmit={startSearch}>
        <input
          type="search"
          value={draft}
          maxLength={60}
          placeholder="Search this channel"
          aria-label="Search this channel"
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button kind="secondary" size="sm" type="submit">Search</Button>
        {query && <Button kind="secondary" size="sm" onClick={clearSearch}>Clear</Button>}
      </form>
      {note && <Alert kind={note.kind}>{note.text}</Alert>}
      {canPost && !writing && <Button kind="teal" onClick={() => setWriting(true)}>Write a post</Button>}
      {canPost && writing && (
        <Composer
          me={me}
          events={events}
          onSend={(body) => call(base, "POST", body)}
          onDone={() => {
            setWriting(false);
            refresh();
          }}
        />
      )}
      {!canPost && (
        <p className="cn-hint">
          {me.muted ? "You have been muted by a school administrator." : "Only school administrators post in this channel."}
        </p>
      )}
      {pinIds.size > 0 && (
        <section aria-label="Pinned posts">
          <h3 className="cn-h">Pinned</h3>
          {pinned.map((p) => (
            <PostCard key={"pin" + p.id} post={p} me={me} kind={channel.kind} acts={acts} />
          ))}
        </section>
      )}
      <h3 className="cn-h">{query ? "Search results" : "Latest"}</h3>
      {shown.length === 0 && pinIds.size === 0 && (
        <EmptyState
          title={query ? "No matching posts" : "No posts yet"}
          text={query ? "Try a different word." : "Posts from the school will appear here."}
        />
      )}
      {shown.map((p) => (
        <PostCard key={p.id} post={p} me={me} kind={channel.kind} acts={acts} />
      ))}
      {feed.hasMore && (
        <Button kind="secondary" busy={loadingMore} onClick={loadEarlier}>Show earlier posts</Button>
      )}
      {pending && (
        <ConfirmDialog
          title={pending.title}
          text={pending.text}
          confirm={pending.confirm}
          danger={pending.danger}
          onYes={runPending}
          onNo={() => setPending(null)}
        />
      )}
    </div>
  );
}

function MembersPanel({ me }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [pending, setPending] = useState(null);

  const load = useCallback(async () => {
    try {
      const suffix = applied ? "?q=" + encodeURIComponent(applied) : "";
      setData(await call("/api/connect/members/" + suffix));
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
  }, [applied]);

  useEffect(() => {
    const t = setTimeout(() => {
      load();
    }, 0);
    return () => clearTimeout(t);
  }, [load]);

  const setMute = async (m, on) => {
    try {
      await call("/api/connect/members/" + m.user_id + "/mute/", on ? "POST" : "DELETE");
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  const runPending = async () => {
    const c = pending;
    setPending(null);
    if (c) await setMute(c.member, true);
  };

  if (err && !data) return <ErrorState text={err} onRetry={load} />;
  if (!data) return <Loading />;
  return (
    <div className="cn-members">
      {err && <Alert kind="err">{err}</Alert>}
      <p className="cn-hint">
        {data.parent_count + (data.parent_count === 1 ? " parent is" : " parents are")} in this group, each linked to a learner.
        {me.is_admin ? "" : " Parents' names are visible only to school administrators."}
      </p>
      {me.is_admin && (
        <form
          className="cn-search"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(q.trim());
          }}
        >
          <input
            type="search"
            value={q}
            maxLength={60}
            placeholder="Search parents by name"
            aria-label="Search parents by name"
            onChange={(e) => setQ(e.target.value)}
          />
          <Button kind="secondary" size="sm" type="submit">Search</Button>
        </form>
      )}
      {data.members.map((m) => (
        <div className="cn-row" key={(m.user_id || "s") + m.name + m.role}>
          <b>{m.name}</b>
          <span className="cn-tag">{ROLE_TEXT[m.role] || "Parent"}</span>
          {m.muted && <span className="cn-tag cn-urgent">Muted</span>}
          {me.is_admin && m.role !== "admin" && (
            m.muted
              ? <Button kind="secondary" size="sm" onClick={() => setMute(m, false)}>Unmute</Button>
              : <Button kind="secondary" size="sm" onClick={() => setPending({ member: m })}>Mute</Button>
          )}
        </div>
      ))}
      {data.truncated && <p className="cn-hint">Showing the first 100 parents. Use search to find others.</p>}
      {pending && (
        <ConfirmDialog
          title={"Mute " + pending.member.name + "?"}
          text="They can still read posts but cannot post until you unmute them."
          confirm="Mute"
          danger
          onYes={runPending}
          onNo={() => setPending(null)}
        />
      )}
    </div>
  );
}

function ReportsPanel() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await call("/api/connect/reports/");
      setRows(d.reports);
      setErr("");
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      load();
    }, 0);
    return () => clearTimeout(t);
  }, [load]);

  const resolve = async (r, hide) => {
    try {
      await call("/api/connect/reports/" + r.id + "/resolve/", "POST", { hide });
      await load();
    } catch (e) {
      setErr(e.message);
    }
  };

  if (err && !rows) return <ErrorState text={err} onRetry={load} />;
  if (!rows) return <Loading />;
  if (rows.length === 0) return <EmptyState title="No open reports" text="Nothing needs your attention." />;
  return (
    <div>
      {err && <Alert kind="err">{err}</Alert>}
      {rows.map((r) => (
        <article className="cn-post urgent" key={r.id}>
          <header className="cn-ph">
            <b>{r.post.author}</b>
            <time className="cn-time" dateTime={r.post.created_at}>{when(r.post.created_at)}</time>
          </header>
          <p className="cn-body">{r.post.body}</p>
          {r.reason && <p className="cn-meta">{"Reason given: " + r.reason}</p>}
          <div className="cn-pa">
            <Button kind="secondary" size="sm" onClick={() => resolve(r, false)}>Dismiss</Button>
            <Button kind="teal" size="sm" onClick={() => resolve(r, true)}>Hide post</Button>
          </div>
        </article>
      ))}
    </div>
  );
}

export default function Connect() {
  const [boot, setBoot] = useState(null);
  const [bad, setBad] = useState("");
  const [channelId, setChannelId] = useState(null);
  const [view, setView] = useState("chat");

  const loadChannels = useCallback(async () => {
    try {
      const data = await call("/api/connect/channels/");
      setBoot(data);
      setBad("");
      setChannelId((cur) => (cur === null && data.channels.length ? data.channels[0].id : cur));
    } catch (e) {
      setBad(e.message);
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(() => {
      loadChannels();
    }, 0);
    const t = setInterval(() => {
      if (!document.hidden) loadChannels();
    }, 30000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [loadChannels]);

  if (bad && !boot) return <ErrorState text={bad} onRetry={loadChannels} />;
  if (!boot) return <Loading />;
  const { channels, me } = boot;
  const current = channels.find((c) => c.id === channelId) || channels[0];
  const tab = (on) => "cn-tab" + (on ? " on" : "");

  return (
    <div className="cn">
      <h2>Connect</h2>
      <p className="cn-hint">The school community space. Notices come from the school. Please keep posts respectful.</p>
      <nav className="cn-tabs" aria-label="Connect sections">
        {channels.map((c) => {
          const on = view === "chat" && current && current.id === c.id;
          return (
            <button
              key={c.id}
              type="button"
              className={tab(on)}
              aria-current={on ? "page" : undefined}
              onClick={() => {
                setChannelId(c.id);
            setView("chat");
              }}
            >
              {c.name}
              {c.unread > 0 && <span className="cn-badge">{c.unread}</span>}
            </button>
          );
        })}
        <button
          type="button"
          className={tab(view === "members")}
          aria-current={view === "members" ? "page" : undefined}
          onClick={() => setView("members")}
        >
          Members
        </button>
        {me.is_admin && (
          <button
            type="button"
            className={tab(view === "reports")}
            aria-current={view === "reports" ? "page" : undefined}
            onClick={() => setView("reports")}
          >
            Reports
          </button>
        )}
      </nav>
      {view === "chat" && current && <ChatPanel key={current.id} channel={current} me={me} onSeen={loadChannels} />}
      {view === "members" && <MembersPanel me={me} />}
      {view === "reports" && me.is_admin && <ReportsPanel />}
    </div>
  );
}
