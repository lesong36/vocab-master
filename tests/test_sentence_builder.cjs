const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('vocabulary_app.html','utf8');
const source = html.slice(html.indexOf('    const sentenceTokens ='),html.indexOf('    const SentenceBuilder ='));
const api = vm.runInNewContext(source+'\n({sentenceTokens, sentenceOrderMatches, moveSentenceToken, shuffleSentenceTokens})');
const sentences = JSON.parse(fs.readFileSync('collocations.json','utf8')).words.filter(w=>w.learning_kind==='sentence');
assert.equal(sentences.length,71);
for (const word of sentences) {
  const tokens=api.sentenceTokens(word.english_word);
  const ids=tokens.map(t=>t.id);
  assert.equal(tokens.map(t=>t.text).join(' '),word.english_word.trim());
  assert.equal(new Set(ids).size,tokens.length);
  assert.ok(api.sentenceOrderMatches(tokens,ids));
  assert.ok(!api.sentenceOrderMatches(tokens,ids.slice(1)));
  const shuffled=api.shuffleSentenceTokens(tokens);
  assert.equal(shuffled.length,tokens.length);
  assert.equal(new Set(shuffled.map(t=>t.id)).size,tokens.length);
  assert.ok(!api.sentenceOrderMatches(tokens,shuffled.map(t=>t.id)), 'Do not give an already assembled answer');
}
const repeated=api.sentenceTokens('I know I can.');
assert.ok(!api.sentenceOrderMatches(repeated,['0','1','0','3']), 'Each physical chip may only be used once');
assert.ok(api.sentenceOrderMatches(repeated,['2','1','0','3']), 'Identical words are interchangeable even when their IDs differ');
assert.equal(JSON.stringify(api.moveSentenceToken(['0','1','2'],'2','0')),JSON.stringify(['2','0','1']));
assert.equal(JSON.stringify(api.moveSentenceToken(['0','1','2'],'0','')),JSON.stringify(['1','2','0']));
assert.equal(JSON.stringify(api.moveSentenceToken(['0','1','2'],'1','1')),JSON.stringify(['0','1','2']));
assert.equal(JSON.stringify(api.moveSentenceToken(['0'],'1','0')),JSON.stringify(['1','0']));
console.log('PASS: all 71 sentence token sets, contractions/punctuation, repeated words, shuffling and insertion/reordering');
