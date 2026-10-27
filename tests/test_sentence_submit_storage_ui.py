"""Regression for an enabled sentence submit button silently failing at local-storage quota."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/recovery/submit-quota-fix'
OUT.mkdir(parents=True,exist_ok=True)
pack=json.loads((ROOT/'collocations.json').read_text())['words']
target=next(w for w in pack if w['english_word']=='Don’t worry.')
phrase=next(w for w in pack if w['english_word']=='in time')
cache=[dict(id=f'ket-fixture-{i}',source='ket',section='KETUnit 1',english_word=f'fixture{i}',chinese_meaning=f'释义{i}',learning_requirement='见到英文，能选出中文意思',recognition_choices=[{'key':f'{i}-{n}','text':f'{i}-{n}-'+'缓存释义'*90,'isCorrect':n==0} for n in range(4)],correctCount=7,incorrectCount=2,consecutiveCorrect=1,mistakeCleared=False) for i in range(30)]
original={'id':'original-answer','wordId':target['id'],'at':'2026-10-26T00:00:00Z','section':target['section'],'result':'correct','wordDefinition':target}
user={'id':'submit-test','name':'组句保存测试','words':[target,phrase,*cache],'selectedGrade':'四上固定搭配','selectedSections':[target['section']],'studyEvents':[original],'rewardLedger':{},'updatedAt':'2026-10-27T00:00:00Z'}
state={'version':1,'currentUserId':user['id'],'users':{user['id']:user}}
setup='''(() => {
 Math.random=()=>0.999;
 const original=Storage.prototype.setItem;
 original.call(localStorage,'vocabmaster_app_data',JSON.stringify(STATE));
 const bytes=()=>Object.keys(localStorage).reduce((n,k)=>n+(k.length+localStorage.getItem(k).length)*2,0);
 const quota=bytes()+32;
 window.blockWrites=BLOCK;
 window.quotaFailures=0;
 Storage.prototype.setItem=function(k,v){
  const old=this.getItem(k);
  if(this===localStorage && (window.blockWrites || bytes()-(old===null?0:(k.length+old.length)*2)+(k.length+v.length)*2>quota)){
   window.quotaFailures++;throw new DOMException('Storage quota exceeded','QuotaExceededError');
  }
  return original.call(this,k,v);
 };
})();'''
def run(browser,blocked):
 page=browser.new_page(viewport={'width':1000,'height':1100})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/api/**',lambda r:r.fulfill(status=404))
 page.route('**/collocations.json',lambda r:r.fulfill(json={'words':[target,phrase]}))
 page.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':cache}))
 page.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\n'))
 page.add_init_script(setup.replace('STATE',json.dumps(state,ensure_ascii=False)).replace('BLOCK',str(blocked).lower()))
 page.goto('http://127.0.0.1:8766/vocabulary_app.html',wait_until='networkidle')
 page.get_by_role('button',name='重点句式',exact=True).click()
 page.get_by_role('button',name='开始学习 (1 条)',exact=True).click()
 bank=page.get_by_label('备选词区',exact=True)
 for text in target['english_word'].split():bank.get_by_role('button',name=f'选入 {text}',exact=True).click()
 button=page.get_by_role('button',name='检查句子',exact=True)
 expect(button).to_be_enabled()
 button.click()
 if blocked:
  expect(page.get_by_role('alert')).to_contain_text('这次答题尚未保存')
  expect(button).to_be_enabled()
  assert page.get_by_role('button',name='下一个 (Enter)',exact=True).count()==0
  expect(page.get_by_test_id('reward-session')).to_have_text('+0')
  page.screenshot(path=str(OUT/'submit-storage-error-visible.png'),full_page=True)
  page.evaluate('window.blockWrites=false')
  button.click()
 expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_visible()
 expect(page.get_by_test_id('reward-session')).to_have_text('+10')
 assert page.get_by_role('alert').count()==0,'Successful retry clears the previous failure'
 page.wait_for_function("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['submit-test'].studyEvents.length===2")
 result=page.evaluate("JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['submit-test']")
 assert len(result['studyEvents'])==2 and result['studyEvents'][0]==original
 assert result['words'][0]['correctCount']==1
 for word in [w for w in result['words'] if w.get('source')=='ket']:
  assert word['correctCount']==7 and word['incorrectCount']==2
  assert 'recognition_choices' not in word,'Bundled choice copies should be rebuilt from the pack instead of consuming the progress cache'
 assert not errors,errors
 page.screenshot(path=str(OUT/('submit-retry-saved.png' if blocked else 'submit-quota-reclaimed.png')),full_page=True)
 page.reload(wait_until='networkidle')
 page.get_by_role('button',name='固定搭配',exact=True).click()
 page.get_by_role('button',name='开始学习 (1 条)',exact=True).click()
 for choice in phrase['recognition_choices']:
  expect(page.get_by_role('button',name=choice['text'],exact=True)).to_be_visible()
 page.close()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 run(browser,True)
 run(browser,False)
 browser.close()
 print('PASS: exact two-word screenshot case; submit failures visible next to button; no false points or success; cache reclaimed; retry saves exactly one answer and preserves original history and counters')
