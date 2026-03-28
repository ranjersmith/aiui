import test from "node:test";
import assert from "node:assert/strict";

import { normalizeBaseUrl } from "../frontend/core/config.mjs";

test("normalizeBaseUrl trims whitespace and trailing slash", () => {
  assert.equal(normalizeBaseUrl("  http://localhost:8081/  "), "http://localhost:8081");
});

test("normalizeBaseUrl keeps empty input empty", () => {
  assert.equal(normalizeBaseUrl(""), "");
});
