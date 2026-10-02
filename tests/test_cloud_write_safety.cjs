const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync(path.join(__dirname, '..', 'vocabulary_app.html'), 'utf8');
const range = (start, end) => {
  const first = html.indexOf(start);
  const last = html.indexOf(end, first);
  assert.ok(first >= 0 && last > first, `Missing application code: ${start}`);
  return html.slice(first, last);
};
const helpers = vm.runInNewContext(
  range('const HIDDEN_GRADES =', 'const LESSON_TEXT_FILES =') +
  range('const parseSectionMeta =', 'const isRecognitionWord =') +
  range('const normalizeWordStats =', 'const loadFromBrowser =') +
  '\n({ mergeCloudAppState, collapseToReaderAccount })',
  { STORAGE_VERSION: 1, READING_VOCAB_SECTION: '阅读生词本' },
);
const callbackStart = 'cloudProgressWriteTimerRef.current = setTimeout(async () => {';
const callback = range(callbackStart, '}, 600);').slice(callbackStart.length);
const event = (id, at) => ({ id, wordId: 'school', at, result: 'incorrect', section: '三上Unit 1' });
const state = (events, incorrectCount) => ({
  version: 1,
  currentUserId: 'reader_account',
  users: { reader_account: {
    id: 'reader_account', name: 'Account',
    words: [{ id: 'school', section: '三上Unit 1', incorrectCount }],
    studyEvents: events,
  } },
});
const historical = event('historical', '2026-09-29T04:00:00Z');
const today = event('today', '2026-10-02T04:00:00Z');

async function runWrite(readResult) {
  const writes = [];
  const statuses = [];
  const snapshot = { current: 'previous-snapshot' };
  const readerSupabase = {
    from(table) {
      assert.equal(table, 'reader_sync_state');
      return {
        select(column) { assert.equal(column, 'vocab_master_progress'); return this; },
        eq(column, account) {
          assert.equal(column, 'user_id');
          assert.equal(account, 'account');
          return this;
        },
        async maybeSingle() { return readResult; },
        async upsert(payload, options) {
          assert.equal(options.onConflict, 'user_id');
          writes.push(JSON.parse(JSON.stringify(payload)));
          return { error: null };
        },
      };
    },
  };
  await vm.runInNewContext(`(async () => {${callback}})()`, {
    ...helpers,
    readerSupabase,
    readerCloudUser: { id: 'account' },
    progress: {},
    masterState: { appState: state([today], 1) },
    lastCloudProgressSnapshotRef: snapshot,
    setCloudReadingStatus: status => statuses.push(status),
  });
  return { writes, statuses, snapshot };
}

(async () => {
  const failedRead = await runWrite({ data: null, error: { message: 'Temporary read failure' } });
  assert.equal(failedRead.writes.length, 0, 'A failed cloud read must never overwrite cloud history');
  assert.equal(failedRead.snapshot.current, 'previous-snapshot', 'Failed reads must remain unsynchronized');
  assert.ok(failedRead.statuses.some(status => status.includes('读取失败')));

  const successfulRead = await runWrite({
    data: { vocab_master_progress: { appState: state([historical], 4), words: {} } },
    error: null,
  });
  assert.equal(successfulRead.writes.length, 1);
  const merged = successfulRead.writes[0].vocab_master_progress.appState.users.reader_account;
  assert.deepEqual(merged.studyEvents.map(item => item.id), ['historical', 'today'],
    'Successful sync must preserve cloud history and new local answers');
  assert.equal(merged.words[0].incorrectCount, 4, 'Successful sync must preserve accumulated cloud mistakes');
  assert.notEqual(successfulRead.snapshot.current, 'previous-snapshot');

  console.log('PASS: failed cloud reads never write; successful reads preserve historical and local answers');
})().catch(error => { console.error(error); process.exitCode = 1; });
