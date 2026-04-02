/** Strip <think>...</think> blocks from text (Qwen best practice: no thinking content in history). */
export function stripThinkBlocks(text: string): string {
  return text.replace(/<think>[\s\S]*?<\/think>\s*/g, "").trim();
}

/** Check if content has an unclosed <think> tag (still streaming thinking). */
export function hasUnclosedThinkBlock(text: string): boolean {
  const opens = (text.match(/<think>/g) || []).length;
  const closes = (text.match(/<\/think>/g) || []).length;
  return opens > closes;
}
