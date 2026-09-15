import type { AttachmentMeta, ChatMeta, SessionInfo, VerificationInfo } from "./types";
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
  const latencyRaw =
    typeof obj.latency_ms === "number"
      ? obj.latency_ms
      : (metaLike.latency_ms as unknown);
  const detailedRaw =
    typeof obj.detailed_solution === "string"
      ? obj.detailed_solution
      : (metaLike.detailed_solution as unknown);
  const verificationRaw =
    obj.verification && typeof obj.verification === "object"
      ? (obj.verification as Record<string, unknown>)
      : null;
  const verificationInfo: VerificationInfo | null =
    verificationRaw &&
    typeof verificationRaw.verdict === "string" &&
    ["confirmed", "corrected", "unavailable"].includes(verificationRaw.verdict)
      ? {
          verdict: verificationRaw.verdict as VerificationInfo["verdict"],
          detail: typeof verificationRaw.detail === "string" ? verificationRaw.detail : "",
        }
      : null;
  const meta: ChatMeta = {
    confidence: normalizeConfidence(metaLike.confidence),
    confidence_reason:
      typeof metaLike.confidence_reason === "string"
        ? metaLike.confidence_reason
        : null,
    uncertainty_factors: Array.isArray(factors)
      ? factors.filter((f): f is string => typeof f === "string" && f.trim().length > 0)
      : null,
    latency_ms:
      typeof latencyRaw === "number" && Number.isFinite(latencyRaw) && latencyRaw >= 0
        ? latencyRaw
        : null,
    detailed_solution:
      typeof detailedRaw === "string" && detailedRaw.trim().length > 0
        ? detailedRaw
        : null,
    verification: verificationInfo,
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

/** Metadata echoed back for attached files. */
function extractAttachments(payload: unknown): AttachmentMeta[] {
  if (payload === null || typeof payload !== "object") return [];
  const raw = (payload as Record<string, unknown>).attachments;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (item): item is Record<string, unknown> =>
        item !== null && typeof item === "object" && typeof (item as Record<string, unknown>).filename === "string",
    )
    .map((item) => ({
      filename: String(item.filename),
      mime_type: typeof item.mime_type === "string" ? item.mime_type : "application/octet-stream",
      size_bytes: typeof item.size_bytes === "number" ? item.size_bytes : 0,
      kind: item.kind === "image" ? ("image" as const) : ("document" as const),
    }));
}

export interface ChatSuccess {
  content: string;
  meta: ChatMeta;
}

// ---------- Sessions (named conversations) ----------

/** GET /sessions — most-recently-active named conversations. */
export async function fetchSessions(): Promise<SessionInfo[]> {
  const res = await fetch("/sessions").catch(() => null);
  if (!res || !res.ok) return [];
  const body: unknown = await res.json().catch(() => null);
  if (!Array.isArray(body)) return [];
  return body.filter(
    (item): item is SessionInfo =>
      item !== null &&
      typeof item === "object" &&
      typeof (item as Record<string, unknown>).conversation_id === "string" &&
      typeof (item as Record<string, unknown>).name === "string",
  );
}

/** PATCH /sessions/{id} — rename a conversation. Throws ApiError on failure. */
export async function renameSession(
  conversationId: string,
  name: string,
): Promise<SessionInfo | null> {
  let res: Response;
  try {
    res = await fetch(`/sessions/${encodeURIComponent(conversationId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  } catch {
    throw new ApiError(FRIENDLY_ERRORS.network, "network");
  }
  if (!res.ok) {
    const detail = await backendDetail(res);
    throw new ApiError(detail ?? FRIENDLY_ERRORS.server, inferCode(res.status));
  }
  const body: unknown = await res.json().catch(() => null);
  if (body === null || typeof body !== "object") return null;
  const obj = body as Record<string, unknown>;
  return {
    conversation_id: String(obj.conversation_id ?? conversationId),
    name: String(obj.name ?? name),
    message_count: typeof obj.message_count === "number" ? obj.message_count : 0,
    created_at: String(obj.created_at ?? ""),
    updated_at: String(obj.updated_at ?? ""),
  };
}

/**
 * POST a chat turn — plain text (JSON) or with files (multipart FormData).
 * Files are streamed as multipart; the backend validates and forwards them
 * to the model as inline parts.
 */
export async function sendChatMessage(
  message: string,
  conversationId: string | null,
  signal?: AbortSignal,
  files?: File[],
): Promise<ChatSuccess> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError(FRIENDLY_ERRORS.offline, "offline");
  }

  const timeoutSignal = AbortSignal.timeout
    ? AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    : undefined;

  try {
    let res: Response;
    if (files && files.length > 0) {
      const form = new FormData();
      form.append("message", message);
      if (conversationId) form.append("conversation_id", conversationId);
      for (const file of files) form.append("files", file);
      res = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        body: form,
        signal: timeoutSignal ?? signal,
      });
    } else {
      res = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          ...(conversationId ? { conversation_id: conversationId } : {}),
        }),
        signal: timeoutSignal ?? signal,
      });
    }

    if (!res.ok) {
      const code = inferCode(res.status);
      // Prefer the backend's own human message (e.g. "LLM not configured",
      // or an attachment-policy rejection), falling back to generic copy.
      const detail = await backendDetail(res);
      throw new ApiError(detail ?? FRIENDLY_ERRORS[code], code);
    }

    const payload: unknown = await res.json().catch(() => null);
    const reply = extractReply(payload);
    if (!reply) {
      throw new ApiError(FRIENDLY_ERRORS.server, "server");
    }
    const attachments = extractAttachments(payload);
    return {
      ...reply,
      meta: { ...reply.meta, attachments: attachments.length > 0 ? attachments : null },
    };
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
