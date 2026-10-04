"""Grade 6 authored cues and actual practice routes, with isolated learning APIs.

Run against a static server on port 8766 with the installed Python Playwright.
AI requests are blocked; this test never reads or writes a real learner profile.
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8766/vocabulary_app.html"
pack = json.loads((ROOT / "mnemonics/grade6.json").read_text())
cards = pack["cards"]
by_word = {card["word"]: card for card in cards}
with (ROOT / "词库.md").open(encoding="utf-8-sig", newline="") as source:
    words = [dict(row, correctCount=0, incorrectCount=0, consecutiveCorrect=0,
                  mistakeCleared=False) for row in csv.DictReader(source)
             if row["section"].startswith("六上")]
counts = Counter(word["section"] for word in words)
assert len(cards) == len(words) == 148


def isolated_state(target):
    # Keep the chosen word first; the init script fixes shuffling at stable order.
    ordered = sorted(words, key=lambda word: word["english_word"] != target)
    user = {"id": "grade6-mnemonic-ui", "name": "Isolated grade 6 test", "words": ordered,
            "selectedGrade": "六上", "selectedSections": [by_word[target]["section"]],
            "studyEvents": [], "createdAt": "2026-10-04T00:00:00.000Z",
            "updatedAt": "2026-10-04T00:00:00.000Z"}
    return {"version": 1, "currentUserId": user["id"], "users": {user["id"]: user},
            "savedAt": "2026-10-04T00:00:00.000Z"}


def learning_snapshot(page):
    return page.evaluate("""() => {
      const data = JSON.parse(localStorage.getItem('vocabmaster_app_data'));
      const user = data.users[data.currentUserId];
      return { events: user.studyEvents, words: user.words.map(w => ({
        id:w.id, correct:w.correctCount, incorrect:w.incorrectCount,
        consecutive:w.consecutiveCorrect, cleared:w.mistakeCleared
      })) };
    }""")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    errors, ai_requests = [], []
    # Exercise all actual cue components, including long textbook annotations.
    source = (ROOT / "vocabulary_app.html").read_text()
    fixture = '''function Grade6Gallery() {
      return <main className="mx-auto max-w-xl p-4">{CARDS.map(card =>
        <article key={card.word} data-word={card.word}><h1>{card.word}</h1>
          <MnemonicDimensions card={card} />
        </article>)}</main>;
    }
    createRoot(document.getElementById('root')).render(<Grade6Gallery/>);'''.replace(
        "CARDS", json.dumps(cards, ensure_ascii=False))
    page = browser.new_page(viewport={"width": 1040, "height": 900})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/vocabulary_app.html?grade6-gallery", lambda route: route.fulfill(
        body=source.replace("createRoot(document.getElementById('root')).render(<App />);", fixture),
        content_type="text/html"))
    page.goto(BASE + "?grade6-gallery", wait_until="networkidle")
    page.locator("article").last.wait_for(timeout=60000)
    for width in (1040, 375):
        page.set_viewport_size({"width": width, "height": 900})
        results = page.locator("article").evaluate_all("""nodes => nodes.map(node => ({
          word:node.dataset.word, cue:node.querySelector('figure figcaption')?.textContent,
          paths:node.querySelectorAll('figure[aria-label="拼写字形路径"]').length,
          selected:[...node.querySelectorAll('button[aria-pressed=true]')].map(b=>b.textContent),
          overflow:node.scrollWidth>node.clientWidth
        }))""")
        assert len(results) == 148
        for card, result in zip(cards, results):
            assert result["word"] == card["word"]
            assert result["cue"] == card["spellingPractice"]["cue"], result
            assert result["paths"] == 1 and result["selected"] == ["拼写线索"], result
            assert not result["overflow"], (width, result)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
    page.close()

    cases = [
        ("stomachache", "stomachache", "stomachac", "漏写 h"),
        ("Toronto", "Toronto", "toronto", "（大写）"),
        ("paper-cutting", "paper-cutting", "papercutting", "漏写 -"),
        ("save ... from", "save people from", "save people fro", "漏写 m"),
        ("keep ... away", "keep children away", "keep children awa", "漏写 y"),
        ("VR (= Virtual Reality)", "VR", "V", "漏写 r"),
        ("BeiDou Navigation Satellite System (abbr. BDS)", "BeiDou Navigation Satellite System",
         "BeiDou Navigation Satelite System", "漏写 l"),
        ("WHO (World Health Organization)", "WHO", "WH", "漏写 o"),
    ]
    for original, target, typo, correction in cases:
        state = isolated_state(original)
        context = browser.new_context(viewport={"width": 375, "height": 900})
        page = context.new_page()
        writes = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: writes.append(request.post_data)
                if request.method == "POST" and request.url.endswith("/api/vocab-data") else None)
        page.route("**/api/health", lambda route: route.fulfill(json={"ok": True}))
        page.route("**/api/vocab-data", lambda route: route.fulfill(
            json=state if route.request.method == "GET" else {"ok": True}))
        def block_ai(route):
            ai_requests.append(route.request.url)
            route.fulfill(status=503, json={"error": "AI blocked in authored cue test"})
        page.route("**/api/ai-*", block_ai)
        page.route("**/chat/completions", block_ai)
        page.route("https://api.dictionaryapi.dev/**", lambda route: route.fulfill(status=404, json={}))
        page.route("**/api/pronunciation?*", lambda route: route.fulfill(status=204, body=""))
        page.add_init_script("Math.random = () => 0.5; localStorage.setItem('vocabmaster_app_data', "
                             + json.dumps(json.dumps(state)) + ");")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(800)  # Drain bootstrap persistence before measuring self-check writes.
        count = counts[by_word[original]["section"]]
        page.get_by_role("button", name=f"开始学习 ({count} 词)", exact=True).click(timeout=30000)
        for _ in range(count):
            page.get_by_role("button", name="点击查看课本单词助记", exact=True).click(timeout=15000)
            page.get_by_text("课本词库", exact=True).wait_for()
            if page.get_by_role("figure", name="拼写字形路径").get_by_text(
                    by_word[original]["spellingPractice"]["cue"], exact=True).count():
                break
            page.get_by_role("button", name="下一个 (Enter)", exact=True).click()
        else:
            raise AssertionError(f"Authored study cue not reached: {original}")
        page.wait_for_timeout(600)  # Entering study schedules a save; drain it before the self-check.
        before_writes, before_learning = len(writes), learning_snapshot(page)
        page.get_by_role("button", name="不看提示，试着回忆", exact=True).click()
        recall = page.get_by_role("region", name="助记回忆练习")
        if original == "WHO (World Health Organization)":
            readings = json.loads((ROOT / "phonetics.json").read_text())["entries"]
            assert recall.locator('[aria-label="国际音标"]').inner_text() == readings[original.lower()]
            assert readings[original.lower()] != readings["who"], "WHO must use letter-name IPA"
        assert not recall.get_by_role("figure", name="拼写字形路径").count()
        assert not any(node.is_visible() for node in page.get_by_text(original, exact=True).all()), original
        assert not any(node.is_visible() for node in page.get_by_text(target, exact=True).all()), target
        recall.get_by_role("textbox", name="回忆英文拼写").fill(typo)
        recall.get_by_role("button", name="写好了，核对", exact=True).click()
        assert recall.get_by_text("对照看看：哪些字母要补上或改一改？", exact=True).is_visible()
        assert correction in recall.locator("ul").inner_text(), (original, recall.inner_text())
        assert not re.search(r"abbr\.|[()=]|\.\.\.", recall.locator("ul").inner_text()), original
        recall.get_by_role("button", name="再试一次", exact=True).click()
        recall.get_by_role("textbox", name="回忆英文拼写").fill(target)
        recall.get_by_role("button", name="写好了，核对", exact=True).click()
        assert recall.get_by_text("拼写一致。过一会儿再试一次。", exact=True).is_visible()
        recall.get_by_role("button", name="再试一次", exact=True).click()
        recall.get_by_role("button", name="换个情境用一用", exact=True).click()
        assert recall.get_by_text(by_word[original]["dimensions"]["context"]["question"], exact=True).is_visible()
        assert not recall.locator('[aria-label="国际音标"]').count()
        assert not recall.get_by_text(by_word[original]["example"], exact=True).count()
        recall.get_by_role("textbox", name="情境问题的回答").fill("我先想一想")
        recall.get_by_role("button", name="想好了，看参考用法", exact=True).click()
        assert recall.get_by_text(by_word[original]["example"], exact=True).is_visible()
        recall.get_by_role("button", name="返回助记线索", exact=True).click()
        assert len(writes) == before_writes, (original, "self-check writes", before_writes, len(writes))
        assert learning_snapshot(page) == before_learning, (original, "learning changed", before_learning, learning_snapshot(page))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), original

        # Verify one complete unit workflow, plus shared flashcard/print content.
        if original == "paper-cutting":
            page.get_by_role("button", name=f"练本单元拼写（{count} 词）", exact=True).click()
            unit = page.get_by_role("region", name="单元拼写练习")
            for _ in range(count):
                if unit.locator("p.font-mono.text-4xl").first.inner_text() == target:
                    break
                unit.get_by_role("button", name="下一词", exact=True).click()
            else:
                raise AssertionError("paper-cutting was absent from authored unit practice")
            unit.get_by_role("button", name="隐藏提示，写出完整单词", exact=True).click()
            assert not unit.get_by_role("figure", name="拼写字形路径").count()
            assert not unit.get_by_text(original, exact=True).count()
            unit.get_by_role("textbox", name="回忆本词拼写").fill(typo)
            unit.get_by_role("button", name="写好了，核对字母", exact=True).click()
            assert unit.get_by_text("漏写 -", exact=True).is_visible()
            unit.get_by_role("button", name="隐藏答案，再写一次", exact=True).click()
            unit.get_by_role("textbox", name="回忆本词拼写").fill(target)
            unit.get_by_role("button", name="写好了，核对字母", exact=True).click()
            assert unit.get_by_text("这次拼写正确。", exact=True).is_visible()
            unit.get_by_role("button", name="返回单词学习", exact=True).click()
            assert len(writes) == before_writes and learning_snapshot(page) == before_learning
            page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
            page.get_by_role("button", name=f"闪卡复习 ({count} 词)", exact=True).click()
            flip = page.get_by_role("button", name="显示词义和助记", exact=True)
            flash_word = flip.locator("h3").inner_text()
            flip.click()
            page.get_by_text("完整读写提示", exact=True).click()
            assert page.get_by_text(by_word[flash_word]["hint"], exact=True).is_visible()
            page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
            page.get_by_role("button", name=f"打印卡片 ({count} 词)", exact=True).click()
            assert page.locator(".print-card").count() == count
            for card in (card for card in cards if card["section"] == by_word[original]["section"]):
                printed = page.locator(".print-card").filter(has=page.locator("span.text-3xl").filter(
                    has_text=re.compile("^" + re.escape(card["word"]) + "$")))
                assert printed.count() == 1, card["word"]
                assert card["hint"] in printed.inner_text(), card["word"]
                assert card["spellingPractice"]["cue"] in printed.inner_text(), card["word"]
            page.emulate_media(media="print")
            assert page.locator(".print-card").first.is_visible()
        context.close()
    assert not errors, errors
    assert not ai_requests, ai_requests
    browser.close()
print("PASS: 148 authored default spelling paths at 1040/375px; eight real recall/typo/context routes, annotation-free answers, unit practice, flashcards and print; AI blocked and self-check learning records unchanged")
