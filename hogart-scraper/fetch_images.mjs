import { chromium } from "playwright";

const url = process.argv[2];

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext({
  userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
});
const page = await context.newPage();
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(4000);

const imgs = await page.evaluate(() => {
  const all = Array.from(document.querySelectorAll("img"));
  return all.map(img => ({
    src: img.currentSrc || img.src,
    naturalWidth: img.naturalWidth,
    naturalHeight: img.naturalHeight,
    alt: img.alt,
  })).filter(i => i.src && i.src.startsWith("http"));
});
console.log(JSON.stringify(imgs, null, 2));
await page.screenshot({ path: "/tmp/fetch-images-debug.png", fullPage: false });

await browser.close();
