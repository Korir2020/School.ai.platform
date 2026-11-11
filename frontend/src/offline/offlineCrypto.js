export const PBKDF2_ITERATIONS = 310_000;
const encoder = new TextEncoder();
const decoder = new TextDecoder();

function cryptoApi() {
  if (!globalThis.crypto?.subtle) throw new Error("Secure offline storage is unavailable in this browser.");
  return globalThis.crypto;
}

export async function deriveOfflineKey(passphrase, salt) {
  if (typeof passphrase !== "string" || passphrase.length < 10) {
    throw new Error("Use an offline passphrase of at least 10 characters.");
  }
  const crypto = cryptoApi();
  const material = await crypto.subtle.importKey("raw", encoder.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

function associatedData(metadata) {
  return encoder.encode(`${metadata.username}|${metadata.schoolId}|${metadata.savedAt}|${metadata.expiresAt ?? ""}`);
}

export async function encryptOfflinePayload(payload, metadata, salt = cryptoApi().getRandomValues(new Uint8Array(16))) {
  const crypto = cryptoApi();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveOfflineKey(metadata.passphrase, salt);
  const additionalData = associatedData(metadata);
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData }, key,
    encoder.encode(JSON.stringify(payload)));
  return {
    salt: Array.from(salt),
    iv: Array.from(iv),
    ciphertext: Array.from(new Uint8Array(ciphertext)),
  };
}

export async function decryptOfflinePayload(envelope, metadata, passphrase) {
  try {
    const key = await deriveOfflineKey(passphrase, new Uint8Array(envelope.salt));
    const additionalData = associatedData(metadata);
    const cleartext = await cryptoApi().subtle.decrypt({
      name: "AES-GCM", iv: new Uint8Array(envelope.iv), additionalData,
    }, key, new Uint8Array(envelope.ciphertext));
    return JSON.parse(decoder.decode(cleartext));
  } catch {
    throw new Error("That offline passphrase is incorrect, or this saved copy has been changed.");
  }
}
