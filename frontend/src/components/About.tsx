"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import { CloseIcon, StatsIcon, SparkIcon, RetryIcon } from "./icons";

const fadeUp = {
  initial: { opacity: 0, y: 26 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
};

const MARQUEE_ITEMS = [
  "TRANSPARENT BY DESIGN",
  "CONFIDENCE YOU CAN SEE",
  "SELF-IMPROVING",
  "POWERED BY GEMINI",
  "MONITORED BY PRISM",
];

const PILLARS = [
  {
    n: "01",
    title: "The black-box problem",
    body: "Most AI systems today operate as black boxes — they give answers without revealing how confident they actually are. This lack of transparency leads to blind trust, potential misinformation, and systems that fail to learn from their own weaknesses.",
  },
  {
    n: "02",
    title: "Confidence, made visible",
    body: "SPIRAL solves this by making confidence visible. After every response, you can view the AI's self-assessed confidence score, the reasoning behind it, and the specific factors that create uncertainty.",
  },
  {
    n: "03",
    title: "A feedback loop, not a display",
    body: "These confidence signals are not just displayed — they are actively used by the system to detect weak areas and continuously improve over time.",
  },
];

/**
 * Fullscreen About overlay — MakeReign-inspired: oversized display type,
 * numbered mono micro-labels, hairline dividers, lime CTA, marquee.
 * Dark, editorial, generous whitespace.
 */
export function About({
  open,
  onClose,
  onLaunch,
}: {
  open: boolean;
  onClose: () => void;
  onLaunch: () => void;
}) {
  // Escape closes; lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="about"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-[60] overflow-y-auto nice-scrollbar bg-forge-bg/95 backdrop-blur-xl"
          role="dialog"
          aria-modal="true"
          aria-label="About SPIRAL AI"
        >
          {/* sticky header */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/[0.07] bg-forge-bg/80 px-4 py-3 backdrop-blur-md sm:px-8">
            <p className="label-mono text-[10px] text-forge-muted/50">
              About — SPIRAL AI
            </p>
            <button
              onClick={onClose}
              aria-label="Close about"
              className="ring-focus flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-forge-muted/80 transition hover:border-forge-lime/40 hover:bg-forge-lime/10 hover:text-forge-lime"
            >
              <CloseIcon width={15} height={15} />
            </button>
          </div>

          <div className="mx-auto max-w-5xl px-5 sm:px-8">
            {/* ————— hero ————— */}
            <header className="relative pb-14 pt-16 sm:pb-20 sm:pt-24">
              <motion.img
                src="/spiral-robot.png"
                alt=""
                aria-hidden
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.7 }}
                className="pointer-events-none absolute -top-10 right-0 hidden h-44 w-auto rounded-full opacity-60 mix-blend-screen lg:block"
              />
              <div className="relative">
                <motion.p
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="label-mono mb-5 flex items-center gap-2 text-[10px] text-forge-lime"
                >
                  <SparkIcon width={12} height={12} />
                  Transparent · Self-improving · Accountable
                </motion.p>
                <motion.img
                  src="/spiral-banner.png"
                  alt="SPIRAL.AI"
                  initial={{ opacity: 0, y: 22 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.08 }}
                  className="w-full max-w-md mix-blend-screen sm:max-w-xl"
                />
                <motion.h1
                  initial={{ opacity: 0, y: 22 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.08 }}
                  className="sr-only"
                >
                  About SPIRAL
                </motion.h1>
                <motion.p
                  initial={{ opacity: 0, y: 18 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.16 }}
                  className="mt-6 max-w-2xl text-base leading-relaxed text-forge-muted/70 sm:text-lg"
                >
                  SPIRAL is a transparent, self-improving AI chatbot designed
                  to make artificial intelligence more trustworthy and
                  accountable.
                </motion.p>
              </div>
            </header>

            {/* ————— marquee ————— */}
            <div className="relative -mx-5 overflow-hidden border-y border-white/[0.07] py-4 sm:-mx-8">
              <div className="marquee-track flex w-max items-center gap-8 pr-8">
                {[...MARQUEE_ITEMS, ...MARQUEE_ITEMS].map((item, i) => (
                  <span
                    key={i}
                    className="label-mono flex items-center gap-8 whitespace-nowrap text-[11px] text-forge-muted/40"
                  >
                    {item}
                    <SparkIcon width={11} height={11} className="text-forge-lime/50" />
                  </span>
                ))}
              </div>
            </div>

            {/* ————— problem → solution pillars ————— */}
            <section className="py-14 sm:py-20">
              {PILLARS.map((p, i) => (
                <motion.div
                  key={p.n}
                  {...fadeUp}
                  transition={{ delay: i * 0.05 }}
                  className="grid grid-cols-[auto_1fr] gap-5 border-t border-white/[0.07] py-8 sm:grid-cols-[80px_1fr_1.4fr] sm:gap-10 sm:py-10"
                >
                  <span className="label-mono pt-1 text-forge-lime/70">
                    /{p.n}
                  </span>
                  <h2 className="text-xl font-semibold leading-snug text-white sm:text-2xl">
                    {p.title}
                  </h2>
                  <p className="col-span-2 max-w-2xl text-sm leading-relaxed text-forge-muted/65 sm:col-span-1 sm:text-base">
                    {p.body}
                  </p>
                </motion.div>
              ))}

              {/* experience strip */}
              <motion.div
                {...fadeUp}
                className="grid grid-cols-[auto_1fr] gap-5 border-t border-white/[0.07] py-8 sm:grid-cols-[80px_1fr_1.4fr] sm:gap-10 sm:py-10"
              >
                <span className="label-mono pt-1 text-forge-lime/70">/04</span>
                <h2 className="text-xl font-semibold leading-snug text-white sm:text-2xl">
                  An experience that feels alive
                </h2>
                <p className="col-span-2 max-w-2xl text-sm leading-relaxed text-forge-muted/65 sm:col-span-1 sm:text-base">
                  At its core, SPIRAL combines a modern conversational
                  interface with a living 3D robot character, creating an
                  engaging experience while keeping transparency at the center.
                  Built with{" "}
                  <span className="font-semibold text-white">Google Gemini</span>{" "}
                  and monitored through{" "}
                  <span className="font-semibold text-white">
                    PRISM by Block Convey
                  </span>
                  , SPIRAL turns uncertainty into a powerful feedback loop for
                  self-improvement.
                </p>
              </motion.div>
            </section>

            {/* ————— mission statement ————— */}
            <motion.section
              {...fadeUp}
              className="relative border-t border-white/[0.07] py-16 text-center sm:py-24"
            >
              <div className="pointer-events-none absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-forge-lime/[0.07] blur-[100px]" />
              <p className="label-mono relative mb-6 text-[10px] text-forge-muted/50">
                Our mission
              </p>
              <p className="relative mx-auto max-w-3xl text-2xl font-semibold leading-snug text-white sm:text-4xl">
                Build AI that doesn&apos;t just answer — but{" "}
                <span className="text-forge-gradient">
                  knows when it might be wrong
                </span>
                , and gets better because of it.
              </p>
            </motion.section>

            {/* ————— CTA ————— */}
            <motion.div
              {...fadeUp}
              className="flex flex-col items-center gap-4 border-t border-white/[0.07] py-14 sm:py-16"
            >
              <motion.button
                onClick={() => {
                  onClose();
                  onLaunch();
                }}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.97 }}
                className="ring-focus label-mono group relative flex items-center gap-2 overflow-hidden rounded-full bg-forge-lime px-7 py-3 text-[12px] font-semibold text-forge-bg shadow-[0_0_24px_rgba(198,255,77,0.35)] transition hover:brightness-110"
              >
                <StatsIcon width={14} height={14} />
                Meet SPIRAL
                <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
              </motion.button>
              <p className="label-mono text-[9px] text-forge-muted/40">
                Ask something — watch it show its work
              </p>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
