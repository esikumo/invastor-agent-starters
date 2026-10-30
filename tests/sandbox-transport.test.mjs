import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../examples/commerce/lifecycle-sandbox.mjs", import.meta.url), "utf8");
const transport = source.slice(0, source.indexOf("const assert="));
function fixture(fetch, url = "https://example.test/api") {
  const waits = [];
  const api = runInNewContext(transport + "\napi", {
    process: { env: { INVASTOR_API_BASE: url }, argv: ["node", "test", "--approve-simulation"] },
    URL, fetch, AbortSignal, console: { error() {} },
    setTimeout(fn, ms) { waits.push(ms); fn(); },
  });
  return { api, waits };
}
const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers });

for (const suffix of ["", "/"]) test("API base works with suffix " + JSON.stringify(suffix), async () => {
  const { api } = fixture(async url => {
    assert.equal(url, "https://example.test/api/commerce/sandbox/scenarios");
    return json({ sandbox: true });
  }, "https://example.test/api" + suffix);
  await api("scenarios");
});
test("proven sandbox rate rejection waits and repeats the exact request", async () => {
  const bodies = [];
  const { api, waits } = fixture(async (_url, options) => {
    bodies.push(options.body);
    return bodies.length === 1
      ? json({ sandbox: true, code: "RATE_LIMITED" }, 429, { "Retry-After": "0" })
      : json({ sandbox: true });
  });
  await api("sessions", undefined, { scenario: "happy_path" });
  assert.equal(bodies.length, 2); assert.equal(bodies[0], bodies[1]);
  assert.deepEqual(waits, [1000]);
});
test("read-only gateway recovery is safe", async () => {
  let calls = 0;
  const { api } = fixture(async () => ++calls === 1
    ? new Response("<html>gateway</html>", { status: 503 }) : json({ sandbox: true }));
  await api("scenarios"); assert.equal(calls, 2);
});
for (const status of [200, 429, 502, 503]) test("uncertain write is not replayed: HTTP " + status, async () => {
  let calls = 0;
  const { api } = fixture(async () => { calls++; return new Response("<html>gateway</html>", { status }); });
  await assert.rejects(api("purchases", undefined, { idempotencyKey: "original" }),
    error => error.code === "SANDBOX_INVALID_RESPONSE" && error.outcomeUnknown === true);
  assert.equal(calls, 1);
});
test("repeated throttling stops after two retries", async () => {
  let calls = 0;
  const { api } = fixture(async () => {
    calls++; return json({ sandbox: true, code: "RATE_LIMITED", error: "Wait" }, 429, { "Retry-After": "0" });
  });
  await assert.rejects(api("sessions", undefined, {}), { code: "RATE_LIMITED" });
  assert.equal(calls, 3);
});
