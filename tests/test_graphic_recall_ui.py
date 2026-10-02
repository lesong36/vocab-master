"""Check new diagrams in real study/recall views and actual print cards."""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mnemonics'
section = '三下Unit 3'
word = {'id': '57', 'section': section, 'english_word': 'leaves',
        'chinese_meaning': '叶子（复数）', 'learning_requirement': '能理解并会用', 'pos': 'n.',
        'correctCount': 0, 'incorrectCount': 0, 'consecutiveCorrect': 0, 'mistakeCleared': False}
state = {'version': 1, 'currentUserId': 'graphic-recall-test', 'users': {
    'graphic-recall-test': {'id': 'graphic-recall-test', 'name': 'Isolated graphic recall test',
                          'words': [word], 'selectedGrade': '三下', 'selectedSections': [],
                          'studyEvents': [], 'createdAt': '2026-10-02T00:00:00.000Z',
                          'updatedAt': '2026-10-02T00:00:00.000Z'}}}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1040, 'height': 1100})
    page.route('**/api/health', lambda route: route.fulfill(json={'ok': True}))
    page.route('**/api/vocab-data', lambda route: route.fulfill(json=state if route.request.method == 'GET' else {'ok': True}))
    page.add_init_script("localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")
    errors, writes = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: writes.append(request.post_data)
            if request.method == 'POST' and request.url.endswith('/api/vocab-data') else None)
    page.goto('http://127.0.0.1:8766/vocabulary_app.html', wait_until='networkidle')
    page.get_by_role('button', name=re.compile(r'^Unit 3\b')).click(timeout=30000)
    start = page.get_by_role('button', name=re.compile(r'^开始学习 \('))
    start.wait_for(timeout=30000)
    count = int(re.search(r'\((\d+) 词\)', start.inner_text()).group(1))
    start.click()
    for _ in range(count):
        cue_button = page.get_by_role('button', name='点击查看课本单词助记')
        if not cue_button.count():
            page.screenshot(path=str(OUTPUT / 'expanded-recall-test-state.png'), full_page=True)
            raise AssertionError(page.locator('body').inner_text()[:2200])
        cue_button.click()
        page.get_by_text('课本词库', exact=True).wait_for()
        if page.locator('[data-graphic-kind="change"]').get_by_text('leaves', exact=True).count():
            break
        page.get_by_role('button', name='下一个 (Enter)', exact=True).click()
    else:
        raise AssertionError('leaves not reached')
    assert page.locator('[data-graphic-kind="change"] mark').all_text_contents() == ['f', 'ves']
    # Study navigation schedules a 400 ms save; its status badge only appears
    # on the selection screen. Let that pending save finish before isolating recall.
    page.wait_for_timeout(700)
    before = len(writes)
    page.get_by_role('button', name='收起线索，试着回忆', exact=True).click()
    recall = page.get_by_role('region', name='助记回忆练习')
    assert not page.locator('[data-graphic-kind]').count()
    assert not page.locator('figure').count()
    assert not recall.get_by_text('leaves', exact=True).count()
    page.wait_for_timeout(700)
    assert len(writes) == before, 'Self-check wrote learning progress'
    page.get_by_role('button', name='返回助记线索', exact=True).click()
    page.get_by_role('button', name=re.compile(r'^练本单元拼写')).click()
    unit = page.get_by_role('region', name='单元拼写练习')
    for _ in range(count):
        if unit.locator('[data-graphic-kind="change"]').get_by_text('leaves', exact=True).count():
            break
        unit.get_by_role('button', name='下一词', exact=True).click()
    else:
        raise AssertionError('Unit leaves not reached')
    unit.get_by_role('button', name='收起线索，写完整单词', exact=True).click()
    assert not unit.locator('figure').count()
    assert not unit.locator('mark').count()
    assert not unit.get_by_text('leaves', exact=True).count()
    unit.screenshot(path=str(OUTPUT / 'expanded-graphic-recall-hidden.png'))
    unit.get_by_role('button', name='返回单词学习', exact=True).click()
    page.get_by_role('button', name='返回 Unit 选择', exact=True).click()
    page.get_by_role('button', name=re.compile(r'^打印卡片 \(')).click()
    page.set_viewport_size({'width': 794, 'height': 1123})
    page.emulate_media(media='print')
    assert page.locator('.print-card').count() == count
    overflow = page.locator('.print-card').evaluate_all("cards => cards.filter(card => card.getBoundingClientRect().height > 1050).map(card => ({word:card.querySelector('span.text-3xl').textContent,height:card.getBoundingClientRect().height}))")
    winter = page.locator('.print-card').filter(has=page.locator('span.text-3xl').filter(has_text=re.compile(r'^winter$')))
    winter.screenshot(path=str(OUTPUT / 'expanded-winter-print-card.png'))
    assert not overflow, overflow
    page.pdf(path=str(OUTPUT / 'expanded-unit-print.pdf'), format='A4', print_background=True)
    assert not errors, errors
    browser.close()
    print(f'PASS: real leaves diagram, hidden graphics/letters/word during recall, isolated self-check, and {count} actual printed cards within page height')
