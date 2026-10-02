"""Browser check with mocked progress APIs; never writes real learning data.

Run against a static server on port 8766 using the installed Playwright runtime.
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


word = {
    "id": "201", "section": "四上Unit 3", "english_word": "use",
    "chinese_meaning": "使用", "learning_requirement": "能理解并会用", "pos": "v.",
    "correctCount": 0, "incorrectCount": 0, "consecutiveCorrect": 0,
    "mistakeCleared": False,
}
state = {
    "version": 1, "currentUserId": "mnemonic-test", "savedAt": "2026-09-30T00:00:00.000Z",
    "users": {"mnemonic-test": {
        "id": "mnemonic-test", "name": "Isolated Test", "words": [word],
        "selectedGrade": "四上", "selectedSections": ["四上Unit 3"],
        "studyEvents": [], "createdAt": "2026-09-30T00:00:00.000Z",
        "updatedAt": "2026-09-30T00:00:00.000Z",
    }},
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.route("**/api/health", lambda route: route.fulfill(json={"ok": True}))
    page.route("**/api/vocab-data", lambda route: route.fulfill(
        json=state if route.request.method == "GET" else {"ok": True}
    ))
    page.add_init_script(
        "localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");"
    )
    errors = []
    writes = []
    page.on("request", lambda request: writes.append(request.post_data) if request.method == "POST" and request.url.endswith("/api/vocab-data") else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8766/vocabulary_app.html", wait_until="networkidle")
    assert not page.get_by_role("button", name="🪄 生成本 Unit 助记", exact=True).count(), "Textbook units still request duplicate AI generation"
    assert not page.get_by_text("整本词库的 AI 自然拼读助记", exact=True).count()
    page.get_by_role("button", name="开始学习 (18 词)").click(timeout=30000)
    for _ in range(18):
        page.get_by_role("button", name="点击查看课本单词助记").click(timeout=15000)
        page.get_by_text("课本词库", exact=True).wait_for(timeout=10000)
        if any(item.is_visible() for item in page.get_by_text("use", exact=True).all()):
            break
        page.get_by_role("button", name="下一个 (Enter)").click()
    else:
        raise AssertionError("The use card was not reached")
    assert page.get_by_text("/juːz/", exact=False).count(), "Verb pronunciation cue missing"
    assert not page.get_by_text("use a bat 是使用球拍。", exact=False).count()
    assert not page.get_by_role("button", name="🪄 一键生成 AI 拼读规则助记", exact=True).count(), "Duplicate mnemonic entrance remains"
    preview = Path(__file__).resolve().parents[1] / "outputs/mnemonics/use-card-preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    page.locator("div.bg-purple-50").screenshot(path=str(preview))
    before_recall = len(writes)
    page.get_by_role("button", name="收起线索，试着回忆", exact=True).click()
    recall = page.get_by_role("region", name="助记回忆练习")
    recall.wait_for()
    recall.screenshot(path=str(preview.parent / "recall-preview.png"))
    assert not any(item.is_visible() for item in page.get_by_text("use", exact=True).all()), "Spelling answer leaked"
    assert page.locator('[aria-label="国际音标"]').inner_text() == "/juːz/", "Spelling recall omits IPA"
    recall.get_by_role("textbox", name="回忆英文拼写").fill("uze")
    recall.get_by_role("textbox", name="回忆英文拼写").press("Enter")
    recall.get_by_text("use · 使用", exact=True).wait_for()
    assert recall.get_by_text("对照看看：哪些字母要补上或改一改？", exact=True).is_visible()
    recall.get_by_role("button", name="再试一次", exact=True).click()
    recall.get_by_role("textbox", name="回忆英文拼写").fill("use")
    recall.get_by_role("button", name="写好了，核对", exact=True).click()
    assert recall.get_by_text("拼写一致。过一会儿再试一次。", exact=True).is_visible()
    recall.get_by_role("button", name="看英文，读一读", exact=True).click()
    assert recall.get_by_text("use", exact=True).is_visible()
    assert not any(item.is_visible() for item in page.get_by_text("使用", exact=True).all()), "Meaning answer leaked"
    recall.get_by_role("button", name="读好了，核对", exact=True).click()
    assert recall.get_by_text("use · 使用", exact=True).is_visible()
    recall.get_by_role("button", name="返回助记线索", exact=True).click()
    assert len(writes) == before_recall, "Self-check changed learning records"
    assert not page.get_by_text("合上故事，依次回想：", exact=True).count()
    before_unit = len(writes)
    page.get_by_role("button", name="练本单元拼写（18 词）", exact=True).click()
    unit = page.get_by_role("region", name="单元拼写练习")
    assert unit.get_by_text("use", exact=True).is_visible()
    unit.screenshot(path=str(preview.parent / "unit-spelling-learn.png"))
    unit.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
    assert not any(item.is_visible() for item in page.get_by_text("use", exact=True).all()), "Unit spelling answer leaked"
    assert not unit.get_by_text("记住这些字母", exact=True).count(), "Letter cue leaked during recall"
    unit.screenshot(path=str(preview.parent / "unit-spelling-recall.png"))
    unit.get_by_role("textbox", name="回忆本词拼写").fill("uze")
    unit.get_by_role("textbox", name="回忆本词拼写").press("Enter")
    assert unit.get_by_text("z 改为 s", exact=True).is_visible()
    unit.get_by_role("button", name="收起答案，再写一次", exact=True).click()
    unit.get_by_role("textbox", name="回忆本词拼写").fill("use")
    unit.get_by_role("textbox", name="回忆本词拼写").press("Enter")
    assert unit.get_by_text("这次拼写正确。", exact=True).is_visible()
    unit.get_by_role("button", name="下一词", exact=True).click()
    assert unit.get_by_text("sorry", exact=True).is_visible()
    assert unit.get_by_text("so－rr－y", exact=False).count(), "Double-r spelling cue missing"
    unit.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
    unit.get_by_role("textbox", name="回忆本词拼写").fill("sory")
    unit.get_by_role("textbox", name="回忆本词拼写").press("Enter")
    assert unit.get_by_text("漏写 r", exact=True).is_visible()
    unit.screenshot(path=str(preview.parent / "unit-spelling-feedback.png"))
    unit.get_by_role("button", name="下一词", exact=True).click()
    assert unit.get_by_text("would", exact=True).is_visible()
    unit.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
    unit.get_by_role("textbox", name="回忆本词拼写").fill("woud")
    unit.get_by_role("textbox", name="回忆本词拼写").press("Enter")
    assert unit.get_by_text("漏写 l", exact=True).is_visible()
    unit.get_by_role("button", name="返回单词学习", exact=True).click()
    assert len(writes) == before_unit, "Unit self-check changed learning records"
    page.get_by_text("课本词情境阅读", exact=True).click()
    page.get_by_text("第 1 段", exact=True).click()
    assert page.locator("details details p").first.is_visible()
    page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
    page.get_by_role("button", name="闪卡复习 (18 词)", exact=True).click()
    flash_word = page.get_by_role("button", name="显示词义和助记", exact=True).locator("h3").inner_text()
    pack = json.loads((Path(__file__).resolve().parents[1] / "mnemonics/grade4.json").read_text())
    expected_hint = next(card["hint"] for card in pack["cards"] if card["section"] == "四上Unit 3" and card["word"] == flash_word)
    page.get_by_role("button", name="显示词义和助记", exact=True).click()
    assert page.get_by_text(expected_hint, exact=True).is_visible(), "Flashcard omits authored cue"
    page.get_by_role("button", name="返回 Unit 选择", exact=True).click()
    page.get_by_role("button", name="打印卡片 (18 词)", exact=True).click()
    use_print = page.locator(".print-card").filter(has=page.get_by_text("use", exact=True))
    assert use_print.count() == 1
    assert "/juːz/" in use_print.inner_text(), "Print does not use the same pronunciation cue"
    assert "use a bat 是使用球拍" not in use_print.inner_text()
    page.emulate_media(media="print")
    assert use_print.is_visible()
    page.emulate_media(media="screen")
    assert not errors, errors
    print("PASS: hidden full-word recall, use/sorry/would letter corrections, unified study/flashcards/print cues; APIs isolated and no self-check progress writes")
    browser.close()
