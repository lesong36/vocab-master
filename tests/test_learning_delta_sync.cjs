const assert = require('node:assert/strict');
globalThis.crypto ||= require('node:crypto').webcrypto;
const {create}=require('../learning_delta_sync.js');
const copy=x=>JSON.parse(JSON.stringify(x));
const event=id=>({id,wordId:'w',at:'2026-11-15T00:00:00Z',result:'correct',rewardPoints:10});
const state=()=>({version:1,currentUserId:'reader_a',users:{reader_a:{id:'reader_a',name:'learner',words:[{id:'w',english_word:'word',correctCount:10000}],studyEvents:Array.from({length:10000},(_,n)=>event('old-'+n)),rewardLedger:{},ignoredReadingWordIds:[]}}});
const envelope=(extra={})=>({full:false,epoch:'epoch',revision:2,words:[],events:[],profile:{},tombstones:[],acknowledgedEventIds:[],hasMore:false,...extra});
const seeded=()=>{const api=create();api.seed('a',{epoch:'epoch',revision:1,master:{appState:state()}});return api};
(async()=>{
 const api=seeded(), local=state(), answer=event('new');local.users.reader_a.studyEvents.push(answer);local.users.reader_a.words[0].correctCount++;
 let outgoing;
 await api.sync({accountId:'a',appState:local,events:[answer],rpc:async(name,args)=>{assert.equal(name,'sync_vocab_delta_v4');outgoing=args;return {data:envelope({words:local.users.reader_a.words,events:[answer],acknowledgedEventIds:['new']})}}});
 assert.equal(outgoing.p_changes.events.length,1);assert.equal(outgoing.p_changes.words.length,1);assert.ok(JSON.stringify(outgoing).length<2000);assert.ok(!JSON.stringify(outgoing).includes('old-'));assert.ok(!('p_master'in outgoing));
 // Lost response: an already confirmed pending event must be transmitted for a fresh receipt.
 await api.sync({accountId:'a',appState:local,events:[answer],rpc:async(_name,args)=>{assert.equal(args.p_changes.events[0].id,'new');return {data:envelope({events:[answer],acknowledgedEventIds:['new']})}}});
 const resumed=create();assert.ok(resumed.seed('a',api.snapshot('a')));
 await resumed.read({accountId:'a',rpc:async(name,args)=>{assert.equal(name,'read_vocab_delta_v4');assert.equal(args.p_after_revision,2);return {data:envelope()}}});
 assert.equal(resumed.snapshot('a').master.appState.users.reader_a.studyEvents.length,10001);
 await resumed.read({accountId:'a',rpc:async()=>({data:envelope({revision:3,tombstones:['w']})})});assert.equal(resumed.snapshot('a').master.appState.users.reader_a.words.length,0);
 for(const mode of ['missing-ack','missing-event']){
  const bad=seeded();await assert.rejects(bad.sync({accountId:'a',appState:local,events:[answer],rpc:async()=>({data:envelope({events:mode==='missing-event'?[]:[answer],acknowledgedEventIds:mode==='missing-ack'?[]:['new']})})}),/确认/);
 }
 const conflict=seeded();let writes=0,reads=0,rebases=0;
 await conflict.sync({accountId:'a',appState:local,events:[answer],rebase:(_r,l)=>{rebases++;return l},rpc:async(name,args)=>{
  if(name==='read_vocab_delta_v4'){reads++;assert.equal(args.p_after_revision,1);return {data:envelope()}}
  writes++;if(writes===1)return {error:{details:'VMREVISION'}};
  assert.equal(args.p_expected_revision,2);return {data:envelope({revision:3,events:[answer],acknowledgedEventIds:['new']})};
 }});assert.equal(writes,2);assert.equal(reads,1);assert.equal(rebases,1);
 const epoch=seeded();let calls=0;await epoch.read({accountId:'a',rpc:async(_n,args)=>{calls++;if(calls===1)return {error:{details:'VMEPOCH'}};assert.equal(args.p_after_revision,null);return {data:envelope({full:true,epoch:'new-epoch',revision:0,words:[{id:'w'}],events:[]})}}});assert.equal(calls,2);
 // More than four bounded pull pages must drain and persist monotonically.
 const paged=seeded(), cursors=[], persisted=[];
 await paged.read({accountId:'a',onCache:async cache=>persisted.push(cache),rpc:async(_n,args)=>{
  cursors.push(args.p_after_revision);const revision=args.p_after_revision+1;
  return {data:envelope({revision,events:[event('page-'+revision)],hasMore:revision<7})};
 }});
 assert.deepEqual(cursors,[1,2,3,4,5,6]);assert.deepEqual(persisted.map(x=>x.revision),[2,3,4,5,6,7]);
 assert.equal(paged.snapshot('a').master.appState.users.reader_a.studyEvents.length,10006);
 const stalled=seeded();await assert.rejects(stalled.read({accountId:'a',rpc:async()=>({data:envelope({revision:1,hasMore:true})})}),/游标/);
 const many=seeded(), bulk=state(), freshEvents=Array.from({length:120},(_,n)=>event('batch-'+n));
 bulk.users.reader_a.studyEvents.push(...freshEvents);let revision=1;const batchSizes=[], allAcks=[];
 const manyResult=await many.sync({accountId:'a',appState:bulk,events:freshEvents,rpc:async(name,args)=>{
  assert.equal(name,'sync_vocab_delta_v4');batchSizes.push(args.p_changes.events.length);
  const ack=args.p_changes.events.map(e=>e.id);allAcks.push(...ack);
  return {data:envelope({revision:++revision,events:args.p_changes.events,acknowledgedEventIds:ack})};
 }});
 assert.deepEqual(batchSizes,[50,50,20]);assert.equal(new Set(manyResult.acknowledgedEventIds).size,120);
 assert.deepEqual(new Set(manyResult.acknowledgedEventIds),new Set(allAcks));
 assert.equal(many.snapshot('a').master.appState.users.reader_a.studyEvents.length,10120);
 const sized=seeded(), large=state();large.users.reader_a.words.push(...Array.from({length:5},(_,n)=>({id:'large-'+n,definition:'字'.repeat(14000)})));
 const byteSizes=[];
 await sized.sync({accountId:'a',appState:large,rpc:async(_n,args)=>{
  byteSizes.push(Buffer.byteLength(JSON.stringify(args.p_changes)));
  return {data:envelope({revision:++revision,words:args.p_changes.words})};
 }});
 assert.ok(byteSizes.length>=3);assert.ok(byteSizes.every(n=>n<=100*1024));
 const oversized=seeded(), giant=state();giant.users.reader_a.words.push({id:'giant',definition:'字'.repeat(40000)});let sent=0;
 await assert.rejects(oversized.sync({accountId:'a',appState:giant,rpc:async()=>{sent++;throw Error('must not send')}}),/大小限制/);
 assert.equal(sent,0,'Oversized item must fail before any request');
 console.log('PASS: 10000-event history -> bounded one-event upload; retry receipts, persistent cursor, tombstones, missing receipts, revision conflict and epoch reset');
})().catch(e=>{console.error(e);process.exitCode=1});
