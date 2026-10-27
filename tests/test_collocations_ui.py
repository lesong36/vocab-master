"""Exercise the real bundled pack in an isolated browser profile, never live learning records."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/collocations'
OUT.mkdir(parents=True, exist_ok=True)
PACK = json.loads((ROOT / 'collocations.json').read_text())['words']
BY_EN = {(w['section'],w['english_word']):w for w in PACK}
TOTAL=len(PACK)
SECTIONS = list(dict.fromkeys(w['section'] for w in PACK))
legacy = dict(id='original',section='四上Unit 1',english_word='happy',chinese_meaning='开心的',learning_requirement='能理解并会用',correctCount=7)
seed = dict(PACK[0],correctCount=3,incorrectCount=1,consecutiveCorrect=1)
for field in ('learning_kind','exampleTranslation','lesson','provenance','pattern','usage','response','responseTranslation'):
    seed.pop(field,None)
seed['exampleSentence']='旧版例句'
seed['chinese_meaning']='旧版释义'
state = {'version':1,'currentUserId':'collocation-test','users':{'collocation-test':{'id':'collocation-test','name':'搭配试用','words':[legacy,seed],'selectedGrade':None,'selectedSections':[],'studyEvents':[]}}}
def saved(page):
    return page.evaluate("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['collocation-test']")
def no_spelling(page):
    assert page.get_by_placeholder('请输入英文拼写...').count()==0
    assert page.get_by_text('练本单元拼写',exact=False).count()==0
    assert page.get_by_text('AI 专属助记',exact=False).count()==0

def settle_screenshot(page,name):
    page.wait_for_timeout(500) # finish the existing fade-in animation
    page.screenshot(path=str(OUT / name),full_page=True)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':390,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/api/**',lambda r:r.fulfill(status=404))
    page.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
    page.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\noriginal,四上Unit 1,happy,开心的,能理解并会用,adj.'))
    page.route('https://api.dictionaryapi.dev/**',lambda r:r.abort())
    page.route('https://translate.google.com/**',lambda r:r.abort())
    page.add_init_script("if(!localStorage.getItem('vocabmaster_app_data'))localStorage.setItem('vocabmaster_app_data',"+json.dumps(json.dumps(state))+");")
    # Capture the exact phrase/sentence sent to the existing speech fallback.
    page.add_init_script("window.spoken=[]; speechSynthesis.speak = u => window.spoken.push(u.text); HTMLMediaElement.prototype.play = () => Promise.reject(new Error('Test speech fallback'));")
    page.goto('http://127.0.0.1:8766/vocabulary_app.html',wait_until='networkidle')
    page.get_by_role('button',name=re.compile('四上固定搭配')).wait_for(timeout=60000)
    initial=saved(page)
    assert len(initial['words'])==TOTAL+1
    assert next(w for w in initial['words'] if w['id']=='original')['correctCount']==7
    migrated=next(w for w in initial['words'] if w['id']==seed['id'])
    assert migrated['correctCount']==3
    assert migrated['exampleSentence']==PACK[0]['exampleSentence']
    assert migrated['learning_kind']==PACK[0]['learning_kind']
    assert migrated['exampleTranslation']==PACK[0]['exampleTranslation']
    page.get_by_role('button',name=re.compile('四上固定搭配')).click()
    for n in (1,2,3,5,6,7):
        page.get_by_role('button',name=re.compile(rf'^Unit {n}\b')).click()
    expect(page.get_by_text('固定搭配：听读、选中文意思。',exact=False)).to_be_visible()
    assert page.get_by_text('整本词库的 AI 自然拼读助记',exact=True).count()==0
    assert page.get_by_role('button',name=re.compile('生成本 Unit')).count()==0
    # Type tabs affect the real study/flashcard/print list while preserving Unit selection.
    for kind,label in [('sentence','重点句式'),('phrase','固定搭配')]:
        page.get_by_role('button',name=label,exact=True).click()
        expected=sum(w['learning_kind']==kind for w in PACK)
        expect(page.get_by_role('button',name=f'开始学习 ({expected} 条)',exact=True)).to_be_visible()
    page.get_by_role('button',name='全部',exact=True).click()
    settle_screenshot(page,'units-mobile.png')
    page.get_by_role('button',name=f'开始学习 ({TOTAL} 条)',exact=True).click()
    visited=[]
    sentence_captured=False
    for i in range(TOTAL):
        no_spelling(page)
        unit=re.search(r'四上固定搭配与重点句式Unit (\d+)',page.locator('main').inner_text())[1]
        if page.get_by_role('region',name='中文组句练习').count():
            zh=page.locator('main h3').inner_text()
            word=next(w for w in PACK if w['section']==f'四上固定搭配Unit {unit}' and w['learning_kind']=='sentence' and w['chinese_meaning']==zh)
            bank=page.get_by_label('备选词区',exact=True)
            for token in word['english_word'].split():
                bank.get_by_role('button',name=f'选入 {token}',exact=True).first.click()
            page.get_by_role('button',name='检查句子',exact=True).click()
        else:
            en=page.locator('main h3').inner_text()
            word=BY_EN[(f'四上固定搭配Unit {unit}',en)]
            for option in word['recognition_choices']:
                expect(page.get_by_role('button',name=option['text'],exact=True)).to_be_visible()
            if i==0:
                settle_screenshot(page,'study-mobile.png')
                page.get_by_title('播放发音',exact=True).click()
                page.wait_for_function('(target)=>window.spoken.includes(target)',arg=en)
            page.get_by_role('button',name=word['chinese_meaning'],exact=True).click()
        visited.append(word['id'])
        expect(page.get_by_role('button',name='听例句',exact=True)).to_be_visible()
        page.get_by_role('button',name='听例句',exact=True).click()
        page.wait_for_function('(target)=>window.spoken.includes(target)',arg=word['exampleSentence'])
        if i==0:
            settle_screenshot(page,'answered-mobile.png')
        if word['learning_kind']=='sentence':
            expect(page.get_by_role('region',name='搭配与句式用法')).to_be_visible()
            expect(page.get_by_role('region',name='搭配与句式用法').get_by_text(word['pattern'],exact=False)).to_be_visible()
            if word.get('response'):
                page.get_by_role('button',name='听答句',exact=True).click()
                page.wait_for_function('(target)=>window.spoken.includes(target)',arg=word['response'])
            if not sentence_captured:
                settle_screenshot(page,'sentence-mobile.png')
                sentence_captured=True
        if i==1:
            page.set_viewport_size({'width':1100,'height':1000})
            settle_screenshot(page,'answered-desktop.png')
            page.set_viewport_size({'width':390,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
    assert len(set(visited))==TOTAL
    expect(page.get_by_text('学习完成',exact=False)).to_be_visible()
    page.wait_for_function("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['collocation-test'].studyEvents.length === " + str(TOTAL))
    before=saved(page)
    assert sum(w.get('incorrectCount',0) for w in before['words'])==1 # seeded mistake; all current answers correct
    assert next(w for w in before['words'] if w['id']=='original')['correctCount']==7
    page.reload(wait_until='networkidle')
    expect(page.get_by_role('button',name=f'闪卡复习 ({TOTAL} 条)',exact=True)).to_be_visible()
    after=saved(page)
    assert len(after['words'])==TOTAL+1
    assert len(after['studyEvents'])==TOTAL
    assert {w['id']:(w.get('correctCount',0),w.get('incorrectCount',0)) for w in before['words']}=={w['id']:(w.get('correctCount',0),w.get('incorrectCount',0)) for w in after['words']}
    page.get_by_role('button',name=f'闪卡复习 ({TOTAL} 条)',exact=True).click()
    page.get_by_role('button',name='显示词义和助记',exact=True).click()
    expect(page.get_by_role('button',name='听例句',exact=True)).to_be_visible()
    expect(page.get_by_text('先读出英文，再说出中文意思。',exact=False)).to_be_visible()
    no_spelling(page)
    settle_screenshot(page,'flashcard-mobile.png')
    assert not errors,errors
    print(f'PASS: {TOTAL} real phrases/sentences, correct/incorrect answers, phrase/example speech requests, mobile/desktop layout, flashcards, reload persistence and existing progress preservation; zero JS errors')
    browser.close()
