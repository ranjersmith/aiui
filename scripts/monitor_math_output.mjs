#!/usr/bin/env node

const DEFAULT_ENDPOINT = process.env.AIUI_MONITOR_ENDPOINT || "http://127.0.0.1:3311/llm/v1/chat/completions";
const DEFAULT_MODEL = process.env.AIUI_MONITOR_MODEL || "Qwen/Qwen2.5-VL-3B-Instruct";
const DEFAULT_PROMPT =
  process.env.AIUI_MONITOR_PROMPT ||
  "Solve a quadratic equation and show formulas clearly using proper math notation.";
const DEFAULT_ATTEMPTS = Number(process.env.AIUI_MONITOR_ATTEMPTS || 20);
const DEFAULT_STREAK = Number(process.env.AIUI_MONITOR_STREAK || 3);
const DEFAULT_MAX_TOKENS = Number(process.env.AIUI_MONITOR_MAX_TOKENS || 700);

function parseArgs(argv) {
  const out = {
    endpoint: DEFAULT_ENDPOINT,
    model: DEFAULT_MODEL,
    prompt: DEFAULT_PROMPT,
    attempts: DEFAULT_ATTEMPTS,
    streak: DEFAULT_STREAK,
    maxTokens: DEFAULT_MAX_TOKENS,
    temperature: 0.2,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--endpoint" && next) {
      out.endpoint = next;
      i += 1;
    } else if (arg === "--model" && next) {
      out.model = next;
      i += 1;
    } else if (arg === "--prompt" && next) {
      out.prompt = next;
      i += 1;
    } else if (arg === "--attempts" && next) {
      out.attempts = Number(next);
      i += 1;
    } else if (arg === "--streak" && next) {
      out.streak = Number(next);
      i += 1;
    } else if (arg === "--max-tokens" && next) {
      out.maxTokens = Number(next);
      i += 1;
    } else if (arg === "--temperature" && next) {
      out.temperature = Number(next);
      i += 1;
    }
  }

  if (!Number.isFinite(out.attempts) || out.attempts < 1) out.attempts = 1;
  if (!Number.isFinite(out.streak) || out.streak < 1) out.streak = 1;
  if (!Number.isFinite(out.maxTokens) || out.maxTokens < 1) out.maxTokens = 700;
  if (!Number.isFinite(out.temperature) || out.temperature < 0) out.temperature = 0.2;

  return out;
}

function preprocessRawText(content) {
  let text = String(content || "").replace(/\r\n?/g, "\n");
  text = text.replace(/\\n/g, "\n");
  text = text.replace(/\\\[((?:.|\n)*?)\\\]/g, (_m, expr) => `$$${String(expr).trim()}$$`);
  text = text.replace(/\\\(((?:.|\n)*?)\\\)/g, (_m, expr) => `$${String(expr).trim()}$`);
  text = text.replace(/\\\(/g, "(").replace(/\\\)/g, ")");
  text = text.replace(/\\\[/g, "[").replace(/\\\]/g, "]");
  text = text.replace(/\\\\(?=[A-Za-z])/g, "\\");
  text = text.replace(/\\+(?=[#$*`_])/g, "");
  text = text.replace(/\\+\$/g, "$");
  return text;
}

function hasMalformedMathDelimiters(text) {
  const withoutCodeFences = text.replace(/```[\s\S]*?```/g, "");

  const displayCount = (withoutCodeFences.match(/(?<!\\)\$\$/g) || []).length;
  if (displayCount % 2 !== 0) return true;

  const maskedDisplay = withoutCodeFences.replace(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$/g, "");
  const inlineCount = (maskedDisplay.match(/(?<!\\)(?<!\$)\$(?!\$)/g) || []).length;
  if (inlineCount % 2 !== 0) return true;

  return false;
}

function analyze(content) {
  const raw = preprocessRawText(content);
  const malformed = hasMalformedMathDelimiters(raw);
  const latexCommands = (raw.match(/\\[A-Za-z]+\b/g) || []).length;
  const inlineMath = (raw.match(/(?<!\\)(?<!\$)\$([^$\n]{1,500})\$(?!\$)/g) || []).length;
  const displayMath = (raw.match(/(?<!\\)\$\$([\s\S]{1,2000}?)(?<!\\)\$\$/g) || []).length;
  const hasMathSignal = latexCommands > 0 || inlineMath > 0 || displayMath > 0;
  const pass = !malformed && hasMathSignal;

  return {
    pass,
    malformed,
    hasMathSignal,
    latexCommands,
    inlineMath,
    displayMath,
    sample: raw.replace(/\s+/g, " ").slice(0, 180),
  };
}

async function fetchCompletion(config) {
  const response = await fetch(config.endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: config.model,
      messages: [
        {
          role: "system",
          content: [
            "Return valid Markdown.",
            "Use \\(...\\) for inline math.",
            "Use $$...$$ for display math.",
            "Never use single-dollar inline delimiters like $...$.",
            "Ensure all math delimiters are balanced and closed."
          ].join("\n"),
        },
        { role: "user", content: config.prompt },
      ],
      stream: false,
      temperature: config.temperature,
      max_tokens: config.maxTokens,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body.slice(0, 300)}`);
  }

  const json = await response.json();
  const text = String(json?.choices?.[0]?.message?.content || "");
  return text;
}

async function main() {
  const cfg = parseArgs(process.argv);

  console.log("monitor config:", {
    endpoint: cfg.endpoint,
    model: cfg.model,
    attempts: cfg.attempts,
    streak: cfg.streak,
    maxTokens: cfg.maxTokens,
    temperature: cfg.temperature,
  });

  let passStreak = 0;
  let totalPasses = 0;

  for (let i = 1; i <= cfg.attempts; i += 1) {
    let content = "";
    try {
      content = await fetchCompletion(cfg);
    } catch (error) {
      console.error(`attempt ${i}/${cfg.attempts}: request failed`, String(error));
      passStreak = 0;
      continue;
    }

    const result = analyze(content);
    if (result.pass) {
      passStreak += 1;
      totalPasses += 1;
    } else {
      passStreak = 0;
    }

    console.log(
      [
        `attempt ${i}/${cfg.attempts}`,
        result.pass ? "PASS" : "FAIL",
        `streak=${passStreak}`,
        `malformed=${result.malformed}`,
        `latex=${result.latexCommands}`,
        `inline=${result.inlineMath}`,
        `display=${result.displayMath}`,
        `sample=${JSON.stringify(result.sample)}`,
      ].join(" | ")
    );

    if (passStreak >= cfg.streak) {
      console.log(`success: reached pass streak ${passStreak}/${cfg.streak}`);
      process.exit(0);
    }
  }

  console.error(`failed: could not reach pass streak ${cfg.streak} within ${cfg.attempts} attempts (passes=${totalPasses})`);
  process.exit(1);
}

main().catch((error) => {
  console.error("fatal:", error);
  process.exit(1);
});
