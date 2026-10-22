const {chromium}=require('playwright');const assert=require('assert/strict');
(async()=>{const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1440,height:1050}});const errors=[];p.on('pageerror',e=>errors.push(e.message));const base='http://127.0.0.1:8098/deal-dashboard/';
assert.equal((await p.request.get(base+'api/supplier-allocation')).status(),401);
await p.goto(base+'supplier-allocation');await p.evaluate(()=>sessionStorage.setItem('dashboard_session','fixture'));await p.reload();await p.locator('.invoice-button').filter({hasText:'TEST-ALLOC'}).click();await p.waitForSelector('#bulk-deal');
assert.match(await p.locator('#mode').innerText(),/черновик/);
await p.locator('#select-all').check();await p.selectOption('#bulk-deal','861');await p.click('#assign');await p.click('#preview');await p.waitForSelector('#financial-preview table');
assert.match(await p.locator('#financial-preview').innerText(),/12\s?751/);
await p.click('#save');await p.waitForFunction(()=>document.querySelector('#save-state').textContent.includes('общем реестре'));
await p.waitForSelector('#apply');
await p.reload();await p.locator('.invoice-button').filter({hasText:'TEST-ALLOC'}).click();await p.waitForSelector('#continue-allocation');await p.click('#continue-allocation');await p.waitForSelector('#apply');await p.waitForSelector('#preview');assert.equal(await p.locator('[data-line]').first().inputValue(),'861');
// Saved manual mapping must expose the exact missing fields and a working continuation.
const target=p.locator('[data-target]').first();const row=await target.locator('option').nth(1).getAttribute('value');await target.selectOption(row);
await p.click('#save');await p.waitForSelector('[data-fix-field="identity"]');await p.waitForSelector('#continue-allocation');
await p.locator('[data-fix-field="identity"]').first().click();assert.equal(await p.locator('[data-identity]').first().evaluate(e=>e===document.activeElement),true);
await p.locator('[data-identity]').first().check();await p.locator('[data-reason]').first().fill('Проверено по маркировке');await p.locator('[data-reason]').first().dispatchEvent('change');
// Return to automatic matching; do not manufacture a false material correspondence in the fixture.
await p.locator('[data-target]').first().selectOption('');
await p.locator('[data-qty]').first().fill('10000');await p.locator('[data-qty]').first().dispatchEvent('change');await p.click('#preview');await p.waitForFunction(()=>document.querySelector('#error').textContent.includes('больше'));
await p.locator('[data-qty]').first().fill('7');await p.locator('[data-qty]').first().dispatchEvent('change');await p.locator('[data-split]').first().click();await p.locator('[data-line]').nth(1).selectOption('894');await p.locator('[data-qty]').nth(1).fill('3');await p.locator('[data-qty]').nth(1).dispatchEvent('change');await p.click('#preview');await p.waitForSelector('#financial-preview table');assert.equal(await p.locator('#error').innerText(),'');
assert.match(await p.locator('.allocation-total').innerText(),/остаётся/);
await p.screenshot({path:'dashboard/evidence/allocation-desktop.png',fullPage:true});
await p.click('#save');await p.waitForFunction(()=>document.querySelector('#save-state').textContent.includes('общем реестре'));
await p.setViewportSize({width:390,height:844});await p.screenshot({path:'dashboard/evidence/allocation-mobile.png',fullPage:true});
const dims=await p.evaluate(()=>({w:document.documentElement.clientWidth,sw:document.documentElement.scrollWidth}));assert.ok(dims.sw<=dims.w+1,JSON.stringify(dims));
await p.waitForSelector('#apply');assert.match(await p.locator('#financial-preview').innerText(),/Дополнительный расход/);await p.click('#apply');await p.waitForSelector('#apply-status');assert.match(await p.locator('#apply-status').innerText(),/Ожидает обработки/);await p.reload();await p.locator('.invoice-button').filter({hasText:'TEST-ALLOC'}).click();await p.waitForSelector('#apply-status');assert.equal(await p.locator('#apply').count(),0);
assert.deepEqual(errors,[]);await b.close();console.log('PASS: authentication, bulk allocation, financial preview, persisted draft, excess quantity rejection, split, mobile layout; no production writes.');})().catch(e=>{console.error(e);process.exit(1)});
