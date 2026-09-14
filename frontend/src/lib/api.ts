import type { ChatMeta } from "./types";
import { normalizeConfidence } from "./confidence";

/**
 * The single place frontend talks to the backend. `/chat` etc. are proxied to
 * the FastAPI server by a Next.js rewrite (see next.config.ts) — in prod, set
 * NEXT_PUBLIC_API_ORIGIN to the public API origin and rebuild.
 */
export const CHAT_ENDPOINT = "/chat";

interface BackendErrorEnvelope {
  error?: boolean;
  message?: string;
  code?: string;
}

const REQUEST_TIMEOUT_MS = 45_000;

export class ApiError extends Error {
  /** Machine code used for UX decisions; never shown raw to the user. */
  code: "network" | "server" | "timeout" | "offline";
  constructor(message: string, code: ApiError["code"]) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

/** User-safe error copy keyed by failure kind. */
const FRIENDLY_ERRORS: Record<ApiError["code"], string> = {
  network: "I couldn't reach SPIRAL. Check your connection and try again.",
  timeout: "SPIRAL took too long to answer. Give it another go.",
  offline: "You appear to be offline. Reconnect and try again.",
  server: "SPIRAL stumbled on that one. Please try again.",
};

/** Detail from the backend's standard error envelope, if the body is one. */
async function backendDetail(res: Response): Promise<string | null> {
  try {
    const body = (await res.json()) as BackendErrorEnvelope;
    const msg = typeof body?.message === "string" ? body.message.trim() : "";
    return msg.length > 0 && msg.length <= 300 ? msg : null;
  } catch {
    return null;
  }
}

export function friendlyError(error: unknown): string {
  if (error instanceof ApiError) return error.message || FRIENDLY_ERRORS[error.code];
  return "Something unexpected happened. Please try again.";
}

function inferCode(status: number): ApiError["code"] {
  if (status === 503 || status === 502 || status === 504) return "server";
  if (status >= 500) return "server";
  return "network";
}

/** Extracts an assistant reply + meta from many plausible backend shapes. */
function extractReply(payload: unknown): { content: string; meta: ChatMeta } | null {
  if (payload === null || typeof payload !== "object") return null;
  const obj = payload as Record<string, unknown>;

  // Reply text can live at `response`, `reply`, `message` (string), or `message.content`.
  let content: string | null = null;
  if (typeof obj.response === "string") content = obj.response;
  else if (typeof obj.reply === "string") content = obj.reply;
  else if (typeof obj.answer === "string") content = obj.answer;
  else if (typeof obj.message === "string") content = obj.message;
  else if (
    obj.message !== null &&
    typeof obj.message === "object" &&
    typeof (obj.message as Record<string, unknown>).content === "string"
  ) {
    content = (obj.message as Record<string, unknown>).content as string;
  }
  if (content === null) return null;

  // Meta may be a sibling `meta`/`confidence` object, or the payload itself.
  const metaLike =
    obj.meta && typeof obj.meta === "object"
      ? (obj.meta as Record<string, unknown>)
      : obj;

  const factors = metaLike.uncertainty_factors;
  const meta: ChatMeta = {
    confidence: normalizeConfidence(metaLike.confidence),
    confidence_reason:
      typeof metaLike.confidence_reason === "string"
        ? metaLike.confidence_reason
        : null,
    uncertainty_factors: Array.isArray(factors)
      ? factors.filter((f): f is string => typeof f === "string" && f.trim().length > 0)
      : null,
    conversation_id:
      typeof obj.conversation_id === "string"
        ? obj.conversation_id
        : typeof metaLike.conversation_id === "string"
          ? (metaLike.conversation_id as string)
          : null,
    timestamp:
      typeof obj.timestamp === "string"
        ? obj.timestamp
        : typeof metaLike.timestamp === "string"
          ? (metaLike.timestamp as string)
          : new Date().toISOString(),
  };

  return { content, meta };
}

export interface ChatSuccess {
  content: string;
  meta: ChatMeta;
}

/** POST { message, conversation_id } → assistant reply + transparency meta. */
export async function sendChatMessage(
  message: string,
  conversationId: string | null,
  signal?: AbortSignal,
): Promise<ChatSuccess> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError(FRIENDLY_ERRORS.offline, "offline");
  }

  const timeoutSignal = AbortSignal.timeout
    ? AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    : undefined;

  try {
    const res = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
      signal: timeoutSignal ?? signal,
    });

    if (!res.ok) {
      const code = inferCode(res.status);
      // Prefer the backend's own human message (e.g. "LLM not configured"),
      // falling back to our generic copy.
      const detail = await backendDetail(res);
      throw new ApiError(detail ?? FRIENDLY_ERRORS[code], code);
    }

    const payload: unknown = await res.json().catch(() => null);
    const reply = extractReply(payload);
    if (!reply) {
      throw new ApiError(FRIENDLY_ERRORS.server, "server");
    }
    return reply;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError")
    ) {
      throw new ApiError(FRIENDLY_ERRORS.timeout, "timeout");
    }
    if (error instanceof TypeError) {
      throw new ApiError(FRIENDLY_ERRORS.network, "network");
    }
    throw new ApiError(FRIENDLY_ERRORS.server, "server");
  }
}
