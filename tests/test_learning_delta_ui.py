"""Real browser + shipped HTML delta dependency: IndexedDB resume, bounded wire payload and receipts."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page()
 # Keep this transport/storage test isolated from live accounts and remote app dependencies.
 page.route('https://**/*',lambda route:route.fulfill(status=200,content_type='application/javascript',body=''))
 page.goto('http://127.0.0.1:8767/vocabulary_app.html',wait_until='load')
 page.wait_for_function('typeof VocabDeltaSync !== "undefined"')
 result=page.evaluate('''async()=>{
  const api=VocabDeltaSync.create(), id='reader_browser';
  const history=Array.from({length:10000},(_,n)=>({id:'old-'+n,wordId:'w',at:'2026-11-15T00:00:00Z',result:'correct'}));
  const state={version:1,currentUserId:id,users:{[id]:{id,name:'isolated',words:[{id:'w',english_word:'word',correctCount:10000}],studyEvents:history,rewardLedger:{},ignoredReadingWordIds:[]}}};
  api.seed('browser',{epoch:'e',revision:1,master:{appState:state}});
  const answer={id:'new-answer',wordId:'w',at:'2026-11-15T00:01:00Z',result:'correct',rewardPoints:10};
  state.users[id].studyEvents.push(answer);state.users[id].words[0].correctCount++;
  let bytes=0;
  const saved=await api.sync({accountId:'browser',appState:state,events:[answer],rpc:async(name,args)=>{
   if(name!=='sync_vocab_delta_v4'||args.p_changes.events.length!==1)throw Error('Full history upload');
   bytes=JSON.stringify(args).length;if(bytes>2000)throw Error('Growing payload');
   return {data:{full:false,epoch:'e',revision:2,words:state.users[id].words,events:[answer],profile:{},tombstones:[],acknowledgedEventIds:['new-answer'],hasMore:false}};
  }});
  const db=await new Promise((ok,no)=>{const r=indexedDB.open('isolated-v4-test',1);r.onupgradeneeded=()=>r.result.createObjectStore('cache');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});
  await new Promise((ok,no)=>{const tx=db.transaction('cache','readwrite');tx.objectStore('cache').put(saved,'canonical');tx.oncomplete=ok;tx.onabort=()=>no(tx.error)});db.close();
  return {bytes,events:saved.master.appState.users[id].studyEvents.length};
 }''')
 page.reload(wait_until='load');page.wait_for_function('typeof VocabDeltaSync !== "undefined"')
 restored=page.evaluate('''async()=>{
 const db=await new Promise(ok=>{const r=indexedDB.open('isolated-v4-test',1);r.onsuccess=()=>ok(r.result)});
 const saved=await new Promise(ok=>{const r=db.transaction('cache').objectStore('cache').get('canonical');r.onsuccess=()=>ok(r.result)});db.close();
 const api=VocabDeltaSync.create();api.seed('browser',saved);
 await api.read({accountId:'browser',rpc:async(name,args)=>{if(name!=='read_vocab_delta_v4'||args.p_after_revision!==2)throw Error('Reload requested full history');return {data:{full:false,epoch:'e',revision:2,words:[],events:[],profile:{},tombstones:[],acknowledgedEventIds:[],hasMore:false}}}});
 const user=api.snapshot('browser').master.appState.users.reader_browser;
 if(user.studyEvents.length!==10001||user.words[0].correctCount!==10001||user.rewardLedger['new-answer']!==10)throw Error('Reload lost answer/count/reward');return true;
 }''')
 assert result['bytes']<2000 and restored
 print('PASS: real HTML delta script, bounded upload, committed IndexedDB cache and reload delta cursor',result)
 browser.close()
