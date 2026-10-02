const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const range = (start, end) => html.slice(html.indexOf(start), html.indexOf(end));
const api = vm.runInNewContext(
  range('const normalizeWordStats =', 'const MAX_STUDY_EVENTS =') +
  range('const splitAlternativeWords =', 'const migrateUserRecord =') +
  range('const mergeCloudWord =', '// 阅读器账号是唯一的学习身份。') +
  range('const mergeWordStats =', 'function App()') +
  '\n({ splitAlternativeWords, parseData, mergeWordStats, pronunciationKey, formatIPA, mergeCloudAppState })',
  {
    STORAGE_VERSION: 1,
    isValidAppData: data => Boolean(data?.users),
    mergeStudyEvents: (remote, local) => [...(remote || []), ...(local || [])],
    migrateUserRecord: user => ({ ...user, words: api.splitAlternativeWords(user.words) }),
  },
);
const oldWords = [
  { id: '279', section: '三上Unit 1', english_word: 'hello/hi', chinese_meaning: '你好', correctCount: 7, incorrectCount: 2, flashcardKnown: true, pronunciation: '/old/', phonicsMnemonic: 'hello and hi' },
  { id: '343', section: '三上Unit 3', english_word: 'a/an', chinese_meaning: '一个', correctCount: 3 },
  { id: '603', section: '五上Unit 2', english_word: 'life (pl. lives)', chinese_meaning: '生活；生命' },
  { id: '600', section: '五上Unit 2', english_word: 'living room', chinese_meaning: '客厅' },
];
const result = api.splitAlternativeWords(oldWords);
assert.deepEqual(Array.from(result, word => word.english_word), ['hello', 'hi', 'a', 'an', 'life (pl. lives)', 'living room']);
assert.equal(result[0].id, '279');
assert.equal(result[0].correctCount, 7);
assert.equal(result[0].incorrectCount, 2);
assert.equal(result[0].flashcardKnown, true);
assert.equal(result[0].pronunciation, undefined, 'Combined pronunciation must not leak to individual words');
assert.equal(result[1].id, '279:hi');
assert.equal(result[1].correctCount, 0);
assert.equal(result[1].incorrectCount, 0);
assert.equal(result[1].flashcardKnown, undefined, 'New word cannot inherit mastery');
assert.equal(result[3].id, '343:an');
assert.equal(JSON.stringify(api.splitAlternativeWords(result)), JSON.stringify(result), 'Migration must be idempotent');
assert.equal(oldWords[0].english_word, 'hello/hi', 'Source records must not be mutated');

const practicedHi = { ...result[1], correctCount: 9, incorrectCount: 1, flashcardKnown: true };
const mixed = api.splitAlternativeWords([...oldWords, practicedHi]);
assert.equal(mixed.filter(word => word.id === '279:hi').length, 1);
assert.equal(mixed.find(word => word.id === '279:hi').correctCount, 9);

const imported = api.parseData('id,section,english_word,chinese_meaning,learning_requirement,pos\n279,三上Unit 1,hello/hi,你好,能理解并会用,int.\n343,三上Unit 3,a/an,一个,能理解并会用,det.');
assert.equal(imported.length, 4);
const merged = api.mergeWordStats(imported, [...oldWords, practicedHi]);
assert.equal(merged.find(word => word.id === '279').correctCount, 7);
assert.equal(merged.find(word => word.id === '279').flashcardKnown, true);
assert.equal(merged.find(word => word.id === '279:hi').correctCount, 9);
assert.equal(merged.find(word => word.id === '279:hi').flashcardKnown, true);
assert.equal(merged.find(word => word.id === '343:an').correctCount, 0);

const cloudState = (words, savedAt) => ({
  version: 1, currentUserId: 'test', savedAt,
  users: { test: { id: 'test', name: 'Test', words, updatedAt: savedAt, studyEvents: [] } },
});
const remote = cloudState(oldWords, '2026-10-01T00:00:00.000Z');
const local = cloudState([...result.filter(word => word.id !== '279:hi'), practicedHi], '2026-10-02T00:00:00.000Z');
for (const [left, right] of [[remote, local], [local, remote]]) {
  const cloudMerged = api.mergeCloudAppState(left, right).users.test.words;
  const hello = cloudMerged.find(word => word.id === '279');
  assert.equal(hello.english_word, 'hello');
  assert.equal(hello.pronunciation, undefined, 'Legacy cloud combined pronunciation must stay removed');
  assert.equal(hello.phonicsMnemonic, undefined, 'Legacy cloud combined mnemonic must stay removed');
  assert.equal(hello.correctCount, 7);
  assert.equal(cloudMerged.find(word => word.id === '279:hi').correctCount, 9);
  assert.equal(cloudMerged.filter(word => word.id === '279:hi').length, 1);
}
assert.equal(remote.users.test.words[0].english_word, 'hello/hi', 'Cloud merge must not mutate source state');
assert.equal(api.formatIPA('[juːz]'), '/juːz/');
assert.equal(api.formatIPA('/juːz/'), '/juːz/');
assert.equal(api.formatIPA(''), '');
assert.equal(api.pronunciationKey('life (pl. lives)'), 'life');
console.log('PASS: independent alternatives, repeat-safe migration/import/cloud merge, preserved progress, phrases/plural annotations and IPA formatting');
