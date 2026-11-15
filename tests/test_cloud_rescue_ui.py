"""Both browser stores fail: real App cloud-only save, ambiguous retry, and refresh restoration."""
import json,copy
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/recovery/cloud-rescue';OUT.mkdir(parents=True,exist_ok=True)
choices=[{'key':str(i),'text':t,'isCorrect':i==0} for i,t in enumerate(['塑料','窗帘','子弹','年老的'])]
word={'id':'plastic','english_word':'plastic','chinese_meaning':'塑料','source':'reading','section':'阅读生词本','learning_requirement':'见到英文，能选出中文意思','sourceContext':'People use a lot of plastic.','sourceArticleTitle':'Unit 5 Straw No More','recognitionChoiceAudit':{'choices':choices}}
uid='reader_rescue-account'
profile={'id':uid,'name':'云端灾备测试','words':[word],'selectedSections':['阅读生词本'],'studyEvents':[],'rewardLedger':{}}
state={'version':1,'currentUserId':uid,'users':{uid:profile}}
source=(ROOT/'vocabulary_app.html').read_text().replace("import { createClient } from 'https://esm.sh/@supabase/supabase-js@2?bundle';",'const createClient = () => window.rescueClient;')
setup='''(() => {
 const seed=STATE;
 const put=Storage.prototype.setItem;
 if(!localStorage.getItem('vocabmaster_app_data'))put.call(localStorage,'vocabmaster_app_data',JSON.stringify(seed));
 Storage.prototype.setItem=function(k,v){if(this===localStorage)throw new DOMException('Quota exceeded','QuotaExceededError');return put.call(this,k,v)};
 indexedDB.open=()=>{throw new DOMException('Database full','QuotaExceededError')};
 const call=async(name,args)=>{const r=await fetch('https://fixture.invalid/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(args)});return r.json()};
 window.rescueClient={
 auth:{getSession:async()=>({data:{session:{user:{id:'rescue-account',email:'rescue@example.invalid'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},
 from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>{const r=await call('read',{});return {data:{vocabulary:[],vocab_master_progress:r.data.master},error:null}}})})}),rpc:call};
})();'''.replace('STATE',json.dumps(state,ensure_ascii=False))
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for mode in ['normal','lost-response','bad-receipt']:
  backend={'version':3,'appState':copy.deepcopy(state)};submitted_ids=[];lost=[False]
  context=browser.new_context(viewport={'width':1100,'height':1100},accept_downloads=True)
  def rpc(route):
   global backend
   name=route.request.url.rsplit('/',1)[-1];args=route.request.post_data_json
   if name=='report_vocab_sync_health_v1':data={'data':True,'error':None}
   elif name=='read':data={'data':{'master':backend,'epoch':'test-epoch','revision':1,'acknowledgedEventIds':[]},'error':None}
   elif name=='read_vocab_delta_v4':
    u=backend['appState']['users'][uid]
    data={'data':{'full':True,'epoch':'test-epoch','revision':1,'words':u['words'],'events':u['studyEvents'],'profile':{k:v for k,v in u.items() if k not in ['words','studyEvents']},'tombstones':[],'acknowledgedEventIds':[],'hasMore':False},'error':None}
   elif name=='sync_vocab_delta_v4':
    changes=args['p_changes'];u=backend['appState']['users'][uid]
    known={e['id']:e for e in u['studyEvents']}
    for e in changes['events']:
     submitted_ids.append(e['id'])
     if e['id'] not in known:
      known[e['id']]=copy.deepcopy(e)
      u['words'][0]['correctCount']=u['words'][0].get('correctCount',0)+(e['result']=='correct')
      u['words'][0]['incorrectCount']=u['words'][0].get('incorrectCount',0)+(e['result']=='incorrect')
      u.setdefault('rewardLedger',{})[e['id']]=e.get('rewardPoints',0)
    u['studyEvents']=list(known.values())
    if mode=='lost-response' and changes['events'] and not lost[0]:lost[0]=True;route.abort();return
    data={'data':{'full':False,'epoch':'test-epoch','revision':2,'words':u['words'],'events':[known[e['id']] for e in changes['events']],'profile':{},'tombstones':[],'acknowledgedEventIds':[] if mode=='bad-receipt' else [e['id'] for e in changes['events']],'hasMore':False},'error':None}
   else:raise AssertionError('Unexpected RPC '+name)
   route.fulfill(json=data,headers={'Access-Control-Allow-Origin':'*'})
  context.route('https://fixture.invalid/**',rpc)
  context.route('**/vocabulary_app.html?cloud-rescue',lambda r:r.fulfill(body=source,content_type='text/html'))
  context.route('**/api/**',lambda r:r.fulfill(status=404))
  context.route('**/collocations.json',lambda r:r.fulfill(json={'words':[]}))
  context.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
  context.route('**/%E8%AF%8D%E5%BA%93.md',lambda r:r.fulfill(body='id,section,english_word,chinese_meaning,learning_requirement,pos\n'))
  context.add_init_script(setup)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8767/vocabulary_app.html?cloud-rescue',wait_until='networkidle')
  page.get_by_role('button',name='开始学习 (1 词)',exact=True).click()
  page.get_by_role('button',name='塑料',exact=True).click()
  if mode in ['lost-response','bad-receipt']:
   expect(page.get_by_role('alert')).to_contain_text('云端也未能确认保存')
   expect(page.get_by_test_id('reward-session')).to_have_text('+0')
   expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_disabled()
   if mode=='lost-response':page.get_by_role('button',name='塑料',exact=True).click()
  if mode!='bad-receipt':
   expect(page.get_by_test_id('reward-session')).to_have_text('+10')
   expect(page.get_by_test_id('reward-total')).to_have_text('10')
   expect(page.get_by_role('button',name='下一个 (Enter)',exact=True)).to_be_enabled()
   if mode=='lost-response':assert len(submitted_ids)==2 and submitted_ids[0]==submitted_ids[1]
   page.screenshot(path=str(OUT/(mode+'-saved.png')),full_page=True)
   page.reload(wait_until='networkidle')
   with page.expect_download() as info:page.get_by_role('button',name='导出记录',exact=True).click()
   restored=json.loads(Path(info.value.path()).read_text())['appState']['users'][uid]
   assert len(restored['studyEvents'])==1 and restored['words'][0]['correctCount']==1
   assert sum(restored['rewardLedger'].values())==10
   (OUT/(mode+'-restored.json')).write_text(json.dumps(restored,ensure_ascii=False,indent=2))
  assert not errors,errors
  results.append({'mode':mode,'allBrowserStoresUnavailable':True,'submittedIds':submitted_ids,'cloudEventCount':len(backend['appState']['users'][uid]['studyEvents']),'passed':True})
  context.close()
 browser.close()
(OUT/'browser-evidence.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('PASS:',json.dumps(results,ensure_ascii=False))
