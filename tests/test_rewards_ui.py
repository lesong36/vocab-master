"""Reward browser checks on a static server; isolated profiles, no real records."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = ROOT / 'outputs/rewards'
PREVIEWS.mkdir(parents=True, exist_ok=True)
TERMS = [('use', '使用'), ('sorry', '抱歉的；难过的'), ('take', '拿走'), ('help', '帮助'), ('please', '请'), ('thank', '感谢')]

MOCK_AUDIO = """
window.rewardNotes = []; window.rewardResumes = 0;
window.AudioContext = class {
  constructor() { this.state = 'suspended'; this.currentTime = 0; this.destination = {}; }
  resume() { window.rewardResumes++; this.state = 'running'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
  createOscillator() { return { frequency: { setValueAtTime: value => window.rewardNotes.push(value) }, connect() {}, disconnect() {}, start() {}, stop() {} }; }
  createGain() { return { gain: { setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, disconnect() {} }; }
};
"""


def setup(page, recognition=False, audio='mock'):
    requirement = '见到英文，能选出中文意思' if recognition else '能理解并会用'
    words = [{'id': str(201 + i), 'section': '四上Unit 3', 'english_word': en, 'chinese_meaning': zh, 'learning_requirement': requirement, 'pos': 'v.'} for i, (en, zh) in enumerate(TERMS)]
    state = {'version': 1, 'currentUserId': 'reward-test', 'users': {'reward-test': {'id': 'reward-test', 'name': 'Isolated Reward Test', 'words': words, 'selectedGrade': '四上', 'selectedSections': ['四上Unit 3'], 'studyEvents': []}}}
    source = 'id,section,english_word,chinese_meaning,learning_requirement,pos\n' + '\n'.join(f'{w["id"]},{w["section"]},{w["english_word"]},{w["chinese_meaning"]},{requirement},v.' for w in words)
    page.route('**/api/**', lambda route: route.fulfill(status=404))
    page.route('**/%E8%AF%8D%E5%BA%93.md', lambda route: route.fulfill(body=source))
    page.route('**/ket_vocab.json', lambda route: route.fulfill(json={'words': []}))
    # Give each test card an example so auto-advance cannot race assertions.
    page.route('**/*%E8%AF%BE%E6%96%87*.md', lambda route: route.fulfill(body='# U3\n## L1 Test\n' + '\n'.join(f'I {en} today.\n练习例句。' for en, _ in TERMS)))
    page.route('https://api.dictionaryapi.dev/**', lambda route: route.abort())
    page.add_init_script("Math.random = () => 0.5; if (!localStorage.getItem('vocabmaster_app_data')) localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")
    if audio == 'mock':
        page.add_init_script(MOCK_AUDIO)
    elif audio == 'missing':
        page.add_init_script('window.AudioContext = undefined; window.webkitAudioContext = undefined;')
    elif audio == 'rejected':
        page.add_init_script("window.AudioContext = class { constructor() {this.state = 'suspended';} resume() {return Promise.reject(new Error('Audio blocked'));} close() {return Promise.resolve();} };")


def saved(page):
    return page.evaluate("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['reward-test']")


def answer(page, text):
    box = page.get_by_placeholder('请输入英文拼写...')
    box.fill(text)
    box.press('Enter')


def next_card(page):
    page.get_by_role('button', name='下一个 (Enter)', exact=True).click()


def start(page):
    page.goto('http://127.0.0.1:8766/vocabulary_app.html', wait_until='networkidle')
    page.get_by_role('button', name='开始学习 (6 词)', exact=True).click()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1000, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    setup(page)
    start(page)
    for index, (en, _) in enumerate(TERMS[:3]):
        answer(page, en)
        expect(page.get_by_test_id('reward-total')).to_have_text(str([10, 20, 35][index]))
        expect(page.get_by_test_id('reward-streak')).to_have_text(str(index + 1))
        if index < 2:
            next_card(page)
    expect(page.get_by_role('status')).to_contain_text('连续答对 3 题')
    assert page.evaluate('rewardNotes.length') == 8, 'Correct uses two tones; streak uses four'
    assert page.evaluate('rewardResumes') == 1, 'Suspended audio must resume on interaction'
    page.screenshot(path=str(PREVIEWS / 'streak-desktop.png'), animations='disabled')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(PREVIEWS / 'streak-mobile.png'), animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Reward panel overflows mobile'
    # Submit twice before React renders again: neither event nor points can double.
    count = len(saved(page)['studyEvents'])
    page.locator('form').first.evaluate("form => {form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true})); form.dispatchEvent(new Event('submit', {bubbles:true,cancelable:true}));}")
    assert len(saved(page)['studyEvents']) == count
    next_card(page)
    answer(page, 'wrong')
    expect(page.get_by_test_id('reward-total')).to_have_text('35')
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    expect(page.get_by_role('status')).to_contain_text('积分不会减少')
    assert page.evaluate('rewardNotes.slice(-2)') == [392, 440]
    count = len(saved(page)['studyEvents'])
    answer(page, 'still wrong')
    assert len(saved(page)['studyEvents']) == count, 'Repeated errors cannot add mistake records'
    answer(page, 'help')
    expect(page.get_by_test_id('reward-total')).to_have_text('40')
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    expect(page.get_by_role('status')).to_contain_text('坚持尝试也值得奖励')
    page.get_by_role('button', name='鼓励音效', exact=True).click()
    expect(page.get_by_role('button', name='鼓励音效')).to_have_attribute('aria-pressed', 'false')
    note_count = page.evaluate('rewardNotes.length')
    next_card(page)
    answer(page, 'please')
    expect(page.get_by_test_id('reward-total')).to_have_text('50')
    assert page.evaluate('rewardNotes.length') == note_count, 'Muted encouragement still played'
    next_card(page)
    page.get_by_role('button', name='不会 / 提示', exact=True).click()
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    expect(page.get_by_test_id('reward-total')).to_have_text('50')
    next_card(page)
    expect(page.get_by_role('heading', name='学习完成！')).to_be_visible()
    expect(page.get_by_test_id('reward-session')).to_have_text('+50')
    expect(page.get_by_text('本次最高连续答对 3 题。', exact=False)).to_be_visible()
    page.screenshot(path=str(PREVIEWS / 'summary-mobile.png'), animations='disabled')
    page.reload(wait_until='networkidle')
    expect(page.get_by_test_id('reward-total')).to_have_text('50')
    expect(page.get_by_role('button', name='鼓励音效')).to_have_attribute('aria-pressed', 'false')
    assert sum(saved(page)['rewardLedger'].values()) == 50
    page.get_by_role('button', name='开始学习 (6 词)', exact=True).click()
    expect(page.get_by_test_id('reward-session')).to_have_text('+0')
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    answer(page, 'use')
    expect(page.get_by_test_id('reward-total')).to_have_text('60')
    next_card(page)
    page.get_by_role('button', name='点击查看课本单词助记', exact=True).click()
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    next_card(page)  # Skip an unanswered word, then answer the next.
    answer(page, 'take')
    expect(page.get_by_test_id('reward-streak')).to_have_text('1')
    assert not errors, errors
    context.close()

    context = browser.new_context()
    page = context.new_page()
    setup(page, recognition=True)
    start(page)
    page.get_by_role('button', name='使用', exact=True).click()
    expect(page.get_by_test_id('reward-total')).to_have_text('10')
    next_card(page)
    # A wrong recognition choice locks this card and never grants points.
    page.get_by_role('button', name='使用', exact=True).click()
    expect(page.get_by_test_id('reward-total')).to_have_text('10')
    expect(page.get_by_test_id('reward-streak')).to_have_text('0')
    assert len(saved(page)['studyEvents']) == 2
    context.close()

    for audio in ['missing', 'rejected', 'native']:
        context = browser.new_context()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        setup(page, audio=audio)
        start(page)
        answer(page, 'use')
        expect(page.get_by_test_id('reward-total')).to_have_text('10')
        assert not errors, (audio, errors)
        context.close()
    browser.close()
    print('PASS: correct/streak/retry/hint/skip rewards, duplicate guards, tone profiles, mute/reload, summary, recognition, mobile and unavailable/rejected/native audio')
