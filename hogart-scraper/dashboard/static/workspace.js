'use strict';
let activeObject=null, objectTab='overview', objectLimit=18, planEdit=null, linkSelection=new Set(), objectSaveId=null;
const kinds={income:'Поступление от клиента',expense:'Оплата поставщику',delivery:'Поставка'};
const kindColors={income:'#13b5aa',expense:'#5167f6',delivery:'#cf881f'};
const objectOf = did => data.objects.find(o=>o.deal_ids.includes(did));
const objectDeals = o => data.deals.filter(d=>!d.is_purchase&&o.deal_ids.includes(d.id));
const objectPlans = o => data.plans.filter(p=>o.deal_ids.includes(p.deal_id));
const objectTasks = o => data.tasks.filter(t=>o.deal_ids.includes(t.deal_id));
const fullSum = (rows,key) => rows.some(d=>d[key]===null)?null:sum(rows,key);
const isBlocked = t => !!t.depends_on&&!data.tasks.find(x=>x.id===t.depends_on)?.done;
function dependencyField(d,t){
  const ids=objectOf(d.id)?.deal_ids||[d.id];
  return `<label for="task-dependency">Начать после задачи</label><select id="task-dependency"><option value="">Без зависимости</option>${data.tasks.filter(x=>ids.includes(x.deal_id)&&x.id!==t?.id).map(x=>`<option value="${esc(x.id)}" ${x.id===t?.depends_on?'selected':''}>№ ${esc(x.deal_id)} · ${esc(x.title)}${x.done?' · выполнено':''}</option>`).join('')}</select>`;
}
function queue(rows){
  const ids=new Set(rows.map(d=>d.id));
  return [...data.tasks.filter(t=>ids.has(t.deal_id)&&!t.done).map(t=>({...t,type:'task',blocked:isBlocked(t)})),
    ...data.plans.filter(p=>ids.has(p.deal_id)&&p.status==='open').map(p=>({...p,type:'plan',blocked:false}))]
    .sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999')||a.title.localeCompare(b.title,'ru'));
}
function renderWorkspace(rows){
  $('#objects-section').hidden=state.nav!=='objects';$('#actions-section').hidden=state.nav!=='actions';
  const q=queue(rows), late=q.filter(x=>x.due&&x.due<today()), soon=q.filter(x=>x.due>=today()&&x.due<=addDays(today(),7));
  $('#today-brief').innerHTML=`<div class="today-brief"><div><span class="eyebrow">РЕШЕНИЯ НА СЕГОДНЯ</span><h2>${late.length?late.length+' сроков требуют проверки':q.length?'Ближайшие действия':'Задайте ближайшие действия и сроки'}</h2><p>${soon.length} на ближайшие 7 дней · ${q.filter(x=>!x.owner).length} без ответственного · ${q.filter(x=>x.blocked).length} ждут предыдущую задачу</p></div><button class="primary" data-nav="actions">Открыть очередь →</button></div>`;
  const current=$('#saved-view').value;
  $('#saved-view').innerHTML='<option value="">Сохранённые виды</option>'+data.views.map(v=>`<option value="${esc(v.id)}">${esc(v.name)}</option>`).join('');$('#saved-view').value=current;
  $('#delete-view').hidden=!$('#saved-view').value;
  const ids=new Set(rows.map(d=>d.id));
  const objects=data.objects.filter(o=>o.deal_ids.some(id=>ids.has(id)));
  $('#object-scope').textContent=`${objects.length} карточек по ${rows.length} сделкам выборки. ${objects.filter(o=>o.confirmed).length} с подтверждёнными связями. Суммы карточки охватывают все её связанные сделки.`;
  $('#objects-grid').innerHTML=objects.slice(0,objectLimit).map(o=>{
    const ds=objectDeals(o),ts=objectTasks(o).filter(t=>!t.done),plans=objectPlans(o).filter(p=>p.status==='open');
    const next=[...ts,...plans].sort((a,b)=>(a.due||'9999').localeCompare(b.due||'9999'))[0];
    const ins=ds.filter(d=>data.installations[d.id]).length;
    return `<button class="deal-card object-card" data-object="${esc(o.id)}"><div class="deal-top"><div class="object-icon">▥</div><div><h3>${esc(o.name)}</h3><div class="deal-id">${ds.length} сделок · ${ds.filter(d=>ids.has(d.id)).length} в выборке</div></div></div><span class="deal-state">${o.confirmed?'Связи подтверждены':'Отдельная сделка · связи не заданы'}</span><div class="deal-amount">${money(fullSum(ds,'total'))}</div><div class="deal-address">${esc(o.address||'Адрес не указан')}</div><div class="object-mini"><span>Поступило<b>${money(fullSum(ds,'received'))}</b></span><span>Монтаж<b>${ins?ins+' ведомостей':'Нет ведомости'}</b></span></div><div class="deal-action ${next?.due&&next.due<today()?'danger':''}">${next?esc((next.due?datefmt(next.due)+' · ':'')+next.title):'Задайте ближайшее действие и сроки'} ›</div></button>`;
  }).join('')||'<div class="empty">По выбранным фильтрам объектов нет.</div>';
  $('#objects-more').hidden=objects.length<=objectLimit;$('#objects-more').textContent=`Показать ещё · сейчас ${Math.min(objectLimit,objects.length)} из ${objects.length}`;
  $('#action-metrics').innerHTML=[['Срок прошёл',late.length,'Проверить выполнение и актуальность'],['На 7 дней',soon.length,'Задачи и введённые сроки'],['Зависимости',q.filter(x=>x.blocked).length,'Ожидают предыдущую задачу'],['Без срока',q.filter(x=>!x.due).length,'Нужно определить дату']].map(([label,n,note])=>`<div class="kpi"><div class="kpi-top">${label}</div><div class="kpi-number">${n}</div><div class="kpi-note">${note}</div></div>`).join('');
  $('#plan-timeline').innerHTML=timeline(data.plans.filter(p=>ids.has(p.deal_id)&&p.status==='open'));
  const groups=[['Срок прошёл',x=>x.due&&x.due<today()],['Ближайшие 7 дней',x=>x.due>=today()&&x.due<=addDays(today(),7)],['Позже',x=>x.due>addDays(today(),7)],['Без срока',x=>!x.due]];
  $('#actions-board').innerHTML=groups.map(([name,test])=>{const list=q.filter(test);return `<section class="action-column"><h3>${name} <span class="pill">${list.length}</span></h3>${list.map(actionCard).join('')||'<div class="queue-empty">Нет действий</div>'}</section>`;}).join('');
}
function actionCard(x){
  const d=data.deals.find(d=>d.id===x.deal_id),o=objectOf(x.deal_id);
  const badge=x.type==='task'?(x.blocked?'Ожидает задачу':'Задача'):(x.certainty==='agreed'?'Согласованный срок':'Предварительный срок');
  return `<button class="action-card" ${x.type==='task'?`data-task-edit="${esc(x.id)}"`:`data-plan-open="${esc(x.id)}"`}><span class="pill">${badge}</span><h4>${esc(x.title)}</h4><p>${esc(o?.name||d?.client)} · № ${esc(x.deal_id)}</p><div class="action-date ${x.due&&x.due<today()?'overdue':''}">${x.due?datefmt(x.due):'Срок не задан'}${x.amount?' · '+money(x.amount):''}</div><p>${esc(x.owner||'Ответственный не назначен')}</p>${x.type==='plan'?'<small>План · факт не сопоставлен автоматически</small>':''}</button>`;
}
function timeline(plans){
  const start=today(), end=addDays(start,41), bins=Array.from({length:6},(_,i)=>({date:addDays(start,i*7),income:0,expense:0,delivery:0}));
  plans.forEach(p=>{const b=bins.find(b=>p.due>=b.date&&p.due<addDays(b.date,7));if(b){if(p.kind==='delivery')b.delivery++;else b[p.kind]+=p.amount||0;}});
  const max=Math.max(1,...bins.flatMap(b=>[b.income,b.expense]));
  let svg='<svg viewBox="0 0 700 210" role="img" aria-label="Введённые плановые поступления, выплаты и поставки по неделям">';
  bins.forEach((b,i)=>{const x=40+i*110;svg+=`<line x1="${x}" x2="${x+90}" y1="150" y2="150" stroke="#dfe6f1"/>`;['income','expense'].forEach((kind,j)=>{const h=b[kind]/max*105;svg+=`<rect x="${x+j*36}" y="${150-h}" width="28" height="${h}" rx="4" fill="${kindColors[kind]}"><title>${esc(datefmt(b.date))}: ${kinds[kind]} ${esc(money(b[kind],false))}</title></rect>`;});svg+=`<text x="${x+30}" y="170" text-anchor="middle" fill="#718198" font-size="11">${esc(datefmt(b.date).replace(' 2026 г.',''))}</text><text x="${x+30}" y="194" text-anchor="middle" fill="#af791f" font-size="11">${b.delivery} поставок</text>`;});
  svg+='</svg>';
  const upcoming=plans.filter(p=>p.due>=start&&p.due<=end);
  return `<div class="panel-head"><div><h2>Введённые сроки · 6 недель</h2><p>${datefmt(start)} — ${datefmt(end)} · предварительные и согласованные</p></div></div><div class="legend"><span><i class="teal"></i>Поступления</span><span><i class="indigo"></i>Выплаты</span><span>Поставки — количество сроков</span></div>${upcoming.length?svg:'<div class="empty">На этот период сроки ещё не введены. Добавьте их в карточке объекта.</div>'}<p class="micro">Это календарь внесённых планов, а не прогноз остатка денег. Фактические оплаты и приёмка остаются в своих источниках. ${plans.filter(p=>p.due<start).length} открытых сроков до периода · ${plans.filter(p=>p.due>end).length} после.</p>`;
}
function openObject(id,tab='overview'){
  activeObject=id;objectTab=tab;planEdit=null;renderObject();if(!$('#object-dialog').open)$('#object-dialog').showModal();
}
function renderObject(){
  const o=data.objects.find(o=>o.id===activeObject);if(!o)return;
  const ds=objectDeals(o),ts=objectTasks(o),ps=objectPlans(o);
  $('#object-content').innerHTML=`<div class="object-heading"><div><h2 class="detail-title">${esc(o.name)}</h2><div class="detail-sub">${esc(o.address||'Адрес не указан')}<br>${ds.length} связанных сделок · ${o.confirmed?'Связи подтверждены в дашборде':'Карточка отдельной сделки — связи ещё не заданы'}</div></div><button class="quiet" data-object-tab="links">Настроить объект ↗</button></div>${o.missing_deal_ids.length?'<div class="notice">Часть связанных сделок отсутствует в снимке: '+esc(o.missing_deal_ids.join(', '))+'. Суммы неполные.</div>':''}<div class="detail-kpis"><div><span>Стоимость связанных сделок</span><strong>${money(fullSum(ds,'total'))}</strong></div><div><span>Поступило по CRM</span><strong>${money(fullSum(ds,'received'))}</strong></div><div><span>Осталось получить · не просрочка</span><strong>${money(fullSum(ds,'outstanding'))}</strong></div></div><div class="tabs object-tabs">${[['overview','Объект'],['plans','Сроки · '+ps.filter(p=>p.status==='open').length],['works','Монтаж'],['tasks','Действия · '+ts.filter(t=>!t.done).length],['history','История'],['links','Связи']].map(([key,title])=>`<button data-object-tab="${key}" class="${objectTab===key?'selected':''}">${title}</button>`).join('')}</div><div id="object-body">${objectTab==='overview'?objectOverview(o,ds):objectTab==='plans'?planPanel(o):objectTab==='works'?workPanel(o):objectTab==='tasks'?tasksPanel(o):objectTab==='links'?linksPanel(o):'<p class="micro">Загружаю историю…</p>'}</div>`;
  if(objectTab==='history')loadHistory(o);
}
function objectOverview(o,ds){
  const ts=objectTasks(o), ps=objectPlans(o).filter(p=>p.status==='open'), items=ds.flatMap(d=>d.items).filter(x=>x.qty>0);
  const progress=items.length?Math.round(items.reduce((n,x)=>n+Math.min(1,Math.max(0,x.received_qty||0)/x.qty),0)/items.length*100):null;
  const milestones=[['Оплаты',ds.every(d=>d.outstanding===0&&d.payments_complete)?'По стоимости получено полностью':'Сверьте остатки по сделкам'],['Комплектация',progress===null?'Нет спецификации':progress+'% количества позиций подтверждено'],['Монтаж',ds.filter(d=>data.installations[d.id]).length+' ведомостей связано'],['Действия',ts.filter(t=>t.done).length+' из '+ts.length+' выполнено']];
  return `<div class="object-milestones">${milestones.map(([name,detail],i)=>`<div><span class="milestone-number">0${i+1}</span><h3>${name}</h3><p>${detail}</p></div>`).join('')}</div><div class="workspace-columns"><article class="panel"><h3>Связанные сделки</h3><p class="micro">Здесь показаны все сделки объекта, включая те, которые не попали в фильтры основного списка.</p>${ds.map(d=>`<button class="linked-deal" data-deal="${esc(d.id)}"><div><b>№ ${esc(d.id)} · ${esc(d.name)}</b><small>${esc(d.state)} · ${esc(d.manager)}</small></div><strong>${money(d.total)} ↗</strong></button>`).join('')}</article><article class="panel"><h3>Ближайшие действия</h3>${queue(ds).slice(0,4).map(actionCard).join('')||'<div class="queue-empty">Пока нет задач и сроков</div>'}<button class="quiet" data-object-tab="tasks">Добавить действие →</button><button class="quiet" data-object-tab="plans">Запланировать оплату или поставку →</button></article></div><div class="panel">${timeline(ps)}</div>`;
}
function tasksPanel(o){
  return `<p class="micro">Задача относится к конкретной сделке. Зависимости могут связывать задачи внутри подтверждённого объекта.</p>${objectDeals(o).map(d=>`<div class="task-group"><h3>№ ${esc(d.id)} · ${esc(d.name)}</h3>${tasksFor(d.id).map(taskHTML).join('')||'<p class="micro">Задач пока нет</p>'}<button class="quiet" data-open="${esc(d.id)}">＋ Добавить действие</button></div>`).join('')}`;
}
function workPanel(o){
  if(data.installation_status!=='ok')return '<div class="notice">Монтажный реестр сейчас недоступен. Это не означает отсутствие работ. Попробуйте обновить страницу.</div>';
  const list=o.deal_ids.map(id=>data.installations[id]).filter(Boolean);
  const statusNames={draft:'Черновик',transferred:'Передано в монтаж',in_progress:'В работе',review:'На проверке',approved:'Принято',partially_approved:'Принято частично',historical:'Исторические данные',submitted:'На проверке',rejected:'Возвращено'};
  return (list.map(ins=>`<article class="panel installation"><div class="panel-head"><div><h3>Монтаж · сделка № ${esc(ins.deal_id)}</h3><p>${esc(ins.installer_name||'Монтажник не указан')} · ${esc(statusNames[ins.status]||ins.status)} · обновлено ${datefmt(ins.updated_at)}</p></div><button class="quiet" data-deal="${esc(ins.deal_id)}">Сделка ↗</button></div><p class="micro">Только принятые количества из утверждённых отчётов. Полоса считается отдельно для каждой позиции, без сложения разных единиц.</p><div class="work-list">${ins.works.map(w=>`<div class="work-row"><div><b>${esc(w.name)}</b><span>${fmt.format(w.accepted_qty)} / ${fmt.format(w.planned_qty)} ${esc(w.unit)} принято ${w.accepted_qty>w.planned_qty?'· выше плана':''}</span></div><div class="mini-progress"><i style="width:${pct(w.accepted_qty,w.planned_qty)}%"></i></div></div>`).join('')||'<p class="micro">Ведомость работ не заполнена</p>'}</div><h3>Отчёты · ${ins.reports.length}</h3>${ins.reports.map(r=>`<div class="event"><div class="event-main"><div class="event-title">Отчёт № ${r.report_no} · ${datefmt(r.report_date)}</div><div class="event-sub">${esc(statusNames[r.status]||r.status)}${r.approved_at?' · принят '+datefmt(r.approved_at):''}</div>${r.manager_comment?`<p class="micro">${esc(r.manager_comment)}</p>`:''}</div></div>`).join('')||'<p class="micro">Отчётов пока нет</p>'}<h3>Проектные документы</h3>${ins.documents.map(d=>`<div class="event"><div class="event-main"><div class="event-title">${esc(d.name)}</div><div class="event-sub">Версия ${d.version_no} · ${esc(d.status)} · ${datefmt(d.created_at)}</div></div></div>`).join('')||'<p class="micro">Проектные документы в реестре не найдены</p>'}<p class="micro">Согласование отчётов и документы доступны в существующем контуре бота и Мегаплана.</p></article>`).join('')||'<div class="empty">У связанных сделок пока нет монтажной ведомости.</div>');
}
function planPanel(o){
  const plans=objectPlans(o),p=plans.find(p=>p.id===planEdit),ds=objectDeals(o);
  if(!planEdit)planEdit=crypto.randomUUID();
  return `<p class="micro">Внесённый срок не меняет финансовые операции или приёмку. «Закрыто вручную» снимает срок с очереди; факт проверяйте по первичному источнику. Согласованный срок требует основания.</p><div class="plans-list">${plans.map(p=>`<button class="linked-deal ${p.status==='open'?'':'plan-closed'}" data-plan-edit="${esc(p.id)}"><div><b>${esc(p.title)}</b><small>№ ${esc(p.deal_id)} · ${kinds[p.kind]} · ${p.certainty==='agreed'?'Согласован':'Предварительно'} · ${p.status==='open'?'Открыт':p.status==='done'?'Закрыт вручную':'Отменён'}</small></div><strong class="${p.status==='open'&&p.due<today()?'overdue':''}">${datefmt(p.due)}<small>${p.amount?money(p.amount):''}</small></strong></button>`).join('')||'<div class="queue-empty">Сроки ещё не внесены</div>'}</div><form id="plan-form" class="task-form" data-id="${esc(planEdit)}" data-revision="${p?.revision||0}"><h3>${p?'Изменить срок':'Добавить срок'}</h3><div class="form-row"><div><label for="plan-deal">Сделка</label><select id="plan-deal" ${p?'disabled':''}>${ds.map(d=>`<option value="${esc(d.id)}" ${d.id===p?.deal_id?'selected':''}>№ ${esc(d.id)} · ${esc(d.name)}</option>`).join('')}</select></div><div><label for="plan-kind">Тип</label><select id="plan-kind">${Object.entries(kinds).map(([k,v])=>`<option value="${k}" ${k===p?.kind?'selected':''}>${v}</option>`).join('')}</select></div></div><label for="plan-title">Что ожидается</label><input id="plan-title" maxlength="200" required value="${esc(p?.title||'')}" placeholder="Например, аванс за оборудование"><div class="form-row"><div><label for="plan-due">Дата</label><input id="plan-due" type="date" required value="${esc(p?.due||'')}"></div><div><label for="plan-amount">Сумма, ₽ · для денежных сроков</label><input id="plan-amount" inputmode="decimal" ${p?.kind==='delivery'?'disabled':''} value="${p?.amount?(p.amount/100).toFixed(2):''}" placeholder="0,00"></div></div><div class="form-row"><div><label for="plan-certainty">Подтверждение даты</label><select id="plan-certainty"><option value="tentative">Предварительная</option><option value="agreed" ${p?.certainty==='agreed'?'selected':''}>Согласованная</option></select></div><div><label for="plan-owner">Ответственный</label><input id="plan-owner" maxlength="100" value="${esc(p?.owner||ds[0]?.manager||'')}"></div></div><label for="plan-note">Основание и комментарий · обязательно для согласованной даты</label><textarea id="plan-note" maxlength="2000" rows="2">${esc(p?.note||'')}</textarea><label for="plan-status">Состояние срока</label><select id="plan-status"><option value="open">Открыт</option><option value="done" ${p?.status==='done'?'selected':''}>Закрыт вручную · факт проверен отдельно</option><option value="cancelled" ${p?.status==='cancelled'?'selected':''}>Отменён</option></select><div><button class="primary" type="submit">Сохранить срок</button>${p?'<button class="quiet" type="button" id="new-plan">＋ Новый срок</button>':''}</div></form>`;
}
function linksPanel(o){
  linkSelection=new Set(o.deal_ids);objectSaveId=o.confirmed?o.id:crypto.randomUUID();
  return `<div class="notice">Связывайте сделки только после проверки адреса и состава работ. Один клиент может иметь несколько объектов. Связи сохраняются в дашборде.</div><form id="object-form" class="task-form" data-revision="${o.revision}"><label for="object-name">Название объекта</label><input id="object-name" maxlength="160" value="${esc(o.name)}" required><label for="object-address">Адрес</label><input id="object-address" maxlength="400" value="${esc(o.address)}"><label for="link-search">Найти сделку по номеру, клиенту, названию или адресу</label><input id="link-search" placeholder="Поиск среди всех продаж"><div id="link-candidates">${linkCandidates(o,'')}</div><p class="micro" id="link-count">Выбрано ${linkSelection.size}. Снятие отметки возвращает сделку в отдельную карточку.</p><button class="primary" type="submit">Подтвердить связи и сохранить</button></form>`;
}
function linkCandidates(o,query){
  const search=query.toLocaleLowerCase('ru'),all=data.deals.filter(d=>!d.is_purchase);
  const list=all.filter(d=>linkSelection.has(d.id)||[d.id,d.name,d.client,d.address].join(' ').toLocaleLowerCase('ru').includes(search));
  list.sort((a,b)=>Number(linkSelection.has(b.id))-Number(linkSelection.has(a.id)));
  return list.slice(0,60).map(d=>{const other=data.objects.find(x=>x.confirmed&&x.id!==o.id&&x.deal_ids.includes(d.id));return `<label class="link-option"><input type="checkbox" data-link="${esc(d.id)}" ${linkSelection.has(d.id)?'checked':''} ${other?'disabled':''}><span><b>№ ${esc(d.id)} · ${esc(d.client)}</b><small>${esc(d.name)} · ${esc(d.address||'Адрес не указан')}${other?' · Уже в объекте «'+esc(other.name)+'»':''}</small></span></label>`;}).join('')+`<p class="micro">Показано ${Math.min(60,list.length)} из ${list.length} совпадений. Уточните поиск, чтобы найти остальные.</p>`;
}
async function loadHistory(o){
  try{const r=await api('history',{deal_ids:o.deal_ids});if(activeObject!==o.id||objectTab!=='history')return;
    $('#object-body').innerHTML='<p class="micro">Последние 100 изменений дашборда. Изменения Мегаплана сюда не входят.</p>'+r.history.map(h=>{const a=h.payload.after||{},b=h.payload.before;return `<div class="history-event"><div class="history-dot"></div><div><b>${h.entity==='object'?'Связи и название объекта':h.entity==='plan'?'Срок оплаты / поставки':'Задача чеклиста'}</b><p>${esc(a.title||a.name||'Изменение')}</p><small>${new Date(h.at*1000).toLocaleString('ru-RU',{timeZone:'Europe/Moscow'})} МСК · владелец ${esc(h.actor)}</small><details><summary>Подробности изменения</summary>${b?`<p>Было: ${esc(historySummary(b))}</p>`:''}<p>Стало: ${esc(historySummary(a))}</p></details></div></div>`;}).join('')+(r.history.length?'':'<div class="empty">Изменений в дашборде пока нет.</div>');
  }catch(e){if(activeObject===o.id&&objectTab==='history')$('#object-body').textContent=e.message;}
}
function historySummary(x){return [x.title||x.name,x.address,x.deal_ids?'Сделки: '+x.deal_ids.join(', '):'',x.due?'Срок: '+datefmt(x.due):'',x.amount?'Сумма: '+money(x.amount,false):'',x.owner,x.note,x.status,x.certainty,x.depends_on?'После задачи '+x.depends_on:'',x.done!==undefined?(x.done?'Выполнено':'В работе'):''].filter(Boolean).join(' · ');}
async function refreshWorkspace(){data=await api('dashboard');render();if(activeObject)renderObject();}
$('#close-object').onclick=()=>$('#object-dialog').close();
$('#object-dialog').addEventListener('close',()=>{activeObject=null;planEdit=null;});
$('#deal-dialog').addEventListener('close',()=>{if(activeObject&&objectTab==='tasks')renderObject();});
$('#objects-more').onclick=()=>{objectLimit+=18;renderWorkspace(filtered());};
$('#save-view').onclick=()=>{$('#view-form').hidden=!$('#view-form').hidden;if(!$('#view-form').hidden)$('#view-name').focus();};
$('#saved-view').onchange=()=>{const v=data.views.find(v=>v.id===$('#saved-view').value);$('#delete-view').hidden=!v;if(!v)return;
  for(const id of ['result','year','manager','company','search','sort','weeks'])if(v.filters[id]!==undefined){const el=$('#'+id);if(el.tagName!=='SELECT'||[...el.options].some(o=>o.value===v.filters[id]))el.value=v.filters[id];else el.value='all';}
  for(const key of ['nav','alert','stage','week','hideZero'])state[key]=v.filters[key]|| (key==='nav'?'overview':'');state.limit=18;objectLimit=18;render();};
$('#delete-view').onclick=async()=>{const id=$('#saved-view').value;if(!id)return;try{await api('views',{id,delete:true});await refreshWorkspace();toast('Вид удалён');}catch(e){toast(e.message);}};
$('#view-form').onsubmit=async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;try{const filters={};for(const id of ['result','year','manager','company','search','sort','weeks'])filters[id]=$('#'+id).value;for(const k of ['nav','alert','stage','week','hideZero'])filters[k]=state[k];await api('views',{id:crypto.randomUUID(),name:$('#view-name').value,filters});$('#view-form').hidden=true;await refreshWorkspace();toast('Вид сохранён');}catch(err){toast(err.message);}finally{btn.disabled=false;}};
document.addEventListener('click',async e=>{
  const el=e.target.closest('[data-object],[data-object-for],[data-object-tab],[data-plan-open],[data-plan-edit],#new-plan');if(!el)return;
  if(el.dataset.object)openObject(el.dataset.object);
  if(el.dataset.objectFor){const o=objectOf(el.dataset.objectFor);$('#deal-dialog').close();if(o)openObject(o.id);}
  if(el.dataset.objectTab){objectTab=el.dataset.objectTab;planEdit=null;renderObject();}
  if(el.dataset.planOpen){const p=data.plans.find(p=>p.id===el.dataset.planOpen);openObject(objectOf(p.deal_id).id,'plans');planEdit=p.id;renderObject();}
  if(el.dataset.planEdit){planEdit=el.dataset.planEdit;renderObject();$('#plan-form').scrollIntoView({block:'start',behavior:'smooth'});}
  if(el.id==='new-plan'){planEdit=null;renderObject();}
});
document.addEventListener('input',e=>{if(e.target.id==='link-search')$('#link-candidates').innerHTML=linkCandidates(data.objects.find(o=>o.id===activeObject),e.target.value);});
document.addEventListener('change',e=>{
  if(e.target.dataset.link){if(e.target.checked)linkSelection.add(e.target.dataset.link);else linkSelection.delete(e.target.dataset.link);$('#link-count').textContent='Выбрано '+linkSelection.size+'. Снятие отметки возвращает сделку в отдельную карточку.';}
  if(e.target.id==='plan-kind')$('#plan-amount').disabled=e.target.value==='delivery';
});
document.addEventListener('submit',async e=>{
  if(!['object-form','plan-form'].includes(e.target.id))return;e.preventDefault();const form=e.target,btn=form.querySelector('button[type="submit"]');btn.disabled=true;
  try{
    if(form.id==='object-form'){
      const r=await api('objects',{id:objectSaveId,revision:Number(form.dataset.revision),name:$('#object-name').value,address:$('#object-address').value,deal_ids:[...linkSelection]});activeObject=r.object.id;objectTab='overview';
    }else{
      const raw=$('#plan-amount').value.replace(/\s/g,'').replace(',','.');let amount=null;
      if($('#plan-kind').value!=='delivery'){if(!/^\d+(\.\d{1,2})?$/.test(raw))throw new Error('Укажите сумму в рублях, до двух знаков после запятой');const [whole,frac='']=raw.split('.');amount=Number(whole)*100+Number(frac.padEnd(2,'0'));if(!Number.isSafeInteger(amount))throw new Error('Сумма слишком велика');}
      await api('plans',{id:form.dataset.id,revision:Number(form.dataset.revision),deal_id:$('#plan-deal').value,kind:$('#plan-kind').value,title:$('#plan-title').value,due:$('#plan-due').value,certainty:$('#plan-certainty').value,amount,owner:$('#plan-owner').value,note:$('#plan-note').value,status:$('#plan-status').value});planEdit=null;
    }
    await refreshWorkspace();toast('Сохранено');
  }catch(err){toast(err.message);btn.disabled=false;}
});
