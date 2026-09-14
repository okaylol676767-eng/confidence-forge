import type { ChatMeta } from "./types";

export type ConfidenceTier = "high" | "medium" | "low";

export const TIER_COLORS: Record<ConfidenceTier, string> = {
  high: "#34d399",
  medium: "#fbbf24",
  low: "#f87171",
};

export const TIER_LABELS: Record<ConfidenceTier, string> = {
  high: "High confidence",
  medium: "Moderate confidence",
  low: "Low confidence",
};

/** Coerce unknown confidence into a 0–1 float; null when unusable. */
export function normalizeConfidence(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw > 1 ? Math.min(raw / 100, 1) : Math.max(Math.min(raw, 1), 0);
  }
  if (typeof raw === "string") {
    const parsed = Number.parseFloat(raw);
    if (Number.isFinite(parsed)) {
      return parsed > 1
        ? Math.min(parsed / 100, 1)
        : Math.max(Math.min(parsed, 1), 0);
    }
  }
  return null;
}

export function getConfidence(meta?: ChatMeta | null): number | null {
  return meta ? normalizeConfidence(meta.confidence) : null;
}

export function getTier(confidence: number | null): ConfidenceTier | null {
  if (confidence === null) return null;
  // Bands match the model's calibrated scale (prompt v2): 0.95+ is
  // arithmetic-level certainty, 0.80-0.92 is a routine textbook result,
  // <0.60 means real doubt. Anything can still self-correct via the
  // vote: agreement is folded into the reported number downstream.
  if (confidence >= 0.93) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

/** Human label for a confidence value, with a graceful fallback. */
export function getConfidenceLabel(confidence: number | null): string {
  const tier = getTier(confidence);
  return tier ? TIER_LABELS[tier] : "Confidence unavailable";
}

/** "97%" or "—" when the value is missing. */
export function formatConfidencePct(confidence: number | null): string {
  return confidence === null
    ? "—"
    : `${Math.round(confidence * 100)}%`;
}

/** Milliseconds -> compact human duration: "2.4s", "38s", "1m 12s"; null if unusable. */
export function formatElapsed(ms: number | null | undefined): string | null {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
}

/** True when a stats payload is present enough to render the full modal. */
export function hasStatsData(meta?: ChatMeta | null): boolean {
  if (!meta) return false;
  const hasConfidence = meta.confidence !== null && meta.confidence !== undefined;
  const hasReason = typeof meta.confidence_reason === "string" && meta.confidence_reason.trim().length > 0;
  const hasFactors = Array.isArray(meta.uncertainty_factors) && meta.uncertainty_factors.length > 0;
  return hasConfidence || hasReason || hasFactors;
}
