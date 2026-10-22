import { chromium } from "playwright";
import { writeFileSync } from "fs";

const SECTION = process.argv[2] || "1053";
const AUTH_STATE = "/home/kocher.av/hogart-scraper/auth.json";

function csvEscape(v) {
  const s = String(v ?? "");
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext({ storageState: AUTH_STATE });
const page = await context.newPage();

async function extractRows() {
  return page.evaluate(() => {
    const trs = Array.from(document.querySelectorAll("table tbody tr"));
    const rows = trs.map((tr) => {
      const tds = Array.from(tr.querySelectorAll(":scope > td"));
      const text = (i) => (tds[i] ? tds[i].innerText.trim().replace(/\s+/g, " ") : "");
      return {
        sku: text(0),
        brand: text(2),
        series: text(3),
        name: text(4),
        stock: text(5),
        stockAlt: text(6),
        producerStock: text(7),
        price: text(8),
      };
    });
    const totalEl = document.body.innerText.match(/Показано[^\n]*из\s*([\d\s]+)\s*товаров/);
    return { rows, totalText: totalEl ? totalEl[1].replace(/\s/g, "") : null };
  });
}

async function scrapePage(pageNum) {
  const url = `https://b2b.hogart.ru/products?criteria%5Bsection%5D=${SECTION}&page=${pageNum}`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });

  // Retry loop: React can briefly re-render the grid empty right after navigation.
  let rows = [];
  let totalText = null;
  for (let attempt = 1; attempt <= 5; attempt++) {
    await page.waitForTimeout(1500);
    const res = await extractRows();
    rows = res.rows;
    totalText = res.totalText || totalText;
    if (rows.length > 0) break;
    console.error(`  page ${pageNum}: attempt ${attempt} got 0 rows, retrying...`);
  }

  return { rows, total: totalText ? parseInt(totalText, 10) : null };
}

console.error("Scraping page 1 to find total count...");
const first = await scrapePage(1);
const perPage = first.rows.length || 20;
const total = first.total || first.rows.length;
const totalPages = Math.max(1, Math.ceil(total / perPage));
console.error(`Total products: ${total}, per page: ${perPage}, total pages: ${totalPages}`);

let allRows = [...first.rows];
for (let p = 2; p <= totalPages; p++) {
  console.error(`Scraping page ${p}/${totalPages}...`);
  const { rows } = await scrapePage(p);
  if (rows.length === 0) {
    console.error(`  page ${p} returned 0 rows after retries, stopping early`);
    break;
  }
  allRows.push(...rows);
}

const header = ["Артикул", "Бренд", "Серия", "Наименование", "Наличие", "Бутово", "Остатки производителя", "Цена"];
const csvLines = [header.join(";")];
for (const r of allRows) {
  csvLines.push([r.sku, r.brand, r.series, r.name, r.stock, r.stockAlt, r.producerStock, r.price].map(csvEscape).join(";"));
}
const outPath = `/home/kocher.av/hogart-scraper/section-${SECTION}.csv`;
writeFileSync(outPath, "﻿" + csvLines.join("\n"), "utf-8");
console.error(`Saved ${allRows.length} rows to ${outPath}`);

await browser.close();
