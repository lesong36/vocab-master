"""Full app account load and sync at a simulated browser quota; synthetic records only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/recovery/quota-fix'
OUT.mkdir(parents=True,exist_ok=True)
word={'id':'quota-word','section':'四上Unit 3','english_word':'help','chinese_meaning':'帮助','learning_requirement':'能理解并会用','correctCount':600,'incorrectCount':0,'consecutiveCorrect':600,'mistakeCleared':False}
def event(i):return {'id':f'fixture-{i}','at':'2026-10-27T00:00:00Z','wordId':word['id'],'section':word['section'],'result':'correct','wordDefinition':dict(word,exampleSentence='Original context. '*250)}
history=[event(i) for i in range(600)]
pending=event(600)
user={'id':'reader_quota-account','name':'quota@example.invalid','words':[word],'studyEvents':history,'selectedGrade':'四上','selectedSections':[],'rewardLedger':{},'updatedAt':'2026-10-27T00:00:00Z'}
remote={'version':1,'currentUserId':user['id'],'users':{user['id']:user}}
local=json.loads(json.dumps(remote))
local['users'][user['id']]['studyEvents'].append(pending)
local['users'][user['id']]['words'][0].update(correctCount=601,consecutiveCorrect=601)
metadata={'version':3,'epoch':None,'revision':0,'events':[history[0],pending]}
source=(ROOT/'vocabulary_app.html').read_text().replace("import { createClient } from 'https://esm.sh/@supabase/supabase-js@2?bundle';",'const createClient = () => window.quotaReaderClient;')
fixture={'local':local,'remote':remote,'metadata':metadata}
setup='''(() => {
 const fixture=FIXTURE;
 const key='vocabmaster_learning_outbox_v3:quota-account';
 const original=Storage.prototype.setItem;
 original.call(localStorage,'vocabmaster_app_data',JSON.stringify(fixture.local));
 original.call(localStorage,key,JSON.stringify(fixture.metadata));
 const bytes=()=>Object.keys(localStorage).reduce((n,k)=>n+(k.length+localStorage.getItem(k).length)*2,0);
 const quota=bytes()+32;
 window.quotaInitialIds=fixture.local.users['reader_quota-account'].studyEvents.map(e=>e.id);
 window.quotaWrites=[]; window.quotaReceipts=0;
 Storage.prototype.setItem=function(k,v){
  if(this===localStorage){
   const old=localStorage.getItem(k);
   if(bytes()-(old===null?0:(k.length+old.length)*2)+(k.length+v.length)*2>quota)throw new DOMException('Quota exceeded','QuotaExceededError');
   window.quotaWrites.push(k);
  }
  return original.call(this,k,v);
 };
 window.quotaReaderClient={
  auth:{getSession:async()=>({data:{session:{user:{id:'quota-account',email:'quota@example.invalid'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},
  from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>({data:{vocabulary:[],vocab_master_progress:{version:3,words:{},appState:fixture.remote}},error:null})})})}),
  rpc:async(name,args)=>{
   if(name==='report_vocab_sync_health_v1')return {data:true,error:null};
   if(name!=='sync_vocab_master_v3')throw new Error('Unexpected RPC '+name);
   window.quotaReceipts++;
   const master=structuredClone(args.p_master);
   return {data:{master,epoch:'fixture-epoch',revision:window.quotaReceipts,acknowledgedEventIds:master.appState.users['reader_quota-account'].studyEvents.map(e=>e.id)},error:null};
  }
 };
})();'''.replace('FIXTURE',json.dumps(fixture,ensure_ascii=False))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1100,'height':1000})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/vocabulary_app.html?quota-regression',lambda r:r.fulfill(body=source,content_type='text/html'))
 page.route('**/api/**',lambda r:r.fulfill(status=404))
 page.route('**/collocations.json',lambda r:r.fulfill(json={'words':[]}))
 page.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
 page.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\n'))
 page.add_init_script(setup)
 page.goto('http://127.0.0.1:8766/vocabulary_app.html?quota-regression',wait_until='networkidle')
 expect(page.get_by_text('学习档案已由云端确认保存。',exact=True)).to_be_visible(timeout=60000)
 result=page.evaluate('''() => {
  const profile=JSON.parse(localStorage.getItem('vocabmaster_app_data')).users['reader_quota-account'];
  const box=JSON.parse(localStorage.getItem('vocabmaster_learning_outbox_v3:quota-account'));
  return {ids:profile.studyEvents.map(e=>e.id),count:profile.words[0].correctCount,original:window.quotaInitialIds,events:box.events,writes:window.quotaWrites,receipts:window.quotaReceipts};
 }''')
 assert set(result['ids'])==set(result['original']) and len(result['ids'])==601
 assert result['count']==601
 assert result['events']==[]
 assert not any(':event:' in key for key in result['writes']), 'Cloud history never copied to individual event keys'
 assert result['receipts']>=1
 assert not errors,errors
 page.screenshot(path=str(OUT/'quota-sync-recovered.png'),full_page=True)
 browser.close()
 print('PASS: full App cloud login at quota, 600 historical plus 1 offline answer retained, legacy queue acknowledged without extra event copies, counters exact, healthy receipt shown')
