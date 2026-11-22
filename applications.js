/* User-owned application records. Browser storage only; no network or server API. */
export const NOTE_LIMIT = 1000;
const VERSION = 1;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_RECORDS = 2000;
const MAX_SCOPE_LENGTH = 4000;
const SNAPSHOT_LIMITS = Object.freeze({
  id: 240, title: 240, company: 180, source: 180, source_url: 2048, apply_url: 2048,
  deadline: 40, location: 240, region: 80, category: 120, company_sector: 120, vacancy_status: 40, posting_identifier: 240,
});
const RECORD_KEYS = new Set(['id', 'identity', 'job_ids', 'job', 'applied_at', 'applied_date', 'note', 'updated_at']);
const SNAPSHOT_KEYS = new Set([...Object.keys(SNAPSHOT_LIMITS), 'shared_listing_url']);
const ENVELOPE_KEYS = new Set(['version', 'scope', 'revision', 'records']);

export class ApplicationStoreError extends Error {
  constructor(code, message) { super(message); this.name = 'ApplicationStoreError'; this.code = code; }
}
const fail = (code, message) => { throw new ApplicationStoreError(code, message); };
const copy = value => value == null ? value : JSON.parse(JSON.stringify(value));
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
  && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
const normalized = value => String(value || '').normalize('NFKC').trim().replace(/\s+/gu, ' ');
function text(value, maximum, field, code = 'invalid_record') {
  if (value == null) return '';
  if (typeof value !== 'string' || value.length > maximum || /\u0000/u.test(value)) {
    fail(code, `Invalid ${field}.`);
  }
  return value;
}
function dateOnly(value, code = 'invalid_record') {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/u.test(value)) fail(code, 'Use a valid application date (YYYY-MM-DD).');
  const date = new Date(value + 'T00:00:00.000Z');
  if (!Number.isFinite(+date) || date.toISOString().slice(0, 10) !== value) fail(code, 'Use a valid application date (YYYY-MM-DD).');
  return value;
}
function timestamp(value, code = 'corrupt_storage') {
  if (typeof value !== 'string' || value.length > 40 || !/^\d{4}-\d{2}-\d{2}T/u.test(value) || !Number.isFinite(Date.parse(value))) {
    fail(code, 'Invalid application timestamp.');
  }
  return value;
}
function bdDate(date) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Dhaka', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
function belongs(host, domain) { return host === domain || host.endsWith('.' + domain); }

function canonicalUrl(value, code = 'invalid_record') {
  if (!value) return '';
  let url;
  try { url = new URL(value); } catch { fail(code, 'The saved job URL is invalid.'); }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || !url.hostname) {
    fail(code, 'The saved job URL must be an HTTP or HTTPS link without credentials.');
  }
  const host = url.hostname.toLowerCase().replace(/\.$/u, '');
  const query = new Map([...url.searchParams].map(([key, val]) => [key.toLowerCase(), val]));
  if (belongs(host, 'linkedin.com')) {
    const match = url.pathname.match(/^\/(?:comm\/)?jobs\/view\/(?:[^/]*-)?(\d+)\/?$/iu);
    const id = match?.[1] || (/^\/(?:comm\/)?jobs(?:\/|$)/iu.test(url.pathname) ? query.get('currentjobid') : '');
    if (/^\d+$/u.test(id || '')) return `https://www.linkedin.com/jobs/view/${id}`;
  }
  if (belongs(host, 'bdjobs.com')) {
    const match = url.pathname.match(/\/(?:details|jobdetails)\/(\d+)(?:\/|$)/iu);
    const id = match?.[1] || (/\/jobdetails?\.(?:asp|aspx|php)$/iu.test(url.pathname) ? query.get('id') || query.get('jobid') : '');
    if (/^\d+$/u.test(id || '')) return `https://jobs.bdjobs.com/jobdetails.asp?id=${id}`;
  }
  if (belongs(host, 'indeed.com')) {
    const id = query.get('jk') || query.get('vjk');
    if (/^[0-9a-f]{12,20}$/iu.test(id || '')) return `https://www.indeed.com/viewjob?jk=${id.toLowerCase()}`;
  }
  if (belongs(host, 'glassdoor.com')) {
    const id = query.get('joblistingid') || query.get('jl');
    if (/^\d+$/u.test(id || '')) return `https://www.glassdoor.com/job-listing/index.htm?jl=${id}`;
  }
  url.hostname = host;
  url.hash = '';
  url.pathname = url.pathname.replace(/\/+$/u, '') || '/';
  for (const key of [...url.searchParams.keys()]) {
    if (/^utm_/iu.test(key) || /^(?:fbclid|gclid|trk|tracking|trackingid)$/iu.test(key)) url.searchParams.delete(key);
  }
  url.searchParams.sort();
  return url.href;
}
function roleKey(value) {
  return normalized(value).toLowerCase().replace(/\bsr\.?\b/gu, 'senior')
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, ' ').trim();
}
function companyKey(value) {
  return roleKey(value).replace(/\b(?:limited|ltd|plc|inc|llc)\b/gu, ' ').replace(/\s+/gu, ' ').trim();
}
function snapshot(job, code = 'invalid_record', stored = false) {
  if (!plain(job)) fail(code, 'A valid job is required.');
  if (stored && Object.keys(job).some(key => !SNAPSHOT_KEYS.has(key))) fail(code, 'Unexpected saved job fields.');
  const result = {};
  for (const [key, maximum] of Object.entries(SNAPSHOT_LIMITS)) {
    const value = ['id','posting_identifier'].includes(key) && Number.isSafeInteger(job[key]) ? String(job[key]) : job[key];
    result[key] = text(value, maximum, `job ${key}`, code).trim();
  }
  if (!result.title) fail(code, 'The job title is required.');
  if (!result.id && !result.source_url && !result.apply_url) fail(code, 'The job needs a posting link or collector ID.');
  if (result.source_url) canonicalUrl(result.source_url, code);
  if (result.apply_url) canonicalUrl(result.apply_url, code);
  if (result.deadline) {
    if (/^\d{4}-\d{2}-\d{2}$/u.test(result.deadline)) dateOnly(result.deadline, code);
    else timestamp(result.deadline, code);
  }
  if (job.shared_listing_url != null && typeof job.shared_listing_url !== 'boolean') fail(code, 'Invalid shared job page flag.');
  result.shared_listing_url = job.shared_listing_url === true;
  return result;
}
function knownPostingUrl(value) {
  if (!value) return false;
  const url = new URL(value), host = url.hostname;
  if (belongs(host, 'linkedin.com')) return /^\/jobs\/view\/\d+$/u.test(url.pathname);
  if (belongs(host, 'bdjobs.com')) return /jobdetails\.asp$/iu.test(url.pathname) && url.searchParams.has('id');
  if (belongs(host, 'indeed.com')) return url.searchParams.has('jk');
  if (belongs(host, 'glassdoor.com')) return url.searchParams.has('jl');
  if (belongs(host, 'lever.co') || belongs(host, 'ashbyhq.com')) return url.pathname.split('/').filter(Boolean).length >= 2;
  if (belongs(host, 'greenhouse.io') || belongs(host, 'greenhouse.com')) return /\/jobs\/\d+/u.test(url.pathname) || url.searchParams.has('token');
  if (belongs(host, 'myworkdayjobs.com')) return /\/job\//u.test(url.pathname);
  if (belongs(host, 'workable.com')) return /\/j\/[^/]+/u.test(url.pathname);
  if (belongs(host, 'smartrecruiters.com')) return /\/[^/]+\/\d+/u.test(url.pathname);
  if (belongs(host, 'recruitee.com')) return /\/o\/[^/]+/u.test(url.pathname);
  return false;
}
function postingUrl(job) {
  const source = canonicalUrl(job.source_url), apply = canonicalUrl(job.apply_url);
  if (knownPostingUrl(source)) return source;
  if (knownPostingUrl(apply)) return apply;
  if (!source) return apply;
  const path = new URL(source).pathname;
  const shared = job.shared_listing_url || /\.pdf$/iu.test(path) || /(?:circular|notice|announcement)/iu.test(path)
    || /^\/?$/u.test(path) || /\/(?:careers?|jobs?|vacanc(?:y|ies)|openings?|recruitment)\/?$/iu.test(path);
  return shared && apply && apply !== source ? apply : source;
}
function identityFor(job) {
  const url = postingUrl(job);
  // Explicit requisition IDs and application links separate identically titled
  // roles on a shared circular; the collector's regenerated hash is not an ID.
  return JSON.stringify([url ? 'url' : 'id', url || job.id, roleKey(job.title), companyKey(job.company), job.posting_identifier || '']);
}
function identityId(identity) {
  // Deterministic non-security identifier. Full identities are also validated
  // and compared, so an accidental hash collision never overwrites a record.
  const words = [0x811c9dc5, 0x9e3779b9, 0x85ebca6b, 0xc2b2ae35];
  for (let i = 0; i < identity.length; i++) {
    const code = identity.charCodeAt(i);
    for (let j = 0; j < words.length; j++) words[j] = Math.imul(words[j] ^ (code + j * 131), 0x01000193) >>> 0;
  }
  return 'applied-' + words.map(word => word.toString(16).padStart(8, '0')).join('');
}
function sized(raw, code) {
  // UTF-8 bytes bound both parsing and writes; localStorage's implementation
  // quota can be smaller and is handled separately by the commit path.
  if (typeof raw !== 'string' || raw.length > MAX_BYTES || new TextEncoder().encode(raw).byteLength > MAX_BYTES) {
    fail(code, 'Application storage is too large to load safely.');
  }
}
function validateRecord(value) {
  if (!plain(value) || Object.keys(value).some(key => !RECORD_KEYS.has(key))) fail('corrupt_storage', 'Invalid saved application record.');
  const job = snapshot(value.job, 'corrupt_storage', true);
  const identity = identityFor(job);
  if (value.identity !== identity || value.id !== identityId(identity)) fail('corrupt_storage', 'Saved application identity is inconsistent.');
  if (!Array.isArray(value.job_ids) || value.job_ids.length > 20 || value.job_ids.some(id => typeof id !== 'string' || !id || id.length > 240)) {
    fail('corrupt_storage', 'Invalid saved job aliases.');
  }
  text(value.note, NOTE_LIMIT, 'application note', 'corrupt_storage');
  if (typeof value.note !== 'string') fail('corrupt_storage', 'Invalid saved note.');
  return {
    id: value.id, identity, job_ids: [...new Set(value.job_ids)], job,
    applied_at: timestamp(value.applied_at), applied_date: dateOnly(value.applied_date, 'corrupt_storage'),
    note: value.note, updated_at: timestamp(value.updated_at),
  };
}
function storageError(error, action) {
  if (error instanceof ApplicationStoreError) return error;
  const quota = error && (error.name === 'QuotaExceededError' || error.name === 'NS_ERROR_DOM_QUOTA_REACHED' || error.code === 22 || error.code === 1014);
  return new ApplicationStoreError(quota ? 'quota_exceeded' : 'storage_unavailable',
    quota ? 'Browser storage is full. The application change was not saved.'
      : `Browser storage is unavailable. Could not ${action} application records.`);
}

/**
 * createApplicationStore({ storage, scope, now? })
 *
 * scope: site base URL + '|user:' + authenticated UID, or '|local'. Scope is
 * supplied by the caller; records never leave this browser. now is an optional
 * clock function returning a Date/ISO timestamp, primarily for deterministic QA.
 *
 * Each mutation rereads the scoped payload before changing one record, which
 * preserves unrelated changes made by other tabs since the last reload. Call
 * reload() on the matching storage event. localStorage has no cross-tab CAS;
 * callers should not represent this as a server or transactional cloud store.
 */
export function createApplicationStore(options = {}) {
  if (!plain(options)) fail('invalid_record', 'Application store options are invalid.');
  const scope = options.scope;
  if (typeof scope !== 'string' || !scope.trim() || scope.length > MAX_SCOPE_LENGTH || /\u0000/u.test(scope)) {
    fail('invalid_record', 'A nonempty application storage scope of at most 4,000 characters is required.');
  }
  let storage;
  try { storage = Object.hasOwn(options, 'storage') ? options.storage : globalThis.localStorage; }
  catch (error) { throw storageError(error, 'access'); }
  if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') fail('storage_unavailable', 'Browser storage is unavailable.');
  const storageKey = 'ccbd:applications:v1:' + encodeURIComponent(scope);
  const clock = typeof options.now === 'function' ? options.now : () => new Date();
  function instant() {
    const date = new Date(clock());
    if (!Number.isFinite(+date)) fail('invalid_record', 'The current application date is invalid.');
    return date;
  }
  function read() {
    let raw;
    try { raw = storage.getItem(storageKey); } catch (error) { throw storageError(error, 'read'); }
    if (raw === null) return { version: VERSION, scope, revision: 0, records: [] };
    sized(raw, 'corrupt_storage');
    let parsed;
    try { parsed = JSON.parse(raw); } catch { fail('corrupt_storage', 'Saved application data is malformed. It has not been overwritten.'); }
    if (!plain(parsed) || Object.keys(parsed).some(key => !ENVELOPE_KEYS.has(key)) || parsed.version !== VERSION || parsed.scope !== scope
        || !Number.isSafeInteger(parsed.revision) || parsed.revision < 0 || !Array.isArray(parsed.records) || parsed.records.length > MAX_RECORDS) {
      fail('corrupt_storage', 'Saved application data has an unsupported or invalid format. It has not been overwritten.');
    }
    const records = parsed.records.map(validateRecord);
    if (new Set(records.map(record => record.id)).size !== records.length || new Set(records.map(record => record.identity)).size !== records.length) {
      fail('corrupt_storage', 'Saved application identities are duplicated. It has not been overwritten.');
    }
    return { version: VERSION, scope, revision: parsed.revision, records };
  }
  let state = read();
  function ordered(records = state.records) {
    return copy([...records].sort((a, b) => b.applied_date.localeCompare(a.applied_date) || b.applied_at.localeCompare(a.applied_at) || a.id.localeCompare(b.id)));
  }
  function resolve(records, target) {
    if (typeof target === 'string') {
      const exact = records.find(record => record.id === target);
      if (exact) return exact;
      const matches = records.filter(record => record.job_ids.includes(target) || record.job.id === target);
      return matches.length === 1 ? matches[0] : null;
    }
    if (!plain(target)) return null;
    // The public record itself is also a convenient caller argument.
    if (typeof target.id === 'string' && target.job) return records.find(record => record.id === target.id) || null;
    const job = snapshot(target);
    const identity = identityFor(job);
    const exact = records.find(record => record.identity === identity);
    if (exact) return exact;
    // A stable collector ID is only an alias, never permission to merge two
    // different role titles or requisition links that happen to reuse that ID.
    const url = postingUrl(job);
    const matches = records.filter(record => (record.job_ids.includes(job.id) || record.job.id === job.id)
      && roleKey(record.job.title) === roleKey(job.title)
      && !(job.posting_identifier && record.job.posting_identifier && job.posting_identifier !== record.job.posting_identifier)
      && (!url || !postingUrl(record.job) || url === postingUrl(record.job)));
    return matches.length === 1 ? matches[0] : null;
  }
  function commit(latest) {
    if (latest.records.length > MAX_RECORDS) fail('too_large', 'Too many application records. Remove an older record before adding another.');
    const next = { ...latest, revision: latest.revision + 1 };
    if (!Number.isSafeInteger(next.revision)) fail('too_large', 'Application storage revision is out of range.');
    const raw = JSON.stringify(next);
    sized(raw, 'too_large');
    try { storage.setItem(storageKey, raw); } catch (error) { throw storageError(error, 'save'); }
    // Persistence must succeed before in-memory records change.
    state = next;
  }
  function existing(latest, target) {
    const found = resolve(latest.records, target);
    if (!found) fail('not_found', 'This job has not been marked as applied in the current browser profile.');
    return found;
  }
  return Object.freeze({
    storageKey,
    list() { return ordered(); },
    get(target) {
      // An unrelated malformed live feed row is not evidence that saved user
      // records are corrupt. Writes and reloads still validate strictly.
      try { return copy(resolve(state.records, target)); }
      catch (error) { if (error instanceof ApplicationStoreError && error.code === 'invalid_record') return null; throw error; }
    },
    reload() { const latest = read(); state = latest; return ordered(); },
    mark(job, appliedDate) {
      const savedJob = snapshot(job);
      const latest = read();
      const previous = resolve(latest.records, savedJob);
      if (previous) {
        const nextDate = appliedDate === undefined ? previous.applied_date : dateOnly(appliedDate);
        const nextAliases = [...new Set([...previous.job_ids, savedJob.id].filter(Boolean))].slice(-20);
        if (nextDate === previous.applied_date && JSON.stringify(nextAliases) === JSON.stringify(previous.job_ids)) {
          state = latest;
          return copy(previous);
        }
        previous.applied_date = nextDate;
        previous.job_ids = nextAliases;
        previous.updated_at = instant().toISOString();
        commit(latest);
        return copy(previous);
      }
      const date = instant(), identity = identityFor(savedJob), id = identityId(identity);
      if (latest.records.some(record => record.id === id)) fail('invalid_record', 'A job identity conflict prevented saving this application.');
      const record = { id, identity, job_ids: savedJob.id ? [savedJob.id] : [], job: savedJob,
        applied_at: date.toISOString(), applied_date: appliedDate === undefined ? bdDate(date) : dateOnly(appliedDate),
        note: '', updated_at: date.toISOString() };
      latest.records.push(record);
      commit(latest);
      return copy(record);
    },
    saveNote(target, note) {
      if (typeof note !== 'string' || note.length > NOTE_LIMIT || /\u0000/u.test(note)) fail('invalid_record', `Notes must contain at most ${NOTE_LIMIT} characters.`);
      const latest = read(), record = existing(latest, target);
      if (record.note === note) { state = latest; return copy(record); }
      record.note = note;
      record.updated_at = instant().toISOString();
      commit(latest);
      return copy(record);
    },
    remove(target) {
      const latest = read(), record = existing(latest, target);
      latest.records = latest.records.filter(item => item.id !== record.id);
      commit(latest);
      return copy(record);
    },
  });
}
