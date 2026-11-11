// Картинки для Word-версии КП: фон обложки и последней страницы, экраны модулей в рамках устройств,
// иконки и логотипы в PNG. Берёт их из HTML-версии (все модули): node word_assets.cjs
const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process');
const HERE = __dirname, DEAL = path.resolve(process.argv[2] || path.join(HERE, 'deal_example.json'));
const OUT = process.argv[2] ? path.join(path.dirname(DEAL), '_word_' + path.basename(DEAL, '.json')) : path.join(HERE, 'assets', 'word');
fs.mkdirSync(OUT, { recursive: true });
const tmp = path.join(OUT, '_all.json');
const d = JSON.parse(fs.readFileSync(DEAL, 'utf8'));
d.modules = ['light', 'climate', 'media', 'telegram', 'scenes']; delete d.table; d.out = '_word_src';
fs.writeFileSync(tmp, JSON.stringify(d));
execFileSync('node', [path.join(HERE, 'build.cjs'), tmp], { stdio: 'inherit' });
const html = path.join(OUT, 'КП__word_src.html');
const KEYS = { 'Почему автоматизация': 'why', 'Модуль · Освещение и шторы': 'light', 'Модуль · Климат': 'climate',
  'Модуль · Медиа': 'media', 'Модуль · Уведомления': 'telegram', 'Модуль · Сценарии': 'scenes' };
(async () => {
  const { chromium } = require('playwright');
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1123, height: 794 }, deviceScaleFactor: 2 });
  await p.goto('file://' + html); await p.waitForTimeout(500);
  const pages = await p.$$('section.page');
  // dark pages: the background only (circuit lines), no text
  await p.addStyleTag({ content: '.dark .cv{visibility:hidden}' });
  await pages[0].screenshot({ path: path.join(OUT, 'cover_bg.png') });
  await pages[pages.length - 1].screenshot({ path: path.join(OUT, 'contacts_bg.png') });
  for (const pg of pages) {
    const k = await pg.$eval('.kicker', (e) => e.textContent).catch(() => null);
    const key = KEYS[k]; if (!key) continue;
    const el = await pg.$('.vis, .devs, .vis1');
    if (el) await el.screenshot({ path: path.join(OUT, 'vis_' + key + '.png'), omitBackground: true });
  }
  // icons and logos as PNG
  if (process.argv[2]) { await b.close(); for (const f of [tmp, html, path.join(OUT, 'КП__word_src.pdf')]) fs.rmSync(f, { force: true }); console.log('ok:', OUT); return; }
  const svgs = ['brand/logo_horizontal_light-bg.svg', 'brand/logo_horizontal_dark-bg.svg']
    .concat(fs.readdirSync(path.join(HERE, 'assets', 'icons')).map((f) => 'icons/' + f));
  for (const s of svgs) {
    const src = fs.readFileSync(path.join(HERE, 'assets', s), 'utf8');
    await p.setContent(`<html><body style="margin:0;background:transparent"><div id="x" style="display:inline-block">${src.replace(/<\?xml[^>]*>/, '')}</div></body></html>`);
    const isIcon = s.startsWith('icons/');
    await p.$eval('#x svg', (e, ic) => { if (ic) { e.setAttribute('width', 96); e.setAttribute('height', 96); } else { e.style.height = '120px'; e.style.width = 'auto'; } }, isIcon);
    await (await p.$('#x svg')).screenshot({ path: path.join(OUT, path.basename(s, '.svg') + '.png'), omitBackground: true });
  }
  await b.close();
  for (const f of [tmp, html, path.join(OUT, 'КП__word_src.pdf')]) fs.rmSync(f, { force: true });
  console.log('ok:', fs.readdirSync(OUT).length, 'files in', OUT);
})();
