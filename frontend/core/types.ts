export type ProviderKind = "openai";

export type RuntimeConfig = {
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
  systemPrompt: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type StreamHandlers = {
  onMeta: (modelName: string) => void;
  onStatus: (textStatus: string) => void;
  onToken: (delta: string) => void;
  onDone: (summary?: string) => void;
  onError: (errorText: string) => void;
};

export type StreamProvider = (args: {
  config: RuntimeConfig;
  userText: string;
  history: ChatMessage[];
  signal: AbortSignal;
  handlers: StreamHandlers;
}) => Promise<void>;
