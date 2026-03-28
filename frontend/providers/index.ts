import type { RuntimeConfig, StreamProvider } from "../core/types";
import { streamAiuiProxy } from "./aiuiProxy";
import { streamOpenAiCompatible } from "./openaiCompatible";

export function providerFor(config: RuntimeConfig): StreamProvider {
  return config.provider === "openai" ? streamOpenAiCompatible : streamAiuiProxy;
}
