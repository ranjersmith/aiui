import test from "node:test";
import assert from "node:assert/strict";

import { parseSseBuffer } from "../frontend/core/sse.mjs";

test("parseSseBuffer handles CRLF events", () => {
  const payloads = [];
  const remainder = parseSseBuffer(
    'data: {"type":"token","delta":"Hi"}\r\n\r\ndata: {"type":"done"}\r\n\r\ndata: {"type":"partial"',
    (payload) => payloads.push(payload)
  );

  assert.deepEqual(payloads, ['{"type":"token","delta":"Hi"}', '{"type":"done"}']);
  assert.equal(remainder, 'data: {"type":"partial"');
});

test("parseSseBuffer joins multiline data payloads", () => {
  const payloads = [];
  const remainder = parseSseBuffer(
    "data: first line\ndata: second line\n\n",
    (payload) => payloads.push(payload)
  );

  assert.deepEqual(payloads, ["first line\nsecond line"]);
  assert.equal(remainder, "");
});
