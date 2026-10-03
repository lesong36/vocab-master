"""Whole-library spelling paths plus a varied-word real App exercise matrix."""
import csv
import io
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mnemonics'
OUTPUT.mkdir(parents=True, exist_ok=True)
cards = [c for g in (3, 4, 5) for c in json.loads((ROOT / f'mnemonics/grade{g}.json').read_text())['cards']]
source = (ROOT / 'vocabulary_app.html').read_text()
render = "createRoot(document.getElementById('root')).render(<App />);"
fixture = 'const SPELLING_CARDS = ' + json.dumps(cards, ensure_ascii=False) + ''';
createRoot(document.getElementById('root')).render(<main className="mx-auto max-w-xl p-4">
  {SPELLING_CARDS.map((card, index) => <article key={index} data-spelling-card={index} className="mb-6">
    <h2>{card.word}</h2><MnemonicDimensions card={card} />
  </article>)}
</main>);'''
# Data fixtures regroup representative actual cards into one isolated test unit.
# App and all study/recall/unit components remain unmodified.
names = ['purple', 'classroom', 'which', 'month', 'worried', 'beautiful', 'well-known', 'take care of', 'I', 'life (pl. lives)', 'Wednesday', 'knife', 'banana', 'take ... lesson', 'Water-Splashing Festival']
selected = [dict(next(c for c in cards if c['word'] == name), section='三下Unit 1') for name in names]
meanings = {row['english_word']: row['chinese_meaning'] for row in csv.DictReader((ROOT / '词库.md').open(encoding='utf-8-sig'))}
words = [dict(id=str(i+1), section='三下Unit 1', english_word=c['word'], chinese_meaning=meanings[c['word']],
              learning_requirement='能理解并会用', pos='n.', correctCount=0, incorrectCount=0,
              consecutiveCorrect=0, mistakeCleared=False) for i,c in enumerate(selected)]
state = {'version':1,'currentUserId':'library-spelling-test','users':{'library-spelling-test':{
    'id':'library-spelling-test','name':'Isolated full spelling test','words':words,'selectedGrade':'三下',
    'selectedSections':[],'studyEvents':[], 'createdAt':'2026-10-03T00:00:00Z','updatedAt':'2026-10-03T00:00:00Z'}}}
stream = io.StringIO()
writer = csv.DictWriter(stream, fieldnames=['id','section','english_word','chinese_meaning','learning_requirement','pos'])
writer.writeheader()
writer.writerows({k:word[k] for k in writer.fieldnames} for word in words)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    gallery = browser.new_page(viewport={'width':375,'height':1000})
    errors = []
    gallery.on('pageerror',lambda e:errors.append(str(e)))
    gallery.route('**/vocabulary_app.html?spelling-library',lambda route:route.fulfill(body=source.replace(render,fixture),content_type='text/html'))
    gallery.goto('http://127.0.0.1:8766/vocabulary_app.html?spelling-library',wait_until='networkidle')
    gallery.locator('[data-spelling-card]').last.wait_for(timeout=60000)
    assert gallery.get_by_role('figure',name='拼写字形路径').count() == 890
    assert '收起写' not in gallery.locator('body').inner_text()
    assert gallery.get_by_text('先看提示，再自己写', exact=True).count()==890
    failures = gallery.locator('[data-spelling-card]').evaluate_all('''articles => articles.flatMap(article => {
      const figure = article.querySelector('figure');
      const chunks = article.querySelector('[aria-label="字形分块"]');
      const word = article.querySelector('h2').textContent;
      return (!figure || (chunks && chunks.textContent !== word) || article.scrollWidth > article.clientWidth)
        ? [word] : [];
    })''')
    assert not failures, failures
    for width in (320,375,1040):
        gallery.set_viewport_size({'width':width,'height':1000})
        assert gallery.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for name in ('classroom','which','worried','take care of','well-known'):
        index = next(i for i,c in enumerate(cards) if c['word']==name)
        gallery.locator('[data-spelling-card]').nth(index).screenshot(path=str(OUTPUT / (name.replace(' ','-')+'-spelling-path.png')))
    assert not errors,errors

    page = browser.new_page(viewport={'width':375,'height':1100})
    page.route('**/api/health',lambda route:route.fulfill(json={'ok':True}))
    page.route('**/api/vocab-data',lambda route:route.fulfill(json=state if route.request.method=='GET' else {'ok':True}))
    page.route('**/%E8%AF%8D%E5%BA%93.md',lambda route:route.fulfill(body=stream.getvalue(),content_type='text/plain'))
    page.route('**/mnemonics/grade3.json',lambda route:route.fulfill(json={'cards':selected,'stories':[]}))
    for grade in (4,5):
        page.route(f'**/mnemonics/grade{grade}.json',lambda route:route.fulfill(json={'cards':[],'stories':[]}))
    page.add_init_script("localStorage.setItem('vocabmaster_app_data',"+json.dumps(json.dumps(state))+");")
    writes=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:writes.append(r.post_data) if r.method=='POST' and r.url.endswith('/api/vocab-data') else None)
    page.goto('http://127.0.0.1:8766/vocabulary_app.html',wait_until='networkidle')
    page.get_by_role('button',name=re.compile(r'^Unit 1\b')).click(timeout=30000)
    page.get_by_role('button',name=re.compile(r'^开始学习 \(')).click()
    tested=set()
    for _ in range(len(selected)):
        page.get_by_role('button',name='点击查看课本单词助记').click()
        page.get_by_role('figure',name='拼写字形路径').wait_for()
        page.wait_for_timeout(700)
        baseline=len(writes)
        saved=page.evaluate('localStorage.getItem("vocabmaster_app_data")')
        page.get_by_role('button',name=re.compile(r'^先补(关键字母|空格和标点)$')).click()
        recall=page.get_by_role('region',name='助记回忆练习')
        masked=recall.locator('[aria-label="关键字母缺口"]').inner_text()
        assert '_' in masked
        meaning=recall.locator('p.text-4xl').inner_text()
        current=next(w for w in words if ('上一节游泳课' if w['english_word']=='take ... lesson' else w['chinese_meaning'])==meaning)
        target=current['english_word']
        tested.add(target)
        if target=='classroom':
            recall.screenshot(path=str(OUTPUT / 'classroom-gap-practice.png'))
        assert target.lower() not in recall.inner_text().lower()
        assert not recall.locator('figure, mark').count()
        field=recall.get_by_role('textbox',name='回忆英文拼写')
        field.fill(target.lower() if target in ('I','Wednesday') else 'zzz')
        recall.get_by_role('button',name='写好了，核对',exact=True).click()
        assert recall.locator('li').count()>0
        if target=='Water-Splashing Festival':
            assert '漏写 -' in recall.inner_text()
            assert '空格' in recall.inner_text()
        if target in ('I','Wednesday'):
            assert '大写' in recall.inner_text()
        assert recall.get_by_role('figure',name='拼写字形路径').count()==1
        recall.get_by_role('button',name='不看提示，写完整词').click()
        assert not recall.locator('[aria-label="关键字母缺口"],figure,mark').count()
        assert target.lower() not in recall.inner_text().lower()
        assert field.input_value()==''
        field.fill('lives' if target=='life (pl. lives)' else 'take a swimming lesson' if target=='take ... lesson' else target)
        recall.get_by_role('button',name='写好了，核对',exact=True).click()
        assert '拼写一致' in recall.inner_text()
        recall.get_by_role('button',name='再试一次',exact=True).click()
        assert not recall.locator('figure,mark').count()
        page.wait_for_timeout(700)
        assert len(writes)==baseline
        assert page.evaluate('localStorage.getItem("vocabmaster_app_data")')==saved
        recall.get_by_role('button',name='返回助记线索').click()
        if len(tested)<len(selected):
            page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
    assert tested==set(names),tested
    page.get_by_role('button',name=re.compile(r'^练本单元拼写')).click()
    unit=page.get_by_role('region',name='单元拼写练习')
    while not unit.get_by_role('button',name='上一词',exact=True).is_disabled():
        unit.get_by_role('button',name='上一词',exact=True).click()
    unit_tested=set()
    for _ in range(len(selected)):
        meaning=unit.locator('h2').inner_text()
        current=next(w for w in words if ('上一节游泳课' if w['english_word']=='take ... lesson' else w['chinese_meaning'])==meaning)
        target=current['english_word']
        unit_tested.add(target)
        if target=='take ... lesson':
            assert '…' not in unit.locator('[aria-label="国际音标"]').inner_text()
            assert 'swɪm' in unit.locator('[aria-label="国际音标"]').inner_text()
        page.wait_for_timeout(700)
        baseline=len(writes)
        saved=page.evaluate('localStorage.getItem("vocabmaster_app_data")')
        unit.get_by_role('button',name=re.compile(r'^先补(关键字母|空格和标点)$')).click()
        assert '_' in unit.locator('[aria-label="关键字母缺口"]').inner_text()
        assert not unit.locator('figure,mark').count()
        field=unit.get_by_role('textbox',name='回忆本词拼写')
        field.fill('zzz')
        unit.get_by_role('button',name='写好了，核对字母').click()
        assert unit.locator('li').count()>0
        assert unit.get_by_role('figure',name='拼写字形路径').count()==1
        if target=='Wednesday':
            unit.screenshot(path=str(OUTPUT / 'wednesday-unit-spelling-feedback.png'))
        if target=='take ... lesson':
            assert unit.get_by_text('take a swimming lesson',exact=True).count()
        unit.get_by_role('button',name='隐藏答案，再写一次').click()
        assert not unit.locator('[aria-label="关键字母缺口"],figure,mark').count()
        field=unit.get_by_role('textbox',name='回忆本词拼写')
        assert field.input_value()==''
        field.fill('lives' if target=='life (pl. lives)' else 'take a swimming lesson' if target=='take ... lesson' else target)
        unit.get_by_role('button',name='写好了，核对字母').click()
        assert '这次拼写正确' in unit.inner_text()
        page.wait_for_timeout(700)
        assert len(writes)==baseline
        assert page.evaluate('localStorage.getItem("vocabmaster_app_data")')==saved
        if not unit.get_by_role('button',name='下一词',exact=True).is_disabled():
            unit.get_by_role('button',name='下一词',exact=True).click()
    assert unit_tested==set(names),unit_tested

    assert not errors,errors
    browser.close()
    print('PASS: all 890 default spelling paths at narrow widths; 15 diverse real App words in main and unit gap→wrong-letter feedback→no-hint spelling; no self-check learning writes')
