// WAKALA — final pitch deck builder (Phase 8).
// Usage (needs pptxgenjs, sharp, react, react-dom, react-icons on NODE_PATH):
//   node submission/source/build_deck.js
// Inputs: submission/screenshots/*.png (genuine prototype captures). Output: submission/WAKALA_Pitch_Deck.pptx
// Every figure on the slides is copied from evidence/phase5/summary.json, evidence/phase6, evidence/phase7
// and docs/FINAL_TECHNICAL_READINESS.md. Nothing here is a government statistic.
const path = require("path");
const fs = require("fs");
const os = require("os");
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const fa = require("react-icons/fa");

const ROOT = path.resolve(__dirname, "..", "..");
const SHOTS = path.join(ROOT, "submission", "screenshots");
const OUT = path.join(ROOT, "submission", "WAKALA_Pitch_Deck.pptx");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "wakala-deck-"));

const C = {
  navy: "0B1630", navy2: "12234A", navy3: "1B2F5E", ink: "0F172A", muted: "475569", line: "D5DDE8",
  teal: "0D9488", tealL: "2DD4BF", tealSoft: "E6F6F4", bg: "F5F7FB", white: "FFFFFF",
  red: "B91C1C", redSoft: "FDECEC", amber: "B45309", amberSoft: "FFF7E6", green: "047857", greenSoft: "E7F6EF",
};
const H = "Segoe UI Semibold";
const B = "Segoe UI";

async function icon(Comp, color, name) {
  const svg = renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: 256 }));
  const file = path.join(TMP, `${name}-${color}.png`);
  await sharp(Buffer.from(svg)).png().toFile(file);
  return file;
}
async function crop(src, left, top, width, height, name) {
  const file = path.join(TMP, name + ".png");
  await sharp(path.join(SHOTS, src)).extract({ left, top, width, height }).png().toFile(file);
  return file;
}

const shadow = () => ({ type: "outer", color: "000000", blur: 6, offset: 1.5, angle: 90, opacity: 0.12 });

function chrome(pres, s, n, title, kicker) {
  s.background = { color: C.bg };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 13.333, h: 0.09, fill: { color: C.teal }, line: { color: C.teal } });
  s.addText(kicker.toUpperCase(), { x: 0.6, y: 0.32, w: 9, h: 0.3, fontFace: H, fontSize: 11, color: C.teal, charSpacing: 3, margin: 0 });
  s.addText(title, { x: 0.6, y: 0.6, w: 12.1, h: 0.7, fontFace: H, fontSize: 28, color: C.navy, margin: 0 });
  s.addShape(pres.shapes.LINE, { x: 0.6, y: 7.0, w: 12.13, h: 0, line: { color: C.line, width: 0.75 } });
  s.addText("WAKALA  ·  Challenge #27  ·  Working prototype on synthetic data — not a production government system",
    { x: 0.6, y: 7.05, w: 11, h: 0.3, fontFace: B, fontSize: 9, color: C.muted, margin: 0 });
  s.addText(String(n), { x: 12.2, y: 7.05, w: 0.53, h: 0.3, fontFace: H, fontSize: 9, color: C.muted, align: "right", margin: 0 });
}

function card(pres, s, x, y, w, h, opts = {}) {
  s.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill: { color: opts.fill || C.white }, line: { color: opts.line || C.line, width: opts.lw || 0.75 },
    shadow: opts.noShadow ? undefined : shadow(),
  });
  if (opts.accent) s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.07, h, fill: { color: opts.accent }, line: { color: opts.accent } });
}

const NOTES = {};

async function main() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  pres.author = "WAKALA team";
  pres.title = "WAKALA — Autonomous AI. Accountable Actions.";
  pres.subject = "UAE Hackathon 2026 · Track 2 Pioneers · Challenge #27 Secure Agentic AI for Government Services";

  const I = {
    shield: await icon(fa.FaShieldAlt, C.tealL, "shield"),
    shieldT: await icon(fa.FaShieldAlt, C.teal, "shieldT"),
    id: await icon(fa.FaIdCard, C.teal, "id"),
    sign: await icon(fa.FaFileSignature, C.teal, "sign"),
    tree: await icon(fa.FaSitemap, C.teal, "tree"),
    stop: await icon(fa.FaHandPaper, C.teal, "stop"),
    eye: await icon(fa.FaEye, C.teal, "eye"),
    officer: await icon(fa.FaUserShield, C.teal, "officer"),
    link: await icon(fa.FaLink, C.teal, "link"),
    doc: await icon(fa.FaFileAlt, C.teal, "doc"),
    receipt: await icon(fa.FaReceipt, C.teal, "receipt"),
    robot: await icon(fa.FaRobot, C.navy2, "robot"),
    user: await icon(fa.FaUser, C.navy2, "user"),
    bank: await icon(fa.FaUniversity, C.navy2, "bank"),
    warnR: await icon(fa.FaExclamationTriangle, C.red, "warnR"),
    check: await icon(fa.FaCheckCircle, C.green, "check"),
    checkT: await icon(fa.FaCheckCircle, C.tealL, "checkT"),
    times: await icon(fa.FaTimesCircle, C.red, "times"),
    flask: await icon(fa.FaFlask, C.amber, "flask"),
    hand: await icon(fa.FaHandshake, C.tealL, "hand"),
  };

  // Genuine screenshot crops (2880x1800 originals; sidebar and top bar removed)
  const IMG = {
    hero: await crop("01_portal_blocked.png", 616, 190, 2184, 1310, "hero"),
    blocked: await crop("01_portal_blocked.png", 1257, 450, 1543, 1187, "blocked"),
    soc: await crop("02_soc_incident.png", 640, 300, 2140, 1500, "soc"),
    recovered: await crop("03_portal_recovered.png", 1257, 450, 1543, 1187, "recovered"),
  };

  // ---------------- Slide 1 — Title ----------------
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.18, h: 7.5, fill: { color: C.teal }, line: { color: C.teal } });
    s.addText("UAE HACKATHON 2026  ·  TRACK 2 PIONEERS  ·  CHALLENGE #27", { x: 0.75, y: 0.75, w: 7, h: 0.35, fontFace: H, fontSize: 12, color: C.tealL, charSpacing: 2, margin: 0 });
    s.addImage({ path: I.shield, x: 0.75, y: 1.5, w: 0.95, h: 0.95 });
    s.addText([
      { text: "WAKALA", options: { fontFace: H, fontSize: 54, color: C.white } },
      { text: "  وكالة", options: { fontFace: H, fontSize: 40, color: "99F6E4" } },
    ], { x: 1.85, y: 1.38, w: 5.6, h: 1.2, margin: 0, valign: "middle" });
    s.addText("Autonomous AI. Accountable Actions.", { x: 0.75, y: 2.75, w: 6.6, h: 0.6, fontFace: H, fontSize: 26, color: C.white, margin: 0 });
    s.addText("An independent authorization gateway that makes every government AI agent identifiable, bound to one citizen's case, stoppable in seconds and safely recoverable.",
      { x: 0.75, y: 3.5, w: 6.2, h: 1.2, fontFace: B, fontSize: 15, color: "CBD5E1", margin: 0, valign: "top" });
    s.addText("Secure Agentic AI for Government Services", { x: 0.75, y: 4.85, w: 6.4, h: 0.35, fontFace: H, fontSize: 13, color: C.tealL, margin: 0 });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.75, y: 5.5, w: 5.6, h: 0.42, fill: { color: C.navy }, line: { color: "F59E0B", width: 1 }, rectRadius: 0.21 });
    s.addText("WORKING PROTOTYPE  ·  SYNTHETIC DATA  ·  NOT PRODUCTION", { x: 0.75, y: 5.5, w: 5.6, h: 0.42, fontFace: H, fontSize: 10.5, color: "FCD34D", align: "center", valign: "middle", charSpacing: 1, margin: 0 });
    // hero screenshot
    s.addShape(pres.shapes.RECTANGLE, { x: 7.45, y: 1.2, w: 5.45, h: 3.31, fill: { color: C.navy2 }, line: { color: C.navy3, width: 1 }, shadow: shadow() });
    s.addImage({ path: IMG.hero, x: 7.5, y: 1.25, w: 5.35, h: 3.21 });
    s.addText("Real prototype screen: a delegated AI agent asked for another citizen's record — WAKALA blocked it before it ran.",
      { x: 7.45, y: 4.65, w: 5.45, h: 0.6, fontFace: B, fontSize: 11, color: "94A3B8", italic: true, margin: 0 });
    NOTES[1] = "[0:00–0:15]  Good morning. We are WAKALA — Arabic for “mandate”. Autonomous AI, accountable actions. We answer Challenge 27: securing the AI agents that will run government services.";
    s.addNotes(NOTES[1]);
  }

  // ---------------- Slide 2 — Problem ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 2, "When an AI agent acts for government, who is accountable?", "The challenge");
    s.addText([
      { text: "Challenge #27 (Cyber Security Council) frames a national shift of ", options: {} },
      { text: "half of government services and operations to agentic AI within two years", options: { bold: true, color: C.navy } },
      { text: ". Agents plan, call tools and delegate to other agents on their own.", options: {} },
    ], { x: 0.6, y: 1.45, w: 12.1, h: 0.75, fontFace: B, fontSize: 15, color: C.ink, margin: 0, valign: "top" });

    const gaps = [
      [I.id, "Who is acting?", "Agents and sub-agents run on broad roles and reusable credentials — not as accountable, identifiable actors.", "Root causes R1, R2"],
      [I.sign, "What may it do?", "Delegated authority is not translated into precise limits: which citizen, which tool, how much, until when.", "Root cause R3"],
      [I.stop, "How do we stop it safely?", "Detection, intervention and recovery sit in separate teams. Stopping one bad agent can stop the whole service.", "Root cause R4"],
    ];
    gaps.forEach((g, i) => {
      const x = 0.6 + i * 4.1;
      card(pres, s, x, 2.45, 3.85, 3.0, { accent: C.teal });
      s.addImage({ path: g[0], x: x + 0.35, y: 2.75, w: 0.5, h: 0.5 });
      s.addText(g[1], { x: x + 0.35, y: 3.38, w: 3.3, h: 0.45, fontFace: H, fontSize: 17, color: C.navy, margin: 0 });
      s.addText(g[2], { x: x + 0.35, y: 3.88, w: 3.3, h: 1.1, fontFace: B, fontSize: 13, color: C.ink, margin: 0, valign: "top" });
      s.addText(g[3], { x: x + 0.35, y: 5.0, w: 3.3, h: 0.3, fontFace: B, fontSize: 10, color: C.muted, margin: 0 });
    });
    card(pres, s, 0.6, 5.75, 12.13, 0.95, { fill: C.redSoft, line: "F5C2C2", noShadow: true });
    s.addImage({ path: I.warnR, x: 0.85, y: 6.0, w: 0.45, h: 0.45 });
    s.addText("Result: an erroneous, manipulated or compromised agent can expose citizen data, move money or interrupt a public service — and no one can prove afterwards who authorized it.",
      { x: 1.5, y: 5.8, w: 11.0, h: 0.85, fontFace: B, fontSize: 14, color: C.ink, margin: 0, valign: "middle" });
    NOTES[2] = "[0:15–0:35]  The challenge describes half of government services moving to agentic AI within two years. Today an agent usually holds a broad role or a reusable credential. So when an agent is wrong or manipulated, nobody can prove who acted, what it was allowed to do — or stop it without stopping the whole service.";
    s.addNotes(NOTES[2]);
  }

  // ---------------- Slide 3 — Solution / architecture ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 3, "An independent gateway between every agent and every service", "How it works");
    // left column: agents
    const lx = 0.6, lw = 2.75;
    card(pres, s, lx, 1.55, lw, 0.95, {});
    s.addImage({ path: I.user, x: lx + 0.2, y: 1.8, w: 0.42, h: 0.42 });
    s.addText([{ text: "Citizen request", options: { fontFace: H, fontSize: 13, color: C.navy, breakLine: true } }, { text: "“Renew my residency permit”", options: { fontSize: 10.5, color: C.muted } }],
      { x: lx + 0.75, y: 1.6, w: 1.95, h: 0.85, fontFace: B, margin: 0, valign: "middle" });
    card(pres, s, lx, 2.75, lw, 2.55, {});
    s.addImage({ path: I.robot, x: lx + 0.2, y: 2.95, w: 0.42, h: 0.42 });
    s.addText("AI agents — any platform", { x: lx + 0.75, y: 2.92, w: 1.95, h: 0.5, fontFace: H, fontSize: 13, color: C.navy, margin: 0, valign: "middle" });
    s.addText([
      { text: "Residency Agent", options: { bullet: true, breakLine: true } },
      { text: "Insurance Agent (delegated)", options: { bullet: true, breakLine: true } },
      { text: "Payment Agent", options: { bullet: true, breakLine: true } },
      { text: "Each signs every request with its own key", options: { bullet: true } },
    ], { x: lx + 0.2, y: 3.5, w: lw - 0.35, h: 1.7, fontFace: B, fontSize: 11.5, color: C.ink, margin: 0, valign: "top", paraSpaceAfter: 3 });
    s.addShape(pres.shapes.LINE, { x: lx + lw / 2, y: 2.5, w: 0, h: 0.25, line: { color: C.navy2, width: 1.5, endArrowType: "triangle" } });

    // middle: gateway
    const gx = 3.85, gw = 5.3;
    s.addShape(pres.shapes.LINE, { x: lx + lw, y: 3.95, w: gx - lx - lw, h: 0, line: { color: C.navy2, width: 2, endArrowType: "triangle" } });
    s.addText("signed request", { x: lx + lw - 0.05, y: 3.6, w: 0.6, h: 0.3, fontFace: B, fontSize: 8.5, color: C.muted, margin: 0, align: "center" });
    s.addShape(pres.shapes.RECTANGLE, { x: gx, y: 1.55, w: gw, h: 3.75, fill: { color: C.navy }, line: { color: C.teal, width: 2 }, shadow: shadow() });
    s.addImage({ path: I.shield, x: gx + 0.25, y: 1.72, w: 0.42, h: 0.42 });
    s.addText("WAKALA authorization gateway", { x: gx + 0.8, y: 1.7, w: 4.3, h: 0.46, fontFace: H, fontSize: 16, color: C.white, margin: 0, valign: "middle" });
    const checks = [
      ["1", "Verified agent identity", "Ed25519-signed request; forged or tampered = denied"],
      ["2", "Case-bound mandate", "One citizen, one case: allowed tools, amount, recipient, expiry"],
      ["3", "Delegation chain", "Child mandate signed by WAKALA, never wider than its parent"],
      ["4", "Replay, revocation, approval", "Nonces, live revocation, officer approval for sensitive steps"],
    ];
    checks.forEach((c, i) => {
      const y = 2.32 + i * 0.72;
      s.addShape(pres.shapes.OVAL, { x: gx + 0.28, y: y + 0.08, w: 0.38, h: 0.38, fill: { color: C.teal }, line: { color: C.teal } });
      s.addText(c[0], { x: gx + 0.28, y: y + 0.08, w: 0.38, h: 0.38, fontFace: H, fontSize: 12, color: C.white, align: "center", valign: "middle", margin: 0 });
      s.addText([{ text: c[1], options: { fontFace: H, fontSize: 13, color: C.white, breakLine: true } }, { text: c[2], options: { fontFace: B, fontSize: 10.5, color: "B6C2D6" } }],
        { x: gx + 0.85, y: y, w: 4.3, h: 0.62, margin: 0, valign: "middle" });
    });

    // right: services
    const rx = 9.65, rw = 3.08;
    s.addShape(pres.shapes.LINE, { x: gx + gw, y: 3.2, w: rx - gx - gw, h: 0, line: { color: C.green, width: 2, endArrowType: "triangle" } });
    s.addText("ALLOW", { x: gx + gw, y: 2.88, w: rx - gx - gw, h: 0.28, fontFace: H, fontSize: 9, color: C.green, align: "center", margin: 0 });
    card(pres, s, rx, 1.55, rw, 2.3, {});
    s.addImage({ path: I.bank, x: rx + 0.2, y: 1.72, w: 0.42, h: 0.42 });
    s.addText("Protected services", { x: rx + 0.75, y: 1.7, w: 2.25, h: 0.46, fontFace: H, fontSize: 13, color: C.navy, margin: 0, valign: "middle" });
    s.addText([
      { text: "Residency registry", options: { bullet: true, breakLine: true } },
      { text: "Insurance verification", options: { bullet: true, breakLine: true } },
      { text: "Treasury fee payment", options: { bullet: true, breakLine: true } },
      { text: "(fictional, synthetic)", options: { color: C.muted, italic: true } },
    ], { x: rx + 0.2, y: 2.3, w: rw - 0.35, h: 1.45, fontFace: B, fontSize: 11.5, color: C.ink, margin: 0, valign: "top", paraSpaceAfter: 3 });
    s.addShape(pres.shapes.LINE, { x: gx + gw, y: 4.65, w: rx - gx - gw, h: 0, line: { color: C.red, width: 2, endArrowType: "triangle" } });
    s.addText("DENY", { x: gx + gw, y: 4.33, w: rx - gx - gw, h: 0.28, fontFace: H, fontSize: 9, color: C.red, align: "center", margin: 0 });
    card(pres, s, rx, 4.15, rw, 1.15, { fill: C.redSoft, line: "F5C2C2" });
    s.addText([{ text: "Blocked before it runs", options: { fontFace: H, fontSize: 13, color: C.red, breakLine: true } }, { text: "No data returned, nothing changed, plain-language reason", options: { fontFace: B, fontSize: 10.5, color: C.ink } }],
      { x: rx + 0.2, y: 4.2, w: rw - 0.35, h: 1.05, margin: 0, valign: "middle" });

    // bottom modules
    const mods = [
      [I.eye, "Behaviour Watch", "Rule-based signals; graduated response"],
      [I.officer, "Officer intervention", "Suspend one mandate, reassign, resume"],
      [I.link, "Tamper-evident audit", "Hash-chained record of every decision"],
      [I.doc, "Document Shield", "Quarantines hidden prompt-injection PDFs"],
      [I.receipt, "Citizen AI receipt", "What each agent did, in plain language"],
    ];
    const mw = 2.29, mg = 0.17;
    mods.forEach((m, i) => {
      const x = 0.6 + i * (mw + mg);
      card(pres, s, x, 5.55, mw, 1.2, { fill: C.tealSoft, line: "A7DCD5", noShadow: true });
      s.addImage({ path: m[0], x: x + 0.15, y: 5.68, w: 0.34, h: 0.34 });
      s.addText(m[1], { x: x + 0.58, y: 5.65, w: mw - 0.65, h: 0.4, fontFace: H, fontSize: 11.5, color: C.navy, margin: 0, valign: "middle" });
      s.addText(m[2], { x: x + 0.15, y: 6.08, w: mw - 0.25, h: 0.6, fontFace: B, fontSize: 10, color: C.ink, margin: 0, valign: "top" });
    });
    NOTES[3] = "[0:35–1:05]  WAKALA puts an independent gateway between every agent and every protected service. Each agent signs every request. Each request is checked against a mandate bound to one citizen's case: tool, amount, recipient, expiry. When agents delegate, WAKALA issues a narrower signed child mandate — authority can never grow. Behaviour Watch flags misuse, officers intervene, and every decision is hash-chained. It is platform-neutral: the control sits at the service, not inside the model.";
    s.addNotes(NOTES[3]);
  }

  // ---------------- Slide 4 — Demo ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 4, "Live prototype: blocked, contained, recovered", "Demonstration");
    const panels = [
      [IMG.blocked, "1", "Blocked before execution", "The delegated Insurance Agent asks for citizen C-1003's record. Mariam's case is paused; nothing charged.", C.red, 1543 / 1187],
      [IMG.soc, "2", "Contained precisely", "Security Operations: violated rule, verified chain — only the one child mandate is suspended.", C.amber, 2140 / 1500],
      [IMG.recovered, "3", "Service recovered", "Officer reassigns to a standby agent; the renewal completes “recovered after a security review”.", C.green, 1543 / 1187],
    ];
    panels.forEach((p, i) => {
      const x = 0.6 + i * 4.1, w = 3.85;
      card(pres, s, x, 1.5, w, 4.55, {});
      const iw = w - 0.24, bh = iw / 1.3, ar = p[5], ih = Math.min(bh, iw / ar), iw2 = ih * ar;
      s.addShape(pres.shapes.RECTANGLE, { x: x + 0.12, y: 1.62, w: iw, h: bh, fill: { color: "F7F6F2" }, line: { color: C.line, width: 0.75 } });
      s.addImage({ path: p[0], x: x + 0.12 + (iw - iw2) / 2, y: 1.62 + (bh - ih) / 2, w: iw2, h: ih });
      const ty = 1.62 + bh + 0.2;
      s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: ty, w: 0.4, h: 0.4, fill: { color: p[4] }, line: { color: p[4] } });
      s.addText(p[1], { x: x + 0.2, y: ty, w: 0.4, h: 0.4, fontFace: H, fontSize: 13, color: C.white, align: "center", valign: "middle", margin: 0 });
      s.addText(p[2], { x: x + 0.72, y: ty, w: w - 0.9, h: 0.4, fontFace: H, fontSize: 15, color: C.navy, margin: 0, valign: "middle" });
      s.addText(p[3], { x: x + 0.2, y: ty + 0.5, w: w - 0.4, h: 1.05, fontFace: B, fontSize: 11.5, color: C.ink, margin: 0, valign: "top" });
    });
    card(pres, s, 0.6, 6.2, 12.13, 0.6, { fill: C.greenSoft, line: "A7DCC4", noShadow: true });
    s.addImage({ path: I.check, x: 0.8, y: 6.33, w: 0.34, h: 0.34 });
    s.addText("Same run: an unrelated citizen's case completed  ·  audit chain verified (495 events)  ·  plain-language AI-activity receipt for Mariam",
      { x: 1.3, y: 6.2, w: 11.3, h: 0.6, fontFace: B, fontSize: 12, color: C.ink, margin: 0, valign: "middle" });
    NOTES[4] = "[1:05–1:40]  This is the real prototype. Mariam asks to renew her residency permit. The delegated Insurance Agent tries to read another citizen's record. WAKALA blocks it before it runs — no data returned. Security Operations sees the same case: the violated rule, the verified chain, and only that one mandate suspended. An officer reassigns the task, and Mariam's renewal completes. An unrelated case never stopped.\n\n(Screens: submission/screenshots 01, 02, 03 — captured from the running prototype, unedited apart from cropping.)";
    s.addNotes(NOTES[4]);
  }

  // ---------------- Slide 5 — Evidence ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 5, "Measured, not claimed", "Evidence");
    const kpis = [
      ["0 / 720", "unauthorized operations executed", "Full WAKALA · intentionally weak role-only baseline executed 624 / 720", C.teal],
      ["0 / 480", "legitimate requests denied", "Same 1,200-request labelled synthetic dataset, fixed seed", C.teal],
      ["0 / 8", "Attack Lab attacks executed", "Baseline executed 7 / 8; one (delegation escalation) denied by both", C.teal],
    ];
    kpis.forEach((k, i) => {
      const y = 1.5 + i * 1.62;
      card(pres, s, 0.6, y, 5.6, 1.45, { accent: k[3] });
      s.addText(k[0], { x: 0.9, y: y + 0.12, w: 2.2, h: 0.8, fontFace: H, fontSize: 36, color: C.navy, margin: 0, valign: "middle" });
      s.addText(k[1], { x: 3.1, y: y + 0.15, w: 3.0, h: 0.8, fontFace: H, fontSize: 14, color: C.ink, margin: 0, valign: "middle" });
      s.addText(k[2], { x: 0.9, y: y + 0.95, w: 5.2, h: 0.4, fontFace: B, fontSize: 10.5, color: C.muted, margin: 0, valign: "top" });
    });
    // recovery chart
    card(pres, s, 6.5, 1.5, 6.23, 3.5, {});
    s.addText("Safe recovery, shared environment (back-to-back incidents)", { x: 6.75, y: 1.6, w: 5.8, h: 0.4, fontFace: H, fontSize: 13, color: C.navy, margin: 0 });
    s.addChart(pres.charts.BAR, [{
      name: "Recovered (%)",
      labels: ["Long run: 50 / 50", "Watch 2.0, 5 repeats: 20 / 20 each", "Original policy: 2 / 20"],
      values: [100, 100, 10],
    }], {
      x: 6.65, y: 2.0, w: 5.95, h: 2.4, barDir: "bar",
      chartColors: [C.teal, C.teal, "94A3B8"], varyColors: true,
      catAxisLabelColor: C.ink, catAxisLabelFontFace: B, catAxisLabelFontSize: 11,
      valAxisHidden: true, valAxisMaxVal: 100, valAxisMinVal: 0,
      valGridLine: { style: "none" }, catGridLine: { style: "none" },
      showValue: false,
      showLegend: false, barGapWidthPct: 60,
    });
    s.addText("Root cause found and fixed: agent-wide counters attached incidents to unrelated cases. Every attack was still denied in every run.",
      { x: 6.75, y: 4.4, w: 5.8, h: 0.55, fontFace: B, fontSize: 10.5, color: C.muted, margin: 0, valign: "top" });
    // speed + tests
    card(pres, s, 6.5, 5.15, 3.0, 1.7, {});
    s.addText([{ text: "≈19 ms", options: { fontFace: H, fontSize: 26, color: C.navy, breakLine: true } },
      { text: "median full gateway authorization (in-memory; ≈55 ms with persisted SQLite) on one laptop", options: { fontFace: B, fontSize: 9.5, color: C.muted } }],
      { x: 6.7, y: 5.2, w: 2.7, h: 1.6, margin: 0, valign: "middle" });
    card(pres, s, 9.73, 5.15, 3.0, 1.7, {});
    s.addText([{ text: "493 tests", options: { fontFace: H, fontSize: 26, color: C.navy, breakLine: true } },
      { text: "backend tests pass, incl. 34 security invariants; 12 / 12 demo steps verified end-to-end", options: { fontFace: B, fontSize: 9.5, color: C.muted } }],
      { x: 9.93, y: 5.2, w: 2.7, h: 1.6, margin: 0, valign: "middle" });
    s.addImage({ path: I.flask, x: 0.6, y: 6.42, w: 0.28, h: 0.28 });
    s.addText("Synthetic prototype benchmark — not production government statistics. Sources: evidence/phase5, phase6, phase7; docs/FINAL_TECHNICAL_READINESS.md.",
      { x: 0.98, y: 6.35, w: 5.3, h: 0.5, fontFace: B, fontSize: 9.5, color: C.amber, margin: 0, valign: "middle" });
    NOTES[5] = "[1:40–2:10]  We measured it. On 1,200 labelled synthetic requests, full WAKALA executed zero of 720 unauthorized operations and denied zero of 480 legitimate ones; a deliberately weak baseline executed 624. In the Attack Lab, seven of eight attacks succeed against the baseline, none against WAKALA. We also found and fixed a recovery flaw: 2 of 20 became 20 of 20, five times over. These are synthetic benchmarks, not government statistics.";
    s.addNotes(NOTES[5]);
  }

  // ---------------- Slide 6 — Business model ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 6, "Who pays, and why they would", "Business model (proposed)");
    const cols = [
      ["Customers", [
        ["Government entities deploying agents", "Accountable for service outcomes, lawful processing and continuity"],
        ["Central digital-government & cyber authorities", "Need common, cross-entity assurance and evidence"],
        ["Agent-platform suppliers & integrators", "Must show equivalent protection to win government work"],
      ]],
      ["Value", [
        ["Prove every agent action was authorized", "Case-bound mandates + hash-chained audit"],
        ["Stop one agent, not the service", "Selective suspension, officer reassignment, recovery"],
        ["Platform-neutral control", "Sits at the service API, not inside one vendor's model"],
      ]],
      ["Proposed licensing", [
        ["Entity licence (annual)", "Tiered by protected services and registered agents"],
        ["Supplier conformance kit", "Attack Lab scenarios + evidence pack for platform vendors"],
        ["Integration & assurance services", "Onboarding, mandate templates, officer playbooks"],
      ]],
    ];
    cols.forEach((c, i) => {
      const x = 0.6 + i * 4.1, w = 3.85;
      card(pres, s, x, 1.5, w, 4.75, { accent: i === 2 ? C.navy2 : C.teal });
      s.addText(c[0], { x: x + 0.3, y: 1.65, w: w - 0.5, h: 0.45, fontFace: H, fontSize: 17, color: C.navy, margin: 0 });
      c[1].forEach((r, j) => {
        const y = 2.25 + j * 1.3;
        s.addText([{ text: r[0], options: { fontFace: H, fontSize: 13, color: C.ink, breakLine: true } }, { text: r[1], options: { fontFace: B, fontSize: 11, color: C.muted } }],
          { x: x + 0.3, y, w: w - 0.5, h: 1.15, margin: 0, valign: "top" });
      });
    });
    card(pres, s, 0.6, 6.35, 12.13, 0.5, { fill: C.amberSoft, line: "F3D19C", noShadow: true });
    s.addText("Channels: national shared-service procurement and system-integrator partners. Pricing is a proposal to be validated in the pilot — no revenue or market figures are claimed.",
      { x: 0.8, y: 6.35, w: 11.8, h: 0.5, fontFace: B, fontSize: 11, color: C.ink, margin: 0, valign: "middle" });
    NOTES[6] = "[2:10–2:30]  Our customers are entities deploying agents, the central digital-government and cyber authorities, and platform suppliers who must prove equivalent protection. We propose an annual entity licence tiered by services and agents, a supplier conformance kit, and integration services.";
    s.addNotes(NOTES[6]);
  }

  // ---------------- Slide 7 — 90-day pilot ----------------
  {
    const s = pres.addSlide();
    chrome(pres, s, 7, "90-day pilot: observe first, then enforce, then decide", "Feasibility and plan");
    const phases = [
      ["Days 1–30", "Observe", [
        "Select one low-risk service, its owner and an accountable sponsor",
        "Agent inventory and mandate templates with the service owner",
        "Deploy in the entity's sandbox; replace dev keys with entity key management",
        "Shadow Mode on copied traffic — nothing is blocked",
      ], "Shadow report: agreement, would-block and false-denial candidates"],
      ["Days 31–60", "Enforce one case type", [
        "Gateway enforcing on one case type; officer approval for payments",
        "Tune Behaviour Watch thresholds on pilot data",
        "Train case officers on suspend / reassign / resume",
        "Independent security test using Attack Lab scenarios",
      ], "Zero unauthorized actions executed; false denials within agreed limit"],
      ["Days 61–90", "Recover and decide", [
        "Delegation and selective-revocation drills",
        "Timed recovery drills: incident → safe resume",
        "Citizen receipt usability test; audit export to the entity's SOC",
        "Evaluation report to sponsor",
      ], "Go / no-go decision on measured results"],
    ];
    phases.forEach((p, i) => {
      const x = 0.6 + i * 4.1, w = 3.85;
      s.addShape(pres.shapes.RECTANGLE, { x, y: 1.5, w, h: 0.75, fill: { color: i === 2 ? C.navy : C.navy2 }, line: { color: C.navy } });
      s.addText([{ text: p[0] + "  ", options: { fontFace: H, fontSize: 15, color: C.tealL } }, { text: p[1], options: { fontFace: H, fontSize: 15, color: C.white } }],
        { x: x + 0.25, y: 1.5, w: w - 0.4, h: 0.75, margin: 0, valign: "middle" });
      card(pres, s, x, 2.25, w, 3.3, {});
      s.addText(p[2].map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < p[2].length - 1 } })),
        { x: x + 0.2, y: 2.4, w: w - 0.35, h: 3.05, fontFace: B, fontSize: 13.5, color: C.ink, margin: 0, valign: "top", paraSpaceAfter: 9 });
      card(pres, s, x, 5.65, w, 0.85, { fill: C.tealSoft, line: "A7DCD5", noShadow: true });
      s.addImage({ path: I.checkT, x: x + 0.18, y: 5.88, w: 0.36, h: 0.36 });
      s.addText(p[3], { x: x + 0.65, y: 5.65, w: w - 0.8, h: 0.85, fontFace: H, fontSize: 11.5, color: C.navy, margin: 0, valign: "middle" });
      if (i < 2) s.addShape(pres.shapes.LINE, { x: x + w + 0.02, y: 1.875, w: 0.21, h: 0, line: { color: C.teal, width: 2, endArrowType: "triangle" } });
    });
    s.addText("Prerequisites from the pilot entity: a sandbox with test data, a service owner, an officer team, and the entity identity provider and key management.",
      { x: 0.6, y: 6.55, w: 12.1, h: 0.4, fontFace: B, fontSize: 10.5, color: C.muted, margin: 0, valign: "middle" });
    NOTES[7] = "[2:30–2:45]  The 90-day pilot starts in Shadow Mode on one low-risk service — observe only. Then we enforce one case type with officers in the loop, and finish with recovery drills and a go/no-go on measured results.";
    s.addNotes(NOTES[7]);
  }

  // ---------------- Slide 8 — Status + ask ----------------
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 13.333, h: 0.09, fill: { color: C.teal }, line: { color: C.teal } });
    s.addText("HONEST STATUS AND OUR ASK", { x: 0.6, y: 0.32, w: 9, h: 0.3, fontFace: H, fontSize: 11, color: C.tealL, charSpacing: 3, margin: 0 });
    s.addText("Ready to pilot — honest about what is not built yet", { x: 0.6, y: 0.6, w: 12.1, h: 0.7, fontFace: H, fontSize: 28, color: C.white, margin: 0 });
    const col = (x, title, items, ic, tc) => {
      s.addShape(pres.shapes.RECTANGLE, { x, y: 1.6, w: 3.85, h: 4.3, fill: { color: C.navy2 }, line: { color: C.navy3, width: 1 } });
      s.addText(title, { x: x + 0.3, y: 1.75, w: 3.3, h: 0.5, fontFace: H, fontSize: 16, color: tc, margin: 0, valign: "middle" });
      items.forEach((t, j) => {
        const y = 2.4 + j * 0.85;
        s.addImage({ path: ic, x: x + 0.3, y: y + 0.05, w: 0.28, h: 0.28 });
        s.addText(t, { x: x + 0.72, y, w: 2.95, h: 0.8, fontFace: B, fontSize: 12, color: "E2E8F0", margin: 0, valign: "top" });
      });
    };
    col(0.6, "Working today", [
      "Signed identities, case-bound mandates, verified delegation",
      "Behaviour Watch, officer intervention, safe recovery",
      "Attack Lab, Document Shield, Shadow Mode, citizen receipt",
      "Tamper-evident audit; 493 passing tests",
    ], I.checkT, C.tealL);
    col(4.7, "Not yet", [
      "No live AI model verified — demo uses a labelled offline planner",
      "No government integration; synthetic data only",
      "Single process, SQLite, development keys",
      "Policy drafts are signed but not enforced",
    ], I.times, "FCA5A5");
    col(8.8, "Our ask", [
      "One government entity and service owner as pilot partner",
      "A sandbox with test data and identity integration",
      "Joint security review aligned with national cyber guidance",
      "90 days to a measured go / no-go",
    ], I.hand, C.tealL);
    s.addImage({ path: I.shield, x: 0.6, y: 6.2, w: 0.55, h: 0.55 });
    s.addText("WAKALA", { x: 1.3, y: 6.15, w: 1.5, h: 0.65, fontFace: H, fontSize: 20, color: C.white, margin: 0, valign: "middle" });
    s.addText("وكالة", { x: 2.8, y: 6.15, w: 1.0, h: 0.65, fontFace: H, fontSize: 20, color: "99F6E4", margin: 0, valign: "middle", rtlMode: true });
    s.addText("Autonomous AI. Accountable Actions.", { x: 3.7, y: 6.15, w: 9.0, h: 0.65, fontFace: H, fontSize: 20, color: C.tealL, margin: 0, valign: "middle" });
    NOTES[8] = "[2:45–3:00]  This is a working prototype on synthetic data — not production, and no live model yet. We ask for one pilot entity and a sandbox. WAKALA: autonomous AI, accountable actions. Thank you.";
    s.addNotes(NOTES[8]);
  }

  await pres.writeFile({ fileName: OUT });
  const words = Object.values(NOTES).map(n => n.split("\n")[0].replace(/^\[[^\]]*\]\s*/, "")).join(" ").split(/\s+/).filter(Boolean).length;
  console.log("wrote", OUT, "| spoken words:", words, "| est. at 150 wpm:", (words / 150 * 60).toFixed(0), "s");
  fs.writeFileSync(path.join(TMP, "notes.json"), JSON.stringify(NOTES, null, 1));
}
main().catch(e => { console.error(e); process.exit(1); });
