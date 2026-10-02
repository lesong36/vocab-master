"""IPA and split-word browser regression; progress APIs are always mocked.

Run against a static server on port 8766. No real learning records are written.
"""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PREVIEWS = ROOT / "outputs/spelling-ipa"
PREVIEWS.mkdir(parents=True, exist_ok=True)
legacy_source = """id,section,english_word,chinese_meaning,learning_requirement,pos
279,三上Unit 1,hello/hi,你好（问候语）,能理解并会用,n.
343,三上Unit 3,a/an,一个,能理解并会用,n.
201,四上Unit 3,use,使用,能理解并会用,v.
202,四上Unit 3,sorry,抱歉的；难过的,能理解并会用,adj.
"""
words = [
    {"id": "279", "section": "三上Unit 1", "english_word": "hello/hi", "chinese_meaning": "你好", "correctCount": 7, "incorrectCount": 2, "flashcardKnown": True},
    {"id": "343", "section": "三上Unit 3", "english_word": "a/an", "chinese_meaning": "一个", "correctCount": 3},
    {"id": "201", "section": "四上Unit 3", "english_word": "use", "chinese_meaning": "使用", "learning_requirement": "能理解并会用", "pos": "v."},
    {"id": "202", "section": "四上Unit 3", "english_word": "sorry", "chinese_meaning": "抱歉的；难过的", "learning_requirement": "能理解并会用", "pos": "adj."},
]
state = {"version": 1, "currentUserId": "spelling-test", "users": {"spelling-test": {
    "id": "spelling-test", "name": "Isolated Test", "words": words,
    "selectedGrade": "四上", "selectedSections": ["四上Unit 3"], "studyEvents": [],
}}}


def setup(page, local_audio):
    page.route("**/api/health", lambda route: route.fulfill(json={"ok": True}) if local_audio else route.fulfill(status=404))
    page.route("**/api/vocab-data", lambda route: route.fulfill(json=state if route.request.method == "GET" else {"ok": True}))
    page.route("**/%E8%AF%8D%E5%BA%93.md", lambda route: route.fulfill(body=legacy_source))
    page.route("**/ket_vocab.json", lambda route: route.fulfill(json={"words": []}))
    page.route("**/api/pronunciation?*", lambda route: route.abort())
    page.add_init_script("Math.random = () => 0.5; localStorage.setItem('vocabmaster_app_data', " + json.dumps(json.dumps(state)) + ");")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for local_audio in (True, False):
        context = browser.new_context(viewport={"width": 1000, "height": 850})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        setup(page, local_audio)
        page.route("https://api.dictionaryapi.dev/**", lambda route: route.abort())
        page.goto("http://127.0.0.1:8766/vocabulary_app.html", wait_until="networkidle")
        page.wait_for_function("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['spelling-test'].words.length === 6")
        migrated = page.evaluate("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['spelling-test'].words")
        by_id = {word["id"]: word for word in migrated}
        assert by_id["279"]["english_word"] == "hello" and by_id["279"]["correctCount"] == 7
        assert by_id["279"]["flashcardKnown"] is True
        assert by_id["279:hi"]["english_word"] == "hi" and by_id["279:hi"]["correctCount"] == 0
        assert by_id["343"]["english_word"] == "a" and by_id["343:an"]["english_word"] == "an"

        page.get_by_role("button", name="开始学习 (2 词)", exact=True).click()
        ipa = page.locator('[aria-label="国际音标"]')
        expect(ipa).to_have_text("/juːz/")
        assert not any(item.is_visible() for item in page.get_by_text("use", exact=True).all()), "Main spelling answer leaked"
        page.screenshot(path=str(PREVIEWS / ("after-local.png" if local_audio else "after-online.png")), animations="disabled")
        page.get_by_role("button", name="点击查看课本单词助记").click()
        page.get_by_role("button", name="收起线索，试着回忆", exact=True).click()
        expect(ipa).to_have_text("/juːz/")
        assert not any(item.is_visible() for item in page.get_by_text("use", exact=True).all()), "Recall spelling answer leaked"
        page.get_by_role("button", name="返回助记线索", exact=True).click()
        page.get_by_role("button", name="练本单元拼写（2 词）", exact=True).click()
        expect(ipa).to_have_text("/juːz/")
        page.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
        expect(ipa).to_have_text("/juːz/")
        assert not any(item.is_visible() for item in page.get_by_text("use", exact=True).all()), "Unit spelling answer leaked"
        page.get_by_role("textbox", name="回忆本词拼写").fill("use")
        page.get_by_role("button", name="写好了，核对字母", exact=True).click()
        page.get_by_role("button", name="下一词", exact=True).click()
        expect(ipa).to_have_text("/ˈsɒri/")
        page.get_by_role("button", name="收起线索，写完整单词", exact=True).click()
        expect(ipa).to_have_text("/ˈsɒri/")
        page.screenshot(path=str(PREVIEWS / "unit-recall.png"), animations="disabled")
        assert not errors, errors
        context.close()

    # With no bundle, even local/automatic audio must still obtain dictionary IPA.
    # Complete an old request last to ensure it cannot replace the next word's IPA.
    context = browser.new_context()
    page = context.new_page()
    setup(page, True)
    page.route("**/phonetics.json", lambda route: route.fulfill(json={"entries": {}}))
    old_requests = []

    def dictionary(route):
        if route.request.url.endswith("/use"):
            old_requests.append(route)
        else:
            route.fulfill(json=[{"phonetic": "/ˈsɒri/", "phonetics": []}])

    page.route("https://api.dictionaryapi.dev/**", dictionary)
    page.goto("http://127.0.0.1:8766/vocabulary_app.html", wait_until="networkidle")
    page.get_by_role("button", name="开始学习 (2 词)", exact=True).click()
    expect(page.get_by_role("heading", name="使用", exact=True)).to_be_visible()
    page.get_by_role("button", name="不会 / 提示", exact=True).click()
    page.get_by_role("button", name="下一个 (Enter)", exact=True).click()
    expect(page.locator('[aria-label="国际音标"]')).to_have_text("/ˈsɒri/")
    assert old_requests, "Local audio skipped dictionary lookup"
    for route in old_requests:
        route.fulfill(json=[{"phonetic": "/juːz/", "phonetics": []}])
    page.wait_for_load_state("networkidle")
    expect(page.locator('[aria-label="国际音标"]')).to_have_text("/ˈsɒri/")
    context.close()
    browser.close()
    print("PASS: IPA in main/recall/unit spelling with offline dictionary, local/online audio, preserved split progress, and stale-response protection")
