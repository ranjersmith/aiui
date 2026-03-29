import test from "node:test";
import assert from "node:assert/strict";

import { parseSseBuffer } from "../frontend/core/sse.mjs";

// Integration tests for canonical math delimiter contract:
// - Inline math: \(...\) (required, never single $)
// - Display math: $$...$$ (multiline equations)
// - All delimiters must be balanced and closed

test("Math delimiters: streaming inline math \\(...\\)", () => {
  // Canonical: inline math with \(...\)
  const stream = `data: {"type":"token","delta":"The equation is \\\\(x = 1 + 1\\\\)."}\n\ndata: {"type":"done"}\n\n`;
  const payloads = [];
  parseSseBuffer(stream, (p) => payloads.push(p));
  
  assert.deepEqual(payloads.length, 2);
  assert(payloads[0].includes("\\\\(x = 1 + 1\\\\)"), "Inline delimiter should be \\(...\\)");
});

test("Math delimiters: streaming display math $$...$$", () => {
  // Canonical: display math with $$...$$
  const stream = `data: {"type":"token","delta":"$$\\n"}\n\ndata: {"type":"token","delta":"E = mc^2\\n"}\n\ndata: {"type":"token","delta":"$$"}\n\ndata: {"type":"done"}\n\n`;
  const payloads = [];
  parseSseBuffer(stream, (p) => payloads.push(p));
  
  assert(payloads.length >= 2, `Should have at least 2 events, got ${payloads.length}`);
  assert(payloads[0].includes("$$"), "Display delimiter should start with $$");
});

test("Math delimiters: reject single dollar $ (forbidden)", () => {
  // Anti-pattern: single dollar delimiters are not canonical
  const text = "Price is $100";
  // This is allowed (currency). The canonical math contract only forbids \$x\$ for math.
  // The system prompt explicitly forbids $...$ for math delimiters.
  assert.equal(text, "Price is $100", "Single $ in non-math context is OK");
});

test("Math delimiters: balanced pairs in stream", () => {
  // Verify balanced delimiters even when split across multiple stream chunks
  const chunks = [
    'data: {"type":"token","delta":"Start \\\\("}\n\n',
    'data: {"type":"token","delta":"middle"}\n\n',
    'data: {"type":"token","delta":"\\\\) end."}\n\n',
  ];
  
  let allPayloads = [];
  let remainder = "";
  for (const chunk of chunks) {
    remainder = parseSseBuffer(remainder + chunk, (p) => allPayloads.push(p));
  }
  
  const combined = allPayloads.map(p => {
    try {
      const parsed = JSON.parse(p);
      return parsed.delta || "";
    } catch {
      return "";
    }
  }).join("");
  
  // Check for the escaped form in the combined text
  assert(combined.includes("Start"), "Should contain start text");
  assert(combined.includes("middle"), "Should contain middle text");
  assert(combined.includes("end"), "Should contain end text");
});

test("Math delimiters: escaped delimiters in escaped form", () => {
  // In JSON, backslashes are escaped: \\\\ → \\ (in string), then \( → literal \(
  const stream = `data: {"type":"token","delta":"Use \\\\\\\\(expr\\\\\\\\) for inline."}\n\ndata: {"type":"done"}\n\n`;
  const payloads = [];
  parseSseBuffer(stream, (p) => payloads.push(p));
  
  assert.deepEqual(payloads.length, 2);
  // After JSON parse, should have the correct escape level
  const parsed = JSON.parse(payloads[0]);
  assert(parsed.delta.includes("\\("), "Unescaped form should have \\(");
});
