const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const range = (start, end) => {
  const from = html.indexOf(start), to = html.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Missing ${start}`);
  return html.slice(from, to);
};
const plain = value => JSON.parse(JSON.stringify(value));
let now = Date.parse('2026-10-03T12:00:00Z');
class Clock extends Date { static now() { return now; } }
const tab = new Map(), browser = new Map();
let sessionFails = false, queueFails = false;
const queue = [{ id: 'secret-id', at: '2026-10-03T11:59:00Z', englishWord: 'PRIVATE' }];
const ctx = {
  Date: Clock, Map, Number, localStorage: { getItem: key => browser.get(key), setItem: (key, value) => browser.set(key, value) }, sessionStorage: {
    getItem: key => tab.get(key),
    setItem: (key, value) => { if (sessionFails) throw new Error('quota'); tab.set(key, value); },
  },
  learningMutationId: randomUUID,
  readLearningOutbox: () => { if (queueFails) throw new Error('private storage failure'); return { events: queue }; },
};
vm.createContext(ctx);
vm.runInContext(range('    // Health metadata uses a separate request', '    const reconcileLearningState =') + '\nthis.report = reportLearningSyncHealth; this.classify = learningSyncErrorCode;', ctx);
const calls = [];
let rejectReport = false;
const rpc = async (name, args) => { calls.push({ name, args: plain(args) }); return { error: rejectReport ? { message: 'PRIVATE token' } : null }; };
const report = (values = {}) => ctx.report({ accountId: 'account', rpc, ...values });
const settle = async () => { for (let index = 0; index < 6; index++) await Promise.resolve(); };
(async () => {
  await report();
  assert.equal(calls.length, 0, 'Unconfirmed startup cannot claim healthy');
  await report({ healthy: false, error: { code: '22P05', message: 'PRIVATE database detail' } });
  assert.equal(calls[0].name, 'report_vocab_sync_health_v1');
  assert.deepEqual(calls[0].args, {
    p_device_id: browser.get('vocabmaster_sync_device_v1:account'), p_pending_count: 1,
    p_oldest_pending_at: '2026-10-03T11:59:00.000Z', p_error_code: 'database_rejected', p_healthy: false,
  });
  assert.match(calls[0].args.p_device_id, /^[a-f0-9-]{36}$/);
  const reopen = vm.createContext({ ...ctx, sessionStorage: { getItem() { return null; }, setItem() {} } });
  vm.runInContext(range('    // Health metadata uses a separate request', '    const reconcileLearningState =') + '\nthis.report = reportLearningSyncHealth;', reopen);
  const reopenCalls = [];
  await reopen.report({ accountId: 'account', rpc: async (_name, args) => { reopenCalls.push(plain(args)); return {}; }, healthy: true });
  assert.equal(reopenCalls[0].p_device_id, calls[0].args.p_device_id, 'Closing and reopening resolves the same browser/account incident');
  await reopen.report({ accountId: 'other-account', rpc: async (_name, args) => { reopenCalls.push(plain(args)); return {}; }, healthy: true });
  assert.notEqual(reopenCalls[1].p_device_id, calls[0].args.p_device_id, 'Device identity scoped to account');
  assert.ok(!JSON.stringify(calls).includes('PRIVATE'), 'No answer content or raw errors leave the browser');
  now += 15000; await report();
  assert.equal(calls.length, 1, 'Unchanged heartbeat limited to one minute');
  now += 45000; await report();
  assert.equal(calls.length, 2);
  assert.equal(calls.at(-1).args.p_error_code, 'database_rejected', 'Heartbeat retains unresolved failure');
  await report({ healthy: true });
  assert.equal(calls.length, 3, 'Actual success transition reports immediately');
  assert.equal(calls.at(-1).args.p_error_code, null);
  rejectReport = true;
  await report({ healthy: false, error: { syncHealthCode: 'receipt_invalid' } });
  now += 15000; await report();
  assert.equal(calls.length, 5, 'Failed telemetry is retried by the 15 second loop');
  assert.equal(calls.at(-1).args.p_error_code, 'receipt_invalid');
  rejectReport = false; await report();
  await report();
  assert.equal(calls.length, 6, 'Successful retry reinstates one minute throttle');
  queueFails = true; await report({ healthy: true });
  assert.equal(calls.at(-1).args.p_error_code, 'storage_failed', 'Unreadable outbox can never report healthy');
  queueFails = false;
  sessionFails = true;
  // Independent tab with blocked sessionStorage must still send storage failure.
  const fallback = vm.createContext({ ...ctx, localStorage: { getItem() { throw new Error('quota'); } }, sessionStorage: { getItem() { throw new Error('quota'); } } });
  vm.runInContext(range('    // Health metadata uses a separate request', '    const reconcileLearningState =') + '\nthis.report = reportLearningSyncHealth;', fallback);
  await fallback.report({ accountId: 'other', rpc, healthy: false, error: { name: 'QuotaExceededError' } });
  assert.equal(calls.at(-1).args.p_error_code, 'storage_failed');
  assert.match(calls.at(-1).args.p_device_id, /^[a-f0-9-]{36}$/);
  assert.equal(ctx.classify({ syncHealthCode: 'invalid_payload', message: 'PRIVATE' }), 'invalid_payload');
  assert.equal(ctx.classify({ message: 'PRIVATE' }), 'sync_failed');

  // Execute the application's actual sync and heartbeat effects with a failed write,
  // failed telemetry request, retry, then a confirmed sync recovery.
  const user = { words: [], studyEvents: [], selectedSections: [], updatedAt: '2026-10-03T12:00:00Z' };
  const state = { version: 1, currentUserId: 'reader_effect', users: { reader_effect: user }, savedAt: new Date(user.updatedAt).toISOString() };
  let writeFails = true, healthFails = true;
  const effectCalls = [], timers = [];
  Object.assign(ctx, {
    readLearningOutbox: () => ({ events: [] }),
    STORAGE_VERSION: 1, readerCloudUser: { id: 'effect' }, currentUserId: 'reader_effect',
    cloudMasterStateLoaded: true, cloudMasterStateAppliedRef: { current: true }, syncAccountRef: { current: 'effect' },
    words: [], users: state.users, usersRef: { current: state.users }, wordsRef: { current: [] },
    syncInFlightRef: { current: false }, cloudProgressWriteTimerRef: { current: null },
    lastCloudProgressSnapshotRef: { current: '' }, syncRetryTick: 0,
    useEffect(fn) { fn(); }, setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {},
    collapseToReaderAccount: state => state, learningSnapshotKey: JSON.stringify,
    reconcileLearningState: state => state, replayPendingLearningEvents: state => state,
    normalizeStudyEvents: events => events, saveToBrowser: () => true,
    setCloudReadingStatus() {}, setUsers(value) { ctx.users = value; }, setWords() {}, setStudyEvents() {},
    setSelectedSections() {}, setSelectedGrade() {}, setReadingFilters() {}, setSections() {},
    syncLearningOutbox: async () => {
      if (writeFails) throw { code: '22P05', message: 'PRIVATE' };
      return { appState: state, master: { words: {}, appState: state }, pendingCount: 0 };
    },
    readerSupabase: { rpc: async (name, args) => {
      effectCalls.push({ name, args: plain(args) });
      return { error: healthFails ? { message: 'PRIVATE' } : null };
    } },
  });
  const syncEffect = range('      useEffect(() => {\n        if (!readerCloudUser || !cloudMasterStateLoaded', '      useEffect(() => {\n        if (!readerCloudUser || syncAccountRef.current');
  const heartbeat = range('      useEffect(() => {\n        if (!readerCloudUser || syncAccountRef.current', '      useEffect(() => {\n        const retry =');
  vm.runInContext(syncEffect, ctx);
  await timers.shift()(); await settle();
  assert.equal(effectCalls.at(-1).args.p_error_code, 'database_rejected');
  healthFails = false; now += 15000;
  vm.runInContext(heartbeat, ctx); await settle();
  assert.equal(effectCalls.length, 2);
  assert.equal(effectCalls.at(-1).args.p_healthy, false);
  writeFails = false;
  vm.runInContext(syncEffect, ctx);
  await timers.shift()(); await settle();
  assert.equal(effectCalls.at(-1).args.p_healthy, true);
  assert.equal(effectCalls.at(-1).args.p_error_code, null);
  vm.runInContext(syncEffect, ctx);
  assert.equal(timers.length, 0, 'Health acknowledgement causes no snapshot sync loop');
  now += 60000; vm.runInContext(heartbeat, ctx); await settle();
  assert.equal(effectCalls.at(-1).args.p_healthy, true, 'Unchanged online profile still reports health');
  assert.ok(!JSON.stringify(effectCalls).includes('PRIVATE'));
  console.log('PASS: safe telemetry, immediate failures/recovery, throttled heartbeat, retry, storage fallback, real sync effect integration');
})().catch(error => { console.error(error); process.exitCode = 1; });
