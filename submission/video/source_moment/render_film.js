// Renders film.html frames [from, to) at 30 fps and pipes them into ffmpeg as one H.264 segment.
// Usage: node render_film.js <fromFrame> <toFrame> <out.mp4>   |   node render_film.js still <t1,t2,...> <outDir>
const puppeteer = require("puppeteer-core");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const { pathToFileURL } = require("url");
const [a, b, out] = process.argv.slice(2);
(async () => {
  const br = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
    args: ["--allow-file-access-from-files", "--force-color-profile=srgb", "--disable-gpu-vsync"] });
  const p = await br.newPage();
  await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await p.goto(pathToFileURL(path.resolve(__dirname, "film.html")).href, { waitUntil: "load" });
  await p.waitForFunction(() => window.ready === true, { timeout: 20000 });
  const grab = async (T) => { await p.evaluate((t) => window.draw(t), T); return p.screenshot({ type: "jpeg", quality: 95 }); };
  if (a === "still") {
    fs.mkdirSync(out, { recursive: true });
    for (const T of b.split(",").map(Number)) fs.writeFileSync(path.join(out, `t${T.toFixed(2)}.jpg`), await grab(T));
  } else {
    const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", "30", "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p", "-r", "30", out], { stdio: ["pipe", "inherit", "inherit"] });
    for (let f = +a; f < +b; f++) { const buf = await grab(f / 30); if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r)); }
    ff.stdin.end(); await new Promise((r) => ff.on("close", r));
    console.log("segment", a, b, out);
  }
  await br.close();
})().catch((e) => { console.error(e); process.exit(1); });
