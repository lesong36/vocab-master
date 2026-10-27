const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const pack = JSON.parse(fs.readFileSync('collocations.json', 'utf8'));
const words = pack.words;
const recognition = html.slice(html.indexOf('    const parseSectionMeta ='), html.indexOf('    const normalizeMeaning ='));
const choices = html.slice(html.indexOf('    const buildRecognitionChoices ='), html.indexOf('    const sortGrades ='));
const examples = html.slice(html.indexOf('    const findLessonExamples ='), html.indexOf('    const highlightLessonWord ='));
const api = vm.runInNewContext('const MAX_LESSON_EXAMPLES = 3;\n' + recognition + choices + examples + '\n({isRecognitionWord, buildRecognitionChoices, findLessonExamples, matchesCollocationKind, displaySectionName})');
const oldWords = JSON.parse(fs.readFileSync('tests/fixtures/collocations-v1.json', 'utf8'));
for (const old of oldWords) {
  const current = words.find(word => word.id === old.id);
  assert.ok(current, `Keep the original ID and progress: ${old.english_word}`);
  assert.equal(current.section, old.section, 'Keep stored Unit selections and event section keys');
  assert.equal(current.english_word, old.english_word);
}
assert.equal(new Set(words.map(w => w.id)).size, words.length);
assert.equal(new Set(words.map(w => `${w.section}|${w.learning_kind}|${w.english_word.toLowerCase()}`)).size, words.length);
const normalize = text => text.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
const lessons = Object.fromEntries(fs.readFileSync('四上英语课文.md','utf8').split(/^# U/m).slice(1).map(part => [Number(part.match(/^\d+/)[0]),normalize(part)]));
const reference = normalize(fs.readFileSync('tests/fixtures/unit3-reference.txt','utf8'));
for (const word of words) {
  const unit = Number(word.section.match(/Unit (\d+)/)[1]);
  assert.ok(['phrase','sentence'].includes(word.learning_kind));
  assert.ok(['textbook','reference'].includes(word.provenance));
  assert.ok(word.exampleTranslation && word.lesson, `Translated, sourced example: ${word.english_word}`);
  const source = word.provenance === 'reference' ? reference : lessons[unit];
  assert.ok(source.includes(normalize(word.exampleSentence)), `Untraceable quotation: U${unit} ${word.exampleSentence}`);
  if (word.provenance === 'reference') assert.equal(unit,3);
  if (word.response) assert.ok(source.includes(normalize(word.response)), `Untraceable response: ${word.response}`);
  if (word.learning_kind === 'sentence') {
    assert.ok(word.pattern, `Missing sentence structure: ${word.english_word}`);
    assert.ok(!word.english_word.includes('...'), 'Read a real example rather than placeholder dots');
  }
  assert.ok(api.isRecognitionWord({...word, learning_requirement: ''}), 'Source alone must prevent a spelling question');
  const options = api.buildRecognitionChoices(word, []);
  assert.equal(options.length, 4);
  assert.equal(new Set(options.map(o=>o.text)).size, 4);
  assert.equal(new Set(options.map(o=>o.key)).size, 4);
  assert.equal(options.filter(o=>o.isCorrect).length, 1);
  assert.equal(options.find(o=>o.isCorrect).text, word.chinese_meaning);
  const example=api.findLessonExamples(word, [])[0];
  assert.equal(example.en, word.exampleSentence, 'Authored examples work without fetched lesson data and with inflected phrases');
  assert.equal(example.zh,word.exampleTranslation);
  assert.equal(api.findLessonExamples(word, [], 0).length, 0);
  assert.equal(api.matchesCollocationKind(word,'all'),true);
  assert.equal(api.matchesCollocationKind(word,word.learning_kind),true);
  assert.equal(api.matchesCollocationKind(word,word.learning_kind==='phrase'?'sentence':'phrase'),false);
}
for (const unit of [1,2,3,5,6,7]) {
  const group = words.filter(w=>w.section===`四上固定搭配Unit ${unit}`);
  assert.ok(group.filter(w=>w.learning_kind==='phrase').length>=15,`U${unit} needs broad phrase coverage`);
  assert.ok(group.filter(w=>w.learning_kind==='sentence').length>=8,`U${unit} needs key sentence coverage`);
  const doc=fs.readFileSync(`unit-${unit}-固定搭配.md`,'utf8');
  for (const word of group) assert.ok(doc.includes(word.english_word),`Missing from reviewable source document: ${word.english_word}`);
}
const required = ['get a ping-pong bat','fix it','ask for help','go home','borrow...from...','share...with...','throw...into...','open the door','get off','stand in line','listen to others','sweep the floor','get some water','clean the blackboard','tidy up','close the window','pass me the water','stop cleaning','in the garden','come in','in the library','a nice person','in a polite way'];
const u3=words.filter(w=>w.section==='四上固定搭配Unit 3'&&w.learning_kind==='phrase');
for (const en of required) assert.ok(u3.some(w=>normalize(w.english_word)===normalize(en)),`Unit 3 reference phrase missing: ${en}`);
assert.equal(u3.find(w=>w.english_word==='in the garden').chinese_meaning.includes('花园'),true,'Correct the reference document garden translation');
assert.equal(api.buildRecognitionChoices({...words[0],recognition_choices:[]},[]).length,0,'No random fallback for a malformed pack');
assert.equal(api.isRecognitionWord({learning_requirement:'能理解并会用'}),false,'Ordinary spelling words retain their behavior');
assert.equal(api.matchesCollocationKind({source:'reading'},'sentence'),true,'Content filter must not hide other vocab sources');
assert.equal(api.displaySectionName('四上固定搭配Unit 3'),'四上固定搭配与重点句式Unit 3');
console.log(`PASS: ${words.length} sourced phrase/sentence entries; all 23 reference phrases; original 31 IDs; fixed choices; translated examples; type filters; no spelling`);
