/** Shape a successful assistant turn from POST /chat is expected to have. */
export interface ChatMeta {
  /** 0–1 float (also accepts 0–100, normalized internally). */
  confidence?: number | null;
  confidence_reason?: string | null;
  uncertainty_factors?: string[] | null;
  conversation_id?: string | null;
  timestamp?: string | null;
  /** Files attached to this turn (echoed by the backend). */
  attachments?: AttachmentMeta[] | null;
}

/** Metadata about one attached file (content is never persisted). */
export interface AttachmentMeta {
  filename: string;
  mime_type: string;
  size_bytes: number;
  kind: "image" | "document";
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
  /** Files attached to a user message (for display; files live in a ref). */
  attachments?: AttachmentMeta[];
  /** Lifecycle of this bubble. */
  status: "pending" | "sent" | "failed";
  /** User-safe error copy when status is "failed". */
  error?: string | null;
}

/** Subset of meta the stats modal cares about. */
export type StatsData = ChatMeta;
