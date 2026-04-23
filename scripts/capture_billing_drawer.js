const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:5000", { waitUntil: "networkidle" });
  await page.click("#billing-pill");
  await page.waitForTimeout(600);
  await page.screenshot({ path: "output/playwright/dashboard_billing_open.png", fullPage: true });
  await browser.close();
  console.log("saved output/playwright/dashboard_billing_open.png");
})();
