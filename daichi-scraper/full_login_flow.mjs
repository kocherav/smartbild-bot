import { chromium } from "playwright";
import { existsSync, readFileSync, unlinkSync } from "fs";

const PHONE = process.argv[2];
const FINAL_STATE = new URL("./auth.json", import.meta.url).pathname;
const CAPTCHA_ANSWER_FILE = "/tmp/daichi-captcha-answer.txt";
const CODE_ANSWER_FILE = "/tmp/daichi-code-answer.txt";
const CAPTCHA_SHOT = "/tmp/daichi-captcha.png";

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForFile(path, label, maxSec) {
  if (existsSync(path)) unlinkSync(path);
  console.error(`Waiting for ${label} at ${path} (up to ${maxSec}s)...`);
  for (let i = 0; i < maxSec; i++) {
    if (existsSync(path)) {
      const val = readFileSync(path, "utf-8").trim();
      console.error(`Got ${label}: ${val}`);
      return val;
    }
    await sleep(1000);
  }
  return null;
}

const browser = await chromium.launch({
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox", "--single-process"],
});
const context = await browser.newContext();
const page = await context.newPage();

console.error("Navigating to auth page...");
await page.goto("https://daichi.business/auth/", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(2000);

console.error("Filling phone and submitting...");
// The field already has a fixed "+7" (Russia) country-code prefix picker —
// fill only the local 10-digit number, not the leading +7, or it double-counts.
const localNumber = PHONE.replace(/^\+?7/, "").replace(/\D/g, "");
console.error("Local number to fill:", localNumber);
await page.fill('#phone', localNumber);
const displayedValue = await page.inputValue('#phone');
const displayedDigits = displayedValue.replace(/\D/g, "");
const fullExpectedDigits = PHONE.replace(/\D/g, ""); // includes leading 7/8 country code
if (!displayedDigits.endsWith(localNumber) || displayedDigits.length < localNumber.length) {
  console.error(`Phone field mismatch: expected to end with ${localNumber}, field shows ${displayedValue} (digits ${displayedDigits}). Aborting.`);
  await browser.close();
  process.exit(1);
}
console.error("Phone field confirmed:", displayedValue);
await page.click('input[name="Login"]');
await page.waitForTimeout(3000);

const captchaFrame = page.frameLocator('iframe[src*="smartcaptcha.yandexcloud.net/advanced"]');
const captchaInput = captchaFrame.locator('input[placeholder]');

let hasCaptcha = false;
try {
  await captchaInput.waitFor({ timeout: 8000 });
  hasCaptcha = true;
} catch {
  hasCaptcha = false;
}

if (hasCaptcha) {
  console.error("Captcha appeared, screenshotting...");
  await page.screenshot({ path: CAPTCHA_SHOT });
  console.error("CAPTCHA_SHOT_READY:" + CAPTCHA_SHOT);

  const answer = await waitForFile(CAPTCHA_ANSWER_FILE, "captcha answer", 180);
  if (!answer) {
    console.error("Timed out waiting for captcha answer.");
    await browser.close();
    process.exit(1);
  }

  await captchaInput.fill(answer);
  await page.waitForTimeout(300);
  await captchaFrame.locator('button:has-text("Submit")').click();
  console.error("Clicked captcha submit.");
  await page.waitForTimeout(3000);
}

let bodyText = await page.evaluate(() => document.body.innerText);
if (!/Введите код/.test(bodyText)) {
  console.error("Did not reach code-entry screen. Current body text:\n" + bodyText.slice(0, 1000));
  await page.screenshot({ path: "/tmp/daichi-unexpected-state.png" });
  await browser.close();
  process.exit(1);
}

console.error("CODE_SCREEN_READY");
await page.screenshot({ path: "/tmp/daichi-code-screen.png" });

const code = await waitForFile(CODE_ANSWER_FILE, "sms code", 180);
if (!code) {
  console.error("Timed out waiting for sms code.");
  await browser.close();
  process.exit(1);
}

// Find the confirmation code input (not phone, not search, not hidden)
const codeInputs = await page.$$('input[type="text"]:visible, input:not([type]):visible');
let codeFilled = false;
for (const inp of codeInputs) {
  const name = await inp.getAttribute('name');
  const id = await inp.getAttribute('id');
  if (id === 'phone' || name === 'q') continue;
  await inp.fill(code);
  codeFilled = true;
  console.error("Filled code into input name=" + name + " id=" + id);
  break;
}
if (!codeFilled) {
  console.error("Could not find code input field.");
  await page.screenshot({ path: "/tmp/daichi-code-fill-fail.png" });
  await browser.close();
  process.exit(1);
}

await page.waitForTimeout(500);
// Try pressing Enter, and also look for a submit/confirm button
await page.keyboard.press('Enter').catch(() => {});
await page.waitForTimeout(2500);

const finalBodyText = await page.evaluate(() => document.body.innerText.slice(0, 1200));
console.error("Body text after code submit:\n" + finalBodyText);
await page.screenshot({ path: "/tmp/daichi-final-state.png" });

await context.storageState({ path: FINAL_STATE });
console.error("Saved final state to " + FINAL_STATE);

await browser.close();
