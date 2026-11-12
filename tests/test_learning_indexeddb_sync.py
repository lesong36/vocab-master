"""Actual IndexedDB transactions with fully unwritable localStorage, cross-tab and receipt checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'vocabulary_app.html').read_text()
source=html[html.index('const normalizeWordStats ='):html.index('const pickNewerData =')]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page();page.goto('http://127.0.0.1:8767/')
 result=page.evaluate('''async source => {
  const disk=new Map();
  const storage={get length(){return disk.size},key:i=>[...disk.keys()][i]??null,getItem:k=>disk.get(k)??null,removeItem:k=>disk.delete(k),setItem(){throw new DOMException('Quota exceeded','QuotaExceededError')}};
  const factory=new Function('localStorage', `const STORAGE_KEY='vocabmaster_app_data',STORAGE_VERSION=1,READING_VOCAB_SECTION='阅读生词本',MISTAKE_EXIT_STREAK=3;
   const isHiddenGrade=()=>false,parseSectionMeta=s=>({grade:s});
   ${source}
   return {enqueueLearningEventDurable,readLearningOutbox,refreshLearningOverflow,syncLearningOutbox,loadFromBrowser};`);
  const a=factory(storage), b=factory(storage);
  const event=id=>({id,at:'2026-11-12T00:00:00Z',wordId:'plastic',result:'correct',rewardPoints:10,wordDefinition:{id:'plastic',english_word:'plastic',chinese_meaning:'塑料',section:'四上Unit 3',sourceContext:'People use a lot of plastic.'}});
  await a.enqueueLearningEventDurable('account',event('answer-a'));
  await b.enqueueLearningEventDurable('account',event('answer-b'));
  await b.enqueueLearningEventDurable('foreign',event('foreign-answer'));
  const user={id:'reader_account',words:[{id:'plastic',correctCount:0,incorrectCount:0}],studyEvents:[],rewardLedger:{}};
  const master={version:3,appState:{version:1,currentUserId:user.id,users:{[user.id]:user}}};
  let submitted;
  const receipt=await a.syncLearningOutbox({accountId:'account',master,rpc:async(_name,args)=>{
   submitted=args.p_master;
   await b.enqueueLearningEventDurable('account',event('during-request'));
   return {data:{master:args.p_master,epoch:'test-epoch',revision:1,acknowledgedEventIds:['answer-a']}};
  }});
  const pending=a.readLearningOutbox('account').events.map(e=>e.id).sort();
  if(JSON.stringify(pending)!==JSON.stringify(['answer-b','during-request']))throw new Error('Wrong remaining IDs: '+pending);
  if(submitted.appState.users.reader_account.words[0].correctCount!==2)throw new Error('Cross-tab answers not submitted');
  const c=factory(storage);await c.refreshLearningOverflow();
  if(c.readLearningOutbox('foreign').events.length!==1)throw new Error('Foreign answer lost');
  if(c.readLearningOutbox('account').events.length!==2)throw new Error('Reload lost pending records');
  if(c.loadFromBrowser().users.reader_account.studyEvents.length!==3)throw new Error('Acknowledged snapshot not durably saved');
  const put=IDBObjectStore.prototype.put;
  IDBObjectStore.prototype.put=function(value){ if(value.key.endsWith(':aborted')){this.transaction.abort();throw new DOMException('Abort test','AbortError')}return put.call(this,value)};
  let rejected=false;try{await c.enqueueLearningEventDurable('account',event('aborted'))}catch{rejected=true}
  IDBObjectStore.prototype.put=put;
  await c.refreshLearningOverflow();
  if(!rejected||c.readLearningOutbox('account').events.some(e=>e.id==='aborted'))throw new Error('Aborted transaction reported success');
  return {localStorageWrites:'all rejected',submittedAnswers:2,pendingAfterPartialReceipt:pending,foreignPreserved:true,reloadSnapshotEvents:c.loadFromBrowser().users.reader_account.studyEvents.length,abortedWriteRejected:rejected,health:receipt.healthErrorCode};
 }''',source)
 print('PASS:',json.dumps(result,ensure_ascii=False))
 out=ROOT/'outputs/recovery/indexeddb-quota';out.mkdir(parents=True,exist_ok=True)
 (out/'database-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 browser.close()
