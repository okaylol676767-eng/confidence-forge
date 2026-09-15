"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import type { Message } from "@/lib/types";
import {
  formatConfidencePct,
  formatElapsed,
  getConfidence,
  getConfidenceLabel,
  getTier,
  TIER_COLORS,
} from "@/lib/confidence";
import {
  AttachIcon,
  ClockIcon,
  RetryIcon,
  StatsIcon,
  ThumbDownIcon,
  ThumbUpIcon,
} from "../icons";
import { MarkdownContent } from "./MarkdownContent";
import { DetailedSolution } from "./DetailedSolution";

const TIME_FMT = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});

function formatTime(timestamp: string | null): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return TIME_FMT.format(date);
}

/** Ticks every 100ms while an assistant reply is generating. */
function ElapsedTicker() {
  const [elapsedMs, setElapsedMs] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsedMs(Date.now() - started),
      100,
    );
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span
      className="label-mono inline-flex items-center gap-1 text-[9px] tabular-nums text-forge-lime/60"
      aria-label="Time elapsed"
    >
      <ClockIcon width={11} height={11} className="animate-pulse" />
      {formatElapsed(elapsedMs) ?? "0s"} elapsed
    </span>
  );
}

interface BubbleProps {
  message: Message;
  onRetry: (id: string) => void;
  onOpenStats: (message: Message) => void;
}

export function MessageBubble({ message, onRetry, onOpenStats }: BubbleProps) {
  const isUser = message.role === "user";
  const isPending = message.status === "pending";
  const isFailed = message.status === "failed";

  const confidence = getConfidence(message.meta);
  const tier = getTier(confidence);
  const tierColor = tier ? TIER_COLORS[tier] : null;
  const time = formatTime(message.timestamp);

  return (
    <motion.div
      layout="position"
      initial={{ opacity: 0, y: 18, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div className={`flex max-w-[86%] flex-col gap-1.5 sm:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {/* ————— bubble ————— */}
        <div
          className={[
            "relative rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-[0_10px_30px_rgba(2,4,14,0.45)] transition",
            isUser
              ? "rounded-br-md border border-forge-lime/30 bg-forge-lime/[0.08] text-forge-muted"
              : "glass rounded-bl-md text-forge-muted",
            isFailed ? "border-forge-red/45" : "",
          ].join(" ")}
        >
          {isUser && message.attachments && message.attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap justify-end gap-1.5 border-b border-forge-lime/15 pb-2">
              {message.attachments.map((att, index) => (
                <span
                  key={`${att.filename}-${index}`}
                  className="label-mono inline-flex max-w-[200px] items-center gap-1.5 rounded-full border border-forge-lime/25 bg-forge-lime/[0.06] py-0.5 pl-2 pr-2.5 text-[9px] text-forge-lime/90"
                  title={`${att.filename} · ${att.mime_type} · ${Math.max(1, Math.round(att.size_bytes / 1024))} KB`}
                >
                  <AttachIcon width={10} height={10} className="shrink-0" />
                  <span className="truncate">{att.filename}</span>
                  <span className="text-forge-muted/40">{att.kind === "image" ? "img" : "doc"}</span>
                </span>
              ))}
            </div>
          )}
          {isPending ? (
            <TypingDots />
          ) : isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <>
              {/* Assistant: markdown + LaTeX math ($...$, $$...$$) via KaTeX. */}
              <MarkdownContent content={message.content} />
              {/* Full derivation, collapsed by default ("See detailed solution"). */}
              {!isPending && (
                <DetailedSolution content={message.meta?.detailed_solution} />
              )}
            </>
          )}

          {isFailed && (
            <div className="mt-2 flex items-center gap-2.5 border-t border-forge-red/25 pt-2">
              <p className="text-xs text-forge-red/90">{message.error ?? "Message failed to send."}</p>
              <button
                onClick={() => onRetry(message.id)}
                className="ring-focus ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-full border border-forge-red/40 bg-forge-red/10 px-3 py-1 text-xs font-semibold text-forge-red transition hover:bg-forge-red/20"
              >
                <RetryIcon width={12} height={12} />
                Retry
              </button>
            </div>
          )}
        </div>

        {/* ————— meta row ————— */}
        {(time ||
          isPending ||
          (message.role === "assistant" && message.status === "sent")) && (
          <div className={`flex items-center gap-2 px-1 ${isUser ? "flex-row-reverse" : ""}`}>
            {isPending && <ElapsedTicker />}
            {time && (
              <span className="label-mono inline-flex items-center gap-1 text-[9px] text-forge-muted/40">
                <ClockIcon width={11} height={11} />
                {time}
              </span>
            )}

            {message.role === "assistant" && message.status === "sent" && (
              <>
                {(() => {
                  const elapsed = formatElapsed(message.meta?.latency_ms);
                  return elapsed ? (
                    <span
                      className="label-mono inline-flex items-center gap-1 text-[9px] tabular-nums text-forge-muted/45"
                      title="Backend-measured response time"
                    >
                      <ClockIcon width={11} height={11} />
                      {elapsed}
                    </span>
                  ) : null;
                })()}

                {(() => {
                  const v = message.meta?.verification;
                  if (!v || v.verdict === "unavailable") return null;
                  const verified = v.verdict === "confirmed";
                  return (
                    <span
                      className="label-mono inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold"
                      style={
                        verified
                          ? { color: "#34d399", borderColor: "#34d39955", backgroundColor: "#34d39914" }
                          : { color: "#fbbf24", borderColor: "#fbbf2455", backgroundColor: "#fbbf2414" }
                      }
                      title={v.detail || (verified ? "Independently re-derived and confirmed" : "Corrected by the verification pass")}
                    >
                      {verified ? "✓ VERIFIED" : "↻ CORRECTED"}
                    </span>
                  );
                })()}

                {confidence !== null && tier && tierColor ? (
                  <span
                    className="label-mono inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold"
                    style={{
                      color: tierColor,
                      borderColor: `${tierColor}55`,
                      backgroundColor: `${tierColor}14`,
                      boxShadow: `0 0 14px ${tierColor}30`,
                    }}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full animate-pulse-glow"
                      style={{ backgroundColor: tierColor, boxShadow: `0 0 8px ${tierColor}` }}
                    />
                    {formatConfidencePct(confidence)} · {getConfidenceLabel(confidence).split(" ")[0]}
                  </span>
                ) : (
                  <span className="label-mono inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[9px] font-medium text-forge-muted/50">
                    <span className="h-1.5 w-1.5 rounded-full bg-forge-muted/40" />
                    Confidence unavailable
                  </span>
                )}

                {/* View Stats */}
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.96 }}
                  onClick={() => onOpenStats(message)}
                  className="label-mono ring-focus group inline-flex items-center gap-1.5 rounded-full border border-forge-lime/40 bg-forge-lime/10 px-3 py-1 text-[9px] font-semibold text-forge-lime shadow-[0_0_16px_rgba(198,255,77,0.2)] transition hover:border-forge-lime/70 hover:bg-forge-lime/20"
                >
                  <StatsIcon width={12} height={12} className="transition group-hover:rotate-6" />
                  View Stats
                </motion.button>

                <FeedbackButtons />
              </>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-0.5" aria-label="Assistant is typing">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

/** 👍/👎 with optimistic visual feedback; no backend wire-up yet. */
function FeedbackButtons() {
  const [choice, setChoice] = useState<"up" | "down" | null>(null);

  const btn = (kind: "up" | "down", Icon: typeof ThumbUpIcon, label: string) => {
    const active = choice === kind;
    const color = kind === "up" ? "#34d399" : "#f87171";
    return (
      <motion.button
        whileTap={{ scale: 0.8 }}
        onClick={() => setChoice(active ? null : kind)}
        className={`ring-focus rounded-lg p-1 transition ${
          active ? "" : "text-slate-500 hover:bg-white/5 hover:text-slate-300"
        }`}
        style={active ? { color, filter: `drop-shadow(0 0 6px ${color})` } : undefined}
        aria-label={label}
        aria-pressed={active}
      >
        <Icon width={13} height={13} />
      </motion.button>
    );
  };

  return (
    <span className="inline-flex items-center gap-0.5">
      {btn("up", ThumbUpIcon, "Helpful")}
      {btn("down", ThumbDownIcon, "Not helpful")}
    </span>
  );
}
