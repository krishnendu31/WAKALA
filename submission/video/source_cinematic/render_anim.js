// Renders an illustration scene of ill.html to PNG frames at 30 fps. Usage: node render_anim.js <scene> <seconds> <outDir> [stillsOnlyAt]
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const [scene, secs, outDir, still] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
(async () => {
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true, args: ["--force-color-profile=srgb"] });
  const p = await b.newPage();
  await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await p.goto(pathToFileURL(path.resolve(__dirname, "ill.html")).href, { waitUntil: "load" });
  await p.waitForFunction(() => window.ready === true);
  const times = still ? still.split(",").map(Number) : Array.from({ length: Math.round(+secs * 30) }, (_, i) => i / 30);
  for (let i = 0; i < times.length; i++) {
    await p.evaluate((s, t) => window.draw(s, t), scene, times[i]);
    await p.screenshot({ path: path.join(outDir, `f${String(i).padStart(5, "0")}.png`) });
  }
  console.log(scene, times.length, "frames");
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
