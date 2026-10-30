import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  MESSAGE_VERSION, MAX_MESSAGE_BYTES, createMessage, parseMessage, serializeMessage
} from "../src/messaging.js";

const sample = () => createMessage("request", "example.ping", "req-1", {
  state: ["ready", true, 42, null], nested: { count: 2 }
});

test("a shared, versioned envelope round-trips as an object or JSON", () => {
  const message = sample();
  assert.equal(MESSAGE_VERSION, 1);
  assert.deepEqual(Object.keys(message), ["version", "kind", "topic", "requestId", "payload"]);
  assert.deepEqual(parseMessage(message), message);
  assert.deepEqual(parseMessage(serializeMessage(message)), message);
  assert.equal(MAX_MESSAGE_BYTES, 16384);
});

test("encoding and decoding always return detached message payloads", () => {
  const payload = { nested: { state: "original" } };
  const message = createMessage("event", "example.update", "req_2", payload);
  payload.nested.state = "changed";
  assert.equal(message.payload.nested.state, "original");
  const decoded = parseMessage(message);
  decoded.payload.nested.state = "changed";
  assert.equal(message.payload.nested.state, "original");
});

test("unknown protocol versions, kinds, fields, and missing fields fail closed", () => {
  const message = sample();
  for (const invalid of [
    { ...message, version: 2 }, { ...message, version: "1" },
    { ...message, kind: "open" }, { ...message, allowOpen: true },
    { ...message, payload: undefined },
    { version: 1, kind: "event", topic: "example.ping", requestId: "id" },
    [], null, 1
  ]) assert.throws(() => parseMessage(invalid), /Invalid shared extension message/);
});

test("topic and request identifiers use bounded, portable syntax", () => {
  for (const topic of ["", ".bad", "bad..topic", "Bad.case", "with/path", "a".repeat(81)]) {
    assert.throws(() => createMessage("event", topic, "valid"), TypeError);
  }
  for (const id of ["", "path/name", "with space", "x".repeat(81)]) {
    assert.throws(() => createMessage("event", "example.ping", id), TypeError);
  }
});

test("payloads reject executable, non-JSON, cyclic, sparse and unsafe data", () => {
  const cyclic = {};
  cyclic.next = cyclic;
  const accessor = {};
  Object.defineProperty(accessor, "secret", { enumerable: true, get() { throw Error("must not execute"); } });
  for (const payload of [
    cyclic, accessor, new Date(), new Map(), () => true, 1n,
    { status: Infinity }, { nested: { __proto__: null, constructor: "x" } },
    JSON.parse('{"__proto__":{"a":1}}'),
    [, "hole"], [1, undefined], { more: Symbol("s") }
  ]) assert.throws(() => createMessage("request", "example.ping", "id", payload), TypeError);
});

test("oversized and deeply nested messages are rejected before use", () => {
  assert.throws(() => createMessage("event", "example.ping", "id", "🦄".repeat(4100)), TypeError);
  assert.throws(() => parseMessage(" ".repeat(MAX_MESSAGE_BYTES + 1) + "{}"), TypeError);
  let nested = {};
  for (let i = 0; i < 10; i += 1) nested = { child: nested };
  assert.throws(() => createMessage("event", "example.ping", "id", nested), TypeError);
  assert.throws(() => parseMessage("{invalid"), TypeError);
});

test("the module has no browser listeners or privileged transport side effects", async () => {
  const source = await readFile(fileURLToPath(new URL("../src/messaging.js", import.meta.url)), "utf8");
  for (const forbidden of [
    "chrome.runtime", "browser.runtime", "sendNativeMessage", "connectNative",
    "addListener(", "fetch(", "WebSocket(", "window.open(", "localStorage"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
