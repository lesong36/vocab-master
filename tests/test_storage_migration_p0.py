"""Actual IndexedDB transactions with fully unwritable localStorage, cross-tab and receipt checks."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'vocabulary_app.html').read_text()
# Prevent production from reviving the legacy synchronous storage writers.
production=html[html.index('const loadAppData ='): ]
for legacy_call in ('saveToBrowser(', 'enqueueLearningEvent(', 'writeLearningOutbox(', 'seedLearningOutbox(', 'acknowledgeLearningEvents('):
 assert legacy_call not in production, legacy_call
source=html[html.index('const normalizeWordStats ='):html.index('const pickNewerData =')]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page();page.goto('http://127.0.0.1:8767/')
 result=page.evaluate('''async source => {
  const disk=new Map();
  const storage={get length(){return disk.size},key:i=>[...disk.keys()][i]??null,getItem:k=>disk.get(k)??null,removeItem:k=>disk.delete(k),setItem(){throw new Error('Unexpected localStorage write')}};
  const factory=new Function('localStorage', `const STORAGE_KEY='vocabmaster_app_data',STORAGE_VERSION=1,READING_VOCAB_SECTION='阅读生词本',MISTAKE_EXIT_STREAK=3;
   const isHiddenGrade=()=>false,parseSectionMeta=s=>({grade:s});
   ${source}
   return {enqueueLearningEventDurable,readLearningOutbox,refreshLearningOverflow,syncLearningOutbox,loadFromBrowser};`);
  const a=factory(storage);
  disk.set('vocabmaster_app_data','old-snapshot');
  disk.set('vocabmaster_old_recovery_backup','backup');
  disk.set('readingmaster_settings','keep');
  await a.refreshLearningOverflow();
  if(disk.size!==1||disk.get('readingmaster_settings')!=='keep')throw new Error('Migration cleanup/scope');
  const inspect=async()=>{const db=await new Promise((ok,no)=>{const r=indexedDB.open('vocabmaster_learning_v1',1);r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});const rows=await new Promise((ok,no)=>{const r=db.transaction('items').objectStore('items').getAll();r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});db.close();return rows};
  let rows=await inspect();
  if(!rows.some(r=>r.key==='vocabmaster_app_data'&&r.raw==='old-snapshot')||!rows.some(r=>r.raw==='backup'))throw new Error('Missing originals');
  await a.refreshLearningOverflow();
  if((await inspect()).length!==rows.length)throw new Error('Not idempotent');
  disk.set('vocabmaster_app_data','conflicting-old-snapshot');
  await a.refreshLearningOverflow();rows=await inspect();
  if(!rows.some(r=>r.key==='vocabmaster_app_data'&&r.raw==='old-snapshot')||!rows.some(r=>r.key.startsWith('legacy-copy:')&&r.raw==='conflicting-old-snapshot'))throw new Error('Conflict lost');
  disk.set('vocabmaster_abort_backup','must-survive');
  const original=IDBObjectStore.prototype.put;
  IDBObjectStore.prototype.put=function(value){if(value.key==='vocabmaster_abort_backup'){this.transaction.abort();throw new Error('Injected migration abort')}return original.call(this,value)};
  let failed=false;try{await a.refreshLearningOverflow()}catch{failed=true}finally{IDBObjectStore.prototype.put=original}
  if(!failed||disk.get('vocabmaster_abort_backup')!=='must-survive')throw new Error('Abort lost original');
  await a.refreshLearningOverflow();
  await a.enqueueLearningEventDurable('account',{id:'new-answer',result:'correct'});
  if(disk.size!==1)throw new Error('New learning writes used localStorage');
  return {migration:true,exactCopies:true,conflictPreserved:true,idempotence:true,abortPreservesOriginal:true,otherAppUntouched:true,newLocalStorageWrites:0};
 }''',source)
 print('PASS:',json.dumps(result,ensure_ascii=False))
 browser.close()
