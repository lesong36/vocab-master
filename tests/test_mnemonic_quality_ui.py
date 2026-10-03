"""All 890 cards start with their actual spelling cue; empty modes stay absent."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'vocabulary_app.html').read_text()
cards=[c for g in (3,4,5) for c in json.loads((ROOT/f'mnemonics/grade{g}.json').read_text())['cards']]
fixture='''function LibraryReviewTest() {
 const [index,setIndex]=useState(null);
 useEffect(()=>{window.reviewOne=setIndex},[]);
 return <main className="mx-auto max-w-xl p-4">{(index === null ? CARDS : [CARDS[index]]).map(card => <article key={card.section+card.word} data-card={card.section+'|'+card.word}><h1>{card.word}</h1><MnemonicDimensions card={card}/></article>)}</main>;
}
createRoot(document.getElementById('root')).render(<LibraryReviewTest/>);'''.replace('CARDS',json.dumps(cards,ensure_ascii=False))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1040,'height':900});errors=[];writes=[]
 page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:writes.append(r.url) if r.method=='POST' else None)
 page.route('**/vocabulary_app.html?quality-review',lambda r:r.fulfill(body=source.replace("createRoot(document.getElementById('root')).render(<App />);",fixture),content_type='text/html'))
 page.goto('http://127.0.0.1:8766/vocabulary_app.html?quality-review',wait_until='networkidle')
 page.locator('article').last.wait_for(timeout=60000)
 assert page.locator('article').count()==890
 checks=page.locator('article').evaluate_all("""nodes=>nodes.map(n=>({key:n.dataset.card,active:[...n.querySelectorAll('button[aria-pressed=true]')].map(b=>b.textContent),figure:!!n.querySelector('figure'),text:n.textContent,buttons:[...n.querySelectorAll('button')].map(b=>b.textContent)}))""")
 for c,result in zip(cards,checks):
  assert result['key']==c['section']+'|'+c['word']
  assert result['active']==['拼写线索'],result['key']
  assert not result['figure'],result['key']
  assert c['hint'] in result['text'],result['key']
  assert ('词形组成' in result['buttons'])==(c['dimensions']['morphology']['kind']!='none'),result['key']
  assert ('词义区别' in result['buttons'])==bool(c['dimensions']['semantic']),result['key']
  assert '整体记' not in result['text'],result['key']
 for word in ('remember','free','blue'):
  index=next(i for i,c in enumerate(cards) if c['word']==word)
  page.evaluate('(i)=>window.reviewOne(i)',index)
  article=page.locator('article');assert article.count()==1
  if word=='free':
   article.get_by_role('button',name='词义图',exact=True).click();assert '¥0' in article.inner_text();assert '空闲' not in article.inner_text()
  page.set_viewport_size({'width':375,'height':900})
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  article.screenshot(path=str(ROOT/f'outputs/mnemonics/full-review-2026-10-03/{word}-review-mobile.png'))
 assert not errors,errors
 assert not writes,writes
 browser.close()
print('PASS: all 890 initial cues, omitted empty/redundant modes, corrected free sense and 375px layout; no data writes')
