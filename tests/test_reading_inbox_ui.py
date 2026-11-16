"""Isolated real UI: cloud inbox -> explicit selection -> partial import."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
uid='reader_inbox-test'
profile={'id':uid,'name':'审核测试','words':[],'studyEvents':[],'selectedSections':[]}
state={'version':1,'currentUserId':uid,'users':{uid:profile}}
source=(ROOT/'vocabulary_app.html').read_text().replace("import { createClient } from 'https://esm.sh/@supabase/supabase-js@2?bundle';",'const createClient = () => window.fixtureClient;')
setup='''localStorage.setItem('vocabmaster_app_data',JSON.stringify(STATE));
window.fixtureEntries=[{word:'population',meaning:'总体'},{word:'Table',meaning:'表格'}];
window.fixtureClient={auth:{getSession:async()=>({data:{session:{user:{id:'inbox-test'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})},
from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>({data:{preferences:{}}})})})}),
rpc:async(name,args)=>{
 if(name==='read_reader_vocabulary_for_review_v1')return {data:{entries:window.fixtureEntries,hasMore:false}};
 if(name==='report_vocab_sync_health_v1')return {data:true};
 if(name==='read_vocab_delta_v4')return {data:{full:true,epoch:'inbox',revision:1,words:[],events:[],profile:PROFILE,tombstones:[],hasMore:false,acknowledgedEventIds:[]}};
 if(name==='sync_vocab_delta_v4')return {data:{full:false,epoch:'inbox',revision:2,words:args.p_changes.words||[],events:[],profile:args.p_changes.profile||{},tombstones:[],hasMore:false,acknowledgedEventIds:[]}};
 throw Error('Unexpected RPC '+name);
}};'''.replace('STATE',json.dumps(state)).replace('PROFILE',json.dumps(profile))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 context=browser.new_context()
 context.route('**/vocabulary_app.html?inbox-test',lambda r:r.fulfill(body=source,content_type='text/html'))
 context.route('**/api/**',lambda r:r.fulfill(status=404))
 context.route('**/collocations.json',lambda r:r.fulfill(json={'words':[]}))
 context.route('**/ket_vocab.json',lambda r:r.fulfill(json={'words':[]}))
 context.add_init_script(setup)
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8767/vocabulary_app.html?inbox-test',wait_until='networkidle')
 page.get_by_role('button',name=re.compile('教师确认后导入')).click()
 expect(page.get_by_role('checkbox')).to_have_count(2)
 assert not any(page.get_by_role('checkbox').nth(i).is_checked() for i in range(2))
 expect(page.get_by_role('button',name='导入教师确认的 0 词',exact=True)).to_be_disabled()
 page.locator('label').filter(has_text='population').get_by_role('checkbox').check()
 # Focus refresh must preserve the user's explicit review selection.
 page.evaluate("fixtureEntries.push({word:'sample',meaning:'样本'}); window.dispatchEvent(new Event('focus'))")
 expect(page.locator('label').filter(has_text='population').get_by_role('checkbox')).to_be_checked()
 page.get_by_role('button',name='导入教师确认的 1 词',exact=True).click()
 page.get_by_role('button',name=re.compile('教师确认后导入')).click()
 expect(page.locator('label').filter(has_text='Table').get_by_role('checkbox')).not_to_be_checked()
 expect(page.locator('label').filter(has_text='sample').get_by_role('checkbox')).not_to_be_checked()
 assert not page.locator('label').filter(has_text='population').count()
 assert not errors,errors
 print('PASS: new cloud words reach review; unchecked by default; only selected population imported; Table remains unchecked; focus refresh preserves selection')
 browser.close()
