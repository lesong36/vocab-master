"""Check every actual print card at the usable width of A4, without real writes."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mnemonics'
OUTPUT.mkdir(parents=True, exist_ok=True)
word = dict(id='1', section='三下Unit 1', english_word='where', chinese_meaning='在哪里',
            learning_requirement='能理解并会用', pos='pron.', correctCount=0, incorrectCount=0,
            consecutiveCorrect=0, mistakeCleared=False)
state = {'version': 1, 'currentUserId': 'print-library-test', 'users': {
    'print-library-test': {'id': 'print-library-test', 'name': 'Isolated print check', 'words': [],
                           'selectedGrade': None, 'selectedSections': [], 'studyEvents': [],
                           'createdAt': '2026-10-02T00:00:00.000Z', 'updatedAt': '2026-10-02T00:00:00.000Z'}}}
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1040, 'height': 1100})
    page.route('**/api/health', lambda route: route.fulfill(json={'ok': True}))
    page.route('**/api/vocab-data', lambda route: route.fulfill(json=state if route.request.method == 'GET' else {'ok': True}))
    page.add_init_script("localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8766/vocabulary_app.html', wait_until='networkidle', timeout=60000)
    for grade in ('三上', '三下', '四上', '四下', '五上', '五下', '六上'):
        page.get_by_role('button', name=re.compile('^' + grade + r'\s')).click(timeout=30000)
        units = page.get_by_role('button', name=re.compile(r'^Unit \d+\s'))
        assert units.count() > 0, grade
        for unit in units.all():
            unit.click()
        page.get_by_role('button', name='返回年级选择', exact=True).click()
    print_button = page.get_by_role('button', name=re.compile(r'^打印卡片 \('))
    selected_count = int(re.search(r'\((\d+) 词\)', print_button.inner_text()).group(1))
    print_button.click()
    # 210 mm A4 minus two 10 mm margins, at 96 CSS pixels per inch.
    page.set_viewport_size({'width': 718, 'height': 1047})
    page.emulate_media(media='print')
    assert page.locator('.print-grid').evaluate("grid => getComputedStyle(grid).gridTemplateColumns.split(' ').length") == 3, 'A4 verification must use the actual three-column print layout'
    assert page.locator('.print-card').count() == selected_count
    expected = {card['section'] + '|' + card['word'] for grade in (3, 4, 5, 6)
                for card in json.loads((ROOT / f'mnemonics/grade{grade}.json').read_text())['cards']}
    actual = set(page.locator('.print-card').evaluate_all("cards => cards.map(card => card.querySelector('span.text-xs.font-mono').textContent + '|' + card.querySelector('span.text-3xl').textContent)"))
    assert actual == expected, {"missing": sorted(expected - actual), "extra": sorted(actual - expected)}
    assert selected_count == len(expected) == 1038
    horizontal = page.locator('.print-card').evaluate_all("""cards => cards.flatMap(card => {
        const bounds = card.getBoundingClientRect();
        const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
        const failures = [];
        let node;
        while (node = walker.nextNode()) {
            if (!node.textContent.trim() || !node.parentElement.getClientRects().length) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            for (const rect of range.getClientRects()) {
                if (rect.width && (rect.left < bounds.left - 1 || rect.right > bounds.right + 1)) {
                    failures.push({word:card.querySelector('span.text-3xl').textContent,
                        text:node.textContent.trim(), left:rect.left, right:rect.right,
                        cardLeft:bounds.left, cardRight:bounds.right});
                    break;
                }
            }
        }
        return failures;
    })""")
    if horizontal:
        failed = horizontal[0]['word']
        page.locator('.print-card').filter(has=page.locator('span.text-3xl').filter(
            has_text=re.compile('^' + re.escape(failed) + '$'))).first.screenshot(
                path=str(OUTPUT / 'grade6-print-horizontal-failure.png'))
    assert not horizontal, horizontal
    overflow = page.locator('.print-card').evaluate_all("""cards => cards.filter(card => card.getBoundingClientRect().height > 1047).map(card => ({word:card.querySelector('span.text-3xl').textContent,height:card.getBoundingClientRect().height}))""")
    if overflow:
        longest = max(overflow, key=lambda card: card['height'])
        page.locator('.print-card').filter(has=page.locator('span.text-3xl').filter(has_text=re.compile('^' + re.escape(longest['word']) + '$'))).first.screenshot(path=str(OUTPUT / 'next-print-library-failure.png'))
    assert not overflow, overflow
    beidou = page.locator('.print-card').filter(has=page.locator('span.text-3xl').filter(
        has_text=re.compile(r'^BeiDou Navigation Satellite System \(abbr\. BDS\)$')))
    assert beidou.count() == 1
    beidou.screenshot(path=str(OUTPUT / 'grade6-beidou-print-card.png'))
    samples = ['communication', 'National Library of China', 'China Science and Technology Museum', 'BeiDou Navigation Satellite System (abbr. BDS)', 'WHO (World Health Organization)', 'VR (= Virtual Reality)']
    page.locator('.print-card').evaluate_all("""(cards, samples) => cards.forEach(card => {
        if (!samples.includes(card.querySelector('span.text-3xl').textContent)) card.remove();
    })""", samples)
    page.pdf(path=str(OUTPUT / 'next-print-examples.pdf'), format='A4', print_background=True)
    assert not errors, errors
    browser.close()
    print(f'PASS: all {len(expected)} actual print cards across seven books fit usable A4 height and horizontal text bounds; long grade 6 examples use actual print layout')
