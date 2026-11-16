const DB_NAME = "marian-learning-offline-v1";
const STORE = "packages";
const PBKDF2_ITERATIONS = 310000;
const enc = new TextEncoder();
const dec = new TextDecoder();
function openDb() {
  if (!globalThis.indexedDB) throw new Error("This browser does not support secure offline learning storage.");
  return new Promise((resolve, reject) => { const r = indexedDB.open(DB_NAME, 1); r.onupgradeneeded = () => r.result.createObjectStore(STORE, { keyPath: "id" }); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
}
async function keyFor(passphrase, salt) { if (!passphrase || passphrase.length < 10) throw new Error("Use an offline passphrase of at least 10 characters."); const c = globalThis.crypto; const raw = await c.subtle.importKey("raw", enc.encode(passphrase), "PBKDF2", false, ["deriveKey"]); return c.subtle.deriveKey({ name: "PBKDF2", salt, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" }, raw, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]); }
async function seal(payload, passphrase) { const c = globalThis.crypto; const salt = c.getRandomValues(new Uint8Array(16)); const iv = c.getRandomValues(new Uint8Array(12)); const key = await keyFor(passphrase, salt); const bytes = await c.subtle.encrypt({ name: "AES-GCM", iv }, key, enc.encode(JSON.stringify(payload))); return { salt: [...salt], iv: [...iv], ciphertext: [...new Uint8Array(bytes)] }; }
async function openEnvelope(envelope, passphrase) { try { const key = await keyFor(passphrase, new Uint8Array(envelope.salt)); const bytes = await crypto.subtle.decrypt({ name: "AES-GCM", iv: new Uint8Array(envelope.iv) }, key, new Uint8Array(envelope.ciphertext)); return JSON.parse(dec.decode(bytes)); } catch { throw new Error("That offline passphrase is incorrect, or the saved learning package changed."); } }
async function put(record) { const db = await openDb(); return new Promise((resolve, reject) => { const tx = db.transaction(STORE, "readwrite"); tx.objectStore(STORE).put(record); tx.oncomplete = () => { db.close(); resolve(); }; tx.onerror = () => { db.close(); reject(tx.error); }; }); }
async function get(id) { const db = await openDb(); return new Promise((resolve, reject) => { const r = db.transaction(STORE, "readonly").objectStore(STORE).get(id); r.onsuccess = () => { db.close(); resolve(r.result || null); }; r.onerror = () => { db.close(); reject(r.error); }; }); }
export function newDeviceId() { const bytes = crypto.getRandomValues(new Uint8Array(16)); return [...bytes].map((x) => x.toString(16).padStart(2, "0")).join(""); }
export async function saveLearningPackage(serverPackage, passphrase) { const record = { id: "learner-package", packageId: serverPackage.package_id, deviceId: serverPackage.device_id, expiresAt: serverPackage.expires_at, savedAt: Date.now(), envelope: await seal(serverPackage.manifest, passphrase) }; await put(record); return record; }
export async function loadLearningPackage(passphrase) { const record = await get("learner-package"); if (!record) throw new Error("No offline learning package is saved on this device."); if (Date.now() >= Date.parse(record.expiresAt)) throw new Error("This offline learning package has expired. Connect and prepare a fresh package."); return { ...record, manifest: await openEnvelope(record.envelope, passphrase) }; }
export async function forgetLearningPackage() { const db = await openDb(); await new Promise((resolve, reject) => { const tx = db.transaction(STORE, "readwrite"); tx.objectStore(STORE).delete("learner-package"); tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); }); db.close(); }
export function newOfflineOperation(itemType, itemId, eventType, details = {}) { return { operation_id: crypto.randomUUID(), item_type: itemType, item_id: Number(itemId), event_type: eventType, details }; }
export const OFFLINE_MAX_AGE_DAYS = 7;

export const LEARNING_COPY = {
  en: { motivation: "Your learning rhythm", streak: "day streak", milestones: "Milestones", challenges: "Optional challenges", turnOff: "Turn off motivation features", turnOn: "Turn on motivation features", prepare: "Prepare offline learning", saved: "Saved on this device", passphrase: "Offline passphrase", sync: "Sync saved learning activity", forget: "Forget offline package", accessibility: "Accessibility" },
  sw: { motivation: "Mdundo wako wa kujifunza", streak: "siku mfululizo", milestones: "Hatua muhimu", challenges: "Changamoto za hiari", turnOff: "Zima vipengele vya motisha", turnOn: "Washa vipengele vya motisha", prepare: "Andaa kujifunza bila intaneti", saved: "Imehifadhiwa kwenye kifaa hiki", passphrase: "Nenosiri la kujifunza bila intaneti", sync: "Sawazisha shughuli za kujifunza", forget: "Ondoa kifurushi cha nje ya mtandao", accessibility: "Ufikiaji" },
};
export function copy(language) { return LEARNING_COPY[language === "sw" ? "sw" : "en"]; }
