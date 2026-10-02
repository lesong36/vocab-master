const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const range = (start, end) => html.slice(html.indexOf(start), html.indexOf(end));
const api = vm.runInNewContext(
  range('const HIDDEN_GRADES =', 'const LESSON_TEXT_FILES =') +
  range('const parseSectionMeta =', 'const isRecognitionWord =') +
  range('const normalizeWordStats =', 'const loadFromBrowser =') +
  '\n({ migrateUserRecord, mergeCloudAppState, collapseToReaderAccount })',
  { STORAGE_VERSION: 1, READING_VOCAB_SECTION: '阅读生词本' },
);
const plain = value => JSON.parse(JSON.stringify(value));
const older = {
  id: 'old', name: 'Old', updatedAt: '2026-10-01T00:00:00Z',
  selectedGrade: '四上', selectedSections: ['四上Unit 1', 'KET', '音乐'],
  words: [{ id: 'school', section: '四上Unit 1', correctCount: 3 }],
};
const latest = {
  id: 'latest', name: 'Latest', updatedAt: '2026-10-02T00:00:00Z',
  selectedGrade: '三上', selectedSections: [],
  words: [{ id: 'ket', section: 'KET', correctCount: 4 }],
};
assert.deepEqual(plain(api.migrateUserRecord(older).selectedSections), ['四上Unit 1']);
for (const records of [[older, latest], [latest, older]]) {
  for (const selectedSections of [[], ['三上Unit 2']]) {
    const users = Object.fromEntries(records.map(user => [user.id,
      user.id === latest.id ? { ...user, selectedSections } : user]));
    const collapsed = api.collapseToReaderAccount({ version: 1, users }, { id: 'reader' });
    const user = collapsed.users.reader_reader;
    assert.deepEqual(plain(user.selectedSections), selectedSections,
      'Historical selections must not override the latest selection, including empty');
    assert.equal(user.selectedGrade, '三上');
    assert.equal(user.words.length, 2, 'Word progress must still merge');
    assert.equal(user.words.find(word => word.id === 'school').correctCount, 3);
    assert.deepEqual(plain(api.collapseToReaderAccount(collapsed, { id: 'reader' })
      .users.reader_reader.selectedSections), selectedSections);
  }
}
const state = user => ({ version: 1, users: { same: { ...user, id: 'same', name: 'Same' } } });
for (const pair of [[older, latest], [latest, older]]) {
  assert.deepEqual(plain(api.mergeCloudAppState(...pair.map(state)).users.same.selectedSections), [],
    'Cloud merge must preserve the newest cancellation');
}
const history = {
  ...latest,
  words: [{ id: 'school', section: '四上Unit 1', correctCount: 5, incorrectCount: 2 }],
  studyEvents: [{ id: 'historical-answer', wordId: 'school', section: '四上Unit 1',
    at: '2026-09-01T00:00:00Z', result: 'incorrect' }],
};
const staleCloud = { ...older, words: [], studyEvents: [] };
const preserved = api.mergeCloudAppState(state(staleCloud), state(history)).users.same;
assert.equal(preserved.words[0].incorrectCount, 2);
assert.equal(preserved.studyEvents[0].id, 'historical-answer');
assert.ok(!html.includes('forceCloudReadRef'),
  'Manual synchronization must not bypass merging and discard local history');
console.log('PASS: hidden grades excluded, latest selections and cancellations retained, progress preserved, repeat-safe account/cloud merge');
