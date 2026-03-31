export type ProviderKind = "openai";
export type Role = "user" | "assistant";

export type RuntimeConfig = {
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
  systemPrompt: string;
  toolProfile: "safe" | "minimal" | "trusted" | "all";
  toolStrategy: "nous" | "qwen_native" | "deepseek";
};

export type Attachment = {
  type: "image" | "text";
  name: string;
  mimeType: string;
  dataUrl?: string;     // set for images (full base64 data URL)
  textContent?: string; // set for text files
};

export type ChatMessage = {
  role: Role;
  content: string;
  attachments?: Attachment[];
};

export type StreamHandlers = {
  onMeta: (modelName: string) => void;
  onStatus: (textStatus: string) => void;
  onToken: (delta: string) => void;
  onThinkingToken?: () => void;
  onDone: (summary?: string) => void;
  onError: (errorText: string) => void;
};

export type StreamProvider = (args: {
  config: RuntimeConfig;
  userText: string;
  history: ChatMessage[];
  attachments: Attachment[];
  signal: AbortSignal;
  handlers: StreamHandlers;
}) => Promise<void>;
