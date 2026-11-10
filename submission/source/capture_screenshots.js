// Provenance: the script the previous Phase 8 session used to capture submission/screenshots (real backend calls,
// Edge via puppeteer-core). The officer password is read from a local file outside the repo and is never stored here.
// Genuine screenshots of the running WAKALA prototype (synthetic data), captured with headless Edge.
// Every state shown is produced by real backend calls in this script; nothing is mocked or edited.
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");

const API = "http://127.0.0.1:8000";
const WEB = "http://localhost:5173";
const OUT = process.argv[2];
const PW = fs.readFileSync(path.join(__dirname, "..", "off.txt"), "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });

const j = async (p, method = "GET", body, token) => {
  const r = await fetch(API + p, { method, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${JSON.stringify(t).slice(0, 200)}`);
  return t;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = [];

(async () => {
  const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
    args: ["--no-first-run", "--disable-extensions"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  const shot = async (name, url, prep, clipSel, scroll) => {
    if (url) { await page.goto(WEB + url, { waitUntil: "networkidle0" }); }
    await sleep(2500);
    if (prep) { await prep(); await sleep(1500); }
    await page.evaluate((sc) => {
      if (sc === "top") { window.scrollTo(0, 0); document.querySelector("main")?.scrollTo?.(0, 0); }
      else if (sc) { const h = [...document.querySelectorAll("p,h2,h3")].find((e) => e.textContent.trim() === sc); h?.scrollIntoView({ block: "start" }); window.scrollBy(0, -90); }
    }, scroll);
    await sleep(600);
    const file = path.join(OUT, name + ".png");
    if (clipSel) {
      const el = await page.$(clipSel);
      await el.screenshot({ path: file });
    } else {
      await page.screenshot({ path: file });
    }
    log.push({ name, url: url || "(same page)", captured_at: new Date().toISOString() });
    console.log("captured", name);
  };
  const click = async (text, sel = "button") => {
    const ok = await page.evaluate((t, s) => { const b = [...document.querySelectorAll(s)].find((e) => e.textContent.includes(t)); if (b) { b.click(); return true; } return false; }, text, sel);
    if (!ok) throw new Error("not found: " + text);
  };

  // --- real demo flow -----------------------------------------------------------------------
  await j("/api/portal/demo/reset", "POST");
  const s1 = await j("/api/portal/requests", "POST", {});
  const s2 = await j("/api/portal/scenes/incident", "POST");
  const caseId = s2.case_id, other = s2.unrelated_case_id;
  await shot("01_portal_blocked", "/portal", null, null, "top");

  const tok = (await j("/api/officer/session", "POST", { officer_id: "OFF-0101", password: PW })).token;
  await page.evaluateOnNewDocument((t) => sessionStorage.setItem("wakala.officer.token", t), tok);
  await shot("02_soc_incident", "/soc", async () => { await click("Incidents", "[role=tab]"); await sleep(1200); await click(caseId); }, null, "Investigation");

  const inc = (await j("/api/officer/incidents", "GET", undefined, tok)).find((i) => i.case_id === caseId && i.status === "open");
  await j(`/api/officer/incidents/${inc.incident_id}/status`, "POST", { status: "under_review", note: "triage" }, tok);
  await j(`/api/officer/cases/${caseId}/reassign`, "POST", { task: "insurance_eligibility_check", receiving_agent_id: "AGT-INS-002", note: "standby" }, tok);
  await j(`/api/officer/cases/${caseId}/resume`, "POST", { note: "affected authority contained" }, tok);
  await j(`/api/portal/cases/${caseId}/continue`, "POST", {});
  const apr = (await j("/api/officer/approvals", "GET", undefined, tok)).find((a) => a.case_id === caseId && a.status === "pending");
  const ap = await j(`/api/officer/approvals/${apr.approval_id}/approve`, "POST", { note: "re-authorized" }, tok);
  await j(`/api/officer/incidents/${inc.incident_id}/status`, "POST", { status: "resolved", note: "recovered" }, tok);
  const done = await j(`/api/portal/cases/${caseId}/continue`, "POST", {});
  const unrelated = await j(`/api/portal/cases/${other}/continue`, "POST", {});
  await shot("03_portal_recovered", "/portal", null, null, "top");
  await shot("04_receipt", null, async () => { await click("My AI Activity"); }, "[role=dialog] > div");
  await shot("05_case_view", `/delegation?case=${caseId}`);
  await shot("06_attack_lab", "/attack-lab", async () => { await click("Run all 8"); await sleep(12000); });
  await shot("07_document_shield", "/documents", async () => { await click("hidden white-text"); await sleep(4000); });
  await shot("08_evidence", "/evidence");
  await shot("09_shadow", "/shadow", async () => { await click("Run shadow"); await sleep(6000); });
  await shot("10_soc_watch", "/soc", async () => { await click("Behaviour Watch", "[role=tab]"); });

  const final = await j(`/api/portal/cases/${caseId}`);
  const audit = await j("/api/audit/integrity");
  fs.writeFileSync(path.join(OUT, "CAPTURE_LOG.json"), JSON.stringify({
    note: "Genuine screenshots of the locally running WAKALA prototype with synthetic data. Produced by real backend calls in shots.js; not edited.",
    case_id: caseId, unrelated_case_id: other, first_case_id: s1.case_id, approval_executed: ap.executed,
    final_state: final.state, recovery_status: final.recovery_status, continue_status: done.status, unrelated_status: unrelated.status,
    audit_chain_valid: audit.valid, audit_events: audit.event_count, shots: log }, null, 1));
  console.log(JSON.stringify({ caseId, final: final.state, recovery: final.recovery_status, unrelated: unrelated.status, audit: audit.valid }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
