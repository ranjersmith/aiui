export type Role = "user" | "assistant";

export type ChatMessage = {
  role: Role;
  content: string;
};

export type RuntimeConfig = {
  provider: "aiui-proxy" | "openai";
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
};

export type StreamHandlers = {
  onMeta: (model: string) => void;
  onStatus: (text: string) => void;
  onToken: (delta: string) => void;
  onDone: (summary: string) => void;
  onError: (text: string) => void;
};

export type StreamRequest = {
  config: RuntimeConfig;
  userText: string;
  history: ChatMessage[];
  signal: AbortSignal;
  handlers: StreamHandlers;
};

export type StreamProvider = (request: StreamRequest) => Promise<void>;
