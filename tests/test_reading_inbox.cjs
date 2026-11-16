const assert = require('node:assert/strict');
const {read} = require('../reading_inbox.js');
(async () => {
  const calls=[];
  const words=await read(async(name,args)=>{
    assert.equal(name,'read_reader_vocabulary_for_review_v1');calls.push(args);
    return {data:args.p_after ? {entries:[{word:'Table'}],hasMore:false} : {entries:[{word:'population'}],nextAfter:'population',hasMore:true}};
  });
  assert.deepEqual(words.map(w=>w.word),['population','Table']);
  assert.equal(calls[1].p_after,'population');assert.equal(calls[0].p_limit,50);
  await assert.rejects(read(async()=>({error:new Error('offline')})),/offline/);
  await assert.rejects(read(async()=>({data:{entries:[],hasMore:true,nextAfter:''}})),/分页/);
  let current=true;
  assert.equal(await read(async()=>{current=false;return {data:{entries:[{word:'other account'}]}}},()=>current),null);
  assert.equal(await read(()=>{throw Error('must not query')},()=>false),null);
  console.log('PASS: paged read, RPC errors, stalled cursor and account-switch cancellation; no write API');
})();
