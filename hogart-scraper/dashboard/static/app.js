'use strict';
const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const fmt = new Intl.NumberFormat('ru-RU', {maximumFractionDigits:0});
const money = (v, compact = true) => {
  if (v === null || v === undefined) return 'Нет данных';
  const r = v / 100, n = Math.abs(r);
  return compact && n >= 1e6 ? new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(r/1e6)+' млн ₽' : compact && n >= 1e4 ? new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(r/1000)+' тыс. ₽' : fmt.format(r)+' ₽';
};
const datefmt = v => {
  if(!v)return 'Не указана';
  let value=String(v);const ru=value.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if(ru)value=ru[3]+'-'+ru[2]+'-'+ru[1];
  const d=new Date(value.length===10?value+'T12:00:00':value);
  return Number.isFinite(d.getTime())?d.toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'}):'Дата не распознана';
};
const pct = (a,b) => b > 0 ? Math.max(0,Math.min(100,a/b*100)) : 0;
const sum = (rows,key) => rows.reduce((n,x)=>n+(x[key]||0),0);
let token = sessionStorage.getItem('dashboard_session') || '', data = null, activeDeal = null, detailTab = 'money', editTask = null;
let state = {nav:'overview', alert:'', stage:'', hideZero:'', week:'', limit:18};
const labels = {paid:'Есть поступления от клиентов',data:'Нужны данные',stale:'Без изменений 90+ дней',partial:'Частичная оплата',procurement:'Есть оплата, заказ не подтверждён',overpaid:'Оплата выше суммы сделки',delivery:'Получение подтверждено не полностью',unpaid:'Осталось получить',tasks:'Просрочены задачи'};
function toast(message) { $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('#toast').hidden=true,4200); }
async function api(path, body) {
  const headers = {}; if(token) headers.Authorization='Bearer '+token;
  if(body!==undefined) headers['Content-Type']='application/json';
  const res = await fetch('./api/'+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  const result = await res.json();
  if (!res.ok) {
    if(res.status===401){token='';sessionStorage.removeItem('dashboard_session');$('#app').hidden=true;$('#login').hidden=false;}
    throw new Error(result.error||'Не удалось загрузить данные');
  } return result;
}
async function authenticate(body, method) { const r=await api('auth/'+method,body); token=r.token;sessionStorage.setItem('dashboard_session',token); await refresh(); }
let requestedDeal=new URLSearchParams(location.search).get('deal_id');
function openRequestedDeal(){if(!requestedDeal)return;const id=requestedDeal;requestedDeal=null;if(data.deals.some(d=>String(d.id)===id))openDeal(data.deals.find(d=>String(d.id)===id).id);else toast('Сделка №'+id+' не найдена или недоступна');}
async function refresh() {
  $('#refresh').disabled=true;
  try { data=await api('dashboard');$('#login').hidden=true;$('#app').hidden=false;fillFilters();render();if(activeDeal)renderDeal();openRequestedDeal();return true; }
  catch(e){if(!data)$('#auth-message').textContent=e.message;else toast(e.message);return false;}
  finally{$('#refresh').disabled=false;}
}
function fillFilters(){
  const ds=data.deals.filter(d=>!d.is_purchase);
  const stages=[...new Map(ds.map(d=>[d.state_id,{name:d.state,program:d.program}])).entries()].sort((a,b)=>a[1].name.localeCompare(b[1].name,'ru'));
  $('#stage-filter').innerHTML='<option value="">Все стадии</option>'+stages.map(([id,v])=>`<option value="${esc(id)}">${esc(v.name)}${stages.filter(([,x])=>x.name===v.name).length>1?' · '+esc(v.program||id):''}</option>`).join('');
  if(state.stage&&!stages.some(([id])=>id===state.stage))state.stage='';
  for (const [id,values] of [['year',[...new Set(ds.map(d=>d.created_at.slice(0,4)).filter(Boolean))].sort().reverse()],['manager',[...new Set(ds.map(d=>d.manager))].sort()],['company',[...new Set(ds.map(d=>d.company))].sort()]]) {
    const el=$('#'+id), old=el.value;el.innerHTML=el.options[0].outerHTML+values.map(v=>`<option value="${esc(v)}">${id==='year'?'Созданы в '+esc(v):esc(v)}</option>`).join('');
    el.value=[...el.options].some(x=>x.value===old)?old:'all';
  }
}
const today = () => new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Moscow'});
const overdue = task => !task.done && task.due && task.due < today();
function tasksFor(did){return data.tasks.filter(t=>t.deal_id===did);}
function hasAlert(d,alert){return alert==='paid' ? d.received>0 : alert==='unpaid' ? d.outstanding>0 : alert==='tasks' ? tasksFor(d.id).some(overdue) : d.alerts.includes(alert);}
function filtered(){
  const q=$('#search').value.trim().toLocaleLowerCase('ru');
  return data.deals.filter(d=>!d.is_purchase && ($('#result').value==='all'||d.result===$('#result').value)
    && ($('#year').value==='all'||d.created_at.startsWith($('#year').value))
    && ($('#manager').value==='all'||d.manager===$('#manager').value)
    && ($('#company').value==='all'||d.company===$('#company').value)
    && (!q||[d.id,d.name,d.client,d.address].join(' ').toLocaleLowerCase('ru').includes(q))
    && (state.hideZero!=='1'||d.total!==0)
    && (!state.alert||hasAlert(d,state.alert))&&(!state.stage||d.state_id===state.stage)
    && (!state.week||d.payments.some(p=>p.date>=state.week&&p.date<addDays(state.week,7))));
}
function addDays(day,n){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
function clearExtraFilters(){
  ['manager','company'].forEach(id=>$('#'+id).value='all');$('#search').value='';
  state={...state,alert:'',stage:'',hideZero:'',week:'',limit:18};
}
function presetYear(result){
  clearExtraFilters();$('#year').value='2026';$('#result').value=result;state.nav='overview';render();
  window.scrollTo({top:0,behavior:'smooth'});
}
function renderScope(rows){
  const yearly=data.deals.filter(d=>!d.is_purchase&&d.created_at.startsWith('2026-'));
  const active=yearly.filter(d=>d.result==='active').length;
  const filteredExtra=!!(state.alert||state.stage||state.hideZero||state.week||$('#search').value.trim()||$('#manager').value!=='all'||$('#company').value!=='all');
  $('#scope-summary').innerHTML=`<div><strong>Сейчас в выборке: ${rows.length}</strong><span>${filteredExtra?'Список ограничен дополнительными фильтрами':'Количество по выбранным году и состоянию'}</span></div><div class="scope-buttons"><button data-preset="all">Все за 2026 год <b>${yearly.length}</b></button><button data-preset="active">В работе за 2026 год <b>${active}</b></button></div>`;
  $('#scope-summary').classList.toggle('restricted',filteredExtra);
}
function render(){
  $('#stage-filter').value=state.stage;$('#hide-zero').checked=state.hideZero==='1';
  const rows=filtered(), age=(Date.now()-new Date(data.synced_at))/60000;
  $('#sync-info').innerHTML=`<span><i class="live-dot"></i> Мегаплан · ${esc(new Date(data.synced_at).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))} МСК</span><span>Автообновление CRM каждые 10 минут</span><span>Выписки: ${(data.bank_status?.accounts||[]).map(a=>esc(a.company)+" по "+esc(datefmt(a.complete_through))).join(" · ")||"дата не подтверждена"}</span><span>Выбрано ${rows.length} из ${data.deals.filter(d=>!d.is_purchase).length} продаж</span>`;
  const stale=age>30||data.sync_status.ok===false;
  $('#banner').hidden=!stale;
  $('#banner').textContent='Показан последний успешный снимок. '+(data.sync_status.ok===false?'Последнее обновление CRM не удалось. ':'Данные старше 30 минут. ')+'Следующая попытка выполняется автоматически.';
  renderScope(rows);
  const chips=['result','year','manager','company'].filter(id=>$('#'+id).value!=='all').map(id=>`<button class="chip" data-clear-select="${id}">${esc($('#'+id).selectedOptions[0].textContent)} ×</button>`).join('')+($('#search').value.trim()?`<button class="chip" data-clear-select="search">Поиск: ${esc($('#search').value)} ×</button>`:'');
  $('#active-filters').innerHTML=chips+(state.hideZero==='1'?'<button class="chip" data-clear="hideZero">Скрыты сделки на 0 ₽ ×</button>':'')+(state.alert?`<button class="chip" data-clear="alert">${esc(labels[state.alert])} ×</button>`:'')+(state.stage?`<button class="chip" data-clear="stage">${esc(data.deals.find(d=>d.state_id===state.stage)?.state)} ×</button>`:'')+(state.week?`<button class="chip" data-clear="week">Платежи с ${esc(datefmt(state.week))} ×</button>`:'');
  $('#overview').hidden=state.nav!=='overview';$('#deals-section').hidden=!['overview','deals','procurement'].includes(state.nav);$('#tasks-section').hidden=state.nav!=='tasks';
  document.querySelectorAll('[data-nav]').forEach(el=>el.classList.toggle('active',el.dataset.nav===state.nav));
  renderKPIs(rows);renderCash(rows);renderDonut(rows);renderProc(rows);renderAttention(rows);renderStages(rows);renderCards(rows);renderTasks(rows);renderWorkspace(rows);
}
function renderKPIs(rows){
  const total=sum(rows,'total'), received=sum(rows,'received'), balance=sum(rows,'outstanding'), valid=rows.filter(d=>d.total>0&&d.payments_complete), amount=sum(valid,'total'), applied=valid.reduce((v,d)=>v+Math.max(0,Math.min(d.total,d.received)),0);
  const list=[['Выбрано сделок',String(rows.length),'Продажи · '+($('#result').value==='active'?'активные статусы':'выбранные состояния'),'◫','deals'],
    ['Сумма сделок',money(total),rows.filter(d=>d.total===null).length+' без рублёвой оценки','₽','amount'],
    ['Получено от клиентов',money(received),'По операциям CRM · за вычетом возвратов','↙','received'],
    ['Осталось получить',money(balance),rows.filter(d=>d.outstanding===null).length?'Не рассчитано для '+rows.filter(d=>d.outstanding===null).length+' сделок':'По стоимости сделок · не просрочка','◷','unpaid']];
  $('#kpis').innerHTML=list.map(([label,value,note,icon,action],i)=>`<button class="kpi" data-kpi="${action}"><div class="kpi-top">${label}<span class="kpi-icon">${icon}</span></div><div class="kpi-number">${esc(value)}</div><div class="kpi-note">${esc(note)}</div>${i===2?`<div class="mini-progress"><i style="width:${pct(applied,amount)}%"></i></div>`:''}</button>`).join('');
}
function renderCash(rows){
  const now=new Date(), day=now.toLocaleDateString('en-CA',{timeZone:'Europe/Moscow'}), weekday=(new Date(day+'T12:00:00Z').getUTCDay()+6)%7, monday=addDays(day,-weekday), count=Number($('#weeks').value);
  const weeks=Array.from({length:count},(_,i)=>({date:addDays(monday,(i-count+1)*7),income:0,expense:0}));
  rows.forEach(d=>d.payments.forEach(p=>{const w=weeks.find(w=>p.date>=w.date&&p.date<addDays(w.date,7));if(!w)return;
    if(p.category==='client')w.income+=p.amount;if(p.category==='client_refund')w.income-=p.amount;
    if(p.category==='supplier')w.expense+=p.amount;if(p.category==='supplier_refund')w.expense-=p.amount;}));
  const max=Math.max(100,...weeks.flatMap(w=>[w.income,w.expense])),min=Math.min(0,...weeks.flatMap(w=>[w.income,w.expense])),range=max-min;
  const width=680,height=220,left=48,top=18,bottom=184,plot=bottom-top,step=(width-left-14)/count;
  const y=v=>bottom-(v-min)/range*plot,zero=y(0);
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Поступления и оплаты поставщикам по неделям"><text x="0" y="10" fill="#8492a8" font-size="10">млн ₽</text>`;
  for(let i=0;i<4;i++){const v=min+range*i/3,yy=y(v);svg+=`<line x1="${left}" x2="${width}" y1="${yy}" y2="${yy}" stroke="#e9edf5"/><text x="${left-8}" y="${yy+4}" text-anchor="end" fill="#8c99ac" font-size="10">${(v/1e8).toLocaleString('ru-RU',{maximumFractionDigits:2})}</text>`;}
  weeks.forEach((w,i)=>{
    const x=left+i*step+step*.15,bw=step*.28;
    svg+=`<g class="chart-bar" tabindex="0" role="button" data-week="${w.date}" aria-label="Неделя ${esc(datefmt(w.date))}, от клиентов ${esc(money(w.income,false))}, поставщикам ${esc(money(w.expense,false))}"><title>${esc(datefmt(w.date))}: поступления ${esc(money(w.income,false))}, поставщикам ${esc(money(w.expense,false))}</title><rect x="${x-6}" y="${top}" width="${step*.86}" height="${plot+24}" fill="${state.week===w.date?'#eff2ff':'transparent'}" rx="5"/>`;
    [w.income,w.expense].forEach((v,j)=>svg+=`<rect x="${x+j*(bw+4)}" y="${Math.min(zero,y(v))}" width="${bw}" height="${Math.max(v===0?0:2,Math.abs(y(v)-zero))}" fill="${j?'#5167f6':'#13b5aa'}" rx="3"/>`);
    const dt=new Date(w.date+'T12:00:00Z');svg+=`<text x="${x+bw}" y="${bottom+23}" text-anchor="middle" fill="#7b8ca3" font-size="10">${dt.toLocaleDateString('ru-RU',{day:'numeric',month:'short'}).replace('.','')}</text></g>`;
  });svg+='</svg>';
  if(!weeks.some(w=>w.income||w.expense))svg+='<div class="micro">В выбранном периоде нет учтённых платежей по этим сделкам.</div>';
  $('#cash-chart').innerHTML=svg;
}
function renderDonut(rows){
  const valid=rows.filter(d=>d.total>0&&d.payments_complete),total=sum(valid,'total'),paid=valid.reduce((s,d)=>s+Math.max(0,Math.min(d.total,d.received)),0),rate=pct(paid,total),circ=2*Math.PI*72;
  $('#payment-chart').innerHTML=`<div class="donut"><svg viewBox="0 0 180 180" aria-label="Оплачено ${Math.round(rate)} процентов"><circle cx="90" cy="90" r="72" fill="none" stroke="#aeb9fb" stroke-width="22"/><circle cx="90" cy="90" r="72" fill="none" stroke="#13b5aa" stroke-width="22" stroke-dasharray="${circ*rate/100} ${circ}"/></svg><div class="donut-center"><strong>${total?Math.round(rate)+'%':'—'}</strong><span>покрыто оплатой</span></div></div><div class="donut-legend"><div><span class="donut-label"><i class="dot teal"></i>В пределах стоимости</span><b>${money(paid)}</b></div><div><span class="donut-label"><i class="dot lavender"></i>Осталось</span><b>${money(total-paid)}</b></div><p class="micro">По ${valid.length} сделкам с рублёвой стоимостью и полным списком операций. Переплаты: ${money(sum(rows,'overpaid'))}.</p></div>`;
}
function procurementCoverage(items,key){const rows=items.filter(x=>x.qty>0);if(!rows.length||(key==='ordered_qty'&&!rows.some(x=>x.ordered_qty!==null)))return null;return rows.reduce((sum,x)=>sum+Math.min(1,Math.max(0,(x[key]||0)/x.qty)),0)/rows.length*100;}
function renderProc(rows){
  const known=rows.filter(d=>d.procurement_known),items=known.flatMap(d=>d.items).filter(x=>x.qty>0),n=items.length;
  const coverage=key=>procurementCoverage(items,key);
  $('#proc-coverage').textContent=known.length+' из '+rows.length+' сделок';
  $('#proc-chart').innerHTML=[['Покрыто счетами поставщиков','invoice_qty'],['Заказ через Хогарт подтверждён','ordered_qty'],['Подтверждено получение','received_qty']].map(([label,key])=>`<div class="proc-line"><div class="proc-label"><span>${label}</span><b>${coverage(key)===null?'Нет данных':fmt.format(coverage(key))+'%'}</b></div><div class="progress-track"><i style="width:${coverage(key)||0}%"></i></div></div>`).join('')+`<p class="micro">${n} позиций · средняя доля количества по каждой позиции. Первый показатель учитывает распределённые количества из счетов всех поставщиков. Заказ через Хогарт — отдельный источник; отсутствие данных о нём не означает отсутствие закупок. Получение подтверждается отдельно.</p><p class="micro">Оплачено поставщикам по операциям CRM: <b>${money(sum(rows,'spent'))}</b>. Полнота закупочной потребности требует проверки.</p>`;
}
function renderAttention(rows){
  const choices=[['tasks','Просрочены задачи чеклистов','red','!'],['procurement','Есть оплата, заказ не подтверждён','','◇'],['partial','Частичная оплата клиента','','◷'],['stale','Нет изменений 90+ дней','blue','↻'],['data','Нужны данные для полной картины','blue','i'],['overpaid','Оплата выше стоимости сделки','red','!']];
  $('#attention').innerHTML=choices.map(([key,label,color,icon])=>{const count=rows.filter(d=>hasAlert(d,key)).length;return count?`<button class="attention-row" data-alert="${key}"><span class="attention-icon ${color}">${icon}</span><b>${count}</b><span class="label">${label}</span><span class="arrow">›</span></button>`:'';}).join('')||'<p class="micro">По доступным данным сигналов нет. Это не подтверждает полноту всех данных.</p>';
}
function renderStages(rows){
  const groups={};rows.forEach(d=>{groups[d.state_id]??={name:d.state,count:0};groups[d.state_id].count++;});
  const entries=Object.entries(groups).sort((a,b)=>b[1].count-a[1].count),max=Math.max(1,...entries.map(x=>x[1].count));
  $('#stage-chart').innerHTML=entries.map(([id,v])=>`<button class="stage ${state.stage===id?'selected':''}" data-stage="${id}"><span class="stage-name">${esc(v.name)}</span><strong>${v.count}</strong><div class="mini-progress"><i style="width:${v.count/max*100}%;background:#7889f7"></i></div></button>`).join('')||'<span class="micro">Нет сделок в выборке</span>';
}
function nextAction(d){
  const ts=tasksFor(d.id).filter(t=>!t.done).sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999'));
  if(ts.length)return {text:(ts[0].due?datefmt(ts[0].due)+' · ':'')+ts[0].title,cls:overdue(ts[0])?'danger':'warn'};
  if(d.alerts.includes('overpaid'))return{text:'Сверить оплату и стоимость сделки',cls:'warn'};
  if(d.total===0)return{text:'Уточнить стоимость сделки',cls:'warn'};
  if(!d.procurement_known)return{text:'Уточнить закупочную спецификацию',cls:''};
  if(d.alerts.includes('procurement'))return{text:'Проверить подтверждение заказа',cls:'warn'};
  return{text:'Добавить следующее действие в чеклист',cls:''};
}
function shipmentBar(d){const p=d.shipment_progress,known=p?.known===true,percent=p?.percent;const label=!known?'Нет данных':percent==null?'—':new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(percent)+'%';const width=known&&percent!=null?Math.max(0,Math.min(100,percent)):0;return `<div class="deal-progress shipment-progress" title="${esc(known?'Подтверждена передача товаров и работ на '+money(p.amount_cents)+' из '+money(d.total):'Реестр передач временно недоступен')}"><span>Отгружено</span><div class="mini-progress" role="progressbar" aria-label="Отгружено по стоимости сделки" aria-valuemin="0" aria-valuemax="100" ${percent!=null&&known?`aria-valuenow="${width}"`:''}><i style="width:${width}%;background:var(--teal)"></i></div><span>${esc(label)}</span></div>`;}
function renderCards(rows){
  let list=[...rows]; const sort=$('#sort').value;
  if(sort==='amount')list.sort((a,b)=>(b.total||0)-(a.total||0));if(sort==='balance')list.sort((a,b)=>(b.outstanding||0)-(a.outstanding||0));if(sort==='attention')list.sort((a,b)=>tasksFor(b.id).filter(overdue).length-tasksFor(a.id).filter(overdue).length||b.alerts.length-a.alerts.length);
  $('#list-title').textContent=state.nav==='procurement'?'Закупки по сделкам':$('#result').value==='active'?'Сделки в работе':'Сделки';
  $('#list-subtitle').textContent=`Показано карточек: ${Math.min(state.limit,list.length)} из ${list.length}.`+(list.length>state.limit?' Остальные — кнопкой «Показать все» или «Показать ещё».':' Все найденные сделки в списке ниже.');
  $('#show-all').hidden=list.length<=state.limit;$('#show-all').textContent=`Показать все ${list.length}`;
  $('#deals-grid').innerHTML=list.slice(0,state.limit).map(d=>{
    const action=nextAction(d),n=d.items.filter(x=>x.qty>0).length,got=n?d.items.reduce((s,x)=>s+(x.qty>0?Math.min(1,(x.received_qty||0)/x.qty):0),0)/n*100:null;
    return `<article class="deal-card" tabindex="0" role="button" data-deal="${d.id}" aria-label="Открыть сделку ${d.id}, ${esc(d.client)}"><div class="deal-top"><div class="object-icon">▥</div><div><h3 title="${esc(d.client)}">${esc(d.client)}</h3><div class="deal-id">№ ${d.id} · ${esc(d.name)}</div></div></div><span class="deal-state">${esc(d.state)}</span><div class="deal-amount">${money(d.total)}</div><div class="deal-address">${esc(d.address||d.program)}</div><div class="deal-progress"><span>Оплата</span><div class="mini-progress"><i style="width:${pct(d.received,d.total)}%"></i></div><span>${d.total>0&&d.payments_complete?Math.round(pct(d.received,d.total))+'%':money(d.received)}</span></div><div class="deal-progress"><span>Получено</span><div class="mini-progress"><i style="width:${got||0}%;background:#7d8bf5"></i></div><span>${got===null?'Нет спецификации':Math.round(got)+'% подтв.'}</span></div>${shipmentBar(d)}<div class="deal-meta">Остаток оплаты: ${money(d.outstanding)} · ${esc(d.manager)}</div><div class="deal-action ${action.cls}">${esc(action.text)} ›</div></article>`;
  }).join('')||'<div class="empty"><strong>Совпадений нет</strong>Измените фильтры или очистите поисковый запрос.</div>';
  $('#more').hidden=list.length<=state.limit;$('#more').textContent=`Показать ещё ${Math.min(18,Math.max(0,list.length-state.limit))} из ${Math.max(0,list.length-state.limit)}`;
}
function taskHTML(t){return `<div class="task ${t.done?'done':''}"><input type="checkbox" data-task-toggle="${t.id}" ${t.done?'checked':''} aria-label="${esc(t.title)}"><div class="task-main"><div class="task-title">${esc(t.title)}</div><div class="event-sub ${overdue(t)?'overdue':''}">${esc(t.owner||'Ответственный не назначен')} · ${t.due?datefmt(t.due):'Без срока'}${overdue(t)?' · просрочено':''}</div>${t.depends_on?`<div class="event-sub">После: ${esc(data.tasks.find(x=>x.id===t.depends_on)?.title||'задача недоступна')} · ${data.tasks.find(x=>x.id===t.depends_on)?.done?'готово':'ожидает выполнения'}</div>`:''}${t.note?`<div class="task-note">${esc(t.note)}</div>`:''}</div><button class="task-edit" data-task-edit="${t.id}">Изменить</button></div>`;}
function renderTasks(rows){
  const groups=rows.filter(d=>tasksFor(d.id).length);
  $('#tasks-list').innerHTML=groups.map(d=>`<div class="task-group"><h3><button data-open="${d.id}">${esc(d.client)} · № ${d.id} ↗</button></h3>${tasksFor(d.id).map(taskHTML).join('')}</div>`).join('')||'<div class="empty"><strong>Здесь будут ближайшие действия</strong>Откройте карточку сделки → «Чеклист» и добавьте задачу или шаблон.</div>';
}
function openDeal(id,tab='money'){activeDeal=id;detailTab=tab;editTask=null;renderDeal();if(!$('#deal-dialog').open)$('#deal-dialog').showModal();}
function renderDeal(){
  const d=data.deals.find(x=>x.id===activeDeal);if(!d)return;
  $('#deal-content').innerHTML=`<h2 class="detail-title">${esc(d.client)}</h2><div class="detail-sub">№ ${d.id} · ${esc(d.name)}<br>${esc(d.address||d.program)}<br>${esc(d.manager)} · ${esc(d.company)}</div><span class="deal-state">${esc(d.state)}</span> <a class="detail-link" href="${esc(d.url)}" target="_blank" rel="noopener">Открыть в Мегаплане ↗</a><a class="detail-link" href="./shipments?deal_id=${encodeURIComponent(d.id)}">Отгрузки и акты ↗</a><button class="quiet" data-object-for="${d.id}">Открыть объект и план сроков ↗</button><div class="detail-kpis"><div><span>Стоимость</span><strong>${money(d.total)}</strong></div><div><span>Получено</span><strong>${money(d.received)}</strong></div><div><span>Осталось получить</span><strong>${money(d.outstanding)}</strong></div></div><div class="tabs"><button data-tab="money" class="${detailTab==='money'?'selected':''}">Деньги</button><button data-tab="proc" class="${detailTab==='proc'?'selected':''}">Закупки</button><button data-tab="tasks" class="${detailTab==='tasks'?'selected':''}">Чеклист · ${tasksFor(d.id).filter(t=>t.done).length}/${tasksFor(d.id).length}</button><button data-tab="data" class="${detailTab==='data'?'selected':''}">Источники</button></div><div class="detail-section">${detailTab==='money'?detailMoney(d):detailTab==='proc'?detailProc(d):detailTab==='tasks'?detailTasks(d):detailSources(d)}</div>`;
}
function detailMoney(d){return `<p class="micro">${esc(data.definitions.received)} Неоплаченный остаток не считается просрочкой без согласованного срока.</p>${!d.payments_complete?'<div class="notice">Список операций неполон: остаток не рассчитывается.</div>':''}<h3>Клиентские счета</h3>${d.invoices.map(x=>`<div class="event"><div class="event-main"><div class="event-title">Счёт № ${esc(x.number)}</div><div class="event-sub">${datefmt(x.date)} · поступило по связям счёта ${money(x.received)}</div></div><div class="event-money">${money(x.amount)}</div></div>`).join('')||'<p class="micro">В CRM нет связанных клиентских счетов.</p>'}<h3>Денежные операции · ${d.payments.length}</h3>${d.payments.map(p=>`<div class="event"><div class="event-main"><div class="event-title">${esc(p.counterparty||p.category)}</div><div class="event-sub">${datefmt(p.date)} · ${esc(p.account)}${p.bank_verified?' · связь с выпиской проверена':''}</div><details><summary>Назначение · № ${p.id}</summary><p>${esc(p.description)}</p></details></div><div class="event-money ${p.kind==='income'?'positive':'negative'}">${p.kind==='income'?'+':'−'}${money(p.amount)}</div></div>`).join('')||'<p class="micro">Связанные денежные операции в CRM не найдены. Фактическую оплату без привязки подтвердить нельзя.</p>'}`;}
function detailProc(d){return `<p class="micro">${esc(data.definitions.procurement)} ${d.procurement_at?'Спецификация обновлена '+datefmt(d.procurement_at)+'.':''}</p><h3>Покрыто счетами поставщиков: ${procurementCoverage(d.items,'invoice_qty')===null?'нет данных':fmt.format(procurementCoverage(d.items,'invoice_qty'))+'%'}</h3><p class="micro">По распределённым количествам всех поставщиков. Подтверждение заказа в Хогарте и получение на объекте учитываются отдельно.</p><h3>Оплачено поставщикам: ${money(d.spent)}</h3><h3>Учтённые счета поставщиков</h3>${d.supplier_invoices.map(x=>`<div class="event"><div class="event-main"><div class="event-title">${esc(x.supplier)} · № ${esc(x.number)}</div><div class="event-sub">${esc(x.date)} · ${x.shared?'Счёт на несколько сделок; оплата по доле не подтверждена':x.paid===null?'Оплата по этой доле не подтверждена':'В реестре оплачено '+money(x.paid)+' · остаток '+money(Math.max(0,x.amount-x.paid))}</div></div><div class="event-money">${money(x.amount)}</div></div>`).join('')||'<p class="micro">В реестре нет связанных счетов. Платежи могут присутствовать отдельно во вкладке «Деньги».</p>'}<h3>Комплектация · ${d.items.length} позиций</h3>${d.items.map(x=>`<div class="event"><div class="event-main"><div class="event-title">${esc(x.name)}</div><div class="event-sub">${esc(x.supplier)} · ${esc(x.sku)} · требуется ${fmt.format(x.qty)} ${esc(x.unit)}</div><div class="item-grid"><div>Заказ подтверждён<b>${x.ordered_qty===null?'Нет подтверждения':fmt.format(x.ordered_qty)}</b></div><div>Учтено по счетам<b>${fmt.format(x.invoice_qty)}</b></div><div>Получено, подтв.<b>${x.received_qty===null?'Нет данных':fmt.format(x.received_qty)}</b></div></div></div></div>`).join('')||'<div class="empty">Закупочная спецификация ещё не связана с этой сделкой.</div>'}`;}
function detailTasks(d){const t=editTask?data.tasks.find(t=>t.id===editTask):null;return `<p class="micro">Чеклист хранится в дашборде. Отметки не меняют оплаты, закупки или статусы Мегаплана.</p>${tasksFor(d.id).map(taskHTML).join('')||'<p class="micro">Задач пока нет. Добавьте ближайшее действие.</p>'}<button id="task-template" class="quiet">＋ Добавить шаблон: спецификация → поставка → акт</button><form id="task-form" class="task-form"><h3>${t?'Изменить задачу':'Следующее действие'}</h3><label for="task-title">Что нужно сделать</label><input id="task-title" maxlength="200" value="${esc(t?.title||'')}" required placeholder="Например, согласовать дату поставки"><div class="form-row"><div><label for="task-owner">Ответственный</label><input id="task-owner" maxlength="100" value="${esc(t?.owner||d.manager)}"></div><div><label for="task-due">Срок</label><input id="task-due" type="date" value="${esc(t?.due||'')}"></div></div>${dependencyField(d,t)}<label for="task-note">Комментарий или причина задержки</label><textarea id="task-note" rows="2" maxlength="2000">${esc(t?.note||'')}</textarea><button type="submit" class="primary">${t?'Сохранить изменения':'Добавить задачу'}</button>${t?'<button type="button" id="cancel-edit" class="quiet">Отменить</button>':''}</form>`;}
function detailSources(d){return `<h3>Что входит в расчёт</h3><p class="micro">${esc(data.definitions.scope)}<br>${esc(data.definitions.outstanding)}</p><div class="event"><div class="event-main"><div class="event-title">Мегаплан</div><div class="event-sub">Снимок ${datefmt(data.synced_at)} · карточка изменена ${datefmt(d.updated_at)}<br>Платежи: ${d.payments_complete?'список связанных операций получен полностью':'нужна сверка состава операций'}</div></div></div><div class="event"><div class="event-main"><div class="event-title">Реестр закупок</div><div class="event-sub">${d.procurement_at?'Обновлён '+datefmt(d.procurement_at):'Спецификация отсутствует'}<br>Реестр может содержать лишь часть общей потребности.</div></div></div><h3>Что требует уточнения</h3>${d.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('')||'<p class="micro">Формальных предупреждений нет.</p>'}<p class="micro">Документы, позиции, связи и даты изменяются в действующем контуре Мегаплана и бота. Здесь доступны чтение и собственный чеклист.</p>`;}
function updateTask(t){const i=data.tasks.findIndex(x=>x.id===t.id);if(i<0)data.tasks.push(t);else data.tasks[i]=t;render();if(activeDeal)renderDeal();}
async function submitTask(body){const r=await api('tasks',body);updateTask(r.task);return r.task;}
$('#code-form').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;try{await authenticate({code:$('#code').value},'code');}catch(err){$('#auth-message').textContent=err.message;}finally{btn.disabled=false;}});
$('#refresh').onclick=refresh;
['result','year','manager','company','sort','weeks'].forEach(id=>$('#'+id).addEventListener('change',()=>{state.limit=18;render();}));
$('#stage-filter').addEventListener('change',()=>{state.stage=$('#stage-filter').value;state.limit=18;render();});
$('#hide-zero').addEventListener('change',()=>{state.hideZero=$('#hide-zero').checked?'1':'';state.limit=18;render();});
$('#search').addEventListener('input',()=>{state.limit=18;render();});
$('#reset').onclick=()=>{['year','manager','company'].forEach(x=>$('#'+x).value='all');$('#result').value='active';$('#search').value='';state={...state,alert:'',stage:'',hideZero:'',week:'',limit:18};render();};
$('#show-all').onclick=()=>{state.limit=filtered().length;renderCards(filtered());};
$('#more').onclick=()=>{state.limit+=18;renderCards(filtered());};
$('#close-dialog').onclick=()=>$('#deal-dialog').close();$('#deal-dialog').addEventListener('close',()=>{activeDeal=null;editTask=null;});
$('#deal-dialog').addEventListener('click',e=>{if(e.target===$('#deal-dialog')&&e.clientX<$('#deal-dialog').getBoundingClientRect().left)$('#deal-dialog').close();});
$('#close-code').onclick=()=>$('#code-dialog').close();
$('#browser-login').onclick=async()=>{try{const r=await api('browser-code',{});$('#browser-code').textContent=r.code;$('#browser-url').textContent=r.url;$('#browser-url').href=r.url;$('#code-dialog').showModal();}catch(e){toast(e.message);}};
$('#copy-code').onclick=async()=>{try{await navigator.clipboard.writeText($('#browser-code').textContent);toast('Код скопирован');}catch{toast('Выделите и скопируйте код вручную');}};
$('#logout').onclick=async()=>{try{await api('logout',{});}finally{token='';sessionStorage.removeItem('dashboard_session');data=null;$('#app').hidden=true;$('#login').hidden=false;$('#auth-message').textContent='Вы вышли. Для повторного входа откройте дашборд заново кнопкой в боте.';}};
document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-preset],[data-clear-select],[data-nav],[data-clear],[data-alert],[data-stage],[data-week],[data-kpi],[data-deal],[data-open],[data-tab],[data-task-edit]');
  if(el){
    if(el.dataset.preset){presetYear(el.dataset.preset);}
    if(el.dataset.clearSelect){const id=el.dataset.clearSelect;$('#'+id).value=id==='search'?'':'all';state.limit=18;render();}
    if(el.dataset.nav){state.nav=el.dataset.nav;state.limit=18;render();window.scrollTo({top:0,behavior:'smooth'});}
    if(el.dataset.clear){state[el.dataset.clear]='';render();}
    if(el.dataset.alert){state.alert=state.alert===el.dataset.alert?'':el.dataset.alert;state.limit=18;render();$('#deals-section').scrollIntoView({behavior:'smooth'});}
    if(el.dataset.stage){state.stage=state.stage===el.dataset.stage?'':el.dataset.stage;render();}
    if(el.dataset.week){state.week=state.week===el.dataset.week?'':el.dataset.week;render();}
    if(el.dataset.kpi){if(el.dataset.kpi==='unpaid'){state.alert='unpaid';render();}if(el.dataset.kpi==='received'){state.alert='paid';render();}if(el.dataset.kpi==='amount'){$('#sort').value='amount';render();}$('#deals-section').scrollIntoView({behavior:'smooth'});}
    if(el.dataset.deal)openDeal(el.dataset.deal,state.nav==='procurement'?'proc':'money');
    if(el.dataset.open)openDeal(el.dataset.open,'tasks');
    if(el.dataset.tab){detailTab=el.dataset.tab;editTask=null;renderDeal();}
    if(el.dataset.taskEdit){const t=data.tasks.find(t=>t.id===el.dataset.taskEdit);activeDeal=t.deal_id;detailTab='tasks';editTask=t.id;renderDeal();if(!$('#deal-dialog').open)$('#deal-dialog').showModal();$('#task-form').scrollIntoView({behavior:'smooth'});}
  }
  if(e.target.closest('#cancel-edit')){editTask=null;renderDeal();}
  if(e.target.closest('#task-template')){
    const btn=e.target.closest('button'),did=activeDeal;btn.disabled=true;
    try{for(const title of ['Согласовать спецификацию','Подтвердить заказ оборудования','Проверить комплектность поставки','Согласовать дату работ','Подписать акт']){if(tasksFor(did).some(t=>t.title===title))continue;await submitTask({deal_id:did,title,owner:data.deals.find(d=>d.id===did).manager,due:'',note:'',done:false});}toast('Шаблон добавлен');}
    catch(err){toast(err.message);}finally{if(activeDeal)renderDeal();}
  }
});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-deal],[data-week]')){e.preventDefault();e.target.click();}});
document.addEventListener('change',async e=>{if(!e.target.matches('[data-task-toggle]'))return;const el=e.target,t=data.tasks.find(t=>t.id===el.dataset.taskToggle);el.disabled=true;try{await submitTask({...t,done:el.checked});toast('Сохранено');}catch(err){el.checked=!!t.done;toast(err.message);}finally{el.disabled=false;}});
document.addEventListener('submit',async e=>{if(e.target.id!=='task-form')return;e.preventDefault();const btn=e.target.querySelector('button[type=submit]');btn.disabled=true;const current=editTask?data.tasks.find(t=>t.id===editTask):null;try{await submitTask({...current,deal_id:activeDeal,title:$('#task-title').value,owner:$('#task-owner').value,due:$('#task-due').value,note:$('#task-note').value,depends_on:$('#task-dependency').value,done:!!current?.done});editTask=null;renderDeal();toast('Задача сохранена');}catch(err){toast(err.message);btn.disabled=false;}});
(async()=>{
  const tg=window.Telegram?.WebApp;try{tg?.ready();tg?.expand();}catch{}
  // A restored Mini App can retain old initData; reuse a valid server session first.
  if(token && await refresh())return;
  if(tg?.initData){
    try{await authenticate({initData:tg.initData},'telegram');}
    catch(e){$('#auth-message').textContent=e.message+' Закройте окно приложения полностью и откройте «Пульт сделок» кнопкой под сообщением бота.';}
  }
})();
// Refresh only when visible, and never replace a partially edited checklist form.
setInterval(()=>{if(data&&token&&!document.hidden&&!$('#deal-dialog').open&&!$('#object-dialog').open&&!$('#view-form:not([hidden])'))refresh();},60000);
