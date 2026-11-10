// Viewport capture of the real Government AI Portal for the recovered incident case (read-only; no state change).
const puppeteer = require("puppeteer-core");
const fs = require("fs");
(async () => {
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true, args: ["--hide-scrollbars"] });
  const p = await b.newPage(); await p.setViewport({ width: 1440, height: 810, deviceScaleFactor: 4 / 3 });
  await p.goto("http://127.0.0.1:5173/portal", { waitUntil: "networkidle0" });
  await p.waitForFunction(() => document.body.innerText.includes("recovered after a security review"), { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2500));
  await p.evaluate(() => { window.scrollTo(0, 0); document.querySelector("main")?.scrollTo?.(0, 0); });
  await p.mouse.move(1439, 809); await new Promise((r) => setTimeout(r, 800));
  await p.screenshot({ path: "capture/p17_portal_recovered.png" });
  const caseId = await p.evaluate(() => (document.body.innerText.match(/CASE-[0-9A-F]{8}/) || [])[0]);
  const log = JSON.parse(fs.readFileSync("capture/run_log.json", "utf8"));
  log.shots.p17_portal_recovered = { file: "p17_portal_recovered.png", css: { w: 1440, h: 810 }, scale: 4 / 3, boxes: {}, at: new Date().toISOString(), url: "/portal", case_id: caseId };
  fs.writeFileSync("capture/run_log.json", JSON.stringify(log, null, 1));
  console.log("portal case", caseId);
  await b.close();
})();
