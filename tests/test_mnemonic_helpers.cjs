const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const tipStart = html.indexOf('const buildCardStudyTip =');
const source = html.slice(tipStart, html.indexOf('\n    };', tipStart) + 7);
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

const letterSource = html.slice(html.indexOf('const getMnemonicLetterParts ='), html.indexOf('const MnemonicPicture ='));
const letterParts = vm.runInNewContext(letterSource + '\ngetMnemonicLetterParts');
for (const [word, focus, expected] of [['sorry', ['rr'], 'rr'], ['would', ['l'], 'l'], ['dessert', ['ss'], 'ss'], ['meatball', ['ea', 'e'], 'ea']]) {
  const parts = letterParts(word, focus);
  assert.equal(parts.map(part => part.text).join(''), word, 'Visual highlighting must preserve the full spelling');
  assert.equal(parts.filter(part => part.focus).map(part => part.text).join(''), expected);
}
assert.equal(letterParts('uncle', ['re']).filter(part => part.focus).length, 0, 'An absent cue must not invent letters');
assert.equal(letterParts('ice cream', ['ea']).map(part => part.text).join(''), 'ice cream', 'Phrase spacing must survive highlighting');
console.log('PASS: visual cues highlight double and silent letters without changing spelling or phrase spacing');

const availabilitySource = html.slice(html.indexOf('const hasMnemonicPicture ='), html.indexOf('const MnemonicPicture ='));
const availability = vm.runInNewContext(availabilitySource + '\n({ hasMnemonicPicture, hasMnemonicMorphology })');
assert.equal(availability.hasMnemonicPicture(null), false);
assert.equal(availability.hasMnemonicMorphology(null), false);
for (const grade of [3, 4, 5, 6]) {
  const cards = JSON.parse(fs.readFileSync(`mnemonics/grade${grade}.json`, 'utf8')).cards;
  for (const card of cards) {
    if (card.dimensions.morphology.kind === 'none') {
      assert.equal(availability.hasMnemonicMorphology(card), false, `${card.word}: no empty morphology entry`);
    }
    if (!card.dimensions.visual.diagram && !['in', 'on', 'under', 'behind', 'next to', 'sorry', 'would', 'dessert', 'meatball'].includes(card.word.toLowerCase())) {
      assert.equal(availability.hasMnemonicPicture(card), false, `${card.word}: emoji alone is not a visual cue`);
    }
  }
}
console.log('PASS: all textbook cards omit emoji-only pictures and empty morphology entries');

const matchingSource = html.slice(html.indexOf('const matchesSpelling ='), html.indexOf('const levenshtein ='));
const matchesSpelling = vm.runInNewContext(matchingSource + '\nmatchesSpelling');
assert.ok(matchesSpelling('hi', 'hi'));
assert.ok(matchesSpelling('an', 'an'));
assert.ok(!matchesSpelling('hi', 'hello'));
assert.ok(!matchesSpelling('an', 'a'));
assert.ok(matchesSpelling('lives', 'life (pl. lives)'));
assert.ok(matchesSpelling('take piano lessons', 'take ... lesson'));
assert.ok(!matchesSpelling('take away lessons', 'take away'));
assert.ok(!matchesSpelling('live', 'life (pl. lives)'));
assert.ok(!matchesSpelling('uze', 'use'));
console.log('PASS: alternatives are tested independently; plural annotations accept real forms; ordinary spelling errors remain incorrect');

const differenceSource = html.slice(html.indexOf('const levenshtein ='), html.indexOf('const getSpellingSimilarity ='));
const spellingDifferences = vm.runInNewContext(matchingSource + differenceSource + '\nspellingDifferences');
assert.ok(spellingDifferences('sory', 'sorry').join(' ').includes('漏写 r'));
assert.ok(spellingDifferences('woud', 'would').join(' ').includes('漏写 l'));
assert.ok(spellingDifferences('uze', 'use').join(' ').includes('z 改为 s'));
assert.ok(spellingDifferences('pleasee', 'please').join(' ').includes('多写 e'));
assert.equal(spellingDifferences('hi', 'hi').length, 0);
console.log('PASS: spelling feedback identifies missing, extra and replaced letters');

const maskStart = html.indexOf('const getMnemonicPracticeTarget =');
const maskSource = html.slice(maskStart, html.indexOf('const MnemonicSpellingGuide =', maskStart));
const mask = vm.runInNewContext(maskSource + '\nbuildMaskedSpelling');
assert.equal(mask('purple', ['ur', 'le']), 'p__p__');
assert.equal(mask('classroom', ['ss', 'oo']), 'cla__r__m');
assert.equal(mask('well-known', ['ll', 'k']), 'we__-_nown');
assert.equal(mask('take care of', ['e', 'f']), 'tak_ car_ o_');
assert.equal(mask('life (pl. lives)', ['f']), 'li_e');
assert.equal(mask('I', ['I']), '_');
assert.equal(mask('month', []), '_____');
for (const word of ['red', 'tea', 'banana', 'a', 'ice cream']) {
  assert.notEqual(mask(word, ['absent']), word, 'An invalid or absent focus cannot leak the complete answer');
}
console.log('PASS: target-specific gap prompts preserve spelling boundaries, hide focused letters and exclude plural annotations');

const chunkStart = html.indexOf('const getMnemonicChunkParts =');
const chunkSource = html.slice(chunkStart, html.indexOf('const getMnemonicPracticeTarget =', chunkStart));
const chunkParts = vm.runInNewContext(chunkSource + '\ngetMnemonicChunkParts', {getMnemonicLetterParts:letterParts});
const splitDouble = chunkParts(['rab', 'bit'], ['bb']);
assert.equal(splitDouble[0].filter(p=>p.focus).map(p=>p.text).join(''), 'b');
assert.equal(splitDouble[1].filter(p=>p.focus).map(p=>p.text).join(''), 'b');
assert.equal(mask('take ... lesson', ['e','ss']), 'tak_ a swimming l___on');
console.log('PASS: difficult letters remain highlighted across spelling chunk boundaries; template practice uses a concrete example');

const matchesMnemonic = vm.runInNewContext(matchingSource + '\nmatchesMnemonicSpelling');
const mnemonicDifferences = vm.runInNewContext(matchingSource + differenceSource + '\nmnemonicSpellingDifferences');
assert.ok(!matchesMnemonic('i','I'));
assert.ok(!matchesMnemonic('wednesday','Wednesday'));
assert.ok(matchesMnemonic('Wednesday','Wednesday'));
assert.ok(matchesMnemonic('lives','life (pl. lives)'));
assert.ok(mnemonicDifferences('i','I').join(' ').includes('i 改为 I（大写）'));
assert.ok(matchesSpelling('wednesday','Wednesday'), 'Formal answer matching stays unchanged');
console.log('PASS: spelling self-checks correct proper-name and I capitalization while formal matching stays unchanged');

assert.equal(mask('Water-Splashing Festival', ['-', ' ']), 'Water_Splashing_Festival');
assert.equal(mask('ice cream', [' ']), 'ice_cream');
console.log('PASS: phrase separator checkpoints mask only the targeted space and hyphen instead of blanking every letter');

const practiceTarget = vm.runInNewContext(maskSource + '\ngetMnemonicPracticeTarget');
const grade6Aliases = [
  ['save ... from', 'save people from', ['e', 'f'], 'sav_ p_opl_ _rom'],
  ['keep ... away', 'keep children away', ['ee', 'ay'], 'k__p children aw__'],
  ['VR (= Virtual Reality)', 'VR', ['R'], 'V_'],
  ['BeiDou Navigation Satellite System (abbr. BDS)', 'BeiDou Navigation Satellite System', ['ll'], 'BeiDou Navigation Sate__ite System'],
  ['WHO (World Health Organization)', 'WHO', ['O'], 'WH_'],
];
for (const [word, target, focus, expectedMask] of grade6Aliases) {
  assert.equal(practiceTarget(word), target, `${word}: use a spoken spelling target`);
  assert.equal(mask(word, focus), expectedMask, `${word}: gaps must hide target letters without copying annotations`);
  assert.ok(!/[()=]|\.\.\.|abbr\./.test(mask(word, focus)), `${word}: textbook metadata leaked into gap practice`);
  assert.ok(matchesMnemonic(target, practiceTarget(word)), `${word}: actual spoken form should pass the self-check`);
  assert.ok(!matchesMnemonic(word, practiceTarget(word)), `${word}: copied textbook notation should not pass`);
  assert.ok(!matchesMnemonic(target.slice(0, -1), practiceTarget(word)), `${word}: missing letters must fail`);
  assert.ok(mnemonicDifferences(target.slice(0, -1), practiceTarget(word)).length, `${word}: typo needs feedback`);
}
assert.equal(practiceTarget('take ... lesson'), 'take a swimming lesson');
assert.equal(mask('take ... lesson', ['e', 'ss']), 'tak_ a swimming l___on');
assert.ok(matchesMnemonic('take a swimming lesson', practiceTarget('take ... lesson')));
assert.ok(!matchesMnemonic('vr', practiceTarget('VR (= Virtual Reality)')), 'Initialism self-check retains uppercase');
console.log('PASS: grade 6 gap masks and self-checks use real phrases/initialisms with no copied textbook annotations; existing lesson template remains unchanged');

for (const [word, answers] of [
  ['save ... from', ['save people from', 'save children from danger']],
  ['keep ... away', ['keep children away', 'keep babies away from fire']],
  ['VR (= Virtual Reality)', ['VR', 'Virtual Reality']],
  ['BeiDou Navigation Satellite System (abbr. BDS)', ['BDS', 'BeiDou Navigation Satellite System']],
  ['WHO (World Health Organization)', ['WHO', 'World Health Organization']],
]) {
  for (const answer of answers) assert.ok(matchesSpelling(answer, word), `${word}: accept ${answer} as a formal answer`);
}
for (const [word, answer] of [['save ... from', 'save from'], ['keep ... away', 'keep away'], ['VR (= Virtual Reality)', 'V R'], ['WHO (World Health Organization)', 'WH'], ['BeiDou Navigation Satellite System (abbr. BDS)', 'BeiDou Navigation Satelite System']]) {
  assert.ok(!matchesSpelling(answer, word), `${word}: reject ${answer}`);
}
console.log('PASS: grade 6 formal answers accept real phrase objects and abbreviated/full names while rejecting missing objects and typos');

const pronunciationSource = html.slice(html.indexOf('const pronunciationKey ='), html.indexOf('const formatIPA ='));
const pronunciationKey = vm.runInNewContext(pronunciationSource + '\npronunciationKey');
assert.equal(pronunciationKey('who'), 'who');
assert.equal(pronunciationKey('WHO'), 'who (world health organization)');
assert.notEqual(pronunciationKey('WHO'), pronunciationKey('who'), 'WHO letter names must not reuse the pronoun IPA');
console.log('PASS: WHO initialism pronunciation stays distinct from the pronoun who');
