// Renders each stage (plan.json) to a 1920x1080 PNG with headless Edge. Usage: node render_stages.js plan.json outDir
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const [planFile, outDir] = process.argv.slice(2);
const plan = JSON.parse(fs.readFileSync(planFile, "utf8"));
fs.mkdirSync(outDir, { recursive: true });
(async () => {
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
    args: ["--allow-file-access-from-files", "--force-color-profile=srgb", "--hide-scrollbars"] });
  const p = await b.newPage();
  await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  const base = pathToFileURL(path.resolve(__dirname, "stage.html")).href;
  for (const shot of plan.shots) {
    const cfg = { ...shot.stage };
    if (cfg.img) cfg.img = pathToFileURL(path.resolve(__dirname, cfg.img)).href;
    const hash = Buffer.from(unescape(encodeURIComponent(JSON.stringify(cfg))), "binary").toString("base64");
    await p.goto(base + "?shot=" + encodeURIComponent(shot.id) + "#" + hash, { waitUntil: "load" }); // query forces a real reload
    await p.waitForSelector("body[data-ready='1']", { timeout: 15000 });
    await p.screenshot({ path: path.join(outDir, shot.id + ".png") });
    console.log("stage", shot.id);
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
