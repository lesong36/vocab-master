"""Real App sentence drag/click exercise, with isolated learning data and controlled audio."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/collocations'
OUT.mkdir(parents=True,exist_ok=True)
names=['Can you help me, please?','I can’t find my ping-pong bat.','What do you do on this festival?','Could you come for dinner with my family tomorrow evening?',"I'd love to."]
pack=json.loads((ROOT/'collocations.json').read_text())['words']
words=[next(w for w in pack if w['english_word']==name) for name in names]
phrase=next(w for w in pack if w['english_word']=='get off')
words.append(phrase)
state={'version':1,'currentUserId':'sentence-test','users':{'sentence-test':{'id':'sentence-test','name':'组句测试','words':words,'selectedGrade':'四上固定搭配','selectedSections':list(dict.fromkeys(w['section'] for w in words)),'studyEvents':[]}}}
def saved(page):
 return page.evaluate("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['sentence-test']")
def snap(page,name):
 page.wait_for_timeout(400)
 page.screenshot(path=str(OUT/name),full_page=True)
def token(page,region,n):
 return page.get_by_label(region,exact=True).locator(f'[data-sentence-token="{n}"]')
def drag(page,source,target):
 source.scroll_into_view_if_needed()
 target.scroll_into_view_if_needed()
 a=source.bounding_box();b=target.bounding_box()
 page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2)
 page.mouse.down()
 page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=12)
 page.mouse.up()
def fill(page,word):
 bank=page.get_by_label('备选词区',exact=True)
 for text in word['english_word'].split():bank.get_by_role('button',name=f'选入 {text}',exact=True).first.click()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':390,'height':1100})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/api/**',lambda r:r.fulfill(status=404))
 page.route('**/collocations.json',lambda r:r.fulfill(json={'words':words}))
 page.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
 page.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\n'))
 page.route('https://api.dictionaryapi.dev/**',lambda r:r.abort())
 page.route('https://translate.google.com/**',lambda r:r.abort())
 page.add_init_script("Math.random=()=>0.999; window.spoken=[]; speechSynthesis.speak=u=>window.spoken.push(u.text); HTMLMediaElement.prototype.play=()=>Promise.reject(new Error('Test speech fallback')); if(!localStorage.getItem('vocabmaster_app_data'))localStorage.setItem('vocabmaster_app_data',"+json.dumps(json.dumps(state))+");")
 page.goto('http://127.0.0.1:8766/vocabulary_app.html',wait_until='networkidle')
 page.get_by_role('button',name='开始学习 (6 条)',exact=True).click()
 expect(page.get_by_role('region',name='中文组句练习')).to_be_visible()
 expect(page.get_by_text(words[0]['chinese_meaning'],exact=True)).to_be_visible()
 assert page.get_by_title('播放发音').count()==0
 assert page.get_by_text(words[0]['english_word'],exact=True).count()==0
 assert page.evaluate('window.spoken.length')==0
 expect(page.get_by_role('button',name='检查句子',exact=True)).to_be_disabled()
 snap(page,'sentence-builder-empty-mobile.png')
 # Mouse drag into the answer zone and insert before an existing chip.
 drag(page,token(page,'备选词区',4),page.get_by_label('句子答题区',exact=True))
 expect(token(page,'句子答题区',4)).to_be_visible()
 drag(page,token(page,'备选词区',0),token(page,'句子答题区',4))
 assert page.get_by_label('句子答题区',exact=True).locator('[data-sentence-token]').evaluate_all('els=>els.map(e=>e.dataset.sentenceToken)')==['0','4']
 for n in (1,2,3):token(page,'备选词区',n).click()
 page.get_by_role('button',name='检查句子',exact=True).click()
 expect(page.get_by_text('顺序还不对',exact=False)).to_be_visible()
 assert page.get_by_role('button',name='听例句',exact=True).count()==0
 page.keyboard.press('Enter')
 expect(page.get_by_text(words[0]['chinese_meaning'],exact=True)).to_be_visible()
 page.get_by_role('button',name='检查句子',exact=True).click()
 # Reorder selected chips by dragging token 4 to the final slot, then return it to bank.
 drag(page,token(page,'句子答题区',4),page.get_by_label('放到句末',exact=True))
 assert page.get_by_label('句子答题区',exact=True).locator('[data-sentence-token]').evaluate_all('els=>els.map(e=>e.dataset.sentenceToken)')==['0','1','2','3','4']
 drag(page,token(page,'句子答题区',4),page.get_by_label('备选词区',exact=True))
 expect(token(page,'备选词区',4)).to_be_visible()
 token(page,'备选词区',4).click()
 page.get_by_role('button',name='检查句子',exact=True).click()
 expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_visible()
 expect(page.get_by_test_id('reward-session')).to_have_text('+5')
 expect(page.get_by_role('button',name='听例句',exact=True)).to_be_visible()
 snap(page,'sentence-builder-correct-mobile.png')
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 # Hints count one error and reveal the target only on request.
 expect(page.get_by_text(words[1]['chinese_meaning'],exact=True)).to_be_visible()
 page.get_by_role('button',name='不会 / 看答案',exact=True).click()
 expect(page.get_by_text('参考答案',exact=True)).to_be_visible()
 assert page.get_by_role('button',name='检查句子',exact=True).count()==0
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 # Repeated words have independent chips; every token must be used once.
 fill(page,words[2])
 assert page.get_by_label('句子答题区',exact=True).get_by_role('button',name='放回 do',exact=True).count()==2
 page.get_by_role('button',name='检查句子',exact=True).click()
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 # Check long sentence layout and successful assembly on phone and desktop.
 for width in (320,390,1100):
  page.set_viewport_size({'width':width,'height':1100})
  if not page.evaluate('document.documentElement.scrollWidth <= innerWidth'):
   snap(page,f'sentence-builder-overflow-{width}.png')
   print(page.locator('body *').evaluate_all("els=>els.filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.className,e.textContent.slice(0,100)])"))
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 page.set_viewport_size({'width':390,'height':1100})
 snap(page,'sentence-builder-long-mobile.png')
 fill(page,words[3])
 page.get_by_role('button',name='检查句子',exact=True).click()
 page.set_viewport_size({'width':1100,'height':1100})
 snap(page,'sentence-builder-desktop.png')
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 # Pointer path used by touchscreens: dispatch touch pointer events with capture.
 page.set_viewport_size({'width':390,'height':1100})
 chip=token(page,'备选词区',0);zone=page.get_by_label('句子答题区',exact=True)
 chip.scroll_into_view_if_needed();zone.scroll_into_view_if_needed()
 a=chip.bounding_box();b=zone.bounding_box()
 client=page.context.new_cdp_session(page)
 client.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':a['x']+a['width']/2,'y':a['y']+a['height']/2}]})
 client.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':b['x']+b['width']/2,'y':b['y']+b['height']/2}]})
 client.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
 expect(token(page,'句子答题区',0)).to_be_visible()
 for n in (1,2):token(page,'备选词区',n).click()
 page.get_by_role('button',name='检查句子',exact=True).click()
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 # Ordinary collocations retain their existing meaning-choice interaction.
 expect(page.get_by_text('固定搭配 · 只认读',exact=True)).to_be_visible()
 page.get_by_role('button',name=phrase['chinese_meaning'],exact=True).click()
 page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
 expect(page.get_by_text('学习完成',exact=False)).to_be_visible()
 page.wait_for_function("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['sentence-test'].studyEvents.length===7")
 stats=saved(page)
 first=next(w for w in stats['words'] if w['id']==words[0]['id'])
 assert first['incorrectCount']==1 and first['correctCount']==1
 assert len(stats['studyEvents'])==7
 page.reload(wait_until='networkidle')
 assert len(saved(page)['studyEvents'])==7
 assert not errors,errors
 browser.close()
 print('PASS: real mouse and touch drag, insertion/reordering/return, repeated words, Chinese-only prompt, no answer audio leak, retry/hint counters and rewards, phrase regression, reload persistence and phone/desktop layouts')
