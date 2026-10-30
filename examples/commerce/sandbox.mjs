// Node.js 20+; no packages needed. SIMULATION ONLY.
// INVASTOR_API_BASE=https://YOUR_HOST/api node invastor-sandbox.mjs happy_path
// Scenarios: happy_path, out_of_stock, price_changed, budget_limit,
// revoked_permission, duplicate_request
// Options: --budget=60 --query=keyboard --quantity=1 --approve-simulation
// Rule-based reference agent, not an LLM or real merchant inventory.
import { randomUUID } from "node:crypto";
import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
const base = process.env.INVASTOR_API_BASE?.replace(/\/$/, "");
if (!base) throw new Error("Set INVASTOR_API_BASE to your serving host plus /api");
const scenario = process.argv[2] || "happy_path";
const options = process.argv.slice(3);
const option = (name, fallback) => options.find(arg => arg.startsWith("--" + name + "="))?.split("=").slice(1).join("=") ?? fallback;
const rawBudget = option("budget", "60");
if (!/^\d+(\.\d{1,2})?$/.test(rawBudget)) throw new Error("Budget must be a positive USD amount with at most two decimals.");
const budgetCents = Math.round(Number(rawBudget) * 100);
const quantity = Number(option("quantity", "1"));
if (!Number.isSafeInteger(budgetCents) || budgetCents <= 0 || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > 10)
  throw new Error("Use a positive budget and a whole quantity from 1 to 10.");
const query = option("query", "keyboard");
const approveSimulation = options.includes("--approve-simulation");
let token;
async function api(path, body, method = body ? "POST" : "GET") {
  const response = await fetch(base + "/commerce/sandbox" + path, {
    method, headers: {"Content-Type":"application/json", "User-Agent":"InVastorSandboxExample/1.0",
      ...(token ? {Authorization:"Bearer " + token} : {})},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(20000)
  });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error || "HTTP " + response.status),
    {code:data.code || "HTTP_ERROR", status:response.status});
  if (data.sandbox !== true) throw new Error("Refusing a response not explicitly marked as sandbox.");
  return data;
}
const session = await api("/sessions", {scenario});
token = session.token; // Never log a bearer credential.
console.log("SIMULATION ONLY. Fixture balance: $100.00. No real order or payment.");
const expected = {out_of_stock:"OUT_OF_STOCK",price_changed:"PRICE_CHANGED",
  budget_limit:"BUDGET_EXCEEDED",revoked_permission:"PERMISSION_REVOKED",
  insufficient_funds:"INSUFFICIENT_FUNDS",expired_permission:"PERMISSION_EXPIRED"};
try {
  if (scenario === "revoked_permission") {
    await api("/session", undefined, "DELETE");
    await api("/catalog");
  } else {
    const {items} = await api("/catalog?q=" + encodeURIComponent(query));
    if (!items.length) throw new Error("No fixture products match the query.");
    console.log("Compared", items.length, "fixture offers; requested budget cents:", budgetCents);
    const available = items.filter(item => item.currency === "USD" && item.stock >= quantity);
    if (!available.length) throw Object.assign(new Error("No matching fixture has sufficient stock."), {code:"OUT_OF_STOCK"});
    const candidates = available.filter(item => Number.isSafeInteger(item.unitPriceUsdCents) && item.unitPriceUsdCents > 0 && item.unitPriceUsdCents * quantity <= budgetCents);
    if (!candidates.length) throw Object.assign(new Error("No matching fixture fits the requested budget."), {code:"BUDGET_EXCEEDED"});
    candidates.sort((a,b) => a.unitPriceUsdCents - b.unitPriceUsdCents || a.id.localeCompare(b.id));
    const selected = candidates[0];
    console.log("Selected:", selected.id, "— lowest-priced in-stock matching fixture.");
    const {quote} = await api("/quotes", {listingId:selected.id,quantity});
    if (quote.totalUsdCents > budgetCents) throw new Error("Fresh quote exceeds the requested budget; not preparing.");
    const key = "example_" + randomUUID().replaceAll("-", "");
    let result;
    try { result = await api("/purchases", {quoteId:quote.id,idempotencyKey:key}); }
    catch (error) {
      if (error.status && error.code!=="OUTCOME_UNKNOWN") throw error;
      try { result = await api("/purchases/by-key/" + encodeURIComponent(key)); }
      catch { throw new Error("Outcome unknown. Keep key " + key + "; query status. Do not retry with a new key."); }
    }
    console.log("Prepared:", result.purchase.state);
    if (result.purchase.state !== "AWAITING_APPROVAL" || (await api("/session")).spentUsdCents !== 0)
      throw new Error("Preparing a purchase must not move simulated funds.");
    if (scenario === "duplicate_request") {
      const replay = await api("/purchases", {quoteId:quote.id,idempotencyKey:key});
      if (!replay.replayed || replay.purchase.id !== result.purchase.id)
        throw new Error("Duplicate request created a different purchase.");
      console.log("Duplicate safely returned the original purchase.");
    }
    if (expected[scenario]) throw new Error("Expected failure was not raised.");
    let answer = approveSimulation ? "y" : "n";
    if (approveSimulation) console.log("Explicit --approve-simulation flag: fixture approval only.");
    else if (stdin.isTTY) {
      const prompt = createInterface({input:stdin,output:stdout});
      try { answer = await prompt.question("Approve this SIMULATED $" + (quote.totalUsdCents / 100).toFixed(2) + " purchase? [y/N] "); }
      finally { prompt.close(); }
    }
    if (answer.toLowerCase() !== "y") {
      console.log("PASS: AWAITING_APPROVAL. No simulated payment made.");
    } else {
      await api("/purchases/" + result.purchase.id + "/approve", {approved:true});
      if (scenario === "duplicate_request")
        await api("/purchases/" + result.purchase.id + "/approve", {approved:true});
      const status = await api("/purchases/" + result.purchase.id);
      const state = await api("/session");
      if (status.purchase.state !== "SIMULATED_PAID" || state.simulatedPaidCount !== 1 || state.spentUsdCents !== quote.totalUsdCents)
        throw new Error("Simulation invariant failed.");
      console.log("PASS:", status.purchase.state, "balance cents:", state.simulatedBalanceUsdCents);
    }
  }
} catch (error) {
   if (expected[scenario] && error.code === expected[scenario]) {
     if (scenario !== "revoked_permission") {
       const state = await api("/session");
       if (state.spentUsdCents !== 0 || state.purchaseCount !== 0) throw new Error("Rejected scenario changed simulated funds or purchases.");
     }
     console.log("PASS: expected safe rejection", error.code);
   }
  else { console.error("FAIL:", error.message); process.exitCode = 1; }
}
