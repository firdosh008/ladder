/**
 * Keeps a headless Chromium tab on the Excalidraw canvas so the server
 * reports websocket_clients >= 1 (PNG export requires it).
 *
 * Env (set by the Python backend):
 *   EXCALIDRAW_HEADLESS_URL — canvas HTTP root, e.g. http://127.0.0.1:3000
 */

import { chromium } from "playwright";

const base = (process.env.EXCALIDRAW_HEADLESS_URL || "http://127.0.0.1:3000").replace(
  /\/$/,
  "",
);
const url = `${base}/`;

let browser;

async function main() {
  browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120_000 });
  console.error(`[headless-canvas] WebSocket client active for ${url}`);
}

let closing = false;
async function shutdown() {
  if (closing) return;
  closing = true;
  try {
    if (browser) await browser.close();
  } finally {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

main().catch((err) => {
  console.error("[headless-canvas]", err);
  process.exit(1);
});
