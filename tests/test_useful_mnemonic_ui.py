"""Check authored spelling cues and omitted empty modes with real components."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mnemonics'
OUTPUT.mkdir(parents=True, exist_ok=True)
all_cards = [card for grade in (3, 4, 5)
             for card in json.loads((ROOT / f'mnemonics/grade{grade}.json').read_text())['cards']]
cards = [next(card for card in all_cards if card['word'] == word)
         for word in ('remember', 'poem', 'raincoat')]
source = (ROOT / 'vocabulary_app.html').read_text()
render = "createRoot(document.getElementById('root')).render(<App />);"
fixture = """function UsefulCueTest() {
  const [index, setIndex] = useState(0);
  const [compact, setCompact] = useState(false);
  useEffect(() => { window.selectCueCard = setIndex; window.setCueCompact = setCompact; }, []);
  return <main className="mx-auto max-w-xl p-4">
    <h1 className="text-xl font-bold">{CARDS[index].word}</h1>
    <MnemonicDimensions card={CARDS[index]} compact={compact} />
  </main>;
}
createRoot(document.getElementById('root')).render(<UsefulCueTest />);""".replace('CARDS', json.dumps(cards, ensure_ascii=False))

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1040, 'height': 900})
    page.route('**/vocabulary_app.html?useful-cues', lambda route: route.fulfill(
        body=source.replace(render, fixture), content_type='text/html'))
    errors, writes = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
    page.goto('http://127.0.0.1:8766/vocabulary_app.html?useful-cues', wait_until='networkidle')
    panel = page.get_by_role('region', name='多维助记')
    panel.get_by_role('button', name='看字形', exact=True).wait_for(timeout=30000)
    assert panel.get_by_role('button', name='看字形', exact=True).get_attribute('aria-pressed') == 'true'
    assert not panel.get_by_role('button', name='拆词理解', exact=True).count()
    assert panel.locator('[data-graphic-kind="spelling"] mark').all_text_contents() == ['m', 'm']
    assert panel.get_by_text('/rɪ/', exact=True).is_visible()
    assert panel.get_by_text('/mem/', exact=True).is_visible()
    assert panel.get_by_text('/bə/', exact=True).is_visible()
    assert '整体记' not in panel.inner_text()
    assert not panel.get_by_text('🧠', exact=True).count()
    panel.screenshot(path=str(OUTPUT / 'remember-useful-desktop.png'))
    panel.get_by_role('button', name='听音拼写', exact=True).click()
    assert panel.get_by_text(cards[0]['hint'], exact=True).is_visible()
    assert not panel.locator('figure').count()
    panel.get_by_role('button', name='看字形', exact=True).click()
    page.set_viewport_size({'width': 375, 'height': 900})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert panel.locator('[aria-label="读音与字母分段"] > div').count() == 3
    panel.screenshot(path=str(OUTPUT / 'remember-useful-mobile.png'))

    # Reuse the same mounted component: a removed visual mode must fall back.
    page.evaluate('window.selectCueCard(1)')
    panel.get_by_role('button', name='听音拼写', exact=True).wait_for()
    assert panel.get_by_role('button', name='听音拼写', exact=True).get_attribute('aria-pressed') == 'true'
    assert not panel.get_by_role('button', name='看图记', exact=True).count()
    assert not panel.get_by_role('button', name='拆词理解', exact=True).count()
    assert panel.get_by_text(cards[1]['hint'], exact=True).is_visible()
    assert not panel.locator('figure').count()

    # Real composition remains available; removing it on the next word is safe.
    page.evaluate('window.selectCueCard(2)')
    panel.get_by_role('button', name='拆词理解', exact=True).click()
    assert panel.get_by_text(cards[2]['dimensions']['morphology']['note'], exact=True).is_visible()
    page.evaluate('window.selectCueCard(0)')
    assert panel.get_by_role('button', name='听音拼写', exact=True).get_attribute('aria-pressed') == 'true'
    assert panel.get_by_text(cards[0]['hint'], exact=True).is_visible()

    page.evaluate('window.setCueCompact(true)')
    compact = page.locator('[aria-label="多维助记"]')
    compact.locator('[data-graphic-kind="spelling"]').wait_for()
    assert compact.locator('mark').all_text_contents() == ['m', 'm']
    assert '拆词理解' not in compact.inner_text()
    page.set_viewport_size({'width': 320, 'height': 1000})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not compact.evaluate('node => node.scrollWidth > node.clientWidth')
    compact.screenshot(path=str(OUTPUT / 'remember-useful-compact.png'))
    page.evaluate('window.selectCueCard(1)')
    assert not compact.locator('figure').count()
    assert '拆词理解' not in compact.inner_text()
    assert not errors, errors
    assert not writes, writes
    browser.close()
    print('PASS: remember spelling and two m cues, content-specific modes, safe card switching, compact cards and narrow screens; no data writes')
