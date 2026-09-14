"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import type { StatsData } from "@/lib/types";
import { getConfidence, hasStatsData } from "@/lib/confidence";
import { ConfidenceRing } from "./ConfidenceRing";
import { ClockIcon, CloseIcon, ShieldQuestionIcon } from "./icons";

interface StatsModalProps {
  open: boolean;
  stats: StatsData | null;
  onClose: () => void;
}

function formatTimestamp(timestamp: string | null | undefined): string | null {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function StatsModal({ open, stats, onClose }: StatsModalProps) {
  // Close on Escape + lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  const confidence = getConfidence(stats);
  const reason = stats?.confidence_reason?.trim() || null;
  const factors =
    stats?.uncertainty_factors?.filter((f) => typeof f === "string" && f.trim().length > 0) ??
    null;
  const timestamp = formatTimestamp(stats?.timestamp);
  const usable = hasStatsData(stats);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="fixed inset-0 z-[80] flex items-end justify-center p-3 sm:items-center sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-label="Answer confidence stats"
          onClick={onClose}
        >
          {/* backdrop */}
          <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-md" />

          <motion.div
            initial={{ opacity: 0, y: 48, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 32, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            className="glass relative max-h-[86dvh] w-full max-w-lg overflow-y-auto nice-scrollbar rounded-3xl p-6 shadow-[0_32px_90px_rgba(2,4,14,0.7)] sm:p-8"
          >
            {/* top glow accent */}
            <div
              aria-hidden
              className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-forge-lime/70 to-transparent"
            />

            <button
              onClick={onClose}
              aria-label="Close stats"
              className="ring-focus absolute right-4 top-4 rounded-xl p-2 text-slate-400 transition hover:bg-white/5 hover:text-white"
            >
              <CloseIcon />
            </button>

            <p className="label-mono text-forge-lime/90">
              Transparency report
            </p>
            <h2 className="font-display mt-1 text-xl font-semibold text-white">
              Answer confidence
            </h2>

            {!usable ? (
              <FallbackState />
            ) : (
              <>
                {/* ————— gauge ————— */}
                <div className="mt-6 flex justify-center">
                  <ConfidenceRing confidence={confidence} />
                </div>

                {/* ————— reason ————— */}
                <div className="mt-6">
                  <p className="label-mono text-forge-muted/60">Why this score</p>
                  {reason ? (
                    <p className="mt-2 rounded-2xl border border-white/10 bg-white/[0.04] p-4 font-mono text-sm leading-relaxed text-forge-muted">
                      {reason}
                    </p>
                  ) : (
                    <p className="mt-2 text-sm italic text-forge-muted/50">
                      No reasoning was provided for this answer.
                    </p>
                  )}
                </div>

                {/* ————— uncertainty factors ————— */}
                <div className="mt-6">
                  <p className="label-mono text-forge-muted/60">Uncertainty factors</p>
                  {factors && factors.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {factors.map((factor, i) => (
                        <motion.span
                          key={`${factor}-${i}`}
                          initial={{ opacity: 0, scale: 0.85, y: 6 }}
                          animate={{ opacity: 1, scale: 1, y: 0 }}
                          transition={{ delay: 0.25 + i * 0.06 }}
                          className="label-mono rounded-full border border-forge-amber/30 bg-forge-amber/[0.08] px-3 py-1.5 text-[10px] text-forge-amber shadow-[0_0_16px_rgba(232,211,122,0.15)]"
                        >
                          {factor}
                        </motion.span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm italic text-slate-500">
                      No uncertainty factors reported.
                    </p>
                  )}
                </div>

                {/* ————— timestamp ————— */}
                {timestamp && (
                  <div className="label-mono mt-6 flex items-center gap-2 border-t border-white/10 pt-4 text-[9px] text-forge-muted/50">
                    <ClockIcon width={13} height={13} />
                    Generated {timestamp}
                  </div>
                )}
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Polished fallback when stats data is missing or malformed. */
function FallbackState() {
  return (
    <div className="mt-8 flex flex-col items-center gap-4 pb-2 text-center">
      <div className="relative">
        <div className="absolute inset-0 -z-10 rounded-full bg-slate-400/20 blur-2xl" />
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-400">
          <ShieldQuestionIcon width={26} height={26} />
        </div>
      </div>
      <div className="space-y-1.5">
        <p className="font-medium text-slate-200">No transparency data available</p>
        <p className="mx-auto max-w-xs text-sm leading-relaxed text-slate-500">
          SPIRAL didn&apos;t attach confidence details to this answer. This
          can happen for very short replies or transient backend hiccups.
        </p>
      </div>
      <div className="grid w-full grid-cols-3 gap-2 pt-2">
        {["Score", "Reason", "Factors"].map((label) => (
          <div
            key={label}
            className="rounded-xl border border-white/[0.06] bg-white/[0.03] px-2 py-3 text-center"
          >
            <p className="text-[10px] uppercase tracking-[0.14em] text-slate-600">{label}</p>
            <p className="mt-1 text-xs text-slate-500">unavailable</p>
          </div>
        ))}
      </div>
    </div>
  );
}
