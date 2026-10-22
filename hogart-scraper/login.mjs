import { chromium } from "playwright";
import { readFileSync } from "fs";

function loadEnv(path) {
  const env = {};
  for (const line of readFileSync(path, "utf-8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const [k, ...rest] = t.split("=");
    env[k.trim()] = rest.join("=").trim();
  }
  return env;
}

const env = loadEnv(new URL("./.env", import.meta.url).pathname);
const PHONE = env.HOGART_PHONE;
const PASSWORD = env.HOGART_PASSWORD;

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext();
const page = await context.newPage();

await page.goto("https://b2b.hogart.ru/", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(2000);
await page.click('text=Войти', { timeout: 15000 });
await page.waitForTimeout(1500);
await page.fill('input[name="identity"]', PHONE);
await page.fill('input[name="password"]', PASSWORD);
await page.click('button[type="submit"]');
await page.waitForTimeout(3000);

await context.storageState({ path: new URL("./auth.json", import.meta.url).pathname });
console.error("Logged in, storage state saved. URL:", page.url());

await browser.close();
