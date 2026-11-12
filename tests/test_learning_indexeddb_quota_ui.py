"""Real browser: totally unwritable localStorage; durable answer, reload recovery, both-store failure."""
import json, sys, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/recovery/indexeddb-quota'
OUT.mkdir(parents=True,exist_ok=True)
pack=json.loads((ROOT/'collocations.json').read_text())['words']
word=next(w for w in pack if w['english_word']=='Don’t worry.')
reading='--reading' in sys.argv
baseline='--baseline' in sys.argv
real_quota='--real-quota' in sys.argv
url='https://lesong36.github.io/vocab-master/vocabulary_app.html?release=idb-overflow-v1' if '--online' in sys.argv else 'http://127.0.0.1:8767/vocabulary_app.html'
if reading:
 choices=[{'key':str(i),'text':text,'isCorrect':i==0} for i,text in enumerate(['塑料','窗帘','从枪里射出的子弹','年老的'])]
 word={'id':'reading:plastic','english_word':'plastic','chinese_meaning':'塑料','source':'reading','section':'阅读生词本','learning_requirement':'见到英文，能选出中文意思','sourceContext':'People use a lot of plastic.','sourceArticleTitle':'Unit 5 Straw No More','recognitionChoiceAudit':{'choices':choices}}
user={'id':'overflow-test','name':'备用存储验证','words':[word],'selectedGrade':'阅读生词本' if reading else '四上固定搭配','selectedSections':[word['section']],'studyEvents':[],'rewardLedger':{}}
state={'version':1,'currentUserId':user['id'],'users':{user['id']:user}}
setup='''(() => {
 Math.random=()=>0.999;
 const original=Storage.prototype.setItem;
 if(!localStorage.getItem('vocabmaster_app_data')) original.call(localStorage,'vocabmaster_app_data',JSON.stringify(STATE));
 window.quotaFailures=0;
 if(REALQUOTA){
  let n=0;
  for(let length=32768;length>=1;length=Math.floor(length/2)){
   while(true){try{original.call(localStorage,'quota-fixture-'+n,'x'.repeat(length));n++;}catch{break}}
  }
 }

 Storage.prototype.setItem=function(k,v){
  if(this===localStorage && !REALQUOTA){window.quotaFailures++;throw new DOMException('Storage quota exceeded','QuotaExceededError');}
  if(this===localStorage){try{return original.call(this,k,v)}catch(error){window.quotaFailures++;throw error}}
  return original.call(this,k,v);
 };
 if(BLOCKSNAPSHOT){ const put=IDBObjectStore.prototype.put; IDBObjectStore.prototype.put=function(value){if(value.key==='vocabmaster_app_data'){this.transaction.abort();throw new DOMException('Snapshot write blocked','AbortError')}return put.call(this,value)}; }
 if(BLOCKDB) indexedDB.open=()=>{throw new DOMException('Database blocked','SecurityError')};
})();'''
def exported(page):
 with page.expect_download() as info:
  page.get_by_role('button',name='导出记录',exact=True).click()
 return json.loads(Path(info.value.path()).read_text())
def answer(page):
 if not reading: page.get_by_role('button',name='重点句式',exact=True).click()
 page.get_by_role('button',name='开始学习 (1 词)' if reading else '开始学习 (1 条)',exact=True).click()
 if reading:
  page.get_by_role('button',name='塑料',exact=True).click()
  return
 bank=page.get_by_label('备选词区',exact=True)
 for text in word['english_word'].split():bank.get_by_role('button',name=f'选入 {text}',exact=True).click()
 page.get_by_role('button',name='检查句子',exact=True).click()
evidence=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for blocked in ((False,) if baseline else (False,True,'snapshot')):
  context=browser.new_context(viewport={'width':1100,'height':1100},accept_downloads=True)
  page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  if baseline:
   old=subprocess.check_output(['git','show','9683e74:vocabulary_app.html'],cwd=ROOT).decode()
   page.route('**/vocabulary_app.html',lambda r:r.fulfill(body=old,content_type='text/html'))
  page.route('**/api/**',lambda r:r.fulfill(status=404))
  page.route('**/collocations.json',lambda r:r.fulfill(json={'words':[word]}))
  page.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
  page.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\n'))
  context.add_init_script(setup.replace('STATE',json.dumps(state,ensure_ascii=False)).replace('BLOCKDB',str(blocked is True).lower()).replace('BLOCKSNAPSHOT',str(blocked=='snapshot').lower()).replace('REALQUOTA',str(real_quota).lower()))
  page.goto(url,wait_until='networkidle')
  initial_storage=page.evaluate('({characters:Object.keys(localStorage).reduce((n,k)=>n+k.length+localStorage.getItem(k).length,0),keys:localStorage.length})')
  answer(page)
  if blocked is True or baseline:
   expect(page.get_by_role('alert')).to_contain_text('这次答题尚未保存')
   expect(page.get_by_test_id('reward-session')).to_have_text('+0')
   next_button=page.get_by_role('button',name='下一个 (Enter)',exact=True)
   if reading: expect(next_button).to_be_disabled()
   else: assert next_button.count()==0
   page.screenshot(path=str(OUT/(('baseline-' if baseline else 'both-stores-blocked-')+('reading' if reading else 'sentence')+'.png')),full_page=True)
   print('BASELINE REPRODUCED: previous release fails at full localStorage' if baseline else 'PASS: both stores blocked => visible failure, zero points, cannot advance')
  else:
   expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_visible()
   expect(page.get_by_test_id('reward-session')).to_have_text('+10')
   expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_enabled()
   assert page.evaluate('window.quotaFailures')>0
   page.screenshot(path=str(OUT/(('real-quota-' if real_quota else '')+('reading' if reading else 'sentence')+('-snapshot-failed' if blocked=='snapshot' else '')+'-saved.png')),full_page=True)
   page.get_by_role('button',name='下一个 (Enter)',exact=True).click()
   expect(page.get_by_text('学习完成！',exact=True)).to_be_visible()
   page.reload(wait_until='networkidle')
   # Export the restored profile through the actual UI, rather than reading memory internals.
   backup=exported(page)
   (OUT/('reading-restored-backup.json' if reading else 'sentence-restored-backup.json')).write_text(json.dumps(backup,ensure_ascii=False,indent=2))
   profile=backup['appState']['users']['overflow-test']
   assert len(profile['studyEvents'])==1
   assert profile['words'][0]['correctCount']==1
   assert sum(profile['rewardLedger'].values())==10
   assert profile['studyEvents'][0]['wordDefinition']['english_word']==word['english_word']
   print(f'PASS: localStorage fully blocked; snapshot failure={blocked=="snapshot"}; reload restores one event, exact counters and 10 points',flush=True)
   page.screenshot(path=str(OUT/'restored-after-reload.png'),full_page=True)
  evidence.append({'reading':reading,'baseline':baseline,'realQuota':real_quota,'url':url,'initialLocalStorage':initial_storage,'databaseBlocked':blocked is True,'snapshotWriteBlocked':blocked=='snapshot','saved':not (blocked is True or baseline),'quotaFailures':page.evaluate('window.quotaFailures'),'pageErrors':errors})
  assert not errors,errors
  context.close()
 browser.close()
 label=('online-' if '--online' in sys.argv else '')+('baseline-' if baseline else 'fixed-')+('reading' if reading else 'sentence')+('-real-quota' if real_quota else '')
 (OUT/(label+'.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 print('EVIDENCE',json.dumps(evidence,ensure_ascii=False))
