/** Shape a successful assistant turn from POST /chat is expected to have. */
export interface ChatMeta {
  /** 0–1 float (also accepts 0–100, normalized internally). */
  confidence?: number | null;
  confidence_reason?: string | null;
  uncertainty_factors?: string[] | null;
  conversation_id?: string | null;
  timestamp?: string | null;
}

/** A single message in the local conversation state. */
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** ISO timestamp or null while pending. */
  timestamp: string | null;
  /** Present on assistant messages; undefined until the reply lands. */
  meta?: ChatMeta;
  /** Lifecycle of this bubble. */
  status: "pending" | "sent" | "failed";
  /** User-safe error copy when status is "failed". */
  error?: string | null;
}

/** Subset of meta the stats modal cares about. */
export type StatsData = ChatMeta;
