import type { RuntimeConfig, StreamProvider } from "../core/types";
import { streamOpenAiCompatible } from "./openaiCompatible";

export function providerFor(_config: RuntimeConfig): StreamProvider {
  return streamOpenAiCompatible;
}
