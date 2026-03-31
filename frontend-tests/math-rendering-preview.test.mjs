import test from "node:test";
import assert from "node:assert/strict";

import {
  hasMalformedMathDelimiters,
  normalizeEscapedMathDelimiters,
  shouldDeferMathRenderDuringStreaming,
} from "../frontend/core/math-rendering.ts";

test("streaming preview defers KaTeX for complete inline math", () => {
  const content = "The result is \\(x^2 + y^2\\).";

  assert.equal(shouldDeferMathRenderDuringStreaming(content), true);
  assert.equal(hasMalformedMathDelimiters(normalizeEscapedMathDelimiters(content)), false);
});

test("streaming preview defers KaTeX for incomplete display math", () => {
  const content = "Working:\n$$\nE = mc^2";

  assert.equal(shouldDeferMathRenderDuringStreaming(content), true);
  assert.equal(hasMalformedMathDelimiters(normalizeEscapedMathDelimiters(content)), true);
});

test("streaming preview does not defer plain markdown", () => {
  const content = "Plain text with a code block.\n\n```js\nconst value = 1;\n```";

  assert.equal(shouldDeferMathRenderDuringStreaming(content), false);
});

test("streaming preview ignores latex-like text inside fenced code blocks", () => {
  const content = "```tex\n\\frac{1}{2}\n```";

  assert.equal(shouldDeferMathRenderDuringStreaming(content), false);
});