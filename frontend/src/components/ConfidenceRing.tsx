"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import {
  getConfidenceLabel,
  getTier,
  TIER_COLORS,
  type ConfidenceTier,
} from "@/lib/confidence";

interface ConfidenceRingProps {
  confidence: number | null;
  size?: number;
}

/** Spring-animated SVG progress ring, color-coded by confidence tier. */
export function ConfidenceRing({ confidence, size = 168 }: ConfidenceRingProps) {
  const tier: ConfidenceTier | null = getTier(confidence);
  const color = tier ? TIER_COLORS[tier] : "#94a3b8";
  const pct = confidence === null ? 0 : Math.round(confidence * 100);

  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  // Animate the number counting up on mount/value change.
  const [displayPct, setDisplayPct] = useState(0);
  useEffect(() => {
    if (confidence === null) return;
    const start = performance.now();
    const from = 0;
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min((now - start) / 1200, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayPct(Math.round(from + (pct - from) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [pct, confidence]);

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      {/* outer glow */}
      <div
        aria-hidden
        className="absolute inset-2 rounded-full opacity-60 blur-xl"
        style={{ background: `radial-gradient(circle, ${color}40 0%, transparent 70%)` }}
      />

      <svg width={size} height={size} className="relative -rotate-90">
        {/* track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(148,163,184,0.14)"
          strokeWidth={stroke}
        />
        {/* value arc */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (c * pct) / 100 }}
          transition={{ type: "spring", stiffness: 60, damping: 18, delay: 0.15 }}
          style={{ filter: `drop-shadow(0 0 8px ${color}aa)` }}
        />
      </svg>

      {/* center readout */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {confidence === null ? (
          <>
            <span className="text-2xl font-bold text-slate-400">—</span>
            <span className="mt-1 text-[10px] uppercase tracking-[0.16em] text-slate-500">
              No data
            </span>
          </>
        ) : (
          <>
            <span className="text-3xl font-bold tracking-tight" style={{ color }}>
              {displayPct}%
            </span>
            <span className="mt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
              {getConfidenceLabel(confidence).split(" ")[0]} confidence
            </span>
          </>
        )}
      </div>
    </div>
  );
}
