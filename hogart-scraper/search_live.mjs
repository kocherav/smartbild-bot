import { chromium } from "playwright";

const KEYWORD = process.argv[2];
const AUTH_STATE = new URL("./auth.json", import.meta.url).pathname;

if (!KEYWORD) {
  console.error("Usage: node search_live.mjs <keyword>");
  process.exit(1);
}

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext({ storageState: AUTH_STATE });
const page = await context.newPage();

const url = `https://b2b.hogart.ru/products?criteria%5Bkeyword%5D=${encodeURIComponent(KEYWORD)}`;
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });

let rows = [];
for (let attempt = 1; attempt <= 5; attempt++) {
  await page.waitForTimeout(1500);
  rows = await page.evaluate(() => {
    const trs = Array.from(document.querySelectorAll("table tbody tr"));
    return trs.map((tr) => {
      const tds = Array.from(tr.querySelectorAll(":scope > td"));
      const text = (i) => (tds[i] ? tds[i].innerText.trim().replace(/\s+/g, " ") : "");
      const img = tr.querySelector("img");
      return {
        sku: text(0),
        brand: text(2),
        series: text(3),
        name: text(4),
        stock: text(5),
        producerStock: text(7),
        price: text(8),
        imageUrl: img ? img.src : null,
      };
    });
  });
  if (rows.length > 0) break;
  console.error(`attempt ${attempt}: 0 rows, retrying...`);
}

console.log(JSON.stringify({ keyword: KEYWORD, count: rows.length, items: rows }, null, 2));

await browser.close();
