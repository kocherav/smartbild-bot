// SmartBild — КП в Word (A4 альбом), те же модули и тексты, что в PDF.
// node build_docx.cjs deal_example.json  →  КП_<сделка>.docx
// Картинки берутся из assets/word (их делает word_assets.cjs). Шрифт Arial — по брендбуку для офисных документов.
const fs = require('fs'), path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  AlignmentType, VerticalAlign, PageOrientation, Footer, PageNumber, LevelFormat, TabStopType,
  HorizontalPositionRelativeFrom, VerticalPositionRelativeFrom, TableLayoutType,
} = require('docx');
const C = require('./content.cjs');
const HERE = __dirname;
const dealPath = path.resolve(process.argv[2] || path.join(HERE, 'deal_example.json'));
const D = JSON.parse(fs.readFileSync(dealPath, 'utf8'));
const DW = path.join(path.dirname(dealPath), '_word_' + path.basename(dealPath, '.json'));
if (path.resolve(dealPath) !== path.join(HERE, 'deal_example.json'))   // this deal's screens, as its PDF shows them
  require('child_process').execFileSync('node', [path.join(HERE, 'word_assets.cjs'), dealPath], { stdio: 'inherit' });
const W = (f) => (fs.existsSync(path.join(DW, f)) ? path.join(DW, f) : path.join(HERE, 'assets', 'word', f));

const GREEN = '19D38A', BLACK = '0B0F10', MID = '5B6168', LGRAY = 'E6E8EB', TXT = '2B3036', SOFT = 'F4F6F7';
const FONT = 'Arial';
const PAGE_W = 16838, PAGE_H = 11906, ML = 850, MR = 850, CW = PAGE_W - ML - MR; // content width, DXA

// ---------- primitives
const run = (text, o) => new TextRun(Object.assign({ text, font: FONT }, o || {}));
const P = (children, o) => new Paragraph(Object.assign({ children: [].concat(children) }, o || {}));
const sp = (after) => P([], { spacing: { before: 0, after: after || 0 } });
const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const noBorders = { top: none, bottom: none, left: none, right: none, insideHorizontal: none, insideVertical: none };
const cellNone = { top: none, bottom: none, left: none, right: none };
function pngSize(f) { const b = fs.readFileSync(f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function img(f, widthPx, o) {
  const s = pngSize(W(f));
  return new ImageRun(Object.assign({ type: 'png', data: fs.readFileSync(W(f)), transformation: { width: widthPx, height: Math.round(widthPx * s.h / s.w) } }, o || {}));
}
function cell(children, width, o) {
  return new TableCell(Object.assign({ children: [].concat(children), width: { size: width, type: WidthType.DXA }, borders: cellNone,
    margins: { top: 0, bottom: 0, left: 0, right: 0 } }, o || {}));
}
function table(widths, rows, o) {
  return new Table(Object.assign({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    layout: TableLayoutType.FIXED, borders: noBorders, rows }, o || {}));
}

// ---------- text blocks in the brand style
const kicker = (t) => P([run('—— ', { color: GREEN, bold: true, size: 16 }), run(t.toUpperCase(), { color: GREEN, size: 15, characterSpacing: 30 })], { spacing: { after: 200 } });
const h2 = (t, size) => P(run(t, { bold: true, size: size || 44, color: BLACK }),
  { spacing: { after: 160 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: LGRAY, space: 8 } }, keepNext: true });
const lead = (t, after) => P(run(t, { size: 22, color: TXT }), { spacing: { after: after == null ? 220 : after, line: 300 } });
const bullet = ([b, t]) => P([run(b, { bold: true, size: 19, color: BLACK }), run(t ? ' ' + t : '', { size: 19, color: TXT })],
  { numbering: { reference: 'pts', level: 0 }, spacing: { after: 110, line: 276 } });
const small = (t, o) => P(run(t, Object.assign({ size: 15, color: MID }, o || {})));

function beforeAfter(ba, width) {
  const a = Math.round((width - 500) / 2);
  const box = (label, text, dark) => cell([
    P(run(label.toUpperCase(), { size: 13, bold: true, color: dark ? GREEN : MID, characterSpacing: 20 }), { spacing: { after: 60 } }),
    P(run(text, { size: 18, color: dark ? 'FFFFFF' : '4A5057' }), { spacing: { line: 264 } })],
  a, { shading: { type: ShadingType.CLEAR, fill: dark ? BLACK : SOFT, color: 'auto' }, margins: { top: 140, bottom: 140, left: 180, right: 180 }, verticalAlign: VerticalAlign.CENTER });
  return table([a, 500, width - a - 500], [new TableRow({ children: [box('Было', ba[0], false),
    cell(P(run('→', { size: 32, color: GREEN }), { alignment: AlignmentType.CENTER }), 500, { verticalAlign: VerticalAlign.CENTER }),
    box('Стало', ba[1], true)] })]);
}

// ---------- footer: logo left, page number right
const footer = new Footer({ children: [P([img('logo_horizontal_light-bg.png', 68),
  new TextRun({ children: ['\t', PageNumber.CURRENT], font: FONT, size: 15, color: MID })],
{ tabStops: [{ type: TabStopType.RIGHT, position: CW }] })] });
const emptyFooter = new Footer({ children: [P([])] });

const props = (o) => ({ page: { size: { width: 11906, height: 16838, orientation: PageOrientation.LANDSCAPE },
  margin: Object.assign({ top: 680, bottom: 760, left: ML, right: MR, footer: 340, header: 300 }, o || {}) } });
const inner = (children) => ({ properties: props(), footers: { default: footer }, children });

// ---------- dark pages (cover, contacts): background picture behind the text
function darkPage(bg, body) {
  const back = P(img(bg, 1123, { floating: { horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
    verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: 0 }, behindDocument: true, allowOverlap: true } }));
  return { properties: props({ top: 870, left: 960, right: 960, bottom: 600 }), footers: { default: emptyFooter },
    children: [back, P(img('logo_horizontal_dark-bg.png', 150))].concat(body) };
}
function darkFields(rows) {
  const lineB = { top: { style: BorderStyle.SINGLE, size: 4, color: '2A3035' }, bottom: none, left: none, right: none };
  return table([2600, 6400], rows.map(([k, v]) => new TableRow({ children: [
    cell(P(run(k, { size: 19, color: '7F8891' }), { spacing: { before: 80, after: 80 } }), 2600, { borders: lineB }),
    cell(P(run(v, { size: 19, color: 'FFFFFF' }), { spacing: { before: 80, after: 80 } }), 6400, { borders: lineB })] })));
}

// ---------- pages
const S = {};
S.cover = () => darkPage('cover_bg.png', [
  sp(2600),
  P(run('━━━', { color: GREEN, size: 20 }), { spacing: { after: 200 } }),
  P(run(C.cover.kicker.toUpperCase(), { color: GREEN, bold: true, size: 18, characterSpacing: 40 }), { spacing: { after: 200 } }),
  ...C.cover.title.map((t) => P(run(t, { bold: true, size: 80, color: 'FFFFFF' }), { spacing: { after: 0, line: 216, lineRule: 'auto' } })),
  P(run(C.cover.sub, { size: 26, color: 'B9C0C7' }), { spacing: { before: 280, after: 560 } }),
  darkFields([['Объект', D.object], ['Заказчик', D.client], ['Предложение', `№ ${D.number} · ${D.date}`]]),
  P(run('smartbild.pro', { size: 15, color: '6B747C', characterSpacing: 30 }), { spacing: { before: 400 } }),
]);

S.why = () => {
  const bw = 3500, cells = C.why.items.map(([i, t, d]) => cell([
    P(img('icon_' + i + '.png', 26), { spacing: { after: 80 } }),
    P(run(t, { bold: true, size: 20, color: BLACK }), { spacing: { after: 40 } }),
    P(run(d, { size: 17, color: '4A5057' }), { spacing: { line: 264 } })], bw, { margins: { top: 0, bottom: 240, left: 0, right: 220 } }));
  const grid = table([bw, bw], [0, 2, 4].map((k) => new TableRow({ children: [cells[k], cells[k + 1]] })));
  return inner([kicker(C.why.kicker), h2(C.why.h), lead(C.why.lead, 260),
    table([7300, CW - 7300], [new TableRow({ children: [cell(grid, 7300), cell(P(img('vis_why.png', 500), { alignment: AlignmentType.RIGHT }), CW - 7300)] })])]);
};

function moduleS(k) {
  const m = C.mod(D, k), LW = 6200;
  const left = [h2(m.h, 40), lead(m.lead)].concat(m.pts.map(bullet));
  if (m.ba) left.push(sp(120), beforeAfter(m.ba, LW - 200));
  if (m.foot) left.push(sp(260), P(run(m.foot, { size: 15, color: MID }), { border: { top: { style: BorderStyle.SINGLE, size: 4, color: LGRAY, space: 8 } } }));
  return inner([kicker(m.kicker), table([LW, CW - LW], [new TableRow({ children: [
    cell(left, LW, { margins: { top: 0, bottom: 0, left: 0, right: 200 } }),
    cell(P(img('vis_' + k + '.png', 545), { alignment: AlignmentType.RIGHT }), CW - LW)] })])]);
}
Object.keys(C.modules).forEach((k) => { S[k] = () => moduleS(k); });

S.scenes = () => {
  const cw = 3300, card = ([t, d]) => cell([P(run(t, { bold: true, size: 20 }), { spacing: { after: 40 } }), P(run(d, { size: 17, color: '4A5057' }), { spacing: { line: 264 } })], cw,
    { margins: { top: 140, bottom: 160, left: 160, right: 160 },
      borders: { top: { style: BorderStyle.SINGLE, size: 18, color: GREEN }, bottom: { style: BorderStyle.SINGLE, size: 4, color: LGRAY },
        left: { style: BorderStyle.SINGLE, size: 4, color: LGRAY }, right: { style: BorderStyle.SINGLE, size: 4, color: LGRAY } } });
  const gap = cell(P([]), 200), vgap = new TableRow({ children: [cell(sp(0), cw), gap, cell(sp(0), cw)], height: { value: 200, rule: 'exact' } });
  const rows = [];
  [0, 2, 4].forEach((k, j) => { if (j) rows.push(vgap); rows.push(new TableRow({ children: [card(C.scenes.cards[k]), cell(P([]), 200), card(C.scenes.cards[k + 1])] })); });
  const grid = table([cw, 200, cw], rows);
  return inner([kicker(C.scenes.kicker), h2(C.scenes.h), lead(C.scenes.lead, 260),
    table([7000, CW - 7000], [new TableRow({ children: [cell(grid, 7000), cell(P(img('vis_scenes.png', 540), { alignment: AlignmentType.RIGHT }), CW - 7000)] })])]);
};

S.process = () => {
  const sw = Math.floor((CW - 4 * 240) / 5), steps = [];
  C.process.steps.forEach(([n, t, d], i) => {
    if (i) steps.push(cell(P([]), 240));
    steps.push(cell([P(run(n, { size: 52, color: GREEN }), { spacing: { before: 160, after: 120 } }), P(run(t, { bold: true, size: 20 }), { spacing: { after: 40 } }),
      P(run(d, { size: 17, color: '4A5057' }), { spacing: { line: 264 } })], sw, { borders: { top: { style: BorderStyle.SINGLE, size: 12, color: BLACK }, bottom: none, left: none, right: none } }));
  });
  const ww = Math.floor((CW - 2 * 300) / 3), why = [];
  C.process.whyus.forEach(([i, t, d], k) => {
    if (k) why.push(cell(P([]), 300));
    why.push(cell([P(img('icon_' + i + '.png', 26), { spacing: { after: 80 } }), P(run(t, { bold: true, size: 20 }), { spacing: { after: 40 } }),
      P(run(d, { size: 17, color: '4A5057' }), { spacing: { line: 264 } })], ww));
  });
  const gar = table([900, CW - 900], [new TableRow({ children: [
    cell(P(img('icon_support.png', 28), { alignment: AlignmentType.CENTER }), 900, { verticalAlign: VerticalAlign.CENTER, shading: { type: ShadingType.CLEAR, fill: SOFT, color: 'auto' }, margins: { top: 200, bottom: 200, left: 200, right: 0 } }),
    cell([P(run('Гарантия и поддержка', { bold: true, size: 20 }), { spacing: { after: 40 } }), P(run(C.process.guarantee(D.warranty), { size: 18, color: '4A5057' }))], CW - 900,
      { verticalAlign: VerticalAlign.CENTER, shading: { type: ShadingType.CLEAR, fill: SOFT, color: 'auto' }, margins: { top: 200, bottom: 200, left: 200, right: 200 } })] })]);
  return inner([kicker(C.process.kicker), h2(C.process.h), lead(C.process.lead, 300),
    table(steps.map((_, i) => (i % 2 ? 240 : sw)), [new TableRow({ children: steps })]),
    sp(500), P([], { border: { top: { style: BorderStyle.SINGLE, size: 4, color: LGRAY, space: 1 } }, spacing: { after: 300 } }),
    table(why.map((_, i) => (i % 2 ? 300 : ww)), [new TableRow({ children: why })]),
    sp(400), gar]);
};

S.table = () => {
  const rows = C.readCsv(fs, path.resolve(path.dirname(dealPath), D.table));
  const secs = []; rows.forEach((r) => { if (!secs.includes(r.sec)) secs.push(r.sec); });
  const cw = [600, CW - 600 - 1000 - 1200 - 2000 - 2000, 1000, 1200, 2000, 2000];
  const line = (c) => ({ top: none, left: none, right: none, bottom: { style: BorderStyle.SINGLE, size: c === 'thick' ? 12 : 4, color: c === 'thick' ? BLACK : LGRAY } });
  const tc = (t, i, o) => cell(P(run(String(t), Object.assign({ size: 18 }, o && o.run)), { alignment: i >= 3 ? AlignmentType.RIGHT : AlignmentType.LEFT }),
    cw[i], Object.assign({ borders: line(), margins: { top: 80, bottom: 80, left: 100, right: 100 } }, o && o.cell));
  const out = [new TableRow({ tableHeader: true, children: ['№', 'Наименование', 'Ед.', 'Кол-во', 'Цена', 'Сумма'].map((h, i) =>
    tc(h.toUpperCase(), i, { run: { size: 14, color: MID, characterSpacing: 20 }, cell: { borders: line('thick') } })) })];
  let total = 0, n = 0;
  secs.forEach((s) => {
    out.push(new TableRow({ children: [cell(P(run(s.toUpperCase(), { bold: true, size: 16, color: GREEN, characterSpacing: 20 })), CW,
      { columnSpan: 6, margins: { top: 200, bottom: 60, left: 100, right: 100 } })] }));
    let sub = 0;
    rows.filter((r) => r.sec === s).forEach((r) => { const sum = r.qty * r.price; sub += sum; n++;
      out.push(new TableRow({ children: [tc(n, 0), tc(r.name, 1), tc(r.unit, 2), tc(r.qty, 3), tc(C.rub(r.price), 4), tc(C.rub(sum), 5)] })); });
    total += sub;
    const shade = { shading: { type: ShadingType.CLEAR, fill: SOFT, color: 'auto' } };
    out.push(new TableRow({ children: [tc('', 0, { cell: shade }), cell(P(run('Итого: ' + s.toLowerCase(), { bold: true, size: 18 })), cw[1] + cw[2] + cw[3] + cw[4],
      Object.assign({ columnSpan: 4, borders: line(), margins: { top: 80, bottom: 80, left: 100, right: 100 } }, shade)), tc(C.rub(sub), 5, { run: { bold: true }, cell: shade })] }));
  });
  const topB = { top: { style: BorderStyle.SINGLE, size: 12, color: BLACK }, bottom: none, left: none, right: none };
  out.push(new TableRow({ children: [cell(P([]), cw[0], { borders: topB }),
    cell(P(run('Итого по предложению', { bold: true, size: 22 })), cw[1] + cw[2] + cw[3] + cw[4], { columnSpan: 4, borders: topB, margins: { top: 160, bottom: 80, left: 100, right: 100 } }),
    cell(P(run(C.rub(total), { bold: true, size: 22 }), { alignment: AlignmentType.RIGHT }), cw[5], { borders: topB, margins: { top: 160, bottom: 80, left: 100, right: 100 } })] }));
  if (D.vat) out.push(new TableRow({ children: [cell(P([]), cw[0]),
    cell(P(run(`В том числе НДС ${D.vat} %`, { size: 18, color: '4A5057' })), cw[1] + cw[2] + cw[3] + cw[4], { columnSpan: 4, margins: { top: 20, bottom: 80, left: 100, right: 100 } }),
    cell(P(run(C.rub(C.vatOf(rows, D.vat)), { size: 18, color: '4A5057' }), { alignment: AlignmentType.RIGHT }), cw[5], { margins: { top: 20, bottom: 80, left: 100, right: 100 } })] }));
  return inner([kicker(C.table.kicker), h2(C.table.h), lead(C.calcLead(D), 200), table(cw, out)]);
};

S.contacts = () => darkPage('contacts_bg.png', [
  sp(3000),
  P(run('━━━', { color: GREEN, size: 20 }), { spacing: { after: 240 } }),
  P(run(C.contacts.title, { bold: true, size: 72, color: 'FFFFFF' })),
  P(run(C.contacts.sub, { size: 26, color: 'B9C0C7' }), { spacing: { before: 200, after: 560 } }),
  darkFields([[D.manager.role, D.manager.name], ['Телефон', D.manager.phone], ['Почта', D.manager.email], ['Сайт', D.manager.site]]),
  P(run(C.contacts.foot, { size: 15, color: '6B747C', characterSpacing: 30 }), { spacing: { before: 400 } }),
]);

// ---------- assemble
const order = ['cover', 'why'].concat((D.modules || []).filter((m) => S[m])).concat(['process']).concat(D.table ? ['table'] : []).concat(['contacts']);
const doc = new Document({
  creator: 'SmartBild.pro', title: 'Коммерческое предложение ' + D.number,
  styles: { default: { document: { run: { font: FONT, size: 20, color: BLACK } } } },
  numbering: { config: [{ reference: 'pts', levels: [{ level: 0, format: LevelFormat.BULLET, text: '●', alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 340, hanging: 300 } }, run: { color: GREEN, size: 14, font: FONT } } }] }] },
  sections: order.map((k) => S[k]()),
});
const out = path.join(path.dirname(dealPath), 'КП_' + (D.out || path.basename(dealPath, '.json')) + '.docx');
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(out, b); console.log('ok:', out, '(' + order.length + ' стр.: ' + order.join(', ') + ')'); });
