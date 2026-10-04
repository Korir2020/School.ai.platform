const BASE = import.meta.env.VITE_API_URL;
const J = { "Content-Type": "application/json" };
const save = (d) => { localStorage.setItem("access", d.access); if (d.refresh) localStorage.setItem("refresh", d.refresh); };

export async function login(username, password) {
  const r = await fetch(`${BASE}/api/auth/login/`, { method: "POST", headers: J, body: JSON.stringify({ username, password }) });
  if (r.status === 429) throw new Error("Too many attempts. Wait a minute and try again.");
  if (!r.ok) throw new Error("Wrong username or password");
  save(await r.json());
}
async function refresh() {
  const r = await fetch(`${BASE}/api/auth/refresh/`, { method: "POST", headers: J, body: JSON.stringify({ refresh: localStorage.getItem("refresh") }) });
  if (!r.ok) return false;
  save(await r.json());
  return true;
}
export async function api(path, method = "GET", body) {
  const run = () => fetch(`${BASE}${path}`, { method, headers: { ...J, Authorization: `Bearer ${localStorage.getItem("access")}` }, body: body ? JSON.stringify(body) : undefined });
  let r = await run();
  if (r.status === 401 && (await refresh())) r = await run();
  return r;
}
export async function logout() {
  try { await api("/api/auth/logout/", "POST", { refresh: localStorage.getItem("refresh") }); } catch (e) {}
  localStorage.clear();
}

// Fetch every page of a list endpoint (also accepts plain arrays).
export async function listAll(path) {
  const sep = path.includes("?") ? "&" : "?";
  let url = `${path}${sep}page_size=200`;
  const out = [];
  for (let i = 0; i < 200 && url; i++) {
    const r = await api(url);
    if (!r.ok) return out;
    const d = await r.json();
    if (Array.isArray(d)) return d;
    out.push(...(d.results || []));
    if (!d.next) break;
    const n = new URL(d.next, "http://x");
    url = `${n.pathname}${n.search}`;
  }
  return out;
}
