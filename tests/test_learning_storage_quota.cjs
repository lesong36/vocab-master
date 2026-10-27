const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {randomUUID}=require('node:crypto');
const html=fs.readFileSync('vocabulary_app.html','utf8');
const source=html.slice(html.indexOf('const normalizeWordStats ='),html.indexOf('const loadFromBrowser ='));
const disk=new Map();
let quota=Infinity,writes=[];
const used=()=>[...disk].reduce((n,[k,v])=>n+(k.length+v.length)*2,0);
const localStorage={
 get length(){return disk.size;},key:i=>[...disk.keys()][i]??null,
 getItem:k=>disk.get(k)??null,removeItem:k=>disk.delete(k),
 setItem(k,v){
  const old=disk.has(k)?(k.length+disk.get(k).length)*2:0;
  if(used()-old+(k.length+v.length)*2>quota)throw Object.assign(new Error('Storage quota exceeded'),{name:'QuotaExceededError'});
  writes.push(k);disk.set(k,v);
 },
};
const api=vm.runInNewContext(source+'\n({seedLearningOutbox,readLearningOutbox,acknowledgeLearningEvents,enqueueLearningEvent})',{
 STORAGE_VERSION:1,READING_VOCAB_SECTION:'阅读生词本',MISTAKE_EXIT_STREAK:3,localStorage,crypto:{randomUUID},
 isHiddenGrade:()=>false,parseSectionMeta:s=>({grade:String(s).slice(0,2)}),
});
const key='vocabmaster_learning_outbox_v3:account';
const prefix=key+':event:';
const event=id=>({id,wordId:'word',at:'2026-10-27T00:00:00Z',result:'correct',section:'四上Unit 3',wordDefinition:{id:'word',exampleSentence:'Original learning context '.repeat(200)}});
const history=Array.from({length:600},(_,i)=>event(`old-${i}`));
const state={version:1,currentUserId:'reader_account',users:{reader_account:{id:'reader_account',words:[],studyEvents:history}}};
const rawSnapshot=JSON.stringify(state);
localStorage.setItem('vocabmaster_app_data',rawSnapshot);
quota=used();writes=[];
api.seedLearningOutbox('account',history,state);
assert.equal(writes.length,0,'Already-cloud-confirmed history must load even with zero free storage');
assert.equal(api.readLearningOutbox('account').events.length,0);
assert.equal(localStorage.getItem('vocabmaster_app_data'),rawSnapshot,'Never rewrite or truncate original learning history during bootstrap');
quota=used()+50000;
const localOnly=event('local-only');
api.seedLearningOutbox('account',[...history,localOnly],state);
assert.deepEqual(JSON.parse(JSON.stringify(api.readLearningOutbox('account').events.map(e=>e.id))),['local-only']);
assert.equal(writes.length,1,'Only a local-only event needs a new durable copy');
quota=used();writes=[];
api.seedLearningOutbox('account',[...history,localOnly],state);
assert.equal(writes.length,0,'Repeated account load cannot copy the same pending answer again');
// An acknowledgement must shrink legacy queue arrays directly, without first duplicating them as event keys.
quota=Infinity;disk.clear();
const confirmed=event('confirmed'),pending=event('pending'),concurrent=event('other-tab');
localStorage.setItem(key,JSON.stringify({version:3,epoch:'old',revision:0,events:[confirmed,pending]}));
localStorage.setItem(prefix+'other-tab',JSON.stringify(concurrent));
localStorage.setItem('vocabmaster_learning_outbox_v3:foreign:event:confirmed',JSON.stringify(confirmed));
quota=used();writes=[];
let remaining=api.acknowledgeLearningEvents('account',['confirmed'],{epoch:'new',revision:1});
assert.deepEqual(JSON.parse(JSON.stringify(remaining.events.map(e=>e.id).sort())),['other-tab','pending']);
assert.ok(!writes.includes(prefix+'confirmed')&&!writes.includes(prefix+'pending'),'Acknowledging never allocates duplicate legacy event keys');
assert.ok(localStorage.getItem('vocabmaster_learning_outbox_v3:foreign:event:confirmed'),'Other accounts are untouched');
assert.ok(used()<quota,'Cloud-confirmed duplicate storage is reclaimed');
// Old partial migrations can have copies in both forms; keep unknown and concurrent events.
quota=Infinity;api.enqueueLearningEvent('account',pending);quota=used();
remaining=api.acknowledgeLearningEvents('account',['pending'],{epoch:'new',revision:2});
assert.deepEqual(JSON.parse(JSON.stringify(remaining.events.map(e=>e.id))),['other-tab']);
assert.equal(localStorage.getItem(prefix+'pending'),null);
// A failed metadata write never removes an unconfirmed answer.
quota=used();
assert.throws(()=>api.acknowledgeLearningEvents('account',[],{epoch:'x'.repeat(10000),revision:3}),/quota/);
assert.deepEqual(JSON.parse(JSON.stringify(api.readLearningOutbox('account').events.map(e=>e.id))),['other-tab']);
quota=Infinity;disk.clear();
api.seedLearningOutbox('account',[event('shared-id')],{users:{reader_foreign:{studyEvents:[event('shared-id')]}}});
assert.equal(api.readLearningOutbox('account').events.length,1,'Only the signed-in account cloud history can confirm an event');
assert.ok(html.includes('seedLearningOutbox(accountId, accountUser?.studyEvents || [], remote)'), 'Real account bootstrap uses delta seeding');
console.log('PASS: full-quota cloud bootstrap, local-only delta migration, repeat-safe loads, legacy acknowledgement without duplication, concurrent/foreign pending preservation and failure retention');
