const {chromium}=require('playwright');
const fs=require('fs');const assert=require('assert/strict');
(async()=>{
 const b=await chromium.launch({headless:true});const ctx=await b.newContext({viewport:{width:1536,height:1100}});const page=await ctx.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base='http://127.0.0.1:8097/deal-dashboard/', origin='http://127.0.0.1:8097';
 const fixture=JSON.parse(fs.readFileSync('/tmp/deal-dashboard-test-auth.json','utf8'));
 let r=await ctx.request.post(base+'api/plans',{headers:{Origin:origin},data:{}});assert.equal(r.status(),401);
 r=await ctx.request.post(base+'api/auth/telegram',{headers:{Origin:origin},data:{initData:fixture.valid}});assert.equal(r.status(),200);const {token}=await r.json();
 const headers={Origin:origin,Authorization:'Bearer '+token};
 const post=async(path,data)=>ctx.request.post(base+'api/'+path,{headers,data});
 const snap=async()=>{const r=await ctx.request.get(base+'api/dashboard',{headers});assert.equal(r.status(),200);return r.json();};
 const before=await snap();assert.equal(before.installation_status,'ok');
 await page.goto(base);await page.evaluate(t=>sessionStorage.setItem('dashboard_session',t),token);await page.reload();await page.waitForSelector('#app:not([hidden])');
 await page.click('[data-preset="active"]');await page.click('[data-nav="objects"]');assert.ok(await page.locator('#objects-grid .object-card').count()>0);
 await page.fill('#search','861');await page.click('#objects-grid .object-card');await page.waitForSelector('#object-dialog[open]');
 await page.click('[data-object-tab="works"]');assert.match(await page.locator('#object-body').innerText(),/Монтаж · сделка № 861/);
 await page.click('[data-object-tab="links"]');await page.fill('#object-name','E2E · JetCar первый этаж');await page.fill('#link-search','853');await page.check('[data-link="853"]');await page.click('#object-form button[type=submit]');await page.waitForSelector('[data-object-tab="overview"].selected');
 assert.match(await page.locator('#object-content').innerText(),/2 связанных сделок/);
 let after=await snap();const object=after.objects.find(o=>o.name==='E2E · JetCar первый этаж');assert.deepEqual(object.deal_ids.sort(),['853','861']);assert.ok(!object.deal_ids.includes('894'));assert.deepEqual(after.deals,before.deals);
 // Two additional pilot objects: unknown address and a different client, kept separate.
 for(const did of ['802','869']){const d=after.deals.find(d=>d.id===did);r=await post('objects',{id:'pilot-'+did,revision:0,name:'E2E · '+d.client,address:d.address,deal_ids:[did]});assert.equal(r.status(),200);}
 r=await post('objects',{id:'conflict-pilot',revision:0,name:'Ошибочное объединение',address:'',deal_ids:['861']});assert.equal(r.status(),400);
 r=await post('objects',{id:object.id,revision:0,name:'Старая версия',address:'',deal_ids:['861']});assert.equal(r.status(),409);
 await page.click('[data-object-tab="plans"]');
 const createPlan=async(kind,title,date,amount)=>{await page.selectOption('#plan-kind',kind);await page.fill('#plan-title',title);await page.fill('#plan-due',date);if(amount)await page.fill('#plan-amount',amount);await page.fill('#plan-owner','Ответственный E2E');await page.selectOption('#plan-certainty','agreed');await page.fill('#plan-note','Подтверждено для теста; отдельная временная база');await page.click('#plan-form button[type=submit]');await page.waitForFunction(t=>[...document.querySelectorAll('[data-plan-edit]')].some(x=>x.textContent.includes(t)),title);};
 const day=new Date().toISOString().slice(0,10);const late=new Date(Date.now()-86400000).toISOString().slice(0,10);
 await createPlan('income','E2E аванс <img src=x onerror=alert(1)>',day,'12345,67');
 await createPlan('delivery','E2E поставка',late,null);
 assert.equal(await page.locator('#object-dialog img').count(),0);
 after=await snap();const plan=after.plans.find(p=>p.title.startsWith('E2E аванс'));assert.equal(plan.amount,1234567);
 r=await post('plans',{...plan,revision:0});assert.equal(r.status(),409);
 await page.locator('[data-plan-edit]').filter({hasText:'E2E поставка'}).click();await page.selectOption('#plan-status','cancelled');await page.click('#plan-form button[type=submit]');await page.waitForFunction(()=>document.querySelector('.plans-list')?.textContent.includes('Отменён'));
 // Dependencies are enforced on the server across linked deals.
 r=await post('tasks',{deal_id:'861',title:'E2E сначала спецификация',owner:'Анна',due:day,note:'',done:false});assert.equal(r.status(),200);const first=(await r.json()).task;
 r=await post('tasks',{deal_id:'853',title:'E2E затем монтаж',owner:'Иван',due:day,note:'',done:false,depends_on:first.id});assert.equal(r.status(),200);let second=(await r.json()).task;
 r=await post('tasks',{...second,done:true});assert.equal(r.status(),400);
 await page.click('[data-object-tab="history"]');await page.waitForSelector('.history-event');assert.match(await page.locator('#object-body').innerText(),/Срок оплаты/);
 await page.click('#close-object');await page.click('#refresh');await page.waitForFunction(()=>document.querySelector('#refresh').disabled===false);
 await page.fill('#search','');await page.click('[data-nav="actions"]');await page.waitForSelector('#actions-board');assert.match(await page.locator('#actions-board').innerText(),/E2E затем монтаж/);assert.equal(await page.locator('#actions-board').getByText('E2E поставка',{exact:true}).count(),0);assert.match(await page.locator('#actions-board').innerText(),/Ожидает задачу/);
 await page.screenshot({path:'dashboard/evidence/v2-test-actions.png',fullPage:true});
 await page.click('#save-view');await page.fill('#view-name','E2E · 2026 и действия');await page.click('#view-form button');await page.waitForFunction(()=>[...document.querySelector('#saved-view').options].some(o=>o.textContent==='E2E · 2026 и действия'));
 await page.reload();await page.waitForSelector('#app:not([hidden])');await page.selectOption('#saved-view',{label:'E2E · 2026 и действия'});assert.equal(await page.locator('#year').inputValue(),'2026');assert.equal(await page.locator('#actions-section').isVisible(),true);
 // Mobile layout, object form, actual installation projection and persistence.
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.click('[data-nav="objects"]');await page.fill('#search','861');await page.click('#objects-grid .object-card');assert.match(await page.locator('#object-content').innerText(),/2 связанных сделок/);
 await page.click('[data-object-tab="tasks"]');await page.locator('#object-dialog [data-task-edit]').filter({hasText:'Изменить'}).first().click();await page.waitForSelector('#deal-dialog[open]');assert.ok(await page.locator('#task-dependency').count());await page.click('#close-dialog');
 await page.click('[data-object-tab="plans"]');assert.equal(await page.evaluate(()=>document.querySelector('#object-dialog').scrollWidth>innerWidth),false);await page.screenshot({path:'dashboard/evidence/v2-test-mobile-plans.png'});
 await page.click('[data-object-tab="works"]');assert.ok(await page.locator('.work-row').count()>0);await page.screenshot({path:'dashboard/evidence/v2-test-mobile-works.png'});
 await page.click('#close-object');await page.setViewportSize({width:1536,height:1100});await page.click('#objects-grid .object-card');await page.screenshot({path:'dashboard/evidence/v2-test-object.png'});
 after=await snap();assert.deepEqual(after.deals,before.deals);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({ok:true,checks:['3 pilot objects','explicit membership and conflict','CRM money unchanged','plan cents and partial schema','agreed dates','cancellation queue','dependency blocking','history','saved views persisted','mobile forms','read-only installation'],pageErrors:errors}));await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
