"""Actual IndexedDB transactions with fully unwritable localStorage, cross-tab and receipt checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'vocabulary_app.html').read_text()
source=html[html.index('const normalizeWordStats ='):html.index('const pickNewerData =')]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page();page.goto('http://127.0.0.1:8767/');page.add_script_tag(path=str(ROOT/'learning_delta_sync.js'))
 result=page.evaluate('''async source => {
  const disk=new Map();
  const storage={get length(){return disk.size},key:i=>[...disk.keys()][i]??null,getItem:k=>disk.get(k)??null,removeItem:k=>disk.delete(k),setItem(){throw new DOMException('Quota exceeded','QuotaExceededError')}};
  const factory=new Function('localStorage', `const STORAGE_KEY='vocabmaster_app_data',STORAGE_VERSION=1,READING_VOCAB_SECTION='阅读生词本',MISTAKE_EXIT_STREAK=3;
   const isHiddenGrade=()=>false,parseSectionMeta=s=>({grade:s});
   ${source}
   return {enqueueLearningEventDurable,readLearningOutbox,refreshLearningOverflow,syncLearningOutbox,loadFromBrowser};`);
  const a=factory(storage), b=factory(storage);
  disk.set('vocabmaster_old_recovery_backup','legacy-backup');
  disk.set('readingmaster_settings','keep-reader');
  await a.refreshLearningOverflow();
  if(disk.has('vocabmaster_old_recovery_backup') || disk.get('readingmaster_settings')!=='keep-reader')throw new Error('Migration scope or cleanup failed');
  const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('vocabmaster_learning_v1',1);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
  const migrated=await new Promise((resolve,reject)=>{const r=db.transaction('items').objectStore('items').get('vocabmaster_old_recovery_backup');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
  db.close();
  if(migrated?.raw!=='legacy-backup')throw new Error('Backup not preserved');
  const event=id=>({id,at:'2026-11-12T00:00:00Z',wordId:'plastic',result:'correct',rewardPoints:10,wordDefinition:{id:'plastic',english_word:'plastic',chinese_meaning:'塑料',section:'四上Unit 3',sourceContext:'People use a lot of plastic.'}});
  await a.enqueueLearningEventDurable('account',event('answer-a'));
  await b.enqueueLearningEventDurable('account',event('answer-b'));
  await b.enqueueLearningEventDurable('foreign',event('foreign-answer'));
  const user={id:'reader_account',words:[{id:'plastic',correctCount:0,incorrectCount:0}],studyEvents:[],rewardLedger:{}};
  const master={version:3,appState:{version:1,currentUserId:user.id,users:{[user.id]:user}}};
  let submitted, partialRejected=false;
  const envelope=(extra={})=>({full:false,epoch:'test-epoch',revision:1,words:[],events:[],profile:{},tombstones:[],acknowledgedEventIds:[],hasMore:false,...extra});
  const rpc=async(name,args)=>{
   if(name==='read_vocab_delta_v4')return {data:envelope({full:true,words:user.words,profile:{id:user.id}})};
   submitted=args.p_changes;
   await b.enqueueLearningEventDurable('account',event('during-request'));
   return {data:envelope({words:[{...user.words[0],correctCount:2}],events:args.p_changes.events,acknowledgedEventIds:['answer-a']})};
  };
  try{await a.syncLearningOutbox({accountId:'account',master,rpc})}catch(error){partialRejected=error.syncHealthCode==='receipt_invalid'}
  if(!partialRejected)throw new Error('Partial receipt reported success');
  await a.refreshLearningOverflow();
  const pending=a.readLearningOutbox('account').events.map(e=>e.id).sort();
  if(JSON.stringify(pending)!==JSON.stringify(['answer-a','answer-b','during-request']))throw new Error('Partial receipt lost IDs: '+pending);
  if(submitted.events.length!==2||submitted.events.some(e=>e.id==='during-request'))throw new Error('Cross-tab request boundary lost');
  const receipt=await a.syncLearningOutbox({accountId:'account',master,rpc:async(name,args)=>{
   if(name!=='sync_vocab_delta_v4')throw Error('Unexpected bootstrap');
   return {data:envelope({revision:2,words:[{...user.words[0],correctCount:3}],events:args.p_changes.events,acknowledgedEventIds:args.p_changes.events.map(e=>e.id)})};
  }});
  const c=factory(storage);await c.refreshLearningOverflow();
  if(c.readLearningOutbox('foreign').events.length!==1)throw new Error('Foreign answer lost');
  if(c.readLearningOutbox('account').events.length!==0)throw new Error('Confirmed records not retired');
  if(c.loadFromBrowser().users.reader_account.studyEvents.length!==3)throw new Error('Acknowledged snapshot not durably saved');
  const put=IDBObjectStore.prototype.put;
  IDBObjectStore.prototype.put=function(value){ if(value.key.endsWith(':aborted')){this.transaction.abort();throw new DOMException('Abort test','AbortError')}return put.call(this,value)};
  let rejected=false;try{await c.enqueueLearningEventDurable('account',event('aborted'))}catch{rejected=true}
  IDBObjectStore.prototype.put=put;
  await c.refreshLearningOverflow();
  if(!rejected||c.readLearningOutbox('account').events.some(e=>e.id==='aborted'))throw new Error('Aborted transaction reported success');
  return {localStorageWrites:'all rejected',submittedAnswers:2,pendingAfterPartialReceipt:pending,partialReceiptRejected:partialRejected,foreignPreserved:true,reloadSnapshotEvents:c.loadFromBrowser().users.reader_account.studyEvents.length,abortedWriteRejected:rejected,health:receipt.healthErrorCode};
 }''',source)
 print('PASS:',json.dumps(result,ensure_ascii=False))
 out=ROOT/'outputs/recovery/indexeddb-quota';out.mkdir(parents=True,exist_ok=True)
 (out/'database-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 browser.close()
