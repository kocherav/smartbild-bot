const {chromium}=require('playwright');const fs=require('fs');const assert=require('assert/strict');
(async()=>{
 const b=await chromium.launch({headless:true});const base='http://127.0.0.1:8097/deal-dashboard/';const fixture=JSON.parse(fs.readFileSync('/tmp/deal-dashboard-test-auth.json','utf8'));
 const admin=await b.newContext();const r=await admin.request.post(base+'api/auth/telegram',{headers:{Origin:'http://127.0.0.1:8097'},data:{initData:fixture.valid}});assert.equal(r.status(),200);const auth=await r.json();
 for(const [name,session,initData,expected,authCalls] of [
  ['restore with stale Telegram data',auth.token,'auth_date=1&hash=expired',true,0],
  ['new launch','',fixture.valid,true,1],
  ['expired session gets fresh Telegram login','expired-session',fixture.valid,true,1],
  ['stale data without session stays locked','','auth_date=1&hash=expired',false,1]
 ]){
   const context=await b.newContext();const page=await context.newPage();let calls=0;const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/auth/telegram'))calls++;});
   await context.route('https://telegram.org/js/telegram-web-app.js',route=>route.fulfill({contentType:'text/javascript',body:'window.Telegram={WebApp:{initData:'+JSON.stringify(initData)+',ready(){},expand(){}}};'}));
   if(process.env.DASHBOARD_APP_OVERRIDE)await context.route('**/app.js',route=>route.fulfill({path:process.env.DASHBOARD_APP_OVERRIDE,contentType:'text/javascript'}));
   if(session)await context.addInitScript(t=>sessionStorage.setItem('dashboard_session',t),session);
   await page.goto(base);
   if(expected){await page.waitForSelector('#app:not([hidden])');await page.reload();await page.waitForSelector('#app:not([hidden])');}
   else await page.waitForFunction(()=>document.querySelector('#auth-message').textContent.includes('Закройте окно'));
   assert.deepEqual(errors,[],name);assert.equal(calls,authCalls*(name.includes('expired session')?2:1),name);
   await context.close();
 }
 await b.close();console.log('PASS: repeated launch, stale initData with session, fresh login, expired session fallback, expired unauthenticated denial');
})().catch(e=>{console.error(e);process.exit(1)});
