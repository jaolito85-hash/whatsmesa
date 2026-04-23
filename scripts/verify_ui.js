const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleMessages = [];
  const pageErrors = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleMessages.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const response = await page.goto("http://127.0.0.1:5000", {
    waitUntil: "networkidle",
  });
  const bodyText = await page.locator("body").innerText();
  const title = await page.title();
  const keyElements = await page.locator("text=MesaZap Demo").count();

  await browser.close();

  console.log(
    JSON.stringify(
      {
        status: response ? response.status() : null,
        title,
        bodyLength: bodyText.trim().length,
        keyElements,
        consoleMessages,
        pageErrors,
      },
      null,
      2,
    ),
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});

