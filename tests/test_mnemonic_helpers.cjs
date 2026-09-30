const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const source = html.slice(html.indexOf('const buildCardStudyTip ='), html.indexOf('const levenshtein ='));
const buildCardStudyTip = vm.runInNewContext(source + '\nbuildCardStudyTip', {
  getWordPos: () => 'v', POS_LABEL_ZH: {},
  SPECIAL_STUDY_TIPS: { remember: 're-(再) + member → 再想起来；反义 forget' },
});
const reviewed = { hint: 'remember 的中间 mem 两端各有 m；首 e 轻读，第二 e 重读。' };
assert.equal(buildCardStudyTip({ english_word: 'remember', chinese_meaning: '记住', pos: 'v.' }, reviewed), reviewed.hint);
const unreviewed = buildCardStudyTip({ english_word: 'uncle', chinese_meaning: '叔叔', pos: 'n.' });
assert.ok(!unreviewed.includes('前缀 un-'), 'Do not invent a negative prefix for uncle');
assert.ok(unreviewed.includes('尚无专属线索'), 'Fallback must identify the missing dedicated cue');
console.log('PASS: reviewed flashcard/print hints take priority; unknown words get no fabricated morphology');

const matchingSource = html.slice(html.indexOf('const matchesSpelling ='), html.indexOf('const levenshtein ='));
const matchesSpelling = vm.runInNewContext(matchingSource + '\nmatchesSpelling');
assert.ok(matchesSpelling('hi', 'hello/hi'));
assert.ok(matchesSpelling('an', 'a/an'));
assert.ok(matchesSpelling('lives', 'life (pl. lives)'));
assert.ok(matchesSpelling('take piano lessons', 'take ... lesson'));
assert.ok(!matchesSpelling('take away lessons', 'take away'));
assert.ok(!matchesSpelling('live', 'life (pl. lives)'));
assert.ok(!matchesSpelling('uze', 'use'));
console.log('PASS: grouped textbook forms accept real words; ordinary spelling errors remain incorrect');

const differenceSource = html.slice(html.indexOf('const levenshtein ='), html.indexOf('const getSpellingSimilarity ='));
const spellingDifferences = vm.runInNewContext(matchingSource + differenceSource + '\nspellingDifferences');
assert.ok(spellingDifferences('sory', 'sorry').join(' ').includes('漏写 r'));
assert.ok(spellingDifferences('woud', 'would').join(' ').includes('漏写 l'));
assert.ok(spellingDifferences('uze', 'use').join(' ').includes('z 改为 s'));
assert.ok(spellingDifferences('pleasee', 'please').join(' ').includes('多写 e'));
assert.equal(spellingDifferences('hi', 'hello/hi').length, 0);
console.log('PASS: spelling feedback identifies missing, extra and replaced letters');
