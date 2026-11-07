/* CyberCareers BD — login gate + in-browser decryption for the GitHub Pages vault.
 *
 * The published site contains only ciphertext (encrypted/*.bin) and a keyring.
 * A username + password derives a per-user key (PBKDF2-SHA256, 600k iterations)
 * that unwraps the current data key; files are AES-256-GCM decrypted and
 * gunzipped locally. Nothing is sent anywhere: there is no server to send to.
 */
const CONFIG = (globalThis.CC_CONFIG && typeof globalThis.CC_CONFIG === 'object') ? globalThis.CC_CONFIG : { mode: 'local' };
const VAULT = String(CONFIG.vault || 'encrypted/');
const SESSION_KEY = 'ccbd-vault-session';
const enc = new TextEncoder();
const dec = new TextDecoder();
let keyring = null;
let dataKey = null;
let identity = null;

export const vaultMode = () => CONFIG.mode === 'vault';
export const currentUser = () => identity;

const b64 = {
  decode: s => Uint8Array.from(atob(s), c => c.charCodeAt(0)),
  encode: bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))),
};

async function sha256hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', enc.encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function userId(username) {
  return sha256hex('cybercareers:v1:' + String(username).trim().toLowerCase().normalize('NFC'));
}

async function deriveKekBits(password, salt, iterations) {
  const base = await crypto.subtle.importKey('raw', enc.encode(String(password).normalize('NFC')), 'PBKDF2', false, ['deriveBits']);
  return crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, base, 256);
}

async function aesKey(raw) {
  return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['decrypt']);
}

async function fetchKeyring(fresh = false) {
  if (keyring && !fresh) return keyring;
  const r = await fetch(VAULT + 'keyring.json?v=' + Date.now(), { cache: 'no-store' });
  if (!r.ok) throw new Error('The encrypted dataset is not published yet (keyring missing).');
  keyring = await r.json();
  return keyring;
}

async function unwrap(uid, kekBits) {
  const ring = await fetchKeyring(true);
  const entry = ring.users && ring.users[uid];
  if (!entry) throw new Error('bad-credentials');
  try {
    const raw = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: b64.decode(entry.iv), additionalData: enc.encode('cc-dek:' + uid) },
      await aesKey(kekBits), b64.decode(entry.ct));
    dataKey = await aesKey(raw);
  } catch {
    throw new Error('bad-credentials');
  }
}

function storage(remember) {
  try { return remember ? localStorage : sessionStorage; } catch { return null; }
}

function saveSession(record, remember) {
  for (const s of [storage(true), storage(false)]) { try { s && s.removeItem(SESSION_KEY); } catch { /* ignore */ } }
  try { const s = storage(remember); s && s.setItem(SESSION_KEY, JSON.stringify(record)); } catch { /* private mode */ }
}

function readSession() {
  for (const s of [storage(false), storage(true)]) {
    try {
      const v = s && JSON.parse(s.getItem(SESSION_KEY) || 'null');
      if (v && v.uid && v.k && Number(v.exp) > Date.now()) return v;
    } catch { /* ignore */ }
  }
  return null;
}

/** Try a stored session; returns true when the data key is unlocked. */
export async function restoreSession() {
  const s = readSession();
  if (!s) return false;
  try {
    await unwrap(s.uid, b64.decode(s.k));
    identity = { name: s.name, uid: s.uid };
    return true;
  } catch (e) {
    if (e.message === 'bad-credentials') logout(false); // revoked, password changed, or key rotated without this user
    return false;
  }
}

export async function login(username, password, remember = false) {
  const uid = await userId(username);
  const ring = await fetchKeyring(true);
  const entry = ring.users && ring.users[uid];
  // Same work for unknown users so timing does not reveal valid usernames.
  const salt = entry ? b64.decode(entry.salt) : enc.encode(uid.slice(0, 16));
  const bits = await deriveKekBits(password, salt, entry ? Number(entry.iterations) : 600000);
  await unwrap(uid, bits);
  identity = { name: String(username).trim(), uid };
  const ttl = remember ? 7 * 24 * 3600e3 : 12 * 3600e3;
  saveSession({ uid, name: identity.name, k: b64.encode(bits), exp: Date.now() + ttl }, remember);
  return identity;
}

export function logout(reload = true) {
  dataKey = null; identity = null;
  for (const s of [storage(true), storage(false)]) { try { s && s.removeItem(SESSION_KEY); } catch { /* ignore */ } }
  if (reload) location.reload();
}

async function gunzip(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Fetch and decrypt one sealed data file, e.g. loadJSON('jobs.json'). */
export async function loadJSON(name) {
  if (!dataKey) throw new Error('Locked');
  const ring = await fetchKeyring();
  const info = ring.files && ring.files[name];
  if (!info) throw new Error(`${name} is not in the encrypted dataset`);
  const r = await fetch(VAULT + info.path + '?v=' + encodeURIComponent(ring.sealed_at || Date.now()), { cache: 'no-store' });
  if (!r.ok) throw new Error(`Could not load ${name}: ${r.status}`);
  const blob = new Uint8Array(await r.arrayBuffer());
  if (dec.decode(blob.slice(0, 4)) !== 'CCV1') throw new Error(`${name}: unexpected file format`);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: blob.slice(4, 16), additionalData: enc.encode('cc-file:' + name) }, dataKey, blob.slice(16));
  return JSON.parse(dec.decode(await gunzip(new Uint8Array(plain))));
}

export function sealedAt() { return keyring && keyring.sealed_at; }

/** Show the login gate and resolve once the vault is unlocked. */
export function requireLogin() {
  const gate = document.getElementById('authGate');
  const form = document.getElementById('authForm');
  const error = document.getElementById('authError');
  const button = document.getElementById('authSubmit');
  const label = button.querySelector('.auth-submit-label');
  let failures = 0;
  gate.hidden = false;
  document.documentElement.classList.add('cc-locked');
  setTimeout(() => document.getElementById('authUser').focus(), 30);
  return new Promise(resolve => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const user = form.username.value, pass = form.password.value, remember = form.remember.checked;
      if (!user.trim() || !pass) { error.textContent = 'Enter your username and password.'; return; }
      button.disabled = true; error.textContent = ''; label.textContent = 'Verifying & decrypting…';
      try {
        await login(user, pass, remember);
        form.password.value = '';
        gate.classList.add('auth-gate-leave');
        document.documentElement.classList.remove('cc-locked');
        setTimeout(() => { gate.hidden = true; }, 260);
        resolve(identity);
      } catch (e) {
        failures += 1;
        error.textContent = e.message === 'bad-credentials'
          ? 'Username or password is incorrect.'
          : (e.message || 'Could not unlock the dataset.');
        form.password.select();
        // Gentle client-side back-off; the real protection is PBKDF2 + strong passwords.
        await new Promise(r => setTimeout(r, Math.min(8000, 600 * failures * failures)));
      } finally {
        button.disabled = false; label.textContent = 'Unlock dashboard';
      }
    });
  });
}
