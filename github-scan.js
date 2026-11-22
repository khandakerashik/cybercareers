/* GitHub Actions control for a static, authenticated CyberCareers dashboard.
 * The GitHub token lives only in this module's closure. Never persist it.
 */
const API = 'https://api.github.com';
const API_VERSION = '2026-03-10';
const CHECK_NAME = 'CyberCareers live collection';
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'pending', 'requested']);
const RUN_STATUSES = new Set([...ACTIVE, 'completed']);
const MAX_CHECK_TEXT = 65000;

export class GitHubScanError extends Error {
  constructor(code, message, details = {}) {
    super(message); this.name = 'GitHubScanError'; this.code = code;
    Object.assign(this, details);
  }
}

const plainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const validId = value => (typeof value === 'string' || Number.isSafeInteger(value)) && /^(?:[1-9]\d{0,23})$/.test(String(value));
const isoDate = value => typeof value === 'string' && value.length < 50 && Number.isFinite(Date.parse(value)) ? value : null;
const fail = (code, message, details) => new GitHubScanError(code, message, details);

function parseEnvelope(text, repository, run) {
  if (typeof text !== 'string' || text.length > MAX_CHECK_TEXT || !text.startsWith('CCLIVE1\n')) {
    throw fail('invalid_progress', 'The workflow published an invalid live progress message.');
  }
  const encoded = text.slice(8);
  if (!encoded || encoded.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) {
    throw fail('invalid_progress', 'The workflow published an invalid live progress message.');
  }
  try {
    const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
    const envelope = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!plainObject(envelope) || envelope.format !== 'CCLIVE1'
        || typeof envelope.repository !== 'string' || envelope.repository.toLowerCase() !== repository.toLowerCase()
        || envelope.workflow_run_id !== run.id || envelope.run_attempt !== run.attempt) throw new Error();
    return envelope;
  } catch {
    throw fail('invalid_progress', 'Live progress does not match this workflow run.');
  }
}

/** Create a scanner for one fixed repository, workflow, and branch/ref.
 * GET failures are reported with retryAfter (seconds); the UI controls polling.
 * A dispatch is sent once. An ambiguous response is reconciled by reads only.
 */
export function createGitHubScanner({ repository, workflow = 'pages.yml', ref, fetchImpl = globalThis.fetch,
  now = () => Date.now(), timeoutMs = 15000 } = {}) {
  if (ref == null) ref = '';
  if (typeof repository !== 'string' || repository.length > 210
      || !/^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(repository)
      || typeof workflow !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$/.test(workflow)
      || typeof ref !== 'string' || ref.length > 250 || /[\x00-\x20\x7f]/.test(ref)
      || typeof fetchImpl !== 'function' || typeof now !== 'function') {
    throw fail('invalid_configuration', 'GitHub repository, workflow, and branch settings are incomplete.');
  }
  ref = ref.replace(/^refs\/heads\//, '');
  const configuredRef = ref;
  timeoutMs = Number.isFinite(timeoutMs) ? Math.min(60000, Math.max(50, timeoutMs)) : 15000;
  const repoPath = '/repos/' + repository.split('/').map(encodeURIComponent).join('/');
  const workflowPath = repoPath + '/actions/workflows/' + encodeURIComponent(workflow);
  let token = '', connected = false, generation = 0, workflowId = null;
  let trackedRun = null, pendingDispatch = null, scanPromise = null, blockedUntil = 0, failures = 0;
  const controllers = new Set(), checkIds = new Map();

  const clock = () => Number(now());
  const assertSession = expected => {
    if (expected !== generation || !token) throw fail('disconnected', 'Connect GitHub to request or follow a scan.');
  };
  const requireConnected = () => {
    if (!connected || !token) throw fail('disconnected', 'Connect GitHub to request or follow a scan.');
    return generation;
  };

  function delayFrom(response) {
    const retry = response.headers?.get?.('retry-after');
    if (retry && /^\d+$/.test(retry)) return Math.min(86400, Math.max(1, Number(retry)));
    if (retry && Number.isFinite(Date.parse(retry))) return Math.min(86400, Math.max(1, Math.ceil((Date.parse(retry) - clock()) / 1000)));
    const reset = Number(response.headers?.get?.('x-ratelimit-reset'));
    if (reset > clock() / 1000) return Math.min(86400, Math.max(1, Math.ceil(reset - clock() / 1000)));
    return 60;
  }

  async function request(path, { method = 'GET', body, expected = generation } = {}) {
    assertSession(expected);
    const remaining = Math.ceil((blockedUntil - clock()) / 1000);
    if (remaining > 0) throw fail('rate_limited', 'GitHub requests are paused briefly. Try again after the displayed wait.', { retryAfter: remaining });
    const controller = new AbortController(); controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      let response;
      try {
        response = await fetchImpl(API + path, {
          method, headers: { Accept: 'application/vnd.github+json', Authorization: 'Bearer ' + token,
            'X-GitHub-Api-Version': API_VERSION, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal,
          redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store',
        });
      } catch {
        assertSession(expected);
        failures += 1;
        throw fail(controller.signal.aborted ? 'timeout' : 'network_error',
          controller.signal.aborted ? 'GitHub did not respond before the request timed out.' : 'GitHub could not be reached. Check the connection and try again.',
          { retryAfter: Math.min(60, 5 * 2 ** Math.min(failures - 1, 4)), uncertain: method === 'POST' });
      }
      assertSession(expected);
      if (response.redirected || response.status >= 300 && response.status < 400) {
        throw fail('redirect_rejected', 'GitHub redirected the request. Check the configured repository before reconnecting.', { uncertain: method === 'POST' });
      }
      if (!response.ok) {
        const status = response.status;
        if (status === 429 || status === 403 && (response.headers?.get?.('retry-after')
            || response.headers?.get?.('x-ratelimit-remaining') === '0')) {
          const retryAfter = delayFrom(response); blockedUntil = clock() + retryAfter * 1000;
          throw fail('rate_limited', 'GitHub has limited requests. Wait before trying again.', { status, retryAfter });
        }
        if (status === 401) throw fail('unauthorized', 'GitHub rejected this token. Reconnect using a valid token.', { status });
        if (status === 403) throw fail('forbidden', 'This token does not have the GitHub permission required for this operation.', { status, retryAfter: 60 });
        if (status === 404) throw fail('not_found', 'The GitHub repository, workflow, or run is unavailable to this token.', { status });
        if (status === 422) throw fail('invalid_request', 'GitHub rejected the scan settings. Check the workflow branch and collect input.', { status });
        failures += 1;
        throw fail('github_error', 'GitHub could not complete this request.',
          { status, retryAfter: Math.min(60, 5 * 2 ** Math.min(failures - 1, 4)), uncertain: method === 'POST' && status >= 500 });
      }
      failures = 0;
      if (response.status === 204) return null;
      let value;
      try { value = await response.json(); }
      catch { throw fail('invalid_response', 'GitHub returned an unreadable response.', { uncertain: method === 'POST' }); }
      assertSession(expected);
      return value;
    } finally { clearTimeout(timer); controllers.delete(controller); }
  }

  function normalize(raw) {
    if (!plainObject(raw) || !validId(raw.id) || raw.repository?.full_name
        && (typeof raw.repository.full_name !== 'string' || raw.repository.full_name.toLowerCase() !== repository.toLowerCase())
        || workflowId && String(raw.workflow_id) !== workflowId || raw.head_branch !== ref) {
      throw fail('invalid_response', 'GitHub returned a workflow run outside the configured workflow or branch.');
    }
    const status = RUN_STATUSES.has(raw.status) ? raw.status : 'unknown';
    const attempt = Number(raw.run_attempt);
    if (!Number.isSafeInteger(attempt) || attempt < 1) throw fail('invalid_response', 'GitHub returned an invalid workflow run attempt.');
    return { id: String(raw.id), attempt, status, conclusion: typeof raw.conclusion === 'string' ? raw.conclusion : null,
      active: ACTIVE.has(status) && !raw.conclusion,
      htmlUrl: 'https://github.com/' + repository + '/actions/runs/' + String(raw.id),
      headSha: /^[a-f\d]{40,64}$/i.test(raw.head_sha || '') ? raw.head_sha : null,
      event: typeof raw.event === 'string' ? raw.event : '', createdAt: isoDate(raw.created_at), updatedAt: isoDate(raw.updated_at),
    };
  }

  async function listRuns(extra = {}, expected = generation) {
    const query = new URLSearchParams({ branch: ref, per_page: '100', ...extra });
    const response = await request(workflowPath + '/runs?' + query, { expected });
    if (!Array.isArray(response?.workflow_runs) || response.workflow_runs.length > 100) throw fail('invalid_response', 'GitHub returned an invalid run list.');
    return response.workflow_runs.map(normalize);
  }

  async function connect(value) {
    if (typeof value !== 'string' || value.trim().length < 10 || value.length > 512 || /[^\x21-\x7e]/.test(value.trim())) {
      throw fail('invalid_token', 'Enter a GitHub access token.');
    }
    disconnect(); token = value.trim(); const expected = generation;
    try {
      if (!configuredRef) {
        const metadata = await request(repoPath, { expected });
        if (!plainObject(metadata) || typeof metadata.full_name !== 'string'
            || metadata.full_name.toLowerCase() !== repository.toLowerCase()
            || typeof metadata.default_branch !== 'string' || !metadata.default_branch
            || metadata.default_branch.length > 250 || /[\x00-\x20\x7f]/.test(metadata.default_branch)) {
          throw fail('invalid_response', 'GitHub did not return a valid default branch for this repository.');
        }
        ref = metadata.default_branch;
      }
      const info = await request(workflowPath, { expected });
      if (!plainObject(info) || !validId(info.id)) throw fail('invalid_response', 'GitHub returned an invalid workflow.');
      if (info.state !== 'active') throw fail('workflow_disabled', 'Enable the GitHub Pages workflow before requesting a scan.');
      workflowId = String(info.id);
      await listRuns({ per_page: '1' }, expected);
      assertSession(expected); connected = true;
      return { repository, workflow, ref, connected: true };
    } catch (error) { if (expected === generation) disconnect(); throw error; }
  }

  function disconnect() {
    generation += 1; token = ''; connected = false; workflowId = null;
    trackedRun = null; pendingDispatch = null; scanPromise = null; blockedUntil = 0; failures = 0; checkIds.clear();
    for (const controller of controllers) controller.abort();
    controllers.clear();
  }

  async function latestRun() {
    const expected = requireConnected();
    return (await listRuns({ per_page: '1' }, expected))[0] || null;
  }

  async function findDispatched(expected) {
    if (!pendingDispatch) return null;
    const context = pendingDispatch;
    const runs = await listRuns({ event: 'workflow_dispatch', created: '>=' + new Date(context.started - 10000).toISOString() }, expected);
    const candidates = runs.filter(run => run.event === 'workflow_dispatch' && run.createdAt
      && Date.parse(run.createdAt) >= context.started - 10000 && !context.previousIds.has(run.id));
    // Concurrent requests from different users cannot be reliably attributed.
    if (candidates.length !== 1) return null;
    trackedRun = candidates[0]; pendingDispatch = null;
    return trackedRun;
  }

  async function requestScanOnce() {
    const expected = requireConnected();
    if (pendingDispatch) {
      const dispatchStartedAt = new Date(pendingDispatch.started).toISOString();
      let run = null;
      try { run = await findDispatched(expected); } catch (error) { if (error.code === 'disconnected') throw error; }
      return { state: run ? 'attached' : 'dispatch_unconfirmed', run, dispatchStartedAt,
        ...(run ? {} : { message: 'The earlier request has not been confirmed. It will be checked again without sending another scan request.' }) };
    }
    // Status-filtered reads also find a long-running scan behind many newer completed runs.
    const groups = await Promise.all([...ACTIVE].map(status => listRuns({ status, per_page: '1' }, expected)));
    const active = groups.flat().filter(run => run.active).sort((a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0));
    if (active.length) {
      trackedRun = active[0];
      return { state: 'attached', run: trackedRun, dispatchStartedAt: null };
    }
    const previous = await listRuns({ event: 'workflow_dispatch', per_page: '100' }, expected);
    const started = clock(), dispatchStartedAt = new Date(started).toISOString();
    pendingDispatch = { started, previousIds: new Set(previous.map(run => run.id)) };
    try {
      const response = await request(workflowPath + '/dispatches', { method: 'POST',
        body: { ref, inputs: { collect: true }, return_run_details: true }, expected });
      if (response && validId(response.workflow_run_id)) {
        const id = String(response.workflow_run_id);
        try {
          trackedRun = normalize(await request(repoPath + '/actions/runs/' + id, { expected }));
          pendingDispatch = null;
          return { state: 'dispatched', run: trackedRun, dispatchStartedAt };
        } catch (error) {
          if (error.code === 'disconnected') throw error;
          // The dispatch ID is confirmed; status will be read on the next poll.
          trackedRun = { id, attempt: 1, status: 'unknown', conclusion: null, active: false,
            htmlUrl: 'https://github.com/' + repository + '/actions/runs/' + id, headSha: null,
            event: 'workflow_dispatch', createdAt: null, updatedAt: null };
          pendingDispatch = null;
          return { state: 'dispatched', run: trackedRun, dispatchStartedAt,
            message: 'GitHub accepted the scan. Its current run status is temporarily unavailable.', retryAfter: error.retryAfter };
        }
      }
    } catch (error) {
      if (expected !== generation) throw error;
      if (!error.uncertain) { pendingDispatch = null; throw error; }
      // The POST may already have succeeded. Never retry it automatically.
    }
    let run = null;
    try { run = await findDispatched(expected); } catch (error) { if (error.code === 'disconnected') throw error; }
    return { state: run ? 'dispatched' : 'dispatch_unconfirmed', run, dispatchStartedAt,
      ...(run ? {} : { message: 'GitHub has not confirmed a run yet. The request will be checked without dispatching it again.' }) };
  }

  function requestScan() {
    if (scanPromise) return scanPromise;
    const task = requestScanOnce();
    scanPromise = task;
    task.finally(() => { if (scanPromise === task) scanPromise = null; }).catch(() => {});
    return task;
  }

  async function lookupCheck(run, expected) {
    if (!run.headSha) return null;
    const cacheKey = run.id + ':' + run.attempt + ':' + run.headSha;
    const externalId = 'CCLIVE1:' + run.id + ':' + run.attempt;
    const matches = check => plainObject(check) && check.name === CHECK_NAME && check.external_id === externalId
      && check.head_sha?.toLowerCase() === run.headSha.toLowerCase() && validId(check.id);
    const cached = checkIds.get(cacheKey);
    if (cached) {
      try {
        const check = await request(repoPath + '/check-runs/' + cached, { expected });
        if (matches(check)) return check;
      } catch (error) { if (error.code !== 'not_found') throw error; }
      checkIds.delete(cacheKey);
    }
    // Scheduled runs commonly share a commit SHA. filter=latest would hide older attempts.
    for (let page = 1; page <= 10; page++) {
      const query = new URLSearchParams({ check_name: CHECK_NAME, filter: 'all', per_page: '100', page: String(page) });
      const response = await request(repoPath + '/commits/' + run.headSha + '/check-runs?' + query, { expected });
      if (!Array.isArray(response?.check_runs) || response.check_runs.length > 100) throw fail('invalid_progress', 'GitHub returned an invalid progress check list.');
      const matching = response.check_runs.filter(matches).sort((a, b) => Number(b.id) - Number(a.id));
      if (matching.length) { checkIds.set(cacheKey, String(matching[0].id)); return matching[0]; }
      if (response.check_runs.length < 100) return null;
    }
    throw fail('progress_history_limit', 'Live progress is outside the current check-history window. Open the workflow for details.');
  }

  async function getRun(runId = null) {
    const expected = requireConnected();
    if (runId !== null && !validId(runId)) throw fail('invalid_run', 'Choose a valid GitHub workflow run.');
    if (!runId && pendingDispatch) {
      const run = await findDispatched(expected);
      if (!run) return { run: null, progressEnvelope: null, progressStatus: 'pending',
        message: 'Waiting for GitHub to confirm the requested workflow run.' };
    }
    const id = runId === null ? trackedRun?.id : String(runId);
    if (!id) {
      trackedRun = await latestRun();
      if (!trackedRun) return { run: null, progressEnvelope: null, progressStatus: 'unavailable', message: 'No workflow runs are available yet.' };
    } else trackedRun = normalize(await request(repoPath + '/actions/runs/' + id, { expected }));
    const run = trackedRun;
    try {
      const check = await lookupCheck(run, expected);
      if (!check?.output?.text) return { run, progressEnvelope: null, progressStatus: run.active ? 'pending' : 'unavailable',
        message: run.active ? 'Waiting for the collection progress check.' : 'This run did not publish readable live progress.' };
      return { run, progressEnvelope: parseEnvelope(check.output.text, repository, run), progressStatus: 'available' };
    } catch (error) {
      if (error.code === 'disconnected') throw error;
      return { run, progressEnvelope: null, progressStatus: error.code === 'invalid_progress' ? 'invalid' : 'unavailable',
        message: error.code === 'forbidden' || error.code === 'not_found'
          ? 'The workflow status is available, but this token cannot read its live progress check. Check repository Checks read access.'
          : error.message || 'Live progress is temporarily unavailable.', retryAfter: error.retryAfter };
    }
  }

  return Object.freeze({ connect, requestScan, getRun, latestRun, disconnect, isConnected: () => connected });
}
