// Known content failures: a valid schema must not hide a wrong learning cue.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const cards = [3, 4, 5].flatMap(grade => JSON.parse(fs.readFileSync(`mnemonics/grade${grade}.json`)).cards);
const card = (word, grade) => cards.find(c => c.word === word && c.section.startsWith(grade));
const html = fs.readFileSync('vocabulary_app.html', 'utf8');
const availability = vm.runInNewContext(html.slice(html.indexOf('const hasMnemonicPicture ='), html.indexOf('const MnemonicPicture =')) + '\n({hasMnemonicPicture,hasMnemonicMorphology,hasMnemonicSemantic})');
assert.ok(card('hard', '四').hint.includes('困难'));
assert.ok(!card('hard', '四').hint.includes('硬糖'));
assert.ok(card('free', '五').dimensions.visual.diagram.panels[0].symbols.join('').includes('¥0'));
assert.ok(!card('free', '五').dimensions.visual.caption.includes('空闲'));
assert.ok(card('old', '三').dimensions.visual.caption.includes('年龄'));
assert.equal(availability.hasMnemonicPicture(card('chicken', '三')), false, 'Chicken meat must not be taught by a chicken-versus-egg diagram');
assert.equal(availability.hasMnemonicPicture(card('drink', '三')), false, 'Drinking action must not be labelled as a noun image');
for (const word of ['pick','soil','begin','come out']) assert.equal(availability.hasMnemonicPicture(card(word, '五')), false, `${word}: generic plant stages do not locate the actual target`);
for (const [word, grade] of [['ruler','三'],['calligraphy','五'],['astronaut','五'],['yesterday','五']]) assert.equal(availability.hasMnemonicMorphology(card(word, grade)), false, `${word}: no unfamiliar historical component dependency`);
assert.ok(!card('poster','五').hint.includes('post（张贴）+er'));
assert.ok(!card('without','四').hint.includes('伞拿出去'));
for (const word of ['feel','call','door','rabbit','need','letter','between']) assert.ok(!/想成|e 形|t 形|皱眉|圆钉/.test(card(word,'四').hint), `${word}: remove forced object-letter associations`);
assert.equal(availability.hasMnemonicSemantic(card('blue','三')), false, 'No redundant colour-category tab');
for (const word of ['free','afraid','comfortable','popular','writer','ceremony']) {
  const question=card(word,'五').dimensions.context.question;
  assert.ok(/英文/.test(question), `${word}: ask for the target word`);
  assert.ok(!/怎样说一句话|还是|能不能|是否/.test(question), `${word}: no metaknowledge or unrestricted sentence question`);
}
const promptStart = html.indexOf('const buildHintPrompt =');
const prompt = vm.runInNewContext(html.slice(promptStart, html.indexOf('const fetchAIHintFromServer',promptStart)) + '\nbuildHintPrompt')({english_word:'remember',chinese_meaning:'记住'});
assert.ok(prompt.includes('不适用就省略'));
assert.ok(prompt.includes('不把任意两件物品强配双字母'));
assert.ok(!prompt.includes('约350字'));
const batchStart=html.indexOf('const buildPhonicsBatchPrompt =');
// The complete function ends before the next top-level declaration, not at
// semicolons inside the template's input lines.
const batchSource=html.slice(batchStart,html.indexOf('\n\n',batchStart));
const batch=vm.runInNewContext(batchSource+'\nbuildPhonicsBatchPrompt')([{id:'1',english_word:'remember',chinese_meaning:'记住'}]);
assert.ok(batch.includes('最多两个具体字母难点'));
assert.ok(batch.includes('不能只输出'));
console.log('PASS: wrong lesson senses, forced analogies, unfamiliar roots, generic diagrams, ambiguous retrieval and generation prompts');
