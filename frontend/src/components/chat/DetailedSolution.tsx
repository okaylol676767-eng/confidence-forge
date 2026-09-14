"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { ChevronIcon } from "../icons";

/**
 * Collapsible full derivation attached to an assistant answer.
 * Renders nothing when there is no detailed solution to show.
 */
export function DetailedSolution({ content }: { content: string | null | undefined }) {
  const [open, setOpen] = useState(false);
  if (!content || !content.trim()) return null;

  return (
    <div className="mt-3 border-t border-white/[0.07] pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="ring-focus label-mono inline-flex items-center gap-1.5 rounded-full border border-forge-lime/30 bg-forge-lime/[0.06] px-3 py-1 text-[9px] font-semibold text-forge-lime/90 transition hover:border-forge-lime/60 hover:bg-forge-lime/15"
      >
        <ChevronIcon
          width={11}
          height={11}
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
        {open ? "Hide detailed solution" : "See detailed solution"}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="mt-2 max-h-[420px] overflow-y-auto nice-scrollbar rounded-2xl border border-white/[0.06] bg-black/20 p-3.5">
              <p className="label-mono mb-2 text-[9px] text-forge-muted/50">
                Full derivation — every step, including sanity checks
              </p>
              <MarkdownContent content={content} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
