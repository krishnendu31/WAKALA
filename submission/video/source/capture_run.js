// Captures ONE real guided-demo run of the running WAKALA prototype (headless Edge, puppeteer-core).
// Every screenshot is a genuine rendered application state reached through the real UI and APIs.
// The officer password is read from a local file passed as an argument and typed into the sign-in form.
// It is never printed, logged or captured: the only screenshot of the sign-in form is taken before typing.
//
// Usage: node capture_run.js <outDir> <passwordFile>
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");

const WEB = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8000";
const [OUT, PWFILE] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const say = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);
const getJSON = async (p) => (await fetch(API + p)).json();

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
    args: ["--no-first-run", "--disable-extensions", "--hide-scrollbars", "--force-color-profile=srgb"],
  });
  const page = await browser.newPage();
  // 1440x810 CSS layout rendered at 4/3 device scale = crisp 1920x1080 pixels per viewport.
  await page.setViewport({ width: 1440, height: 810, deviceScaleFactor: 4 / 3 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shots = {};

  const waitText = (t, ms = 30000) => page.waitForFunction((x) => document.body.innerText.includes(x), { timeout: ms }, t);
  const click = async (t, ms = 30000) => {
    await page.waitForFunction((x) => [...document.querySelectorAll("button,a")].some((b) => b.textContent.trim().includes(x) && !b.disabled), { timeout: ms }, t);
    await page.evaluate((x) => [...document.querySelectorAll("button,a")].find((b) => b.textContent.trim().includes(x) && !b.disabled).click(), t);
    say("clicked:", t);
  };
  /** Bounding box (page CSS px) of the closest `sel` ancestor of the smallest element containing `text`. */
  const box = (text, sel) => page.evaluate((t, s) => {
    const all = [...document.querySelectorAll("body *")].filter((e) => e.innerText && e.innerText.includes(t));
    const leaf = all.sort((a, b) => a.innerText.length - b.innerText.length)[0];
    const el = leaf && (s ? leaf.closest(s) : leaf);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
  }, text, sel);
  const shot = async (name, boxes = {}) => {
    await page.mouse.move(1439, 809); // keep the pointer off the content
    await sleep(900);
    const file = path.join(OUT, name + ".png");
    await page.screenshot({ path: file, fullPage: true });
    const dims = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
    const b = {};
    for (const [k, [t, s]] of Object.entries(boxes)) b[k] = await box(t, s);
    shots[name] = { file: name + ".png", css: dims, scale: 4 / 3, boxes: b, at: new Date().toISOString(), url: page.url().replace(WEB, "") };
    say("shot", name);
  };

  // ---- one coherent run, from a new demo session
  await page.goto(WEB + "/demo", { waitUntil: "networkidle0" });
  await waitText("STEP");
  await sleep(1500);
  await click("Restart demo");
  await waitText("Nothing yet.");
  await shot("02a_normal_start", { request: ["I want to renew my residency permit.", "section"] });
  await click("Submit Mariam's request");
  await waitText("Case status: Completed");
  await shot("02b_normal_done", { result: ["WHAT HAPPENED", "section"], decisions: ["agent actions, each checked", "section"] });

  await click("Next step");
  await waitText("Run the unauthorized request");
  await shot("03a_attack_ready", { panel: ["different citizen (C-1003)", "section"] });
  await click("Run the unauthorized request");
  await waitText("Unauthorized access blocked.");
  await shot("03b_blocked", { panel: ["Unauthorized access blocked.", "section"], facts: ["PROTECTED DATA RETURNED", "dl"] });

  await click("Next step");
  await waitText("Security review required. Switch to the officer console.");
  await shot("04a_officer_signin", { officer: ["Security review required", "section"] }); // password field still empty
  await page.type('input[type="password"]', fs.readFileSync(PWFILE, "utf8").trim());
  await click("Sign in as officer");
  await waitText("Mark incident under review");
  await sleep(1500);
  // open the officer panel's technical details to show the verified authority chain
  await page.evaluate(() => { const d = [...document.querySelectorAll("details")].find((x) => x.innerText.includes("delegated authority")); if (d) d.open = true; });
  await shot("04b_incident", { incident: ["Attempt to access a citizen outside the case", "div"], chain: ["delegated authority and evidence", "details"], officer: ["Signed in:", "section"] });
  await page.evaluate(() => { const d = [...document.querySelectorAll("details")].find((x) => x.innerText.includes("delegated authority")); if (d) d.open = false; });
  await click("Mark incident under review");
  await waitText("Reassign the insurance check");
  await click("Reassign the insurance check");
  await waitText("Resume Mariam's case");
  await shot("04c_reassigned", { reassign: ["Replace only the agent that overstepped", "li"] });
  await click("Resume Mariam's case");
  await waitText("Intervention complete");
  await shot("04d_intervention_done", { checklist: ["Intervention complete", "section"] });

  await click("Next step");
  await click("Continue Mariam's renewal");
  await waitText("Approve & re-authorize");
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Approve & re-authorize") && !b.disabled), { timeout: 30000 });
  await shot("05a_held", { held: ["Officer approves the held step", "li"], citizen: ["What the AI assistant reported", "section"] });
  await click("Approve & re-authorize");
  await click("Resolve incident");
  await click("Continue Mariam's renewal");
  await waitText("recovered after a security review. Click");
  await click("Continue Omar's case").catch(() => say("Omar: no continue button (already completed)"));
  await page.waitForFunction(() => !document.body.innerText.includes("Continue Omar's case"), { timeout: 30000 }).catch(() => {});
  await sleep(2500);
  await shot("05b_recovered", { citizen: ["Mariam Al Hashimi", "section"], other: ["Another citizen, same time", "section"], checklist: ["take turns, in the order WAKALA requires", "section"] });

  await click("Next step");
  await waitText("Security evidence");
  await sleep(2500);
  await shot("05c_results", { results: ["Replacement agent", "div.grid"], evidence: ["Security evidence", "section"] });

  // the real Security Evidence page
  await page.goto(WEB + "/evidence", { waitUntil: "networkidle0" });
  await waitText("Back-to-back recovery");
  await sleep(2000);
  await shot("06_evidence", { tiles: ["Requests evaluated", "div.grid"], recovery: ["Back-to-back recovery", "section"] });

  // ---- backend state for validation (no credentials involved)
  const demo = await getJSON("/api/portal/demo");
  const v = async (k) => (demo.cases[k] ? getJSON("/api/portal/cases/" + demo.cases[k].case_id) : null);
  const s1 = await v("scene1"), mar = await v("scene2_mariam"), omar = await v("scene2_unrelated");
  const audit = await getJSON("/api/audit/integrity");
  const evidence = await getJSON("/api/evidence/summary");
  const log = {
    note: "One real guided-demo run captured from the locally running WAKALA prototype (synthetic data, deterministic offline planner). No password is recorded here.",
    captured_at: new Date().toISOString(), demo_session: demo.session_id, model: demo.model,
    normal_case: { case_id: s1?.case_id, state: s1?.state, allowed_actions: s1?.timeline.filter((t) => t.decision === "allowed").length,
                   agents: [...new Set(s1?.timeline.map((t) => t.agent_name))], ledger: s1?.ledger },
    incident_case: { case_id: mar?.case_id, citizen: mar?.citizen_name, final_state: mar?.state, recovery_status: mar?.recovery_status,
                     denied: mar?.timeline.filter((t) => t.decision === "denied").map((t) => ({ agent: t.agent_name, tool: t.tool_name, reason_codes: t.reason_codes, plain_english: t.plain_english })),
                     standby_actions: mar?.timeline.filter((t) => t.agent_id === "AGT-INS-002").map((t) => ({ decision: t.decision, plain_english: t.plain_english })),
                     incidents: mar?.incidents, ledger: mar?.ledger },
    unrelated_case: { case_id: omar?.case_id, citizen: omar?.citizen_name, state: omar?.state, recovery_status: omar?.recovery_status },
    audit_chain_valid: audit.valid, audit_events: audit.event_count,
    evidence: { total_requests: evidence.dataset?.total_requests, C_unauthorized_executed: evidence.configurations?.C?.unauthorized_operations_executed,
                C_legitimate_denied: evidence.configurations?.C?.legitimate_incorrectly_denied, A_unauthorized_executed: evidence.configurations?.A?.unauthorized_operations_executed },
    page_errors: errors, shots,
  };
  fs.writeFileSync(path.join(OUT, "run_log.json"), JSON.stringify(log, null, 1));
  say("final:", JSON.stringify({ normal: log.normal_case.state, incident: log.incident_case.final_state, recovery: log.incident_case.recovery_status, unrelated: log.unrelated_case.state, audit: log.audit_chain_valid, errors: errors.length }));
  await browser.close();
})().catch((e) => { console.error("CAPTURE FAILED:", e.message); process.exit(1); });
