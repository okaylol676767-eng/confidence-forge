"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { SparkIcon } from "./icons";
import { SpiralLoader } from "./SpiralLoader";

const IDLE_LINES = [
  "Ask me anything — I'll show my confidence.",
  "Every answer ships with a transparency report.",
  "Uncertainty is information. I surface mine.",
  "Built to show you what I don't know.",
];

const BUSY_LINES = [
  "Consulting the spiral…",
  "Weighing the evidence…",
  "Measuring confidence…",
];

/**
 * A "thought bubble" that floats above the robot's head: phrases fade in,
 * linger while the bot "thinks" them, then fade away — on a loop.
 */
export function ThoughtBubble({
  busy,
  className = "",
}: {
  busy: boolean;
  className?: string;
}) {
  const [visible, setVisible] = useState(false);
  const [idx, setIdx] = useState(0);

  // Appear → linger → disappear → (advance phrase) → repeat.
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    let showing = false;

    const tick = () => {
      if (cancelled) return;
      if (showing) {
        showing = false;
        setVisible(false);
        setIdx((i) => i + 1);
        timer = window.setTimeout(tick, busy ? 450 : 1400);
      } else {
        showing = true;
        setVisible(true);
        timer = window.setTimeout(tick, busy ? 1900 : 3400);
      }
    };

    timer = window.setTimeout(tick, 700);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [busy]);

  const lines = busy ? BUSY_LINES : IDLE_LINES;
  const text = lines[idx % lines.length];

  return (
    <div className={`pointer-events-none z-20 ${className}`} aria-live="polite">
      <AnimatePresence>
        {visible && (
          <motion.div
            key="bubble"
            initial={{ opacity: 0, y: 12, scale: 0.82 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 320, damping: 24 }}
            className="glass relative rounded-2xl rounded-bl-md px-4 py-2.5 shadow-[0_0_36px_rgba(198,255,77,0.18)]"
          >
            {/* thought-trail dots pointing at the robot's head */}
            <span className="absolute -bottom-3 left-7 h-2.5 w-2.5 rounded-full border border-white/10 bg-slate-400/35 backdrop-blur-sm" />
            <span className="absolute -bottom-6 left-4 h-1.5 w-1.5 rounded-full bg-slate-400/20" />

            <div className="flex items-center gap-2">
              {busy ? (
                <SpiralLoader size={15} className="shrink-0" />
              ) : (
                <SparkIcon
                  width={13}
                  height={13}
                  className="shrink-0 animate-pulse-glow text-forge-lime"
                />
              )}
              <AnimatePresence mode="wait">
                <motion.span
                  key={text}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.22 }}
                  className={`font-mono text-xs tracking-wide ${
                    busy ? "text-forge-lime" : "text-forge-muted/80"
                  }`}
                >
                  {text}
                </motion.span>
              </AnimatePresence>
              {busy && (
                <span className="flex shrink-0 items-center gap-1 pl-0.5">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
