"""Render authored diagrams with the app's real components, without learning-data writes."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/mnemonics"
OUTPUT.mkdir(parents=True, exist_ok=True)
targets = ("raincoat", "leaves", "fan", "recyclable")
cards = {card["word"]: card for grade in (3, 4, 5)
         for card in json.loads((ROOT / f"mnemonics/grade{grade}.json").read_text())["cards"]
         if card["word"] in targets}
source = (ROOT / "vocabulary_app.html").read_text()
render = "createRoot(document.getElementById('root')).render(<App />);"
assert source.count(render) == 1
fixture = """createRoot(document.getElementById('root')).render(
  <main className="mx-auto max-w-5xl bg-stone-50 p-4 sm:p-8">
    <h1 className="mb-2 text-2xl font-bold text-stone-800">从图形连到词义与字形</h1>
    <p className="mb-6 text-sm text-stone-600">组合 · 变化 · 词义对照</p>
    <div className="grid gap-6 sm:grid-cols-2">{CARDS.map(card =>
      <article key={card.word} data-word={card.word} className="min-w-0 rounded-2xl border border-stone-200 bg-white p-4">
        <h2 className="text-xl font-bold text-stone-800">{card.word}</h2>
        <MnemonicDimensions card={card} />
      </article>
    )}</div>
  </main>);""".replace("CARDS", json.dumps([cards[word] for word in targets], ensure_ascii=False))
source = source.replace(render, fixture)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1040, "height": 1200})
    page.route("**/vocabulary_app.html?graphics-test", lambda route: route.fulfill(body=source, content_type="text/html"))
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: writes.append(request.url) if request.method == "POST" else None)
    page.goto("http://127.0.0.1:8766/vocabulary_app.html?graphics-test", wait_until="networkidle")
    page.locator('[data-word="raincoat"] button').first.wait_for(timeout=30000)
    for word in targets:
        page.locator(f'[data-word="{word}"]').get_by_role('button', name='词义图', exact=True).click()
    for word in targets:
        article = page.locator(f'[data-word="{word}"]')
        for button in article.get_by_role("group", name="选择助记线索").get_by_role("button").all():
            assert button.locator('svg[aria-hidden="true"]').count() == 1
            assert button.inner_text().strip(), "Icon-only control loses its meaning"
        assert article.locator('[aria-label="图与词的对应"]').is_visible()
    leaves = page.locator('[data-word="leaves"] figure')
    assert leaves.locator('mark').all_text_contents() == ["f", "ves"]
    assert page.locator('[data-word="recyclable"] figure mark').all_text_contents() == ["e", "able"], "Only the final e is removed"
    fan = page.locator('[data-word="fan"] figure')
    assert fan.get_by_text("本课词义", exact=True).is_visible()
    assert fan.get_by_text("歌迷、爱好者", exact=True).is_visible()
    page.screenshot(path=str(OUTPUT / "mnemonic-graphic-examples.png"), full_page=True)
    page.set_viewport_size({"width": 375, "height": 1000})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile diagram overflows"
    for word in targets:
        for label in page.locator(f'[data-word="{word}"] figure p.font-mono').all():
            assert label.evaluate("node => node.scrollWidth <= node.clientWidth"), word
            assert label.evaluate("node => parseFloat(getComputedStyle(node).fontSize) >= 16"), word
    page.locator('[data-word="raincoat"]').screenshot(path=str(OUTPUT / "mnemonic-graphic-mobile.png"))
    page.locator('[data-word="recyclable"]').screenshot(path=str(OUTPUT / "mnemonic-graphic-recyclable-mobile.png"))
    # Real mode switching removes the picture and exposes the matching authored cue.
    article = page.locator('[data-word="raincoat"]')
    article.get_by_role("button", name="词义区别", exact=True).click()
    assert not article.locator('figure').count()
    assert article.get_by_text(cards["raincoat"]["dimensions"]["semantic"], exact=True).is_visible()
    compact_source = source.replace('<MnemonicDimensions card={card} />', '<MnemonicDimensions card={card} compact />').replace('sm:grid-cols-2', 'grid-cols-3')
    page.unroute("**/vocabulary_app.html?graphics-test")
    page.route("**/vocabulary_app.html?graphics-test", lambda route: route.fulfill(body=compact_source, content_type="text/html"))
    page.set_viewport_size({"width": 794, "height": 1123})
    page.reload(wait_until="networkidle")
    for word in targets:
        card = page.locator(f'[data-word="{word}"]')
        assert card.evaluate("node => node.getBoundingClientRect().height < 1000"), "Printed card exceeds a page"
        assert card.get_by_role('figure', name='拼写字形路径').is_visible()
        for label in card.locator('figure p.font-mono').all():
            assert label.evaluate("node => node.scrollWidth <= node.clientWidth"), "Printed spelling is clipped"
    page.screenshot(path=str(OUTPUT / "mnemonic-graphic-compact.png"), full_page=True)
    assert not errors, errors
    assert not writes, writes
    browser.close()
    print("PASS: four authored diagrams, word-change labels, lesson meaning, accessible icon/text controls, mode switching and 375px layout")
