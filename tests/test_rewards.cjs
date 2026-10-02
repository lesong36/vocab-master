const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const range = (start, end) => html.slice(html.indexOf(start), html.indexOf(end));
const api = vm.runInNewContext(
  range('const normalizeWordStats =', 'const MAX_STUDY_EVENTS =') +
  range('const MAX_STUDY_EVENTS =', 'const loadFromBrowser =') +
  '\n({ getAnswerReward, normalizeRewardLedger, mergeRewardLedgers, getRewardTotal, normalizeStudyEvents, migrateUserRecord, mergeCloudAppState, collapseToReaderAccount })',
  { STORAGE_VERSION: 1, READING_VOCAB_SECTION: '阅读生词本', isHiddenGrade: () => false, parseSectionMeta: section => ({ grade: section.slice(0, 2) }) },
);
const plain = value => JSON.parse(JSON.stringify(value));

let streak = 0;
let total = 0;
for (let index = 1; index <= 6; index++) {
  const reward = api.getAnswerReward(streak, true);
  assert.equal(reward.streak, index);
  assert.equal(reward.points, index % 3 === 0 ? 15 : 10);
  assert.equal(reward.kind, index % 3 === 0 ? 'streak' : 'correct');
  total += reward.points;
  streak = reward.streak;
}
assert.equal(total, 70);
assert.equal(api.getAnswerReward(6, false).streak, 0);
assert.equal(api.getAnswerReward(6, false).points, 0, 'Mistakes never deduct points');
assert.equal(api.getAnswerReward(0, true, true).points, 5);
assert.equal(api.getAnswerReward(2, true, true).streak, 0, 'Corrections cannot earn streak bonus');
assert.equal(api.getAnswerReward(2, true, true).bonus, 0);

assert.deepEqual(plain(api.normalizeRewardLedger({ good: 10, bonus: 15, retry: 5, zero: 0, negative: -1, nan: NaN, string: '10', huge: 16, fraction: 0.5 })), { good: 10, bonus: 15, retry: 5 });
for (const invalid of [null, undefined, [], 'invalid']) assert.equal(api.getRewardTotal(invalid), 0);
const a = { shared: 10, local: 5 };
const b = { shared: 10, remote: 15 };
const mergedLedger = api.mergeRewardLedgers(a, b);
assert.equal(api.getRewardTotal(mergedLedger), 30);
assert.deepEqual(plain(api.mergeRewardLedgers(a, b)), plain(api.mergeRewardLedgers(b, a)));
assert.deepEqual(plain(api.mergeRewardLedgers(mergedLedger, mergedLedger)), plain(mergedLedger));
assert.deepEqual(a, { shared: 10, local: 5 }, 'Merging must not mutate original ledgers');

const makeUser = (ledger, events = []) => ({ id: 'test', name: 'Test', words: [], selectedSections: [], studyEvents: events, rewardLedger: ledger, updatedAt: '2026-10-02T00:00:00Z' });
const makeState = user => ({ version: 1, currentUserId: user.id, users: { [user.id]: user } });
const oldEvents = [{ id: 'old', at: '2026-10-01T00:00:00Z', wordId: 'word', result: 'correct' }];
assert.equal(api.getRewardTotal(api.migrateUserRecord(makeUser(undefined, oldEvents)).rewardLedger), 0, 'Historical answers must not invent rewards');
for (const [remote, local] of [[a, b], [b, a]]) {
  const merged = api.mergeCloudAppState(makeState(makeUser(remote)), makeState(makeUser(local)));
  assert.equal(api.getRewardTotal(merged.users.test.rewardLedger), 30);
  assert.equal(api.getRewardTotal(api.mergeCloudAppState(merged, merged).users.test.rewardLedger), 30);
}
const manyEvents = Array.from({ length: 5001 }, (_, index) => ({ id: `event-${index}`, wordId: 'word', at: '2026-10-02T00:00:00Z', result: 'correct' }));
const migrated = api.migrateUserRecord(makeUser({ 'event-0': 10 }, manyEvents));
assert.equal(migrated.studyEvents.length, 5000);
assert.equal(api.getRewardTotal(migrated.rewardLedger), 10, 'Event retention cannot erase earned rewards');
const accounts = { version: 1, users: { one: { ...makeUser(a), id: 'one' }, two: { ...makeUser(b), id: 'two' } } };
assert.equal(api.getRewardTotal(api.collapseToReaderAccount(accounts, { id: 'reader' }).users.reader_reader.rewardLedger), 30);
console.log('PASS: streak milestones, corrections, no deductions, ledger validation, historical compatibility, repeat-safe cloud/account merge and event retention');
