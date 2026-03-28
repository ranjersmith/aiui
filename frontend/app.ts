import { createMemo, createSignal } from "solid-js";
import { render } from "solid-js/web";
import html from "solid-js/html";

import { readConfig } from "./core/config.mjs";
import { providerFor } from "./providers";
import type { ChatMessage, StreamHandlers } from "./core/types";

const MAX_RENDERED_MESSAGES = 120;

function App() {
  const config = createMemo(readConfig);
  const [messages, setMessages] = createSignal<ChatMessage[]>([]);
  const [input, setInput] = createSignal("");
  const [isStreaming, setIsStreaming] = createSignal(false);
  const [status, setStatus] = createSignal("idle");
  const [activeModel, setActiveModel] = createSignal(config().model);
  const [firstTokenLatencyMs, setFirstTokenLatencyMs] = createSignal<number | null>(null);
  const [flushesPerSecond, setFlushesPerSecond] = createSignal(0);
  const [tokenCount, setTokenCount] = createSignal(0);
  const [tokensPerSecond, setTokensPerSecond] = createSignal(0);
  const [totalElapsedMs, setTotalElapsedMs] = createSignal<number | null>(null);

  let currentAbort: AbortController | null = null;
  let pendingDelta = "";
  let flushAnimationFrame: number | null = null;
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

  function scheduleFlush() {
    if (flushAnimationFrame !== null) return;
    flushAnimationFrame = window.requestAnimationFrame(() => {
      flushAnimationFrame = null;
      flushPendingDelta();
    });
  }

  function cancelScheduledFlush() {
    if (flushAnimationFrame !== null) {
      window.cancelAnimationFrame(flushAnimationFrame);
      flushAnimationFrame = null;
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

  async function sendMessage() {
    const text = input().trim();
    if (!text || isStreaming()) return;

    const history = messages();
    setMessages([...history, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setInput("");
    setStatus("streaming...");
    setIsStreaming(true);

    streamStartedAtMs = performance.now();
    hasSeenFirstToken = false;
    setFirstTokenLatencyMs(null);
    setTokenCount(0);
    setTokensPerSecond(0);
    setTotalElapsedMs(null);
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
        scheduleFlush();
      },
      onDone: (summary) => {
        cancelScheduledFlush();
        flushPendingDelta();
        const elapsedMs = Math.round(performance.now() - streamStartedAtMs);
        setTotalElapsedMs(elapsedMs);
        const finalRate = Math.round((tokenCount() * 1000) / Math.max(elapsedMs, 1));
        setTokensPerSecond(finalRate);
        setStatus(summary ? `done | ${summary}` : "done");
      },
      onError: (errorText) => {
        cancelScheduledFlush();
        flushPendingDelta();
        const elapsedMs = Math.round(performance.now() - streamStartedAtMs);
        setTotalElapsedMs(elapsedMs);
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

  const messageList = () =>
    visibleMessages().map((msg) =>
      html`<article class=${`msg ${msg.role}`}>
        <div class="msg-meta">${msg.role === "assistant" ? "aiui" : "user"}</div>
        <div class="msg-content">
          <div class="md-plain">${msg.content}</div>
        </div>
      </article>`
    );

  return html`<div class="aiui-shell">
    <div class="panel app-layout">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="brand">aiui</div>
          <div class="muted">provider: ${() => config().provider}</div>
          <div class="muted">model: ${activeModel}</div>
          <div class="muted">${status}</div>
          <div class="muted">
            first token: ${() => (firstTokenLatencyMs() === null ? "-" : `${firstTokenLatencyMs()} ms`)}
          </div>
          <div class="muted">tokens: ${tokenCount}</div>
          <div class="muted">rate: ${tokensPerSecond} t/s</div>
          <div class="muted">
            elapsed: ${() => (totalElapsedMs() === null ? "-" : `${totalElapsedMs()} ms`)}
          </div>
          <div class="muted">flushes/s: ${flushesPerSecond}</div>
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
          <div class="composer-shell">
            <textarea
              class="input composer-textarea"
              value=${input}
              placeholder="ask anything..."
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
