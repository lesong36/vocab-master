"""Exercise cue switching, transfer recall, print consistency and narrow screens.

Run against the isolated static server on port 8766. Progress APIs are mocked.
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/mnemonics"
OUTPUT.mkdir(parents=True, exist_ok=True)
pack = json.loads((ROOT / "mnemonics/grade4.json").read_text())
cards = {card["word"]: card for card in pack["cards"] if card["section"] == "四上Unit 3"}
word = {"id": "201", "section": "四上Unit 3", "english_word": "use", "chinese_meaning": "使用",
        "learning_requirement": "能理解并会用", "pos": "v.", "correctCount": 0,
        "incorrectCount": 0, "consecutiveCorrect": 0, "mistakeCleared": False}
state = {"version": 1, "currentUserId": "dimensions-test", "savedAt": "2026-10-02T00:00:00.000Z",
         "users": {"dimensions-test": {"id": "dimensions-test", "name": "Isolated dimensions test",
                    "words": [word], "selectedGrade": "四上", "selectedSections": ["四上Unit 3"],
                    "studyEvents": [], "createdAt": "2026-10-02T00:00:00.000Z",
                    "updatedAt": "2026-10-02T00:00:00.000Z"}}}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1040, "height": 1100})
    page.route("**/api/health", lambda route: route.fulfill(json={"ok": True}))
    page.route("**/api/vocab-data", lambda route: route.fulfill(
        json=state if route.request.method == "GET" else {"ok": True}))
    page.add_init_script("localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")
    errors, writes = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: writes.append(request.post_data)
            if request.method == "POST" and request.url.endswith("/api/vocab-data") else None)
    page.goto("http://127.0.0.1:8766/vocabulary_app.html", wait_until="networkidle")
    page.get_by_role("button", name="开始学习 (18 词)").click(timeout=30000)
    for _ in range(18):
        page.get_by_role("button", name="点击查看课本单词助记").click(timeout=15000)
        page.get_by_text("课本词库", exact=True).wait_for()
        if any(item.is_visible() for item in page.get_by_text("use", exact=True).all()):
            break
        page.get_by_role("button", name="下一个 (Enter)").click()
    else:
        raise AssertionError("use was not reached")
    panel = page.get_by_role("region", name="多维助记")
    assert panel.get_by_role("button", name="拼写线索", exact=True).get_attribute("aria-pressed") == "true"
    assert panel.get_by_text(cards["use"]["hint"], exact=True).is_visible()
    panel.get_by_role("button", name="词义图", exact=True).click()
    assert panel.get_by_text(cards["use"]["dimensions"]["visual"]["caption"], exact=True).is_visible()
    assert not panel.get_by_text(cards["use"]["hint"], exact=True).count(), "All cues appear at once"
    for name, expected in (("词义区别", cards["use"]["dimensions"]["semantic"]),
                           ("用法与例句", cards["use"]["example"]),
                           ("拼写线索", cards["use"]["hint"])):
        panel.get_by_role("button", name=name, exact=True).click()
        assert panel.get_by_text(expected, exact=True).is_visible(), name
    assert not panel.get_by_role("button", name="词形组成", exact=True).count(), "No useful morphology exists for use"
    before = len(writes)
    page.get_by_role("button", name="收起线索，试着回忆", exact=True).click()
    recall = page.get_by_role("region", name="助记回忆练习")
    assert not page.get_by_role("region", name="多维助记").count(), "Cue panel leaked during spelling recall"
    recall.get_by_role("button", name="换个情境用一用", exact=True).click()
    assert recall.get_by_text(cards["use"]["dimensions"]["context"]["question"], exact=True).is_visible()
    assert not recall.get_by_text("use", exact=True).count(), "Answer leaked during transfer recall"
    assert not recall.get_by_text(cards["use"]["example"], exact=True).count(), "Example leaked before retrieval"
    assert not recall.locator('[aria-label="国际音标"]').count(), "Pronunciation leaks context answer"
    recall.screenshot(path=str(OUTPUT / "multidimensional-context-recall.png"))
    recall.get_by_role("textbox", name="情境问题的回答").fill("I use a spoon.")
    recall.get_by_role("button", name="想好了，看参考用法", exact=True).click()
    assert recall.get_by_text(cards["use"]["example"], exact=True).is_visible()
    recall.get_by_role("button", name="再试一次", exact=True).click()
    assert recall.get_by_role("textbox", name="情境问题的回答").input_value() == ""
    assert not recall.get_by_text(cards["use"]["example"], exact=True).count()
    recall.get_by_role("button", name="返回助记线索", exact=True).click()
    assert len(writes) == before, "Transfer self-check changed learning records"

    page.get_by_role("button", name="练本单元拼写（18 词）", exact=True).click()
    unit = page.get_by_role("region", name="单元拼写练习")
    assert unit.get_by_role("region", name="多维助记").is_visible()
    unit.get_by_role("button", name="下一词", exact=True).click()
    unit.get_by_role("button", name="词义图", exact=True).click()
    assert unit.get_by_role("img", name="sorry 的视觉线索", exact=True).is_visible()
    assert unit.locator('mark').inner_text() == "rr"
    unit.screenshot(path=str(OUTPUT / "multidimensional-sorry-desktop.png"))
    page.set_viewport_size({"width": 375, "height": 900})
    unit.screenshot(path=str(OUTPUT / "multidimensional-sorry-mobile.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Narrow screen overflows"
    unit.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
    assert not unit.get_by_role("img", name="sorry 的视觉线索", exact=True).count()
    assert not unit.locator('mark').count(), "Highlighted letters leaked during recall"
    unit.get_by_role("textbox", name="回忆本词拼写").fill("sorry")
    unit.get_by_role("button", name="写好了，核对字母", exact=True).click()
    unit.get_by_role("button", name="下一词", exact=True).click()
    unit.get_by_role("button", name="词义图", exact=True).click()
    assert unit.get_by_role("img", name="would 的视觉线索", exact=True).is_visible()
    assert unit.locator('mark').inner_text() == "l"
    unit.get_by_role("button", name="返回单词学习", exact=True).click()
    page.set_viewport_size({"width": 1040, "height": 1100})
    page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
    page.get_by_role("button", name="闪卡复习 (18 词)", exact=True).click()
    english = page.get_by_role("button", name="显示词义和助记", exact=True).locator('h3').inner_text()
    page.get_by_role("button", name="显示词义和助记", exact=True).click()
    visual = cards[english]["dimensions"]["visual"]
    has_picture = "diagram" in visual or english in {"in", "on", "under", "behind", "next to", "sorry", "would", "dessert", "meatball"}
    if has_picture:
        label = "看字形" if visual.get("diagram", {}).get("kind") == "spelling" else "词义图"
        page.get_by_role("button", name=label, exact=True).click()
        assert page.get_by_text(visual["caption"], exact=True).is_visible()
    else:
        assert page.get_by_text(cards[english]["hint"], exact=True).is_visible()
        assert not page.get_by_role("button", name="词义图", exact=True).count()
    if cards[english]["dimensions"]["semantic"]:
        page.get_by_role("button", name="词义区别", exact=True).click()
        assert page.get_by_text(cards[english]["dimensions"]["semantic"], exact=False).is_visible()
    else:
        assert not page.get_by_role("button", name="词义区别", exact=True).count()
        page.get_by_role("button", name="拼写线索", exact=True).click()
        assert page.get_by_text(cards[english]["hint"], exact=True).is_visible()
    assert not page.get_by_text(cards[english]["dimensions"]["visual"]["caption"], exact=True).count(), "Flashcard shows all cues at once"
    assert not page.locator('button button').count(), "Flashcard contains nested interactive controls"
    page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
    page.get_by_role("button", name="打印卡片 (18 词)", exact=True).click()
    use_print = page.locator('.print-card').filter(has=page.get_by_text("use", exact=True))
    assert cards["use"]["hint"] in use_print.inner_text()
    assert "用法与例句：" not in use_print.inner_text()
    assert cards["use"]["dimensions"]["context"]["question"] in use_print.inner_text()
    page.emulate_media(media="print")
    assert use_print.is_visible()
    assert use_print.evaluate("""card => {
        for (let node = card; node; node = node.parentElement) {
            if (Number(getComputedStyle(node).opacity) < 1) return false;
        }
        return true;
    }"""), "Print snapshots can freeze an unfinished fade-in and produce blank pages"
    page.pdf(path=str(OUTPUT / "multidimensional-print.pdf"), format="A4", print_background=True)
    assert not errors, errors
    browser.close()
    print("PASS: content-specific cue modes, independent context retrieval, hidden visuals/letters, no self-check writes, shared flashcard/print data, desktop and 375px layouts")
