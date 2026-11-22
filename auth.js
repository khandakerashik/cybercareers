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
let loginPromise = null;
// Keep the unlocked user's KEK available when browser storage is blocked.
// It is never used as (or installed over) the published snapshot's data key.
let liveSession = null;

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
    liveSession = { uid: s.uid, k: s.k, exp: Number(s.exp) };
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
  const session = { uid, name: identity.name, k: b64.encode(bits), exp: Date.now() + ttl };
  liveSession = { uid, k: session.k, exp: session.exp };
  saveSession(session, remember);
  return identity;
}

export function logout(reload = true) {
  dataKey = null; identity = null; liveSession = null;
  for (const s of [storage(true), storage(false)]) { try { s && s.removeItem(SESSION_KEY); } catch { /* ignore */ } }
  if (reload) location.reload();
}

async function gunzip(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

const liveError = (code, message) => Object.assign(new Error(message), { code });
const liveObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function liveBytes(value, min, max = min) {
  if (typeof value !== 'string' || value.length > Math.ceil(max / 3) * 4 || value.length % 4
      || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw liveError('invalid_progress', 'Invalid encrypted live progress.');
  let bytes;
  try { bytes = b64.decode(value); } catch { throw liveError('invalid_progress', 'Invalid encrypted live progress.'); }
  if (bytes.length < min || bytes.length > max) throw liveError('invalid_progress', 'Invalid encrypted live progress.');
  return bytes;
}

async function gunzipLive(bytes) {
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  const chunks = []; let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 1024 * 1024) {
        await reader.cancel();
        throw liveError('invalid_progress', 'Live progress exceeded the allowed size.');
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const plain = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { plain.set(chunk, offset); offset += chunk.length; }
  return plain;
}

/** Decrypt an authenticated Checks envelope for exactly the selected run.
 * This never changes the snapshot key or keyring used by loadJSON().
 */
export async function decryptLiveProgress(envelope, { repository, runId, runAttempt } = {}) {
  const authenticatedIdentity = identity, uid = identity?.uid;
  if (!dataKey || !uid) throw liveError('locked', 'Unlock the dashboard to read encrypted live progress.');
  const keys = ['format', 'repository', 'workflow_run_id', 'run_attempt', 'generated_at', 'iv', 'ct', 'users'];
  if (!liveObject(envelope) || Object.keys(envelope).some(key => !keys.includes(key)) || envelope.format !== 'CCLIVE1'
      || typeof repository !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(repository)
      || typeof envelope.repository !== 'string' || envelope.repository.toLowerCase() !== repository.toLowerCase()
      || !/^[1-9]\d{0,23}$/.test(String(runId ?? '')) || envelope.workflow_run_id !== String(runId)
      || !Number.isInteger(runAttempt) || runAttempt < 1 || runAttempt > 1000000 || envelope.run_attempt !== runAttempt
      || typeof envelope.generated_at !== 'string' || envelope.generated_at.length > 40 || !Number.isFinite(Date.parse(envelope.generated_at))
      || !liveObject(envelope.users)) throw liveError('invalid_progress', 'Live progress does not match this workflow run.');
  const users = Object.entries(envelope.users);
  if (users.length < 1 || users.length > 100) throw liveError('invalid_progress', 'Invalid encrypted live progress recipients.');
  for (const [recipient, wrapper] of users) {
    if (!/^[a-f\d]{64}$/.test(recipient) || !liveObject(wrapper) || Object.keys(wrapper).some(key => key !== 'iv' && key !== 'ct')) {
      throw liveError('invalid_progress', 'Invalid encrypted live progress recipients.');
    }
    liveBytes(wrapper.iv, 12); liveBytes(wrapper.ct, 48);
  }
  const iv = liveBytes(envelope.iv, 12), ciphertext = liveBytes(envelope.ct, 16, 48000);
  if (JSON.stringify(envelope).length > 48744) throw liveError('invalid_progress', 'Encrypted live progress exceeded the allowed size.');
  const wrapper = Object.hasOwn(envelope.users, uid) ? envelope.users[uid] : null;
  if (!wrapper) throw liveError('progress_access', 'This run did not include your dashboard account. Reconnect after the account configuration is updated.');
  const stored = readSession();
  const session = stored?.uid === uid ? stored : liveSession?.uid === uid ? liveSession : null;
  if (!session || Number(session.exp) <= Date.now()) throw liveError('locked', 'Unlock the dashboard again to read encrypted live progress.');
  const context = envelope.repository + ':' + envelope.workflow_run_id + ':' + envelope.run_attempt;
  let progress;
  try {
    const rawKey = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: liveBytes(wrapper.iv, 12), additionalData: enc.encode('cc-live-key:' + context + ':' + uid) },
      await aesKey(liveBytes(session.k, 32)), liveBytes(wrapper.ct, 48));
    const compressed = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv, additionalData: enc.encode('cc-live:' + context) }, await aesKey(rawKey), ciphertext);
    progress = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await gunzipLive(new Uint8Array(compressed))));
    if (!liveObject(progress)) throw new Error();
  } catch (error) {
    if (error.code === 'invalid_progress') throw error;
    throw liveError('progress_decryption', 'Live progress could not be decrypted for this account. Its encryption or account credentials may have changed.');
  }
  if (identity !== authenticatedIdentity || !dataKey) throw liveError('locked', 'The dashboard account changed while reading live progress.');
  return progress;
}

/** Fetch and decrypt one sealed data file, e.g. loadJSON('jobs.json'). */
export async function loadJSON(name) {
  if (!dataKey) throw new Error('Locked');
  const ring = await fetchKeyring();
  const decryptKey = dataKey;
  const info = ring.files && ring.files[name];
  if (!info) throw new Error(`${name} is not in the encrypted dataset`);
  const r = await fetch(VAULT + info.path + '?v=' + encodeURIComponent(ring.sealed_at || Date.now()), { cache: 'no-store' });
  if (!r.ok) throw new Error(`Could not load ${name}: ${r.status}`);
  const blob = new Uint8Array(await r.arrayBuffer());
  if (dec.decode(blob.slice(0, 4)) !== 'CCV1') throw new Error(`${name}: unexpected file format`);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: blob.slice(4, 16), additionalData: enc.encode('cc-file:' + name) }, decryptKey, blob.slice(16));
  return JSON.parse(dec.decode(await gunzip(new Uint8Array(plain))));
}

export function sealedAt() { return keyring && keyring.sealed_at; }

/** Refresh the hourly published snapshot without requiring a browser reload.
 * Install ring + key together, so a failed refresh cannot corrupt an open view.
 */
export async function refreshPublishedSession() {
  if (!vaultMode() || !dataKey) return { changed: false };
  const response = await fetch(VAULT + 'keyring.json?v=' + Date.now(), { cache: 'no-store' });
  if (!response.ok) throw new Error('Published snapshot is temporarily unavailable.');
  const ring = await response.json();
  const session = readSession();
  if (!session) { logout(false); return { reauthenticate: true }; }
  if (ring.sealed_at === keyring?.sealed_at && JSON.stringify(ring.fingerprints) === JSON.stringify(keyring?.fingerprints)
      && ring.users?.[session.uid]?.ct === keyring?.users?.[session.uid]?.ct) return { changed: false };
  const entry = ring.users && ring.users[session.uid];
  if (!entry) { logout(false); return { reauthenticate: true }; }
  try {
    const raw = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: b64.decode(entry.iv), additionalData: enc.encode('cc-dek:' + session.uid) },
      await aesKey(b64.decode(session.k)), b64.decode(entry.ct));
    const nextKey = await aesKey(raw);
    keyring = ring; dataKey = nextKey;
    return { changed: true };
  } catch {
    logout(false); return { reauthenticate: true };
  }
}

/** Show the login gate and resolve once the vault is unlocked. */
export function requireLogin() {
  if (loginPromise) return loginPromise;
  const gate = document.getElementById('authGate');
  const form = document.getElementById('authForm');
  const error = document.getElementById('authError');
  const button = document.getElementById('authSubmit');
  const label = button.querySelector('.auth-submit-label');
  let failures = 0;
  gate.classList.remove('auth-gate-leave');
  gate.hidden = false;
  button.disabled = false;
  label.textContent = 'Unlock dashboard';
  error.textContent = '';
  document.documentElement.classList.add('cc-locked');
  setTimeout(() => document.getElementById('authUser').focus(), 30);
  loginPromise = new Promise(resolve => {
    const handleSubmit = async event => {
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
        form.removeEventListener('submit', handleSubmit);
        loginPromise = null;
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
    };
    form.addEventListener('submit', handleSubmit);
  });
  return loginPromise;
}
