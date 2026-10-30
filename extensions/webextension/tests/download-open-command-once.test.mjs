import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createDownloadOpenCommandGate } from "../src/download-open-command-once.js";

const acknowledged = () => Promise.resolve({ accepted: true });
const expected = (status) => ({
  status, scanVerified: false, authorizesOpen: false, opened: false
});

test("one scan request sends exactly one command across independent trusted views", async () => {
  const gate = createDownloadOpenCommandGate();
  let commands = 0;
  const viewA = () => gate.requestOpenOnce("scan_42", () => {
    commands++;
    return acknowledged();
  });
  const viewB = () => gate.requestOpenOnce("scan_42", () => {
    commands++;
    return acknowledged();
  });
  assert.deepEqual(await viewA(), expected("command-submitted"));
  assert.deepEqual(await viewB(), expected("duplicate"));
  assert.deepEqual(await viewA(), expected("duplicate"));
  assert.equal(commands, 1);
  assert.equal(Object.isFrozen(gate), true);
  gate.dispose();
});

test("reservation happens synchronously before any asynchronous response", async () => {
  const gate = createDownloadOpenCommandGate();
  let finish;
  let commands = 0;
  const first = gate.requestOpenOnce("scan_42", () => {
    commands++;
    return new Promise((resolve) => { finish = resolve; });
  });
  const second = gate.requestOpenOnce("scan_42", () => {
    commands++;
    return acknowledged();
  });
  assert.equal(commands, 1);
  assert.deepEqual(await second, expected("duplicate"));
  finish({ accepted: true, scanVerified: true, opened: true });
  assert.deepEqual(await first, expected("command-submitted"));
  assert.equal(commands, 1);
  gate.dispose();
});

test("reentrant native callbacks cannot dispatch twice for the same scan", async () => {
  const gate = createDownloadOpenCommandGate();
  let calls = 0;
  const first = await gate.requestOpenOnce("job_7", async () => {
    calls++;
    const nested = await gate.requestOpenOnce("job_7", () => {
      calls++;
      return acknowledged();
    });
    assert.deepEqual(nested, expected("duplicate"));
    return { accepted: true };
  });
  assert.deepEqual(first, expected("command-submitted"));
  assert.equal(calls, 1);
  gate.dispose();
});

test("rejected command remains reserved, avoiding duplicate openings on retries", async () => {
  const gate = createDownloadOpenCommandGate();
  for (const [id, callback] of [
    ["error_1", () => { throw Error("/private/path.pdf"); }],
    ["error_2", () => Promise.reject(Error("https://private.example/token"))],
    ["error_3", () => Promise.resolve({ accepted: false })],
    ["error_4", () => Promise.resolve(null)],
    ["error_5", () => ({ accepted: true })],
    ["error_6", () => Promise.resolve({ accepted: "true" })]
  ]) {
    assert.deepEqual(await gate.requestOpenOnce(id, callback),
      expected("command-rejected"));
    let retried = false;
    assert.deepEqual(await gate.requestOpenOnce(id, () => {
      retried = true;
      return acknowledged();
    }), expected("duplicate"));
    assert.equal(retried, false);
  }
  gate.dispose();
});

test("hostile acknowledgement accessors cannot attest to a command", async () => {
  const gate = createDownloadOpenCommandGate();
  let accessed = 0;
  const forged = {};
  Object.defineProperty(forged, "accepted", { get() {
    accessed++;
    throw Error("private file");
  } });
  assert.deepEqual(await gate.requestOpenOnce("job_9", () => Promise.resolve(forged)),
    expected("command-rejected"));
  assert.equal(accessed, 0);
  assert.deepEqual(await gate.requestOpenOnce("job_9", acknowledged), expected("duplicate"));
  gate.dispose();
});

test("distinct scan request IDs can each send one command, including numeric-looking zero", async () => {
  const gate = createDownloadOpenCommandGate();
  const sent = [];
  for (const id of ["0", "scan_0", "scan-1", "job_9", "AbC-123"]) {
    assert.deepEqual(await gate.requestOpenOnce(id, () => {
      sent.push(id);
      return acknowledged();
    }), expected("command-submitted"));
  }
  assert.deepEqual(sent, ["0", "scan_0", "scan-1", "job_9", "AbC-123"]);
  for (const id of sent) {
    assert.deepEqual(await gate.requestOpenOnce(id, acknowledged), expected("duplicate"));
  }
  gate.dispose();
});

test("malformed IDs and missing callback never invoke opening and consume no slot", async () => {
  const gate = createDownloadOpenCommandGate();
  let opened = 0;
  for (const id of [
    null, undefined, "", 0, 1, 1.5, {}, [], "a b", "a/b",
    "a\nb", "a\0b", "a.b", "a".repeat(81), "ü"
  ]) {
    assert.deepEqual(await gate.requestOpenOnce(id, () => {
      opened++;
      return acknowledged();
    }), expected("unavailable"));
  }
  assert.deepEqual(await gate.requestOpenOnce("good", undefined), expected("unavailable"));
  assert.equal(opened, 0);
  assert.deepEqual(await gate.requestOpenOnce("good", () => {
    opened++;
    return acknowledged();
  }), expected("command-submitted"));
  assert.equal(opened, 1);
  gate.dispose();
});

test("fixed capacity fails closed without evicting an old reservation", async () => {
  const gate = createDownloadOpenCommandGate();
  let calls = 0;
  for (let i = 0; i < 256; i++) {
    assert.equal((await gate.requestOpenOnce("job_" + i, () => {
      calls++;
      return acknowledged();
    })).status, "command-submitted");
  }
  assert.deepEqual(await gate.requestOpenOnce("job_0", acknowledged), expected("duplicate"));
  assert.deepEqual(await gate.requestOpenOnce("job_256", () => {
    calls++;
    return acknowledged();
  }), expected("capacity-exhausted"));
  assert.equal(calls, 256);
  gate.dispose();
});

test("dispose rejects late submissions and invalidates a pending acknowledgement", async () => {
  const gate = createDownloadOpenCommandGate();
  let finish;
  const pending = gate.requestOpenOnce("job_1", () =>
    new Promise((resolve) => { finish = resolve; }));
  gate.dispose();
  gate.dispose();
  finish({ accepted: true });
  assert.deepEqual(await pending, expected("command-rejected"));
  let invoked = false;
  assert.deepEqual(await gate.requestOpenOnce("job_2", () => {
    invoked = true;
    return acknowledged();
  }), expected("unavailable"));
  assert.equal(invoked, false);
});

test("acknowledgement of submission is never reported as scanned or opened", async () => {
  const gate = createDownloadOpenCommandGate();
  for (const [i, response] of [
    { accepted: true, scanVerified: true, authorizesOpen: true, opened: true },
    { accepted: true, malwareDetected: false, path: "/private/report.pdf" },
    { accepted: true, sourceUrl: "https://private.example/token" }
  ].entries()) {
    const result = await gate.requestOpenOnce("scan_" + i, () => Promise.resolve(response));
    assert.deepEqual(result, expected("command-submitted"));
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(Object.isFrozen(result), true);
  }
  gate.dispose();
});

test("a native callback receives no path, URL, scanner verdict or browser metadata", async () => {
  const gate = createDownloadOpenCommandGate();
  let argumentsPassed = null;
  await gate.requestOpenOnce("scan_1", (...args) => {
    argumentsPassed = args;
    return acknowledged();
  });
  assert.deepEqual(argumentsPassed, []);
  gate.dispose();
});

test("the gate never clears reservations on browser lifecycle or a failed open", async () => {
  const gate = createDownloadOpenCommandGate();
  assert.equal((await gate.requestOpenOnce("scan_1", acknowledged)).status,
    "command-submitted");
  // A new browser download or another UI rendering must not reset a native
  // scan-session opening command. Only disposal ends this session.
  assert.deepEqual(await gate.requestOpenOnce("scan_1", acknowledged), expected("duplicate"));
  gate.dispose();
});

test("module is passive and leaves native safety, opening, popup and settings untouched", async () => {
  const code = await readFile(new URL("../src/download-open-command-once.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const popup = await readFile(new URL("../src/popup.html", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.match(popup, /Not active/);
  for (const forbidden of [
    "window.open(", "downloads.open(", "connectNative(", "sendNativeMessage(",
    "scan_and_open", "clamscan", "node:fs", "fetch(", "localStorage",
    "storage.local", "permissions.request(", "innerHTML"
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
