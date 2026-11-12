// SmartBild — коммерческое предложение из модулей.
// node build.cjs deal_example.json  →  <имя сделки>.html и .pdf рядом с файлом сделки
// Модули в "modules": light, climate, media, telegram, scenes (в любом порядке и составе).
// Таблица расчёта — CSV с разделителем «;»: Раздел;Наименование;Ед.;Кол-во;Цена.
const fs = require('fs'), path = require('path');
const HERE = __dirname;
const dealPath = path.resolve(process.argv[2] || path.join(HERE, 'deal_example.json'));
const D = JSON.parse(fs.readFileSync(dealPath, 'utf8'));
const A = (p) => 'file://' + path.join(HERE, 'assets', p);
const esc = (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const svg = (p) => fs.readFileSync(path.join(HERE, 'assets', p), 'utf8').replace(/<\?xml[^>]*>/, '');
const icon = (n, color) => svg('icons/icon_' + n + '.svg').replace(/#0B0F10/g, color || '#0B0F10');

// ---------- graphic language: circuit lines at 45° with nodes (covers)
function circuit(w, h, seed, op) {
  let s = seed || 7; const r = () => (s = (s * 9301 + 49297) % 233280) / 233280;
  let out = '';
  for (let i = 0; i < 16; i++) {
    let x = w * (0.35 + r() * 0.65), y = h * r(), d = 'M' + x.toFixed(0) + ' ' + y.toFixed(0);
    for (let k = 0; k < 3 + Math.floor(r() * 3); k++) {
      const len = 30 + r() * 140, t = Math.floor(r() * 4);
      if (t === 0) x += len; else if (t === 1) y += len; else if (t === 2) { x += len * 0.7; y -= len * 0.7; } else y -= len;
      d += ' L' + x.toFixed(0) + ' ' + y.toFixed(0);
    }
    out += `<path d="${d}"/><circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="3.2" fill="#19D38A" stroke="none"/>`;
  }
  return `<svg class="circ" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMaxYMid slice"><g fill="none" stroke="#19D38A" stroke-width="1.4" stroke-linecap="round" opacity="${op || 0.55}">${out}</g></svg>`;
}

// ---------- devices
const ipad = (img, cls) => `<div class="ipad ${cls || ''}"><img src="${A('shots/' + img)}"></div>`;
const iphone = (img, cls) => `<div class="iphone ${cls || ''}"><img src="${A('shots/' + img)}"></div>`;

// ---------- page chrome
let pageNo = 0;
function page(body, opt) {
  pageNo++;
  const o = opt || {};
  if (o.dark) return `<section class="page dark">${body}</section>`;
  return `<section class="page">
    <div class="head"><span class="bar"></span><span class="kicker">${esc(o.kicker || '')}</span></div>
    ${body}
    <div class="foot"><img src="${A('brand/logo_horizontal_light-bg.svg')}"><span>${String(pageNo).padStart(2, '0')}</span></div>
  </section>`;
}
const bullets = (arr) => '<ul class="pts">' + arr.map(([b, t]) => `<li><b>${b}</b>${t ? ' ' + t : ''}</li>`).join('') + '</ul>';

// ---------- pages (texts: content.cjs)
const C = require('./content.cjs');
const P = {};
P.cover = () => page(`
  ${circuit(1123, 794, 11, 0.6)}
  <div class="cv">
    <img class="logo" src="${A('brand/logo_horizontal_dark-bg.svg')}">
    <div class="cvmid">
      <div class="gbar"></div>
      <div class="cvk">${C.cover.kicker}</div>
      <h1>${C.cover.title.join('<br>')}</h1>
      <p class="cvs">${C.cover.sub}</p>
    </div>
    <table class="cvt">
      <tr><td>Объект</td><td>${esc(D.object)}</td></tr>
      <tr><td>Заказчик</td><td>${esc(D.client)}</td></tr>
      <tr><td>Предложение</td><td>№ ${esc(D.number)} · ${esc(D.date)}</td></tr>
    </table>
    <div class="cvf">smartbild.pro</div>
  </div>`, { dark: true });

P.why = () => page(`
  <h2>${C.why.h}</h2>
  <p class="lead">${C.why.lead}</p>
  <div class="why">
    <div class="ben">${C.why.items.map(([i, t, d]) => `<div class="b"><div class="ic">${icon(i)}</div><div><b>${t}</b><span>${d}</span></div></div>`).join('')}</div>
    <div class="devs">${ipad('home.jpg', 'big')}${iphone('iphone_home.jpg', 'over')}</div>
  </div>`, { kicker: C.why.kicker });

function tgPhone(chat) {
  return `<div class="iphone tg"><div class="tgh"><img src="${A('brand/symbol_fullcolor_light-bg.svg')}"><div><b>Умный дом</b><span>бот</span></div></div>
    <div class="tgb">${chat.map(([t, m]) => `<div class="msg">${m}<i>${t}</i></div>`).join('')}</div></div>`;
}
function moduleP(k) {
  const m = C.mod(D, k);
  const visual = m.chat ? `${ipad(m.shots[0], 'm1 t')}${tgPhone(m.chat)}` : `${ipad(m.shots[0], 'm1')}${ipad(m.shots[1], 'm2')}`;
  return page(`
    <div class="mod">
      <div class="txt"><h2>${m.h}</h2><p class="lead">${m.lead}</p>${bullets(m.pts)}
        ${m.ba ? `<div class="ba"><div><i>Было</i>${m.ba[0]}</div><div class="arr">→</div><div class="now"><i>Стало</i>${m.ba[1]}</div></div>` : ''}
        ${m.foot ? `<div class="compat">${m.foot}</div>` : ''}</div>
      <div class="vis">${visual}</div>
    </div>`, { kicker: m.kicker });
}
Object.keys(C.modules).forEach((k) => { P[k] = () => moduleP(k); });

P.scenes = () => page(`
  <h2>${C.scenes.h}</h2>
  <p class="lead">${C.scenes.lead}</p>
  <div class="scn">
    <div class="cards">${C.scenes.cards.map(([t, d]) => `<div class="c"><b>${t}</b><span>${d}</span></div>`).join('')}</div>
    <div class="vis1">${ipad('scenes.jpg', 'big')}</div>
  </div>`, { kicker: C.scenes.kicker });

P.process = () => page(`
  <h2>${C.process.h}</h2>
  <p class="lead">${C.process.lead}</p>
  <div class="steps">${C.process.steps.map(([n, t, d]) => `<div class="st"><div class="n">${n}</div><b>${t}</b><span>${d}</span></div>`).join('')}</div>
  <div class="whyus">${C.process.whyus.map(([i, t, d]) => `<div class="b"><div class="ic">${icon(i)}</div><div><b>${t}</b><span>${d}</span></div></div>`).join('')}</div>
  <div class="gar"><div class="ic">${icon('support')}</div><div><b>Гарантия и поддержка</b><span>${esc(C.process.guarantee(D.warranty))}</span></div></div>`,
  { kicker: C.process.kicker });

const rub = C.rub;
P.table = () => {
  const rows = C.readCsv(fs, path.resolve(path.dirname(dealPath), D.table));
  const secs = []; rows.forEach((r) => { if (!secs.includes(r.sec)) secs.push(r.sec); });
  let total = 0, i = 0, body = '';
  secs.forEach((s) => {
    let sub = 0; body += `<tr class="sec"><td colspan="6">${esc(s)}</td></tr>`;
    rows.filter((r) => r.sec === s).forEach((r) => { const sum = r.qty * r.price; sub += sum; i++;
      body += `<tr><td>${i}</td><td>${esc(r.name)}</td><td>${esc(r.unit)}</td><td class="r">${r.qty}</td><td class="r">${rub(r.price)}</td><td class="r">${rub(sum)}</td></tr>`; });
    total += sub; body += `<tr class="sub"><td></td><td colspan="4">Итого: ${esc(s.toLowerCase())}</td><td class="r">${rub(sub)}</td></tr>`;
  });
  return page(`
    <h2>${C.table.h}</h2>
    <p class="lead">${esc(C.calcLead(D))}</p>
    <table class="calc"><thead><tr><th>№</th><th>Наименование</th><th>Ед.</th><th class="r">Кол-во</th><th class="r">Цена</th><th class="r">Сумма</th></tr></thead>
    <tbody>${body}</tbody><tfoot><tr><td></td><td colspan="4">Итого по предложению</td><td class="r">${rub(total)}</td></tr>${D.vat ? `<tr class="vat"><td></td><td colspan="4">В том числе НДС ${D.vat} %</td><td class="r">${rub(C.vatOf(rows, D.vat))}</td></tr>` : ''}</tfoot></table>`,
    { kicker: C.table.kicker });
};

P.contacts = () => page(`
  ${circuit(1123, 794, 29, 0.5)}
  <div class="cv">
    <img class="logo" src="${A('brand/logo_horizontal_dark-bg.svg')}">
    <div class="cvmid">
      <div class="gbar"></div>
      <h1 style="font-size:40pt">${C.contacts.title}</h1>
      <p class="cvs">${C.contacts.sub}</p>
    </div>
    <table class="cvt">
      <tr><td>${esc(D.manager.role)}</td><td>${esc(D.manager.name)}</td></tr>
      <tr><td>Телефон</td><td>${esc(D.manager.phone)}</td></tr>
      <tr><td>Почта</td><td>${esc(D.manager.email)}</td></tr>
      <tr><td>Сайт</td><td>${esc(D.manager.site)}</td></tr>
    </table>
    <div class="cvf">${C.contacts.foot}</div>
  </div>`, { dark: true });

// ---------- assemble
const order = ['cover', 'why'].concat((D.modules || []).filter((m) => P[m])).concat(['process']).concat(D.table ? ['table'] : []).concat(['contacts']);
// Inter is bundled (assets/fonts, SIL OFL) so the PDF looks the same on any server.
const FONTS = path.join(HERE, 'assets', 'fonts');
const fontCss = fs.existsSync(FONTS) ? fs.readdirSync(FONTS).filter((f) => f.endsWith('.woff2')).map((f) => {
  const m = f.match(/^inter-(cyrillic|latin)-(\d+)-normal\.woff2$/); if (!m) return '';
  const range = m[1] === 'cyrillic' ? 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116' : 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD';
  return `@font-face{font-family:Inter;font-style:normal;font-weight:${m[2]};src:url("file://${path.join(FONTS, f)}") format("woff2");unicode-range:${range}}`;
}).join('\n') : '';
const css = fontCss + '\n' + fs.readFileSync(path.join(HERE, 'kp.css'), 'utf8');
const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>КП ${esc(D.number)}</title><style>${css}</style></head><body>${order.map((k) => P[k]()).join('\n')}</body></html>`;
const base = path.join(path.dirname(dealPath), 'КП_' + (D.out || path.basename(dealPath, '.json')));
fs.writeFileSync(base + '.html', html);
(async () => {
  const { chromium } = require('playwright');
  const b = await chromium.launch({ args: ['--disable-dev-shm-usage', '--no-sandbox'], ...(process.env.KP_CHROMIUM_PATH ? { executablePath: process.env.KP_CHROMIUM_PATH } : {}) }); const p = await b.newPage();
  await p.goto('file://' + base + '.html'); await p.waitForTimeout(400);
  await p.pdf({ path: base + '.pdf', width: '297mm', height: '210mm', printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  if (process.argv.includes('--png')) {
    await p.setViewportSize({ width: 1123, height: 794 });
    const n = await p.$$eval('section.page', (s) => s.length);
    for (let i = 0; i < n; i++) { const el = (await p.$$('section.page'))[i]; await el.screenshot({ path: `${base}_${String(i + 1).padStart(2, '0')}.png` }); }
  }
  await b.close();
  console.log('ok:', base + '.pdf', '(' + order.length + ' стр.: ' + order.join(', ') + ')');
})();
