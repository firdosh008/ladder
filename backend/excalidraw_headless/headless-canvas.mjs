/**
 * Opens the mcp_excalidraw web UI in headless Chromium so the canvas WebSocket
 * connects and /health reports websocket_clients >= 1 (needed for PNG export).
 *
 * Environment:
 *   EXCALIDRAW_HEADLESS_URL  Base URL of the canvas (default http://127.0.0.1:3000)
 *
 * Setup once:
 *   cd backend/excalidraw_headless && npm install && npx playwright install chromium
 */
import { chromium } from "playwright";

const url = (process.env.EXCALIDRAW_HEADLESS_URL || "http://127.0.0.1:3000").replace(/\/$/, "");

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  const page = await browser.newPage();
  try {
    await page.goto(url + "/", { waitUntil: "load", timeout: 120_000 });
  } catch (e) {
    console.error("headless-canvas: navigation failed:", e);
    await browser.close();
    process.exit(1);
  }
  // Allow the SPA to open its WebSocket to the same host.
  await new Promise((r) => setTimeout(r, 2500));

  const shutdown = async () => {
    try {
      await browser.close();
    } catch {
      /* ignore */
    }
  };
  process.on("SIGINT", () => void shutdown().finally(() => process.exit(0)));
  process.on("SIGTERM", () => void shutdown().finally(() => process.exit(0)));

  await new Promise(() => {
    /* keep process alive until signal */
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
