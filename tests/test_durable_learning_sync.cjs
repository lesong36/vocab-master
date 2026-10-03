const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const range = (start, end) => {
  const from = html.indexOf(start), to = html.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Missing code ${start}`);
  return html.slice(from, to);
};
const plain = value => JSON.parse(JSON.stringify(value));
const disk = new Map();
let storageFails = false;
const localStorage = {
  get length() { return disk.size; },
  key: index => [...disk.keys()][index] ?? null,
  removeItem: key => disk.delete(key),
  getItem: key => disk.get(key) || null,
  setItem: (key, value) => { if (storageFails) throw new Error('QuotaExceededError'); disk.set(key, value); },
};
const source = range('const normalizeWordStats =', 'const loadFromBrowser =');
const createApi = () => vm.runInNewContext(source + '\n({ sanitizeLearningPayload, normalizeReadingQueueCursor, enqueueLearningEvent, readLearningOutbox, writeLearningOutbox, syncLearningOutbox, replayPendingLearningEvents, normalizeStudyEvents, mergeStudyEvents, mergeCloudAppState, reconcileLearningState, collapseToReaderAccount, learningAccountKey, learningSnapshotKey, normalizeRewardLedger })', {
  STORAGE_VERSION: 1, READING_VOCAB_SECTION: '阅读生词本', MISTAKE_EXIT_STREAK: 3,
  localStorage, crypto: { randomUUID }, isHiddenGrade: () => false,
  createEmptyUser: name => ({ id: 'empty', name, words: [], studyEvents: [], selectedSections: [], updatedAt: '2026-10-03T08:00:00Z' }),
  parseSectionMeta: section => ({ grade: String(section || '').slice(0, 2) }),
});
let api = createApi();
const event = (id, result = 'incorrect') => ({ id, at: `2026-10-03T08:00:0${id === 'a' ? 0 : 1}Z`, wordId: 'word', result, section: '三上Unit 1' });
const state = (events = [], count = 0) => ({ version: 1, currentUserId: 'reader_account', savedAt: '2026-10-03T08:00:00Z', users: {
  reader_account: { id: 'reader_account', name: 'learner', words: [{ id: 'word', section: '三上Unit 1', correctCount: 0, incorrectCount: count, consecutiveCorrect: 0 }], studyEvents: events },
} });
const master = (events = [], count = 0) => ({ version: 3, words: {}, appState: state(events, count) });
const response = (events, count, ack = events.map(event => event.id)) => ({ data: { master: master(events, count), epoch: 'epoch-1', revision: 2, acknowledgedEventIds: ack }, error: null });

(async () => {
  const legacyCursor = '2026-10-01\u0000reading:term';
  assert.deepEqual(plain(api.sanitizeLearningPayload({ readingQueueCursor: legacyCursor })), { readingQueueCursor: { importedAt: '2026-10-01', wordId: 'reading:term' } });
  assert.throws(() => api.sanitizeLearningPayload({ note: 'cannot\u0000send' }), /空字符/);
  assert.throws(() => api.sanitizeLearningPayload({ ['bad\u0000key']: 'value' }), /空字符/);
  const historical = Array.from({ length: 5100 }, (_, index) => ({ ...event(`old-${index}`), id: `old-${index}` }));
  assert.equal(api.normalizeStudyEvents(historical).length, 5100, 'No history cap');
  const merged = api.mergeCloudAppState(state([event('old')]), state([event('new')]));
  assert.equal(merged.users.reader_account.studyEvents.length, 2, 'Merge file/browser records instead of selecting only newest snapshot');

  const tabA = createApi(), tabB = createApi();
  const staleTabB = tabB.readLearningOutbox('two-tabs');
  tabA.enqueueLearningEvent('two-tabs', event('tab-a'));
  tabB.enqueueLearningEvent('two-tabs', event('tab-b'));
  tabB.writeLearningOutbox('two-tabs', staleTabB);
  assert.deepEqual(plain(tabA.readLearningOutbox('two-tabs').events.map(event => event.id).sort()), ['tab-a', 'tab-b'], 'Stale metadata from another tab cannot overwrite appended answers');
  let receipt;
  const tabsFlight = tabA.syncLearningOutbox({ accountId: 'two-tabs', master: { ...master(), appState: { ...state(), currentUserId: 'reader_two-tabs', users: { 'reader_two-tabs': state().users.reader_account } } }, rpc: () => new Promise(resolve => { receipt = resolve; }) });
  tabB.enqueueLearningEvent('two-tabs', event('tab-c'));
  receipt({ data: { master: { ...master(), appState: { ...state(), currentUserId: 'reader_two-tabs', users: { 'reader_two-tabs': { ...state().users.reader_account, studyEvents: [event('tab-a'), event('tab-b')] } } } }, epoch: 'tabs-epoch', revision: 1, acknowledgedEventIds: ['tab-a', 'tab-b'] } });
  await tabsFlight;
  assert.deepEqual(plain(tabB.readLearningOutbox('two-tabs').events.map(event => event.id)), ['tab-c'], 'Acknowledgement removes only confirmed IDs while another tab appends');

  api.enqueueLearningEvent('account', event('a'));
  api = createApi();
  assert.equal(api.readLearningOutbox('account').events.length, 1, 'Reload retains pending answer');
  api.enqueueLearningEvent('account', { ...event('a'), result: 'correct' });
  assert.equal(api.readLearningOutbox('account').events[0].result, 'incorrect', 'Immutable event ID cannot be rewritten');
  storageFails = true;
  assert.throws(() => api.enqueueLearningEvent('account', event('b')), /QuotaExceeded/);
  storageFails = false;
  assert.deepEqual(plain(api.readLearningOutbox('account').events.map(event => event.id)), ['a'], 'Storage failure retains previously saved queue');

  let calls = 0;
  const rpc = async (name, args) => {
    calls++;
    assert.equal(name, 'sync_vocab_master_v3');
    assert.match(args.p_mutation_id, /^[0-9a-f-]{36}$/);
    assert.ok(args.p_master.appState.users.reader_account.studyEvents.some(event => event.id === 'a'));
    if (calls === 1) return { error: { code: '400', message: 'bad request' }, data: null };
    return response([event('a')], 1);
  };
  await assert.rejects(api.syncLearningOutbox({ accountId: 'account', master: master([], 999), rpc }), error => error.code === '400');
  assert.equal(api.readLearningOutbox('account').events.length, 1, '400 failure must remain retryable');
  const success = await api.syncLearningOutbox({ accountId: 'account', master: master([], 999), rpc });
  assert.equal(success.appState.users.reader_account.words[0].incorrectCount, 1, 'Server counters replace arbitrary stale client counters');
  assert.equal(api.readLearningOutbox('account').events.length, 0);
  assert.equal(api.readLearningOutbox('account').epoch, 'epoch-1');

  api.enqueueLearningEvent('account', event('a'));
  const incompleteAck = await api.syncLearningOutbox({ accountId: 'account', master: master(), rpc: async () => response([], 0, ['a']) });
  assert.equal(incompleteAck.pendingCount, 1, 'Receipt missing returned event does not clear queue');
  assert.equal(incompleteAck.appState.users.reader_account.words[0].incorrectCount, 1);
  const noReceipt = await api.syncLearningOutbox({ accountId: 'account', master: master(), rpc: async () => response([event('a')], 1, []) });
  assert.equal(noReceipt.pendingCount, 1);
  assert.equal(noReceipt.appState.users.reader_account.words[0].incorrectCount, 1, 'Returned event is never replayed twice');

  let finish;
  const inFlight = api.syncLearningOutbox({ accountId: 'account', master: master(), rpc: () => new Promise(resolve => { finish = resolve; }) });
  api.enqueueLearningEvent('account', event('b'));
  finish(response([event('a')], 1));
  const reconciled = await inFlight;
  assert.equal(reconciled.pendingCount, 1);
  assert.deepEqual(plain(reconciled.appState.users.reader_account.studyEvents.map(event => event.id)), ['a', 'b']);
  assert.equal(reconciled.appState.users.reader_account.words[0].incorrectCount, 2, 'Answer during request is applied once over acknowledged server baseline');
  const duplicate = await api.syncLearningOutbox({ accountId: 'account', master: master(), rpc: async () => response([event('a'), event('b')], 2) });
  assert.equal(duplicate.pendingCount, 0);
  assert.equal(duplicate.appState.users.reader_account.words[0].incorrectCount, 2);

  api.enqueueLearningEvent('account', event('a'));
  const switched = await api.syncLearningOutbox({ accountId: 'account', master: master(), rpc: async () => response([event('a')], 1), isCurrentAccount: () => false });
  assert.equal(switched, null);
  assert.equal(api.readLearningOutbox('account').events.length, 1, 'Account switch does not consume another account queue or apply its response');
  assert.equal(api.readLearningOutbox('other').events.length, 0);

  let epochCalls = 0;
  const rebased = await api.syncLearningOutbox({ accountId: 'account', master: master([], 999), rpc: async (_name, args) => {
    epochCalls++;
    if (epochCalls === 1) return { error: { code: 'P0001', details: 'VMEPOCH', message: 'Learning baseline changed; reload before syncing' } };
    if (epochCalls === 2) {
      assert.deepEqual(plain(args.p_master.appState.users), {});
      return response([], 0);
    }
    assert.equal(args.p_expected_epoch, 'epoch-1');
    assert.equal(args.p_master.appState.users.reader_account.words[0].incorrectCount, 1, 'Rebase discards obsolete snapshot counters while preserving pending answer');
    return response([event('a')], 1);
  } });
  assert.equal(rebased.pendingCount, 0);
  console.log('PASS: safe cursor boundary; durable reload; immutable events; retryable failures; receipt verification; authoritative counters; in-flight answer; account isolation; epoch rebase; unlimited history');
})().catch(error => { console.error(error); process.exitCode = 1; });

// Execute the real save/sync effects with controlled timers, rather than asserting source strings.
(async () => {
  const accountId = 'integration';
  const start = state(); start.currentUserId = `reader_${accountId}`;
  start.users = { [start.currentUserId]: { ...start.users.reader_account, id: start.currentUserId, updatedAt: start.savedAt, selectedSections: [], selectedGrade: null, readingFilters: { group: '', article: '', date: '', level: '' } } };
  const ctx = {
    ...api, STORAGE_VERSION: 1, localStorage, Date, JSON, console, crypto: { randomUUID },
    setErrorMsg() {},
    readerCloudUser: { id: accountId }, currentUserId: start.currentUserId, users: start.users,
    words: start.users[start.currentUserId].words, studyEvents: [], selectedGrade: null, selectedSections: [], readingFilters: { group: '', article: '', date: '', level: '' },
    cloudMasterStateLoaded: true, isHydrated: true, appState: 'select', syncRetryTick: 0,
    cloudMasterStateAppliedRef: { current: true }, cloudProgressWriteTimerRef: { current: null },
    lastCloudProgressSnapshotRef: { current: '' }, syncInFlightRef: { current: false }, syncAccountRef: { current: accountId },
    usersRef: { current: start.users }, wordsRef: { current: start.users[start.currentUserId].words },
    saveTimerRef: { current: null }, serverAvailableRef: { current: false },
    clearTimeout() {}, useEffect(fn) { fn(); }, timers: [],
    setTimeout(fn) { ctx.timers.push(fn); return ctx.timers.length; },
    setUsers(users) { ctx.users = users; ctx.usersRef.current = users; },
    setWords(words) { ctx.words = words; ctx.wordsRef.current = words; },
    setStudyEvents(events) { ctx.studyEvents = typeof events === 'function' ? events(ctx.studyEvents) : events; },
    setSelectedSections(value) { ctx.selectedSections = typeof value === 'function' ? value(ctx.selectedSections) : value; },
    setSelectedGrade(value) { ctx.selectedGrade = typeof value === 'function' ? value(ctx.selectedGrade) : value; },
    setReadingFilters(value) { ctx.readingFilters = typeof value === 'function' ? value(ctx.readingFilters) : value; },
    setSections(value) { ctx.sections = typeof value === 'function' ? value(ctx.sections || []) : value; },
    setCloudReadingStatus() {}, setSaveStatus() {}, saveToBrowser() { return true; },
    persistAppData: async () => 'browser', buildPayload: (currentUserId, users) => ({ version: 1, currentUserId, users }),
    serverAvailable: false,
  };
  let requests = 0;
  ctx.readerSupabase = { rpc: async (_name, args) => {
    requests++;
    return { data: { master: JSON.parse(api.learningSnapshotKey(args.p_master)), epoch: 'integration-epoch', revision: 1, acknowledgedEventIds: [] } };
  } };
  const runtime = vm.createContext(ctx);
  const syncEffect = range('      useEffect(() => {\n        if (!readerCloudUser || !cloudMasterStateLoaded', '      useEffect(() => {\n        const retry =');
  const saveEffect = range('      // Auto-save to local JSON file + browser cache', '      // Load bundled school vocabulary');
  vm.runInContext(syncEffect, runtime);
  while (ctx.timers.length) await ctx.timers.shift()();
  assert.equal(requests, 1);
  const timestamp = ctx.users[ctx.currentUserId].updatedAt;
  vm.runInContext(saveEffect, runtime);
  while (ctx.timers.length) await ctx.timers.shift()();
  assert.equal(ctx.users[ctx.currentUserId].updatedAt, timestamp, 'Remote hydration alone cannot stamp a new local modification');
  vm.runInContext(syncEffect, runtime);
  assert.equal(ctx.timers.length, 0, 'Acknowledged unchanged profile must not schedule another write');
  assert.equal(requests, 1, 'No save/sync feedback loop');
  ctx.lastCloudProgressSnapshotRef.current = '';
  let deliver;
  ctx.readerSupabase.rpc = (_name, args) => new Promise(resolve => { deliver = () => resolve({ data: { master: JSON.parse(api.learningSnapshotKey(args.p_master)), epoch: 'integration-epoch', revision: 2, acknowledgedEventIds: [] } }); });
  vm.runInContext(syncEffect, runtime);
  const request = ctx.timers.shift()();
  const changed = { ...ctx.usersRef.current[ctx.currentUserId], selectedSections: ['三上Unit 3'], updatedAt: '2026-10-03T10:00:00Z', words: [...ctx.wordsRef.current, { id: 'flight-word', english_word: 'flight', section: '阅读生词本', incorrectCount: 0, vocabMasterProgressUpdatedAt: '2026-10-03T10:00:00Z' }] };
  ctx.usersRef.current = { [ctx.currentUserId]: changed }; ctx.users = ctx.usersRef.current; ctx.wordsRef.current = changed.words; ctx.words = changed.words;
  deliver(); await request;
  assert.ok(ctx.words.some(word => word.id === 'flight-word'), 'Real sync response preserves imports added during its request');
  assert.deepEqual(plain(ctx.users[ctx.currentUserId].selectedSections), ['三上Unit 3'], 'Real sync response preserves selections changed during its request');
  assert.deepEqual(plain(ctx.selectedSections), ['三上Unit 3'], 'Selection controls reflect the reconciled authoritative profile');
  vm.runInContext(saveEffect, runtime);
  while (ctx.timers.length) await ctx.timers.shift()();
  assert.deepEqual(plain(ctx.users[ctx.currentUserId].selectedSections), ['三上Unit 3'], 'Autosave cannot overwrite canonical selections with stale controls');

  const remote = state();
  const local = state();
  local.users.reader_account.updatedAt = '2026-10-03T09:00:00Z';
  local.users.reader_account.selectedSections = ['三上Unit 2'];
  local.users.reader_account.words.push({ id: 'offline', english_word: 'offline', section: '阅读生词本', incorrectCount: 900, vocabMasterProgressUpdatedAt: '2026-10-03T09:00:00Z' });
  const reconciled = api.reconcileLearningState(remote, local, 'account');
  assert.equal(reconciled.users.reader_account.words.find(word => word.id === 'offline').incorrectCount, 0);
  assert.deepEqual(plain(reconciled.users.reader_account.selectedSections), ['三上Unit 2'], 'In-flight selection retained');
  const foreign = api.collapseToReaderAccount(state(), { id: 'foreign' });
  assert.equal(foreign.users.reader_foreign.words.length, 0, 'Reader A data cannot become reader B data');
  assert.equal(api.learningAccountKey('reader_account'), 'account');
  const archiveCode = range('              const primary = loadFromBrowser();', '            } catch (error) {');
  const archivedKeys = [];
  const largePrimary = { currentUserId: 'reader_account', users: { reader_account: { ...state().users.reader_account, source: 'x'.repeat(1705134) } } };
  const archiveContext = { loadFromBrowser: () => largePrimary, usersRef: { current: {} }, session: { user: { id: 'account' } }, localStorage: { setItem() { throw new Error('QuotaExceededError'); } } };
  vm.runInNewContext('{'+archiveCode+'}', archiveContext);
  archiveContext.session.user.id = 'other';
  archiveContext.localStorage.setItem = key => archivedKeys.push(key);
  vm.runInNewContext('{'+archiveCode+'}', archiveContext);
  assert.deepEqual(archivedKeys, ['vocabmaster_account_archive_v3:account'], 'Whole profile archived only on a real account switch; startup does not duplicate near-quota snapshot');

  const recordCode = range('      const recordStudyEvent =', '      const updateGlobalWordStats =');
  vm.runInContext(recordCode + '\nthis.recordActual = recordStudyEvent;', runtime);
  ctx.readerCloudUser = { id: 'different-account' };
  const before = api.readLearningOutbox('different-account').events.length;
  assert.equal(ctx.recordActual('word', false, ctx.words, null), false, 'Answer rejected while cloud identity differs from loaded profile');
  assert.equal(api.readLearningOutbox('different-account').events.length, before);
  ctx.readerCloudUser = { id: accountId };
  assert.equal(ctx.recordActual('word', false, ctx.words, null), true);
  const genuine = api.readLearningOutbox(accountId).events.at(-1);
  assert.equal(genuine.durableVersion, 3, 'Only newly accepted answer gets durable accounting marker');
  assert.equal(genuine.wordDefinition.id, 'word', 'Durable answer carries recoverable word definition');

  console.log('PASS: actual save/sync effect settles after one acknowledgement; in-flight metadata and offline definitions retained; foreign reader profiles excluded');
})().catch(error => { console.error(error); process.exitCode = 1; });
