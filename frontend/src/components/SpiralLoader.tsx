"use client";

import { motion } from "framer-motion";

/**
 * Spiral-themed loading indicator: the spiral logo mark rotates inside
 * concentric orbiting rings with a soft lime glow — used while SPIRAL
 * is "thinking".
 */
export function SpiralLoader({
  size = 28,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      role="status"
      aria-label="SPIRAL is thinking"
      className={`relative inline-flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
    >
      {/* glow bed */}
      <span
        className="pointer-events-none absolute inset-0 rounded-full bg-forge-lime/25 blur-md"
        aria-hidden
      />

      {/* orbiting ring 1 — full circle, spins clockwise */}
      <motion.span
        aria-hidden
        className="absolute inset-0 rounded-full border border-transparent"
        style={{
          borderTopColor: "var(--color-forge-lime)",
          borderRightColor: "rgba(198,255,77,0.25)",
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: 1.1, ease: "linear", repeat: Infinity }}
      />

      {/* orbiting ring 2 — spins counter-clockwise */}
      <motion.span
        aria-hidden
        className="absolute inset-[3px] rounded-full border border-transparent"
        style={{
          borderBottomColor: "rgba(198,255,77,0.7)",
          borderLeftColor: "rgba(198,255,77,0.15)",
        }}
        animate={{ rotate: -360 }}
        transition={{ duration: 1.8, ease: "linear", repeat: Infinity }}
      />

      {/* the spiral mark, gently pulsing */}
      <motion.img
        src="/spiral-robot.png"
        alt=""
        aria-hidden
        className="rounded-full object-cover"
        style={{ width: size * 0.52, height: size * 0.52 }}
        animate={{ scale: [1, 0.86, 1] }}
        transition={{
          duration: 1.4,
          ease: "easeInOut",
          repeat: Infinity,
        }}
      />
    </span>
  );
}
