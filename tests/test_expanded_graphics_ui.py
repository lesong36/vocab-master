"""Render every real graphic, including compact cards; never touch learning records."""

import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/mnemonics"
SPECIAL = {"in", "on", "under", "behind", "next to", "sorry", "would", "dessert", "meatball"}
cards = [card for grade in (3, 4, 5)
         for card in json.loads((ROOT / f"mnemonics/grade{grade}.json").read_text())["cards"]
         if "diagram" in card["dimensions"]["visual"] or card["word"] in SPECIAL]
source = (ROOT / "vocabulary_app.html").read_text()
render = "createRoot(document.getElementById('root')).render(<App />);"
assert source.count(render) == 1
fixture = """function GraphicAudit() {
  const [compact, setCompact] = useState(false);
  useEffect(() => { window.setGraphicCompact = setCompact; }, []);
  return <main className="mx-auto max-w-5xl p-4">
    <div className={compact ? 'grid grid-cols-3 gap-3' : 'grid gap-4 sm:grid-cols-2'}>
      {CARDS.map((card, index) => <article key={index} data-graphic-index={index} className="min-w-0 rounded-xl border border-stone-200 bg-white p-3">
        <h2 className={compact ? 'break-words text-3xl font-bold' : 'break-words text-xl font-bold'}>{card.word}</h2>
        {compact && <p className="my-2 text-xl">词义</p>}
        {compact && <p className="mt-2 whitespace-pre-line text-sm leading-6">{card.hint}</p>}
        {compact ? <MnemonicDimensions card={card} compact /> : <div className="p-4"><MnemonicPicture card={card} /></div>}
      </article>)}
    </div>
  </main>;
}
createRoot(document.getElementById('root')).render(<GraphicAudit />);""".replace("CARDS", json.dumps(cards, ensure_ascii=False))
audit_source = source.replace(render, fixture)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1040, "height": 1100})
    page.route("**/vocabulary_app.html?expanded-graphics", lambda route: route.fulfill(body=audit_source, content_type="text/html"))
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: writes.append(request.url) if request.method == "POST" else None)
    page.goto("http://127.0.0.1:8766/vocabulary_app.html?expanded-graphics", wait_until="networkidle")
    page.locator('article figure').last.wait_for(timeout=30000)
    assert page.locator('article figure').count() == len(cards)
    for index, card in enumerate(cards):
        diagram = card["dimensions"]["visual"].get("diagram")
        if not diagram:
            continue
        article = page.locator(f'[data-graphic-index="{index}"]')
        assert article.locator('[aria-label="图与词的对应"]').is_visible(), card["word"]
        if diagram['kind'] == 'spelling':
            segments = article.locator('[aria-label="读音与字母分段"] > div > p:first-child')
            assert segments.count() == len(diagram['segments']), card['word']
            assert ''.join(segments.all_text_contents()) == card['word'], card['word']
        if diagram["kind"] == "count":
            if diagram.get("ordinal"):
                ordinal = article.locator('[data-ordinal-target="true"]')
                assert ordinal.count() == 1 and ordinal.get_attribute('fill') == '#a96d29'
                assert ordinal.locator('..').locator('text').text_content() == str(diagram["value"])
            else:
                assert article.locator('circle[fill="#a96d29"]').count() == diagram["value"]
        if diagram["kind"] == "measure":
            rectangles = article.locator('[data-measure-value]').all()
            attribute = 'height' if diagram['dimension'] in ('height', 'thickness') else 'width'
            actual_ratio = float(rectangles[0].get_attribute(attribute)) / float(rectangles[1].get_attribute(attribute))
            expected_ratio = diagram['labels'][0]['value'] / diagram['labels'][1]['value']
            assert abs(actual_ratio - expected_ratio) < 0.01
        if diagram["kind"] == "body":
            assert article.locator(f'[data-body-target="{diagram["part"]}"]').count() == 1
        if diagram["kind"] == "clock":
            angle = ((diagram["hour"] % 12) + diagram["minute"] / 60) * math.pi / 6
            hand = article.locator('[data-clock-hand="hour"]')
            assert abs(float(hand.get_attribute("x2")) - (160 + math.sin(angle) * 47)) < 0.01
        if diagram["kind"] == "family":
            assert article.locator('[data-family-node]').count() >= 2
        if diagram['kind'] == 'reference':
            assert article.locator('[data-reference-node]').count() == 2
            assert article.locator('mark').all_text_contents() == [diagram['sentence']['word']]
            assert article.locator('[data-reference-link]').get_attribute('data-reference-link') == diagram['relation']
        if diagram['kind'] == 'deixis':
            assert article.locator('[data-deixis-target]').get_attribute('data-deixis-target') == card['word']
        if diagram['kind'] == 'motion':
            start = article.locator('[data-motion-start]')
            end = article.locator('[data-motion-end]')
            axis = 'y' if diagram['direction'] in ('up', 'down') else 'x'
            delta = float(end.get_attribute(axis)) - float(start.get_attribute(axis))
            reverse = diagram['direction'] in ('toward', 'left', 'pull', 'in', 'up')
            assert (delta < 0) == reverse, (card['word'], delta)
            if diagram.get('focusEndpoint'):
                assert article.locator('[data-motion-focus]').get_attribute('data-motion-focus') == diagram['focusEndpoint']
            assert bool(article.locator('[data-motion-history]').count()) == diagram.get('returning', False)
        if diagram['kind'] == 'frequency':
            assert article.locator('[data-frequency-hit="true"]').count() == len(diagram['hits'])
        if diagram['kind'] == 'selection':
            assert article.locator('[data-selection-active="true"]').count() == len(diagram['selected'])
            if 'comparison' in diagram:
                assert article.locator('[data-comparison-dot]').count() == diagram['comparison']
        if diagram['kind'] == 'timeline':
            assert article.locator('[data-time-active="true"]').count() == sum(point['active'] for point in diagram['points'])
        if diagram['kind'] == 'shape':
            assert article.locator('[data-shape-name]').count() == 3
        if diagram['kind'] == 'category':
            assert article.locator('li').count() == len(diagram['items'])
        if diagram['kind'] == 'partition':
            assert article.locator('[data-partition-piece]').count() == diagram['pieces']
            assert article.locator('[data-partition-piece="selected"]').count() == len(diagram['selected'])
        if diagram['kind'] == 'feature':
            assert article.locator('[data-feature-scene]').get_attribute('data-feature-scene') == diagram['scene']
            if diagram['scene'] == 'jump':
                feet = article.locator('[data-jump-phase]').evaluate_all("groups => groups.map(g => new DOMPoint(14, 0).matrixTransform(g.transform.baseVal.consolidate().matrix).y)")
                assert feet[0] == feet[2] and feet[1] < feet[0], card['word']
                assert article.locator('[data-jump-arc]').count() == 1
            elif diagram['scene'] == 'fall-over':
                bottom = article.locator('[data-fall-pose="fallen"]').evaluate("g => { const b=g.getBBox(), m=g.transform.baseVal.consolidate().matrix; return Math.max(...[[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y]) => new DOMPoint(x,y).matrixTransform(m).y)); }")
                assert bottom <= 169, (card['word'], 'Body crosses the ground', bottom)
            elif diagram['scene'] == 'stick':
                contacts = article.locator('[data-stuck-seed]').evaluate_all("seeds => seeds.map(seed => { const shoe=seed.parentElement.querySelector('path').getBBox(), b=seed.getBBox(); return Math.abs(b.y-(shoe.y+shoe.height)); })")
                assert len(contacts) == 2 and all(gap < 0.01 for gap in contacts), contacts
            elif diagram['scene'] == 'posting':
                assert article.locator('[data-paper-fixing]').count() == 4
                assert article.locator('[data-posted-paper]').count() == 1
            elif diagram['scene'] == 'arrangement':
                objects = [article.locator(f'[data-arrangement="{state}"] [data-same-object]').evaluate_all("objects => objects.map(o => [o.dataset.sameObject,o.getAttribute('fill')])") for state in ('messy', 'neat')]
                assert len(objects[0]) == 6 and objects[0] == objects[1], card['word']
    assert not errors, errors

    def check_layout(compact=False):
        failures = page.evaluate("""() => [...document.querySelectorAll('article')].flatMap(card => {
          const labels = [...card.querySelectorAll('figure p.font-mono')];
          const bad = labels.filter(label => label.scrollWidth > label.clientWidth + 1);
          return bad.map(label => ({word: card.querySelector('h2').textContent, label: label.textContent}));
        })""")
        assert not failures, failures
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Page overflows"
        clipped_svg_labels = page.evaluate("""() => [...document.querySelectorAll('article figure svg text')].filter(text => {
          if (Number(text.getAttribute('font-size')) > 18) return false;
          const b = text.getBBox(), v = text.ownerSVGElement.viewBox.baseVal;
          return b.x < v.x - 1 || b.x + b.width > v.x + v.width + 1;
        }).map(text => ({word: text.closest('article').querySelector('h2').textContent, label: text.textContent}))""")
        assert not clipped_svg_labels, clipped_svg_labels
        if compact:
            too_tall = page.evaluate("""() => [...document.querySelectorAll('article')]
              .filter(card => card.getBoundingClientRect().height > 1050)
              .map(card => ({word: card.querySelector('h2').textContent, height: card.getBoundingClientRect().height}))""")
            assert not too_tall, too_tall

    try:
        check_layout()
    except AssertionError:
        international_index = next(index for index, card in enumerate(cards) if card['word'] == 'international')
        page.locator(f'[data-graphic-index="{international_index}"]').screenshot(path=str(OUTPUT / 'expanded-graphics-long-word-failure.png'))
        raise
    page.set_viewport_size({"width": 375, "height": 1000})
    try:
        check_layout()
    except AssertionError:
        page.screenshot(path=str(OUTPUT / "expanded-graphics-layout-failure.png"))
        raise
    page.evaluate("window.setGraphicCompact(true)")
    page.set_viewport_size({"width": 740, "height": 1123})
    page.locator('[aria-label="多维助记"]').first.wait_for()
    try:
        check_layout(compact=True)
    except AssertionError:
        page.locator('article').filter(has=page.get_by_role('heading', name='winter', exact=True)).screenshot(path=str(OUTPUT / 'expanded-graphics-print-failure.png'))
        raise

    # A gallery uses the same real cards/components, selecting diverse mechanisms.
    samples = [next(card for card in cards if card["word"] == word)
               for word in ("I", "my", "these", "take out", "often", "ago", "each", "ourselves")]
    gallery = fixture.replace(json.dumps(cards, ensure_ascii=False), json.dumps(samples, ensure_ascii=False))
    gallery_source = source.replace(render, gallery)
    page.unroute("**/vocabulary_app.html?expanded-graphics")
    page.route("**/vocabulary_app.html?expanded-graphics", lambda route: route.fulfill(body=gallery_source, content_type="text/html"))
    page.set_viewport_size({"width": 1040, "height": 1100})
    page.reload(wait_until="networkidle")
    page.locator('article figure').first.wait_for()
    page.screenshot(path=str(OUTPUT / "next-graphic-examples.png"), full_page=True)
    page.set_viewport_size({"width": 375, "height": 1000})
    page.locator('[data-graphic-index="7"]').screenshot(path=str(OUTPUT / "next-reflexive-mobile.png"))
    concrete_samples = [next(card for card in cards if card['word'] == word)
                        for word in ('kite', 'rope', 'door', 'cut', 'carry', 'sort', 'balance', 'square')]
    concrete_gallery = fixture.replace(json.dumps(cards, ensure_ascii=False), json.dumps(concrete_samples, ensure_ascii=False))
    page.unroute("**/vocabulary_app.html?expanded-graphics")
    page.route("**/vocabulary_app.html?expanded-graphics", lambda route: route.fulfill(body=source.replace(render, concrete_gallery), content_type='text/html'))
    page.set_viewport_size({'width': 1040, 'height': 1100})
    page.reload(wait_until='networkidle')
    page.locator('article figure').last.wait_for()
    page.screenshot(path=str(OUTPUT / 'next-concrete-graphic-examples.png'), full_page=True)
    assert not errors, errors
    assert not writes, writes
    browser.close()
    print(f"PASS: all {len(cards)} real graphics render; actual counts, ordinal markers, body targets, moving hour hands, family connections, desktop/mobile/compact layouts; no learning-data writes")
