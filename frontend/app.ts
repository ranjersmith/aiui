import { createMemo, createSignal } from "solid-js";
import { render } from "solid-js/web";
import html from "solid-js/html";
import createDOMPurify from "dompurify";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkMath from "remark-math";
import remarkRehype from "remark-rehype";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import rehypeStringify from "rehype-stringify";

import { readConfig } from "./core/config.mjs";
import { providerFor } from "./providers";
import type { Attachment, ChatMessage, StreamHandlers } from "./core/types";

const MAX_RENDERED_MESSAGES = 120;
const MAX_MARKDOWN_CACHE_SIZE = 500;
const STREAM_FLUSH_INTERVAL_MS = 80;

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
type RenderFallbackReason = "malformed-math-delimiters" | "pipeline-error";

type RenderedMarkdown = {
  html: string;
  fallbackReason: RenderFallbackReason | null;
  trace: RenderTrace;
};

type RenderTrace = {
  raw: string;
  normalized: string;
  finalHtml: string;
  malformedMathDelimiters: boolean;
  fallbackReason: RenderFallbackReason | null;
  updatedAt: string;
};

type StreamingPreview = {
  html: string;
  isBuffered: boolean;
  trace: RenderTrace;
};

type NotationDiagnostics = {
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

const markdownHtmlCache = new Map<string, RenderedMarkdown>();

// See MATH_DELIMITERS_CONTRACT.json for canonical contract.
// Frontend normalizes backend-provided \(...\) and $$...$$ to remark-math's $...$ and $$...$$ format.
function normalizeEscapedMathDelimiters(text: string): string {
  const codeFences: string[] = [];
  const withoutCodeFences = text.replace(/```[\s\S]*?```/g, (block) => {
    const token = `@@AIUI_CODE_FENCE_${codeFences.length}@@`;
    codeFences.push(block);
    return token;
  });

  const normalized = withoutCodeFences
    // Backend sends \[...\] and \(...\), remark-math expects $$...$$ and $...$ respectively.
    .replace(/\\\[([\s\S]+?)\\\]/g, (_match, inner: string) => `$$${inner}$$`)
    .replace(/\\\((.+?)\\\)/g, (_match, inner: string) => `$${inner}$`)
    .replace(/\\\$\\\$([\s\S]+?)\\\$\\\$/g, (_match, inner: string) => `$$${inner}$$`)
    .replace(/\\\$(.+?)\\\$/g, (match, inner: string) => {
      const looksMath = /[A-Za-z\\^_{}=+\-*/]/.test(inner);
      return looksMath ? `$${inner}$` : match;
    });

  return normalized.replace(/@@AIUI_CODE_FENCE_(\d+)@@/g, (_token, index: string) => {
    const i = Number(index);
    return Number.isInteger(i) && codeFences[i] ? codeFences[i] : "";
  });
}

function preprocessRawText(content: string): string {
  const normalizedNewlines = String(content || "").replace(/\r\n?/g, "\n");
  return normalizeEscapedMathDelimiters(normalizedNewlines);
}

function hasMalformedMathDelimiters(text: string): boolean {
  // Hide fenced code blocks from delimiter checks.
  const withoutCodeFences = text.replace(/```[\s\S]*?```/g, "");

  const displayCount = (withoutCodeFences.match(/(?<!\\)\$\$/g) || []).length;
  if (displayCount % 2 !== 0) return true;

  const maskedDisplay = withoutCodeFences.replace(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$/g, "");
  const inlineCount = (maskedDisplay.match(/(?<!\\)(?<!\$)\$(?!\$)/g) || []).length;
  if (inlineCount % 2 !== 0) return true;

  return false;
}

function sanitizeHtml(fragment: string): string {
  return domPurify ? domPurify.sanitize(fragment) : fragment;
}

function buildRenderTrace(
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

  // Delimiter-driven rendering: when delimiters are malformed, skip math parsing
  // and render plain markdown without mutating source content.
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

function logNotationDiagnostics(diag: NotationDiagnostics): void {
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

function logRenderTrace(trace: RenderTrace): void {
  console.debug("[aiui][render-trace]", {
    fallbackReason: trace.fallbackReason,
    malformedMathDelimiters: trace.malformedMathDelimiters,
    raw: trace.raw,
    normalized: trace.normalized,
    finalHtml: trace.finalHtml,
  });
}

function renderMessageMarkdown(content: string): RenderedMarkdown {
  const source = String(content || "");
  const cached = markdownHtmlCache.get(source);
  if (cached) return cached;

  // renderMarkdownFromPipeline handles all fallback logic and error recovery.
  const rendered = renderMarkdownFromPipeline(source);

  // LRU eviction: remove oldest key when cache is full (not clear all).
  if (markdownHtmlCache.size >= MAX_MARKDOWN_CACHE_SIZE) {
    const firstKey = markdownHtmlCache.keys().next().value;
    if (firstKey !== undefined) markdownHtmlCache.delete(firstKey);
  }
  markdownHtmlCache.set(source, rendered);
  return rendered;
}

function renderStreamingPreview(content: string, previousHtml: string): StreamingPreview {
  const rendered = renderMessageMarkdown(content);

  if (!rendered.trace.malformedMathDelimiters) {
    return {
      html: rendered.html,
      isBuffered: false,
      trace: rendered.trace,
    };
  }

  const normalized = preprocessRawText(content);

  try {
    const html = sanitizeHtml(renderMarkdownPlain(normalized));
    return {
      html,
      isBuffered: Boolean(previousHtml),
      trace: buildRenderTrace(String(content || ""), normalized, html, "malformed-math-delimiters"),
    };
  } catch {
    const html = sanitizeHtml(normalized);
    return {
      html,
      isBuffered: false,
      trace: buildRenderTrace(String(content || ""), normalized, html, "pipeline-error"),
    };
  }
}

function buildNotationDiagnostics(
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

function App() {
  const config = createMemo(readConfig);
  const [messages, setMessages] = createSignal<ChatMessage[]>([]);
  const [input, setInput] = createSignal("");
  const [pendingAttachments, setPendingAttachments] = createSignal<Attachment[]>([]);
  const [isStreaming, setIsStreaming] = createSignal(false);
  const [status, setStatus] = createSignal("idle");
  const [activeModel, setActiveModel] = createSignal(config().model);
  const [firstTokenLatencyMs, setFirstTokenLatencyMs] = createSignal<number | null>(null);
  const [flushesPerSecond, setFlushesPerSecond] = createSignal(0);
  const [tokenCount, setTokenCount] = createSignal(0);
  const [tokensPerSecond, setTokensPerSecond] = createSignal(0);
  const [totalElapsedMs, setTotalElapsedMs] = createSignal<number | null>(null);
  const [notationDiagnostics, setNotationDiagnostics] = createSignal<NotationDiagnostics | null>(null);
  const [streamingPreview, setStreamingPreview] = createSignal<StreamingPreview | null>(null);
  const [renderTrace, setRenderTrace] = createSignal<RenderTrace | null>(null);
  const [lastCompletedMetrics, setLastCompletedMetrics] = createSignal<string | null>(null);

  let currentAbort: AbortController | null = null;
  let fileInputRef: HTMLInputElement | undefined;
  let pendingDelta = "";
  let flushTimer: number | null = null;
  let lastMonitorLogAtMs = 0;
  let streamStartedAtMs = 0;
  let hasSeenFirstToken = false;
  let flushCountCurrentSecond = 0;
  let flushRateInterval: number | null = null;

  function flushPendingDelta() {
    if (!pendingDelta) return;
    const chunk = pendingDelta;
    pendingDelta = "";
    flushCountCurrentSecond += 1;

    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = { ...last, content: `${last.content}${chunk}` };
      }
      return next;
    });
  }

  function assistantTailTextWithPending(): string {
    const all = messages();
    const last = all[all.length - 1];
    const committed = last?.role === "assistant" ? last.content : "";
    return `${committed}${pendingDelta}`;
  }

  function scheduleFlush() {
    if (flushTimer !== null) return;
    flushTimer = window.setTimeout(() => {
      flushTimer = null;
      flushPendingDelta();
    }, STREAM_FLUSH_INTERVAL_MS);
  }

  function cancelScheduledFlush() {
    if (flushTimer !== null) {
      window.clearTimeout(flushTimer);
      flushTimer = null;
    }
  }

  function stopFlushRateMeter() {
    if (flushRateInterval !== null) {
      window.clearInterval(flushRateInterval);
      flushRateInterval = null;
    }
  }

  function startFlushRateMeter() {
    flushCountCurrentSecond = 0;
    setFlushesPerSecond(0);
    stopFlushRateMeter();
    flushRateInterval = window.setInterval(() => {
      setFlushesPerSecond(flushCountCurrentSecond);
      flushCountCurrentSecond = 0;
    }, 1000);
  }

  const TEXT_EXTS = new Set([
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".csv", ".xml", ".html", ".css", ".sh", ".bash", ".zsh", ".rb",
    ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".sql", ".env", ".ini",
    ".cfg", ".conf", ".log",
  ]);

  function isTextFile(file: File): boolean {
    if (file.type.startsWith("text/")) return true;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    return TEXT_EXTS.has(ext);
  }

  function handleFileSelect(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files || []);
    input.value = "";

    for (const file of files) {
      const reader = new FileReader();
      if (file.type.startsWith("image/")) {
        reader.onload = () => {
          setPendingAttachments((prev) => [
            ...prev,
            {
              type: "image",
              name: file.name,
              mimeType: file.type,
              dataUrl: reader.result as string,
            },
          ]);
        };
        reader.readAsDataURL(file);
      } else if (isTextFile(file)) {
        reader.onload = () => {
          setPendingAttachments((prev) => [
            ...prev,
            {
              type: "text",
              name: file.name,
              mimeType: file.type || "text/plain",
              textContent: reader.result as string,
            },
          ]);
        };
        reader.readAsText(file);
      }
      // PDF/DOCX silently ignored — requires backend support
    }
  }

  async function sendMessage() {
    const text = input().trim();
    const attachments = pendingAttachments();
    if ((!text && attachments.length === 0) || isStreaming()) return;

    const history = messages();
    setMessages([
      ...history,
      { role: "user", content: text, attachments: attachments.length ? attachments : undefined },
      { role: "assistant", content: "" },
    ]);
    setInput("");
    setPendingAttachments([]);
    setStatus("streaming...");
    setIsStreaming(true);

    streamStartedAtMs = performance.now();
    hasSeenFirstToken = false;
    setFirstTokenLatencyMs(null);
    setTokenCount(0);
    setTokensPerSecond(0);
    setTotalElapsedMs(null);
    setStreamingPreview(null);
    setLastCompletedMetrics(null);
    startFlushRateMeter();

    const abortController = new AbortController();
    currentAbort = abortController;

    const handlers: StreamHandlers = {
      onMeta: (modelName) => {
        if (modelName.trim()) setActiveModel(modelName.trim());
      },
      onStatus: (textStatus) => setStatus(textStatus || "streaming..."),
      onToken: (delta) => {
        if (!hasSeenFirstToken) {
          hasSeenFirstToken = true;
          setFirstTokenLatencyMs(Math.max(0, Math.round(performance.now() - streamStartedAtMs)));
        }
        setTokenCount((prev) => prev + 1);
        const elapsedMs = performance.now() - streamStartedAtMs;
        const rate = Math.round((tokenCount() * 1000) / Math.max(elapsedMs, 1));
        setTokensPerSecond(rate);
        pendingDelta += delta;
        const preview = renderStreamingPreview(assistantTailTextWithPending(), streamingPreview()?.html || "");
        setStreamingPreview(preview);
        setRenderTrace(preview.trace);
        const diag = buildNotationDiagnostics(assistantTailTextWithPending(), "streaming", null);
        setNotationDiagnostics(diag);
        const now = performance.now();
        if (now - lastMonitorLogAtMs >= 750) {
          logNotationDiagnostics(diag);
          logRenderTrace(preview.trace);
          lastMonitorLogAtMs = now;
        }
        scheduleFlush();
      },
      onDone: (summary) => {
        cancelScheduledFlush();
        flushPendingDelta();
        const finalRendered = renderMessageMarkdown(assistantTailTextWithPending());
        setStreamingPreview(null);
        setRenderTrace(finalRendered.trace);
        const diag = buildNotationDiagnostics(assistantTailTextWithPending(), "final", finalRendered.fallbackReason);
        setNotationDiagnostics(diag);
        logNotationDiagnostics(diag);
        logRenderTrace(finalRendered.trace);
        const elapsedMs = Math.round(performance.now() - streamStartedAtMs);
        setTotalElapsedMs(elapsedMs);
        const finalRate = Math.round((tokenCount() * 1000) / Math.max(elapsedMs, 1));
        setTokensPerSecond(finalRate);
        const ttftSnap = firstTokenLatencyMs() ?? 0;
        const toksSnap = tokenCount();
        setLastCompletedMetrics(`⏱ ${ttftSnap}ms • ${toksSnap}t • ${finalRate}t/s • ${elapsedMs}ms`);
        if (summary && summary !== "done") {
          setStatus(`done | ${summary}`);
        } else {
          setStatus("done");
        }
      },
      onError: (errorText) => {
        cancelScheduledFlush();
        flushPendingDelta();
        setStreamingPreview(null);
        const errored = renderMessageMarkdown(assistantTailTextWithPending());
        setRenderTrace(errored.trace);
        const diag = buildNotationDiagnostics(assistantTailTextWithPending(), "error", "pipeline-error");
        setNotationDiagnostics(diag);
        logNotationDiagnostics(diag);
        logRenderTrace(errored.trace);
        const elapsedMs = Math.round(performance.now() - streamStartedAtMs);
        setTotalElapsedMs(elapsedMs);
        const ttftErr = firstTokenLatencyMs() ?? 0;
        const toksErr = tokenCount();
        const rateErr = Math.round((toksErr * 1000) / Math.max(elapsedMs, 1));
        setLastCompletedMetrics(`⏱ ${ttftErr}ms • ${toksErr}t • ${rateErr}t/s • ${elapsedMs}ms`);
        setStatus(`error: ${errorText}`);
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant" && !last.content.trim()) {
            next[next.length - 1] = { role: "assistant", content: `Error: ${errorText}` };
          }
          return next;
        });
      },
    };

    try {
      const provider = providerFor(config());
      await provider({
        config: config(),
        userText: text,
        history,
        attachments,
        signal: abortController.signal,
        handlers,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setStatus("stopped");
        return;
      }
      const errorText = error instanceof Error ? error.message : String(error);
      handlers.onError(errorText);
    } finally {
      cancelScheduledFlush();
      flushPendingDelta();
      stopFlushRateMeter();
      setIsStreaming(false);
      currentAbort = null;
    }
  }

  function stopStream() {
    if (!currentAbort) return;
    currentAbort.abort();
    currentAbort = null;
    stopFlushRateMeter();
    setIsStreaming(false);
    setStatus("stopped");
  }

  function clearChat() {
    if (isStreaming()) return;
    setMessages([]);
    setStatus("idle");
  }

  const visibleMessages = () => {
    const all = messages();
    return all.length > MAX_RENDERED_MESSAGES
      ? all.slice(all.length - MAX_RENDERED_MESSAGES)
      : all;
  };

  const hiddenMessageCount = () => Math.max(0, messages().length - MAX_RENDERED_MESSAGES);

  const messageList = () => {
    const visible = visibleMessages();
    const lastIndex = visible.length - 1;

    return visible.map((msg, index) => {
      const isStreamingAssistantTail = isStreaming() && msg.role === "assistant" && index === lastIndex;
      const rendered = isStreamingAssistantTail
        ? streamingPreview() || renderStreamingPreview(msg.content, "")
        : renderMessageMarkdown(msg.content);

      const isLastAssistant = msg.role === "assistant" && index === lastIndex;

      return html`<article class=${`msg ${msg.role}`}>
        <div class="msg-meta">
          ${msg.role === "assistant" ? "aiui" : "user"}
          ${isStreamingAssistantTail
            ? html`<span class="render-debug-badge">${() => {
                const ttft = firstTokenLatencyMs() ?? 0;
                const toks = tokenCount();
                const rate = tokensPerSecond().toFixed(1);
                const elapsed = totalElapsedMs() ?? 0;
                return `⏱ ${ttft}ms • ${toks}t • ${rate}t/s • ${elapsed}ms`;
              }}</span>`
            : isLastAssistant && lastCompletedMetrics()
              ? html`<span class="render-debug-badge">${lastCompletedMetrics}</span>`
              : null}
        </div>
        <div class="msg-content">
          ${msg.attachments?.length
            ? html`<div class="msg-attachments">
                ${msg.attachments.map((a) =>
                  a.type === "image" && a.dataUrl
                    ? html`<img class="msg-attachment-thumb" src=${a.dataUrl} alt=${a.name} title=${a.name} />`
                    : html`<span class="msg-attachment-file" title=${a.name}>📄 ${a.name}</span>`
                )}
              </div>`
            : null}
          <div class="md-rendered" innerHTML=${rendered.html}></div>
        </div>
      </article>`;
    });
  };

  return html`<div class="aiui-shell">
    <div class="panel app-layout">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="brand">aiui</div>
          <div class="muted">${activeModel}</div>
          <!-- Debug monitor UI hidden by default; enable with ?debug=1 URL param -->
          ${() => {
            // Notation diagnostics debug monitor (development only)
            const debug = new URLSearchParams(location.search).get("debug") === "1";
            if (!debug) return null;
            
            const diag = notationDiagnostics();
            if (!diag) return null;

            return html`<div class="monitor-card">
              <div class="monitor-title">notation monitor (${diag.source})</div>
              <div class="monitor-grid">
                <div class="monitor-row">latex commands: ${diag.latexCommandCount}</div>
                <div class="monitor-row">inline math segments: ${diag.inlineMathSegments}</div>
                <div class="monitor-row">display math segments: ${diag.displayMathSegments}</div>
                <div class="monitor-row">render mode: ${diag.renderMode}</div>
                <div class="monitor-row">fallback reason: ${diag.fallbackReason || "none"}</div>
                <div class="monitor-row">scientific notation: ${diag.scientificNotationCount}</div>
                <div class="monitor-row">unicode math symbols: ${diag.unicodeMathSymbolCount}</div>
                <div class=${`monitor-row ${diag.malformedMathDelimiters ? "warn" : "ok"}`}>
                  delimiters: ${diag.malformedMathDelimiters ? "malformed" : "balanced"}
                </div>
                <div class="monitor-row">updated: ${diag.updatedAt}</div>
              </div>
              <div class="monitor-sample">${diag.sample || "(empty)"}</div>
            </div>`;
          }}
          ${() => {
            // Render trace debug monitor (development only)
            const debug = new URLSearchParams(location.search).get("debug") === "1";
            if (!debug) return null;
            
            const trace = renderTrace();
            if (!trace) return null;

            return html`<div class="monitor-card">
              <div class="monitor-title">render trace</div>
              <div class="monitor-grid">
                <div class=${`monitor-row ${trace.malformedMathDelimiters ? "warn" : "ok"}`}>
                  normalized delimiters: ${trace.malformedMathDelimiters ? "malformed" : "balanced"}
                </div>
                <div class="monitor-row">fallback: ${trace.fallbackReason || "none"}</div>
                <div class="monitor-row">updated: ${trace.updatedAt}</div>
              </div>
              <details>
                <summary>raw output</summary>
                <pre class="monitor-sample">${trace.raw || "(empty)"}</pre>
              </details>
              <details>
                <summary>normalized output</summary>
                <pre class="monitor-sample">${trace.normalized || "(empty)"}</pre>
              </details>
              <details>
                <summary>rendered html</summary>
                <pre class="monitor-sample">${trace.finalHtml || "(empty)"}</pre>
              </details>
            </div>`;
          }}
        </div>
        <div class="chat-list" aria-hidden="true"></div>
        <div class="sidebar-footer">
          <button class="button" onClick=${clearChat} disabled=${isStreaming}>clear</button>
        </div>
      </aside>

      <main class="main">
        <section class="thread">
          ${() =>
            hiddenMessageCount() > 0
              ? html`<div class="muted">Showing latest ${MAX_RENDERED_MESSAGES} of ${messages().length} messages</div>`
              : null}
          ${() =>
            messages().length
              ? messageList()
              : html`<div class="thread-empty-card">
                  <div class="thread-empty-title">minimal llm ui</div>
                  <div class="thread-empty-copy">provider is modular. swap llm by config only.</div>
                </div>`}
        </section>

        <section class="composer">
          <input
            type="file"
            multiple
            accept="image/png,image/jpeg,image/gif,image/webp,.txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.toml,.csv,.xml,.html,.css,.sh,.rb,.go,.rs,.java,.c,.cpp,.h,.sql"
            style="display:none"
            ref=${(el: HTMLInputElement) => { fileInputRef = el; }}
            onChange=${handleFileSelect}
          />
          ${() => {
            const chips = pendingAttachments();
            if (!chips.length) return null;
            return html`<div class="composer-attachments">
              ${chips.map((a, i) =>
                html`<div class="attachment-chip">
                  ${a.type === "image" && a.dataUrl
                    ? html`<img class="attachment-chip-thumb" src=${a.dataUrl} alt=${a.name} />`
                    : html`<span class="attachment-chip-icon">📄</span>`}
                  <span class="attachment-chip-name">${a.name}</span>
                  <button
                    class="attachment-chip-remove"
                    title="Remove"
                    onClick=${() => setPendingAttachments((prev) => prev.filter((_, j) => j !== i))}
                  >×</button>
                </div>`
              )}
            </div>`;
          }}
          <div class="composer-shell">
            <textarea
              class="input composer-textarea"
              value=${input}
              placeholder="ask anything..."
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              onInput=${(event: InputEvent) => {
                const target = event.currentTarget as HTMLTextAreaElement;
                setInput(target.value);
              }}
              onKeyDown=${(event: KeyboardEvent) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              disabled=${isStreaming}
            ></textarea>
          </div>

          <div class="composer-buttons">
            <button
              class="button secondary"
              title="Attach file"
              onClick=${() => fileInputRef?.click()}
              disabled=${isStreaming}
            >📎</button>
            <button class="button primary" onClick=${() => void sendMessage()} disabled=${isStreaming}>
              ${() => (isStreaming() ? "streaming..." : "send")}
            </button>
            <button class="button warn" onClick=${stopStream} disabled=${() => !isStreaming()}>
              stop
            </button>
          </div>
        </section>
      </main>
    </div>
  </div>`;
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}

render(App, root);
