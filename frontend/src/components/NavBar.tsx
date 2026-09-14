"use client";

import { motion } from "framer-motion";
import { GitHubIcon, StatsIcon, SparkIcon } from "./icons";

/**
 * Three-zone navigation bar: brand (left) · centered pill nav · GitHub (right).
 * C0RTEX design: mono uppercase labels, lime accent, pill radius.
 * All links are functional buttons — no dead anchors.
 */
export function NavBar({
  onHowItWorks,
  onLaunch,
  onAbout,
  onDocs,
  onHome,
}: {
  onHowItWorks: () => void;
  onLaunch: () => void;
  onAbout: () => void;
  onDocs: () => void;
  onHome: () => void;
}) {
  const linkCls =
    "label-mono ring-focus relative hidden rounded-full px-4 py-1.5 text-[11px] text-forge-muted/70 transition hover:text-forge-lime md:block";

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-40 grid grid-cols-[1fr_auto_1fr] items-center gap-3 p-4 sm:p-6">
      {/* ————— left: brand (acts as Home) ————— */}
      <motion.button
        onClick={onHome}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        aria-label="Go to home"
        className="glass pointer-events-auto flex w-max items-center gap-2.5 rounded-full p-2 text-left shadow-[0_8px_32px_rgba(0,0,0,0.65)] sm:py-2 sm:pl-2.5 sm:pr-4"
      >
        <span className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full ring-1 ring-white/20">
          <img
            src="/spiral-robot.png"
            alt="SPIRAL AI logo"
            className="h-full w-full object-cover"
          />
        </span>
        <span className="hidden leading-tight sm:block">
          <span className="block font-display text-[13px] font-semibold tracking-wide text-white">
            SPIRAL AI
          </span>
          <span className="label-mono block text-[9px] text-forge-muted/60">
            Transparent AI
          </span>
        </span>
      </motion.button>

      {/* ————— center: nav pill ————— */}
      <nav
        className="glass pointer-events-auto flex items-center gap-1 rounded-full p-1.5 shadow-[0_8px_32px_rgba(0,0,0,0.65)]"
        aria-label="Main navigation"
      >
        <button onClick={onHome} className={linkCls}>
          Home
        </button>
        <button onClick={onAbout} className={linkCls}>
          About
        </button>
        <button onClick={onDocs} className={linkCls}>
          Docs
        </button>

        {/* "How it works" — centered, lime */}
        <motion.button
          onClick={onHowItWorks}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          className="label-mono ring-focus group relative flex items-center gap-1.5 overflow-hidden rounded-full bg-forge-lime px-4 py-1.5 text-[11px] font-semibold text-forge-bg shadow-[0_0_18px_rgba(198,255,77,0.35)] transition hover:brightness-110"
        >
          <StatsIcon
            width={13}
            height={13}
            className="transition group-hover:rotate-6"
          />
          How it works
          <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
        </motion.button>
      </nav>

      {/* ————— right: actions ————— */}
      <div className="flex items-center justify-end gap-2">
        <motion.a
          href="https://github.com/okaylol676767-eng/confidence-forge"
          target="_blank"
          rel="noopener noreferrer"
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.95 }}
          aria-label="View on GitHub"
          className="glass ring-focus pointer-events-auto flex h-10 w-10 items-center justify-center rounded-full text-forge-muted/80 shadow-[0_8px_32px_rgba(0,0,0,0.65)] transition hover:text-forge-lime"
        >
          <GitHubIcon width={17} height={17} />
        </motion.a>
        <motion.button
          onClick={onLaunch}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.96 }}
          className="ring-focus label-mono pointer-events-auto flex items-center gap-1.5 rounded-full border border-forge-lime/40 bg-forge-lime/10 px-4 py-2 text-[11px] font-semibold text-forge-lime shadow-[0_0_18px_rgba(198,255,77,0.2)] transition hover:bg-forge-lime/20 sm:px-5"
        >
          <SparkIcon width={13} height={13} />
          Launch
        </motion.button>
      </div>
    </header>
  );
}
