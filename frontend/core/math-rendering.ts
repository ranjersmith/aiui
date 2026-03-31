const FENCED_CODE_BLOCK_REGEX = /```[\s\S]*?```/g;

function stripFencedCodeBlocks(text: string): string {
  return String(text || "").replace(FENCED_CODE_BLOCK_REGEX, "");
}

// See MATH_DELIMITERS_CONTRACT.json for canonical contract.
// Frontend normalizes backend-provided \(...\) and $$...$$ to remark-math's $...$ and $$...$$ format.
export function normalizeEscapedMathDelimiters(text: string): string {
  const codeFences: string[] = [];
  const withoutCodeFences = String(text || "").replace(FENCED_CODE_BLOCK_REGEX, (block) => {
    const token = `@@AIUI_CODE_FENCE_${codeFences.length}@@`;
    codeFences.push(block);
    return token;
  });

  const normalized = withoutCodeFences
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

export function preprocessRawText(content: string): string {
  const normalizedNewlines = String(content || "").replace(/\r\n?/g, "\n");
  return normalizeEscapedMathDelimiters(normalizedNewlines);
}

export function hasMalformedMathDelimiters(text: string): boolean {
  const withoutCodeFences = stripFencedCodeBlocks(text);

  const displayCount = (withoutCodeFences.match(/(?<!\\)\$\$/g) || []).length;
  if (displayCount % 2 !== 0) return true;

  const maskedDisplay = withoutCodeFences.replace(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$/g, "");
  const inlineCount = (maskedDisplay.match(/(?<!\\)(?<!\$)\$(?!\$)/g) || []).length;
  if (inlineCount % 2 !== 0) return true;

  return false;
}

export function shouldDeferMathRenderDuringStreaming(content: string): boolean {
  const raw = String(content || "");
  const normalized = preprocessRawText(raw);
  const rawWithoutCodeFences = stripFencedCodeBlocks(raw);
  const normalizedWithoutCodeFences = stripFencedCodeBlocks(normalized);

  if (hasMalformedMathDelimiters(normalizedWithoutCodeFences)) {
    return true;
  }

  if (/\\\(|\\\)|\\\[|\\\]/.test(rawWithoutCodeFences)) {
    return true;
  }

  if (/\\[A-Za-z]+\b/.test(rawWithoutCodeFences)) {
    return true;
  }

  if (/(?<!\\)\$\$/.test(normalizedWithoutCodeFences)) {
    return true;
  }

  if (/(?<!\\)(?<!\$)\$(?!\$)/.test(normalizedWithoutCodeFences)) {
    return true;
  }

  return false;
}