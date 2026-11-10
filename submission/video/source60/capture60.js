// Raw footage for the 60-second film: ten real features of the running WAKALA prototype, one fresh demo session.
// Every frame is a genuine rendered application state reached through the real UI and APIs (headless Edge).
// The officer password is read from a local file given as an argument, typed into the real sign-in form, and
// never printed, logged or captured (no screenshot is taken while the sign-in form is visible).
// Usage: node capture60.js <outDir> <passwordFile>
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
  const browser = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true,
    args: ["--no-first-run", "--disable-extensions", "--hide-scrollbars", "--force-color-profile=srgb"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 810, deviceScaleFactor: 4 / 3 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const shots = {};
  const waitText = (t, ms = 40000) => page.waitForFunction((x) => document.body.innerText.includes(x), { timeout: ms }, t);
  const click = async (t, sel = "button,a", ms = 40000) => {
    await page.waitForFunction((x, s) => [...document.querySelectorAll(s)].some((b) => b.textContent.trim().includes(x) && !b.disabled), { timeout: ms }, t, sel);
    await page.evaluate((x, s) => [...document.querySelectorAll(s)].find((b) => b.textContent.trim().includes(x) && !b.disabled).click(), t, sel);
    say("clicked:", t);
  };
  const box = (text, sel) => page.evaluate((t, s) => {
    const all = [...document.querySelectorAll("body *")].filter((e) => e.innerText && e.innerText.includes(t));
    const leaf = all.sort((a, b) => a.innerText.length - b.innerText.length)[0];
    const el = leaf && (s ? leaf.closest(s) : leaf);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height };
  }, text, sel);
  const shot = async (name, boxes = {}) => {
    const pw = await page.$('input[type="password"]');
    if (pw && (await page.evaluate((e) => e.value.length, pw)) > 0) throw new Error("refusing to capture a filled password field");
    await page.mouse.move(1439, 809);
    await sleep(900);
    await page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: true });
    const dims = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
    const b = {};
    for (const [k, [t, s]] of Object.entries(boxes)) b[k] = await box(t, s);
    shots[name] = { file: name + ".png", css: dims, scale: 4 / 3, boxes: b, at: new Date().toISOString(), url: page.url().replace(WEB, "") };
    say("shot", name, JSON.stringify(Object.fromEntries(Object.entries(b).map(([k, v]) => [k, v ? "ok" : "MISSING"]))));
  };

  // 1) welcome page
  await page.goto(WEB + "/", { waitUntil: "networkidle0" });
  await shot("w01_welcome", { hero: ["WAKALA protects government AI agents", "h1"] });

  // 2) fresh demo session + normal authorized service
  await page.goto(WEB + "/demo", { waitUntil: "networkidle0" });
  await waitText("STEP"); await sleep(1500);
  await click("Restart demo");
  await waitText("Nothing yet.");
  await click("Submit Mariam's request");
  await waitText("Case status: Completed");
  await shot("g02_normal_done", { result: ["WHAT HAPPENED", "section"] });
  const s1 = (await getJSON("/api/portal/demo")).cases.scene1.case_id;

  // 3) the real Government AI Portal for the same case
  await page.goto(WEB + "/portal", { waitUntil: "networkidle0" });
  await waitText("What WAKALA verified"); await waitText("COMPLETED"); await sleep(1500);
  await shot("p03_portal", { verified: ["What WAKALA verified", null], progress: ["Application received", null] });

  // 4) delegation verification (Case View built from the stored, verified mandate chain)
  await page.goto(WEB + `/delegation?case=${s1}`, { waitUntil: "networkidle0" });
  await waitText("Insurance Agent — delegated"); await sleep(1500);
  await shot("d04_delegation", { delegated: ["Insurance Agent — delegated", null], caseview: ["Mariam asked", null] });

  // 5) unauthorized action blocked (separate, deliberately triggered test case)
  await page.goto(WEB + "/demo", { waitUntil: "networkidle0" });
  await waitText("STEP"); await sleep(1200);
  await click("Unauthorized access");
  await click("Run the unauthorized request");
  await waitText("Unauthorized access blocked.");
  await shot("g05_blocked", { panel: ["Unauthorized access blocked.", "section"], facts: ["PROTECTED DATA RETURNED", "dl"] });
  const demo2 = await getJSON("/api/portal/demo");
  const s2 = demo2.cases.scene2_mariam.case_id;

  // 6) officer signs in (no capture while the form is shown), incident in the guided view
  await click("Next step");
  await waitText("Security review required. Switch to the officer console.");
  await page.type('input[type="password"]', fs.readFileSync(PWFILE, "utf8").trim());
  await click("Sign in as officer");
  await waitText("Mark incident under review"); await sleep(1500);
  await shot("g06_incident", { incident: ["Attempt to access a citizen outside the case", "div"], officer: ["Signed in:", "section"] });

  // 7) Security Operations: Behaviour Watch and the investigation (same officer session)
  await page.goto(WEB + "/soc", { waitUntil: "networkidle0" });
  await click("Behaviour Watch", "[role=tab]"); await sleep(2500);
  await shot("soc07_watch", { watch: ["Policy watch-2.0", "section"] });
  await click("Incidents", "[role=tab]"); await sleep(1500);
  await click(s2); await waitText("Investigation"); await sleep(2000);
  await shot("soc08_investigation", { header: ["Attempt to access a citizen outside the case", "section"], rule: ["VIOLATED RULE", "div"], chain: ["DELEGATED AUTHORITY CHAIN", "div"] });

  // 8) officer intervention in the guided view
  await page.goto(WEB + "/demo", { waitUntil: "networkidle0" });
  await waitText("Mark incident under review"); await sleep(1200);
  await click("Officer intervention"); // pin step 3 (a fresh page load follows the first unfinished step)
  await click("Mark incident under review");
  await click("Reassign the insurance check");
  await click("Resume Mariam's case");
  await waitText("Intervention complete");
  await shot("g09_intervention", { checklist: ["Intervention complete", "section"], reassign: ["Replace only the agent that overstepped", "li"] });

  // 9) safe recovery: held step, approval, resolution, completion; unrelated case
  await click("Next step");
  await click("Continue Mariam's renewal");
  await click("Approve & re-authorize");
  await click("Resolve incident");
  await click("Continue Mariam's renewal");
  await waitText("recovered after a security review. Click");
  await click("Continue Omar's case").catch(() => say("Omar already completed"));
  await page.waitForFunction(() => !document.body.innerText.includes("Continue Omar's case"), { timeout: 30000 }).catch(() => {});
  await sleep(2500);
  await shot("g10_recovered", { citizen: ["Mariam Al Hashimi", "section"], checklist: ["take turns, in the order WAKALA requires", "section"] });

  // 10) results + citizen AI Activity receipt
  await click("Next step");
  await waitText("Security evidence"); await sleep(2000);
  await shot("g11_results", { results: ["Replacement agent", "div.grid"] });
  await click("Open Mariam's AI Activity receipt");
  await waitText("Every completed action", 20000).catch(() => {});
  await sleep(2000);
  await shot("g12_receipt", { receipt: ["My AI Activity", "[role=dialog] > div"] });

  // 11) Attack Lab: all eight scenarios, fresh isolated environments
  await page.goto(WEB + "/attack-lab", { waitUntil: "networkidle0" });
  await click("Run all 8");
  await waitText("DENIED IN BOTH", 120000).catch(() => waitText("Denied in both", 60000));
  await page.waitForFunction(() => !document.body.innerText.includes("Running"), { timeout: 120000 }).catch(() => {});
  await sleep(2500);
  await shot("a13_attack_lab", { tiles: ["EXECUTED WITHOUT", "div.grid"], first: ["Cross-citizen data access", "section"] });

  // 12) Document Shield: the hidden white-text synthetic PDF
  await page.goto(WEB + "/documents", { waitUntil: "networkidle0" });
  await click("hidden white-text");
  await waitText("QUARANTINED", 60000); await sleep(3000);
  await shot("ds14_document", { verdict: ["QUARANTINED", "section"] });

  // 13) Shadow Mode: observe copies, then enforce separately
  await page.goto(WEB + "/shadow", { waitUntil: "networkidle0" });
  await click("Run shadow evaluation, then enforcement");
  await waitText("WOULD BLOCK", 120000); await sleep(2500);
  await shot("sh15_shadow", { tiles: ["EVENTS OBSERVED", "div.grid"], note: ["Counterfactual, not prevention", "div"] });
  await click("2 · Enforce");
  await waitText("matched enforcement", 60000); await sleep(2000);
  await shot("sh16_enforce", { agreement: ["Shadow prediction matched enforcement", null] });

  // 14) Security Evidence
  await page.goto(WEB + "/evidence", { waitUntil: "networkidle0" });
  await waitText("Back-to-back recovery"); await sleep(2000);
  await shot("ev16_evidence", { tiles: ["Requests evaluated", "div.grid"], recovery: ["Back-to-back recovery", "section"] });

  // ---- backend state for verification (no credentials)
  const demo = await getJSON("/api/portal/demo");
  const v = async (k) => (demo.cases[k] ? getJSON("/api/portal/cases/" + demo.cases[k].case_id) : null);
  const n1 = await v("scene1"), mar = await v("scene2_mariam"), omar = await v("scene2_unrelated");
  const lab = await page.evaluate(() => document.body.innerText.match(/ATTACKS RUN\s*(\d+)[\s\S]*?WITHOUT\s*WAKALA\s*(\d+)[\s\S]*?WITH\s*WAKALA\s*(\d+)[\s\S]*?IN BOTH\s*(\d+)/i));
  const audit = await getJSON("/api/audit/integrity");
  const ev = await getJSON("/api/evidence/summary");
  const log = {
    note: "Raw footage for the 60-second film: one fresh demo session on the locally running prototype (synthetic data, deterministic offline planner). No password recorded.",
    captured_at: new Date().toISOString(), demo_session: demo.session_id, model: demo.model,
    normal_case: { case_id: n1?.case_id, state: n1?.state, allowed: n1?.timeline.filter((t) => t.decision === "allowed").length, agents: [...new Set(n1?.timeline.map((t) => t.agent_name))],
                   delegations: n1?.delegations?.map((d) => ({ child: d.child_mandate_id, parent: d.parent_mandate_id, from: d.from_agent, to: d.to_agent, task: d.task })) },
    incident_case: { case_id: mar?.case_id, final_state: mar?.state, recovery_status: mar?.recovery_status,
                     denied: mar?.timeline.filter((t) => t.decision === "denied").map((t) => ({ agent: t.agent_name, tool: t.tool_name, reason_codes: t.reason_codes, plain_english: t.plain_english })),
                     standby: mar?.timeline.filter((t) => t.agent_id === "AGT-INS-002").map((t) => t.decision), incidents: mar?.incidents, ledger_rows: mar?.ledger?.length },
    unrelated_case: { case_id: omar?.case_id, citizen: omar?.citizen_name, state: omar?.state },
    attack_lab_summary_from_ui: lab ? { run: +lab[1], baseline_executed: +lab[2], wakala_executed: +lab[3], denied_in_both: +lab[4] } : null,
    audit_chain_valid: audit.valid, audit_events: audit.event_count,
    evidence: { total: ev.dataset?.total_requests, C_unauth: ev.configurations?.C?.unauthorized_operations_executed, C_legit_denied: ev.configurations?.C?.legitimate_incorrectly_denied, A_unauth: ev.configurations?.A?.unauthorized_operations_executed },
    page_errors: errors, shots,
  };
  fs.writeFileSync(path.join(OUT, "run_log.json"), JSON.stringify(log, null, 1));
  say("final", JSON.stringify({ normal: log.normal_case.state, incident: log.incident_case.final_state, recovery: log.incident_case.recovery_status, unrelated: log.unrelated_case.state, lab: log.attack_lab_summary_from_ui, audit: audit.valid, errors: errors.length }));
  await browser.close();
})().catch((e) => { console.error("CAPTURE FAILED:", e.message); process.exit(1); });
