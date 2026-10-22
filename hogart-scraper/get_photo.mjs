import { chromium } from "playwright";
import { writeFileSync } from "fs";

const SKU = process.argv[2];
const AUTH_STATE = new URL("./auth.json", import.meta.url).pathname;

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext({ storageState: AUTH_STATE });
const page = await context.newPage();

const url = `https://b2b.hogart.ru/products?criteria%5Bkeyword%5D=${encodeURIComponent(SKU)}`;
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });

let imgUrl = null;
for (let attempt = 1; attempt <= 5; attempt++) {
  await page.waitForTimeout(1500);
  imgUrl = await page.evaluate(() => {
    const row = document.querySelector("table tbody tr");
    if (!row) return null;
    const img = row.querySelector("img");
    return img ? img.src : null;
  });
  if (imgUrl) break;
  console.error(`attempt ${attempt}: no image yet, retrying...`);
}

console.error("Image URL:", imgUrl);
await page.screenshot({ path: "/tmp/product-row.png" });

if (imgUrl) {
  writeFileSync("/tmp/image-url.txt", imgUrl);
}

await browser.close();
