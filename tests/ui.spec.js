const { test, expect } = require("@playwright/test");

test("dashboard loads with operational columns", async ({ page }) => {
  const consoleMessages = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleMessages.push(`${message.type()}: ${message.text()}`);
    }
  });

  const remoteJid = `ui-test-${Date.now()}`;
  await page.request.post("http://127.0.0.1:5000/api/demo/message", {
    data: {
      message_id: `${remoteJid}-mesa`,
      remote_jid: remoteJid,
      text: "Mesa 11",
    },
  });
  await page.request.post("http://127.0.0.1:5000/api/demo/message", {
    data: {
      message_id: `${remoteJid}-pedido`,
      remote_jid: remoteJid,
      text: "Me ve 2 Corona e uma porcao de batata",
    },
  });
  await page.request.post("http://127.0.0.1:5000/api/demo/message", {
    data: {
      message_id: `${remoteJid}-confirma`,
      remote_jid: remoteJid,
      text: "1",
    },
  });

  await page.goto("http://127.0.0.1:5000", { waitUntil: "networkidle" });

  await expect(page.getByRole("heading", { name: "MesaZap Demo" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Bar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cozinha" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Salão" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Caixa" })).toBeVisible();
  await expect(page.getByText("Corona long neck").first()).toBeVisible();
  await expect(page.getByText("Porcao de batata frita").first()).toBeVisible();

  expect(consoleMessages).toEqual([]);
});
