"""Exercise real purple study, recall and unit feedback without learning writes."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mnemonics'
OUTPUT.mkdir(parents=True, exist_ok=True)
word = {'id': '400', 'section': '三上Unit 6', 'english_word': 'purple',
        'chinese_meaning': '紫色的', 'learning_requirement': '能理解并会用', 'pos': 'adj.',
        'correctCount': 0, 'incorrectCount': 0, 'consecutiveCorrect': 0, 'mistakeCleared': False}
state = {'version': 1, 'currentUserId': 'spelling-test', 'users': {'spelling-test': {
    'id': 'spelling-test', 'name': 'Isolated spelling test', 'words': [word],
    'selectedGrade': '三上', 'selectedSections': [], 'studyEvents': [],
    'createdAt': '2026-10-03T00:00:00.000Z', 'updatedAt': '2026-10-03T00:00:00.000Z'}}}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1040, 'height': 1100})
    page.route('**/api/health', lambda route: route.fulfill(json={'ok': True}))
    page.route('**/api/vocab-data', lambda route: route.fulfill(json=state if route.request.method == 'GET' else {'ok': True}))
    page.add_init_script("localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")
    errors, writes = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: writes.append(request.post_data)
            if request.method == 'POST' and request.url.endswith('/api/vocab-data') else None)
    page.goto('http://127.0.0.1:8766/vocabulary_app.html', wait_until='networkidle')
    page.get_by_role('button', name=re.compile(r'^Unit 6\b')).click(timeout=30000)
    start = page.get_by_role('button', name=re.compile(r'^开始学习 \('))
    count = int(re.search(r'\((\d+) 词\)', start.inner_text()).group(1))
    start.click()
    for _ in range(count):
        page.get_by_role('button', name='点击查看课本单词助记').click()
        guide = page.get_by_role('figure', name='拼写字形路径')
        if guide.count() and guide.locator('mark').all_text_contents() == ['ur', 'le']:
            break
        page.get_by_role('button', name='下一个 (Enter)', exact=True).click()
    else:
        raise AssertionError('purple not reached')
    assert page.get_by_role('button', name='拼写线索', exact=True).get_attribute('aria-pressed') == 'true'
    assert guide.get_by_text('pur', exact=True).is_visible()
    assert guide.get_by_text('ple', exact=True).is_visible()
    assert not page.locator('[data-graphic-kind="colour"]').count()
    guide.screenshot(path=str(OUTPUT / 'purple-spelling-path.png'))
    page.set_viewport_size({'width': 375, 'height': 1000})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    guide.screenshot(path=str(OUTPUT / 'purple-spelling-mobile.png'))
    page.wait_for_timeout(700)
    before = len(writes)
    progress = page.evaluate('localStorage.getItem("vocabmaster_app_data")')
    page.get_by_role('button', name='收起提示，写完整词', exact=True).click()
    recall = page.get_by_role('region', name='助记回忆练习')

    def hidden(region, field, submit):
        assert not region.locator('figure, mark').count()
        assert 'purple' not in region.inner_text().lower()
        assert field.input_value() == ''
        assert submit.is_disabled()

    field = recall.get_by_role('textbox', name='回忆英文拼写')
    submit = recall.get_by_role('button', name='写好了，核对', exact=True)
    for answer, expected in [('perple', 'e 改为 u'), ('purpl', '漏写 e'), ('purpel', 'e 改为 l'), ('purple', '拼写一致')]:
        hidden(recall, field, submit)
        field.fill(answer)
        submit.click()
        assert expected in recall.inner_text()
        assert recall.get_by_role('figure', name='拼写字形路径').locator('mark').all_text_contents() == ['ur', 'le']
        if answer == 'perple':
            recall.screenshot(path=str(OUTPUT / 'purple-letter-feedback.png'))
        recall.get_by_role('button', name='再试一次', exact=True).click()
    hidden(recall, field, submit)
    recall.screenshot(path=str(OUTPUT / 'purple-spelling-hidden.png'))
    recall.get_by_role('button', name='返回助记线索').click()
    page.get_by_role('button', name=re.compile(r'^练本单元拼写')).click()
    unit = page.get_by_role('region', name='单元拼写练习')
    for _ in range(count):
        guide = unit.get_by_role('figure', name='拼写字形路径')
        if guide.count() and guide.locator('mark').all_text_contents() == ['ur', 'le']:
            break
        unit.get_by_role('button', name='下一词', exact=True).click()
    else:
        raise AssertionError('unit purple not reached')
    unit.get_by_role('button', name='收起提示，写完整词', exact=True).click()
    for answer, expected in [('perple', 'e 改为 u'), ('purpl', '漏写 e'), ('purpel', 'e 改为 l'), ('purple', '这次拼写正确')]:
        field = unit.get_by_role('textbox', name='回忆本词拼写')
        submit = unit.get_by_role('button', name='写好了，核对字母')
        hidden(unit, field, submit)
        field.fill(answer)
        submit.click()
        assert expected in unit.inner_text()
        assert unit.get_by_role('figure', name='拼写字形路径').locator('mark').all_text_contents() == ['ur', 'le']
        unit.get_by_role('button', name='收起答案，再写一次').click()
    page.wait_for_timeout(700)
    assert len(writes) == before, 'Self-check wrote learning progress'
    assert page.evaluate('localStorage.getItem("vocabmaster_app_data")') == progress
    assert not errors, errors
    browser.close()
    print('PASS: purple default letter path; three specific corrections and correct answer in main/unit; retries hide answers; no learning writes; mobile fits')
