// Run with: node tests/test_reading_context_ui.cjs (static server on port 8766).
// All learning writes and cloud requests are intercepted; real records are untouched.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'outputs/reading-context');
fs.mkdirSync(output, { recursive: true });
const words = [{ id: 'reading:cat', section: '阅读生词本', source: 'reading',
  english_word: 'cat', chinese_meaning: '猫', learning_requirement: '见到英文，能选出中文意思',
  sourceContext: 'The CAT and cats sat near a caterpillar. <img src=x onerror=alert(1)>',
  sourceArticleTitle: 'The garden', exampleSentence: 'AI example must not replace original context.',
  pronunciation: '/kæt/', correctCount: 0, incorrectCount: 0 },
  { id: 'reading:dog', section: '阅读生词本', source: 'reading', english_word: 'dog',
    chinese_meaning: '狗', learning_requirement: '见到英文，能选出中文意思',
    exampleSentence: 'Another AI example.', correctCount: 0, incorrectCount: 0 }];
const state = { version: 1, currentUserId: 'context-test', users: { 'context-test': {
  id: 'context-test', name: 'Context test', words, selectedGrade: null,
  selectedSections: ['阅读生词本'], studyEvents: [] } } };
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/health', route => route.fulfill({ json: { ok: true } }));
    await page.route('**/api/vocab-data', route => route.fulfill({ json: route.request().method() === 'GET' ? state : { ok: true } }));
    await page.route('**/api/pronunciation?*', route => route.abort());
    await page.route('**/rest/v1/**', route => route.fulfill({ json: [] }));
    await page.route('**/auth/v1/**', route => route.fulfill({ status: 401, json: {} }));
    await page.route('https://api.dictionaryapi.dev/**', route => route.abort());
    await page.route('**/ket_vocab.json', route => route.fulfill({ json: { words: [] } }));
    await page.addInitScript(data => {
      Math.random = () => 0.5;
      localStorage.setItem('vocabmaster_app_data', JSON.stringify(data));
    }, state);
    await page.goto('http://127.0.0.1:8766/vocabulary_app.html', { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /闪卡复习 \(2 词\)/ }).waitFor({ timeout: 60000 });
    await page.getByRole('button', { name: /闪卡复习 \(2 词\)/ }).click();
    const block = page.locator('[data-reading-context]');
    const verifyOriginal = async () => {
      assert.equal(await block.count(), 1);
      assert.equal(await block.locator('mark').allTextContents().then(JSON.stringify), '["CAT","cats"]');
      assert((await block.innerText()).includes(words[0].sourceContext));
      assert.equal(await block.locator('img').count(), 0);
      assert(!(await page.locator('body').innerText()).includes('AI example must'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    };
    await verifyOriginal();
    await page.screenshot({ path: path.join(output, 'flashcard-front.png'), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: '显示词义和助记', exact: true }).click();
    await verifyOriginal();
    await page.screenshot({ path: path.join(output, 'flashcard-back.png'), fullPage: true, animations: 'disabled' });
    console.log('Flashcard original context, boundary highlighting, escaping, mobile layout: PASS');
    await page.getByRole('button', { name: '下一张 →', exact: true }).click();
    await block.getByText('这个词尚未保存收录时的原句。', { exact: true }).waitFor();
    assert(!(await page.locator('body').innerText()).includes('Another AI example.'));
    await page.getByRole('button', { name: '返回 Unit 选择', exact: true }).click();
    await page.getByRole('button', { name: /开始学习 \(2 词\)/ }).click();
    await block.waitFor();
    await verifyOriginal();
    assert.equal(await page.getByRole('heading', { name: 'cat', exact: true }).count(), 0);
    await page.getByText('请根据原句，选择高亮单词的中文含义', { exact: true }).waitFor();
    const beforeOptions = await page.evaluate(() => {
      const original = document.querySelector('[data-reading-context]');
      const choice = [...document.querySelectorAll('button')].find(button => button.textContent.trim() === '猫');
      return Boolean(original && choice && (original.compareDocumentPosition(choice) & Node.DOCUMENT_POSITION_FOLLOWING));
    });
    assert(beforeOptions, 'Collected sentence must appear above answer choices');
    await page.screenshot({ path: path.join(output, 'study-before-answer-mobile.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 1280, height: 1000 });
    await verifyOriginal();
    await page.screenshot({ path: path.join(output, 'study-before-answer-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 1000 });
    console.log('Original sentence replaces isolated word before answering, above choices on mobile and desktop: PASS');
    await page.getByRole('button', { name: /猫/ }).click();
    await block.waitFor();
    await verifyOriginal();
    await page.waitForTimeout(1600); // Beyond the old automatic advance delay.
    await verifyOriginal();
    await page.screenshot({ path: path.join(output, 'study-correct.png'), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: /下一个 \(Enter\)/ }).click();
    await block.getByText('这个词尚未保存收录时的原句。', { exact: true }).waitFor();
    assert(!(await block.innerText()).includes(words[0].sourceContext), 'Previous word context must not leak');
    await page.getByRole('button', { name: '不会 / 提示', exact: true }).click();
    await block.getByText('这个词尚未保存收录时的原句。', { exact: true }).waitFor();
    console.log('Missing context, correct answer retention, hint feedback: PASS');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
