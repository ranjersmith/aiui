/**
 * Markdown rendering pipeline — unified/remark/rehype with KaTeX math and code highlighting.
 *
 * Pure, stateless module: no SolidJS signals or DOM references.
 */

import createDOMPurify from "dompurify";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkMath from "remark-math";
import remarkRehype from "remark-rehype";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import rehypeStringify from "rehype-stringify";

import {
  hasMalformedMathDelimiters,
  preprocessRawText,
  shouldDeferMathRenderDuringStreaming,
} from "./math-rendering";

// ── Types ─────────────────────────────────────────────────────────────────

export type RenderFallbackReason = "malformed-math-delimiters" | "pipeline-error" | "streaming-math-deferred";

export type RenderedMarkdown = {
  html: string;
  fallbackReason: RenderFallbackReason | null;
  trace: RenderTrace;
};

export type RenderTrace = {
  raw: string;
  normalized: string;
  finalHtml: string;
  malformedMathDelimiters: boolean;
  fallbackReason: RenderFallbackReason | null;
  updatedAt: string;
};

export type StreamingPreview = {
  html: string;
  trace: RenderTrace;
};

export type NotationDiagnostics = {
  source: "streaming" | "final" | "error";
  sample: string;
  renderMode: "streaming-preview" | "final-math" | "final-plain-fallback" | "error-plain";
  fallbackReason: RenderFallbackReason | null;
  malformedMathDelimiters: boolean;
  latexCommandCount: number;
  inlineMathSegments: number;
  displayMathSegments: number;
  scientificNotationCount: number;
  unicodeMathSymbolCount: number;
  updatedAt: string;
};

// ── Pipeline instances ────────────────────────────────────────────────────

const markdownTokenizer = unified().use(remarkParse).use(remarkMath, {
  singleDollarTextMath: true,
});
const plainMarkdownTokenizer = unified().use(remarkParse);
const mdastToHast = unified().use(remarkRehype);
const mathRenderer = unified().use(rehypeKatex, {
  throwOnError: false,
  strict: "ignore",
});
const codeHighlighter = unified().use(rehypeHighlight, { detect: true, ignoreMissing: true });
const hastStringifier = unified().use(rehypeStringify);

const domPurify = typeof window !== "undefined" ? createDOMPurify(window) : null;

const MAX_MARKDOWN_CACHE_SIZE = 500;
const markdownHtmlCache = new Map<string, RenderedMarkdown>();

// ── Rendering helpers ─────────────────────────────────────────────────────

function sanitizeHtml(fragment: string): string {
  return domPurify ? domPurify.sanitize(fragment) : fragment;
}

export function buildRenderTrace(
  raw: string,
  normalized: string,
  finalHtml: string,
  fallbackReason: RenderFallbackReason | null
): RenderTrace {
  return {
    raw,
    normalized,
    finalHtml,
    malformedMathDelimiters: hasMalformedMathDelimiters(normalized),
    fallbackReason,
    updatedAt: new Date().toLocaleTimeString(),
  };
}

function renderMarkdownWithMath(raw: string): string {
  const mdast = markdownTokenizer.parse(raw);
  const hast = mdastToHast.runSync(mdast);
  const hastWithMath = mathRenderer.runSync(hast);
  const hastWithHighlight = codeHighlighter.runSync(hastWithMath);
  return String(hastStringifier.stringify(hastWithHighlight));
}

function renderMarkdownPlain(raw: string): string {
  const mdast = plainMarkdownTokenizer.parse(raw);
  const hast = mdastToHast.runSync(mdast);
  const hastWithHighlight = codeHighlighter.runSync(hast);
  return String(hastStringifier.stringify(hastWithHighlight));
}

function renderMarkdownFromPipeline(content: string): RenderedMarkdown {
  const raw = String(content || "");
  const normalized = preprocessRawText(raw);
  const malformedMathDelimiters = hasMalformedMathDelimiters(normalized);

  if (malformedMathDelimiters) {
    const html = sanitizeHtml(renderMarkdownPlain(normalized));
    return {
      html,
      fallbackReason: "malformed-math-delimiters",
      trace: buildRenderTrace(raw, normalized, html, "malformed-math-delimiters"),
    };
  }

  try {
    const html = sanitizeHtml(renderMarkdownWithMath(normalized));
    return {
      html,
      fallbackReason: null,
      trace: buildRenderTrace(raw, normalized, html, null),
    };
  } catch {
    const html = sanitizeHtml(renderMarkdownPlain(normalized));
    return {
      html,
      fallbackReason: "pipeline-error",
      trace: buildRenderTrace(raw, normalized, html, "pipeline-error"),
    };
  }
}

function resolveRenderMode(source: NotationDiagnostics["source"], fallbackReason: RenderFallbackReason | null): NotationDiagnostics["renderMode"] {
  if (source === "streaming") return "streaming-preview";
  if (source === "error") return "error-plain";
  if (fallbackReason) return "final-plain-fallback";
  return "final-math";
}

export function logNotationDiagnostics(diag: NotationDiagnostics): void {
  const payload = {
    source: diag.source,
    renderMode: diag.renderMode,
    fallbackReason: diag.fallbackReason,
    malformedMathDelimiters: diag.malformedMathDelimiters,
    latexCommandCount: diag.latexCommandCount,
    inlineMathSegments: diag.inlineMathSegments,
    displayMathSegments: diag.displayMathSegments,
    scientificNotationCount: diag.scientificNotationCount,
    unicodeMathSymbolCount: diag.unicodeMathSymbolCount,
    sample: diag.sample,
  };
  console.debug("[aiui][notation-monitor]", payload);
}

export function logRenderTrace(trace: RenderTrace): void {
  console.debug("[aiui][render-trace]", {
    fallbackReason: trace.fallbackReason,
    malformedMathDelimiters: trace.malformedMathDelimiters,
    raw: trace.raw,
    normalized: trace.normalized,
    finalHtml: trace.finalHtml,
  });
}

export function renderMessageMarkdown(content: string): RenderedMarkdown {
  const source = String(content || "");
  const cached = markdownHtmlCache.get(source);
  if (cached) return cached;

  const rendered = renderMarkdownFromPipeline(source);

  if (markdownHtmlCache.size >= MAX_MARKDOWN_CACHE_SIZE) {
    const firstKey = markdownHtmlCache.keys().next().value;
    if (firstKey !== undefined) markdownHtmlCache.delete(firstKey);
  }
  markdownHtmlCache.set(source, rendered);
  return rendered;
}

export function renderStreamingPreview(content: string): StreamingPreview {
  const normalized = preprocessRawText(content);
  const shouldDeferMath = shouldDeferMathRenderDuringStreaming(content);

  if (!shouldDeferMath) {
    const rendered = renderMessageMarkdown(content);
    return {
      html: rendered.html,
      trace: rendered.trace,
    };
  }

  try {
    const html = sanitizeHtml(renderMarkdownPlain(normalized));
    return {
      html,
      trace: buildRenderTrace(
        String(content || ""),
        normalized,
        html,
        hasMalformedMathDelimiters(normalized) ? "malformed-math-delimiters" : "streaming-math-deferred"
      ),
    };
  } catch {
    const html = sanitizeHtml(normalized);
    return {
      html,
      trace: buildRenderTrace(String(content || ""), normalized, html, "pipeline-error"),
    };
  }
}

export function buildNotationDiagnostics(
  content: string,
  source: NotationDiagnostics["source"],
  fallbackReason: RenderFallbackReason | null
): NotationDiagnostics {
  const raw = preprocessRawText(content);
  const sample = raw.replace(/\s+/g, " ").trim().slice(0, 160);

  const latexCommandCount = (raw.match(/\\[A-Za-z]+\b/g) || []).length;
  const inlineMathSegments = (raw.match(/(?<!\\)(?<!\$)\$([^$\n]{1,500})\$(?!\$)/g) || []).length;
  const displayMathSegments = (raw.match(/(?<!\\)\$\$([\s\S]{1,2000}?)(?<!\\)\$\$/g) || []).length;
  const scientificNotationCount =
    (raw.match(/\b\d+(?:\.\d+)?e[+-]?\d+\b/gi) || []).length +
    (raw.match(/\b10\^\{?-?\d+\}?\b/g) || []).length;
  const unicodeMathSymbolCount = (raw.match(/[±×÷≈≠≤≥∞∑∫√∆∂πμσλθΩωα-ωΑ-Ω]/g) || []).length;

  return {
    source,
    sample,
    renderMode: resolveRenderMode(source, fallbackReason),
    fallbackReason,
    malformedMathDelimiters: hasMalformedMathDelimiters(raw),
    latexCommandCount,
    inlineMathSegments,
    displayMathSegments,
    scientificNotationCount,
    unicodeMathSymbolCount,
    updatedAt: new Date().toLocaleTimeString(),
  };
}
