const PRIVATE_PATH = /(?:^|\/)(?:api|auth|receipt|receipts|report|reports|attachment|attachments|private|mutation)(?:\/|$)/i;
const STATIC_EXT = /\.(?:html|js|mjs|css|svg|png|jpg|jpeg|webp|ico|webmanifest|woff2?)$/i;

export function isShellCacheRequest({ url, origin, method = "GET", authorization = false }, knownAssets = []) {
  let parsed;
  try { parsed = new URL(url, origin); } catch { return false; }
  if (String(method).toUpperCase() !== "GET" || parsed.origin !== origin || authorization || parsed.search || parsed.hash) return false;
  if (PRIVATE_PATH.test(parsed.pathname) || parsed.pathname.startsWith("/api")) return false;
  if (parsed.pathname === "/" || parsed.pathname === "/index.html") return true;
  if (!STATIC_EXT.test(parsed.pathname)) return false;
  return knownAssets.includes(parsed.pathname);
}

export function isApiPath(pathname) {
  return /^\/api(?:\/|$)/i.test(pathname);
}
