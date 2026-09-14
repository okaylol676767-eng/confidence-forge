"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { CloseIcon, CopyIcon, CheckIcon, SparkIcon } from "./icons";

const REQUEST_EXAMPLE = `POST /chat
Content-Type: application/json

{
  "message": "Explain quantum computing simply",
  "conversation_id": "optional-existing-conversation"
}`;

const RESPONSE_EXAMPLE = `{
  "answer": "Quantum computers use qubits…",
  "confidence": 0.87,
  "confidence_reason": "Well-established topic; high-quality sources retrieved.",
  "uncertainty_factors": [
    "Analogies simplify the physics",
    "Field is rapidly evolving"
  ],
  "conversation_id": "conv_9f2b…",
  "timestamp": "2026-09-14T12:00:00Z"
}`;

const FIELDS = [
  {
    name: "answer",
    where: "response",
    type: "string",
    note: "The assistant reply text. Also accepted: response, reply, message.",
  },
  {
    name: "confidence",
    where: "response",
    type: "number 0–1",
    note: "Self-assessed confidence. 0–100 values are normalized automatically. Renders green > 0.8, amber 0.5–0.8, red < 0.5.",
  },
  {
    name: "confidence_reason",
    where: "response",
    type: "string | null",
    note: "Human-readable explanation of the score, shown in the stats panel.",
  },
  {
    name: "uncertainty_factors",
    where: "response",
    type: "string[] | null",
    note: "Specific sources of uncertainty, rendered as glowing chips.",
  },
  {
    name: "conversation_id",
    where: "request + response",
    type: "string | null",
    note: "Echo it back on the next request to continue a thread. The client persists it in localStorage.",
  },
  {
    name: "timestamp",
    where: "response",
    type: "ISO 8601 string",
    note: "Optional — the client stamps its own time when omitted.",
  },
];

const ERRORS = [
  { code: "401 / 403", when: "Auth rejected — treated as network error" },
  { code: "5xx", when: "Backend failure — friendly server error bubble" },
  { code: "timeout (45s)", when: "Client aborts — friendly timeout bubble" },
  { code: "malformed JSON", when: "Treated as server error — fallback bubble" },
];

function CodeBlock({ code, label }: { code: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — non-fatal */
    }
  };
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black/50">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-2">
        <p className="label-mono text-[9px] text-forge-muted/50">{label}</p>
        <button
          onClick={copy}
          aria-label={copied ? "Copied" : "Copy code"}
          className="ring-focus flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] text-forge-muted/70 transition hover:border-forge-lime/40 hover:text-forge-lime"
        >
          {copied ? (
            <CheckIcon width={12} height={12} className="text-forge-lime" />
          ) : (
            <CopyIcon width={12} height={12} />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="nice-scrollbar overflow-x-auto px-4 py-3 font-mono text-[11px] leading-relaxed text-forge-muted/85 sm:text-xs">
        {code}
      </pre>
    </div>
  );
}

/**
 * Fullscreen Docs overlay — the /chat API contract, styled like the About
 * page: editorial rows, mono labels, copyable code blocks.
 */
export function Docs({ open, onClose }: { open: boolean; onClose: () => void }) {
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
          key="docs"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-[60] overflow-y-auto nice-scrollbar bg-forge-bg/95 backdrop-blur-xl"
          role="dialog"
          aria-modal="true"
          aria-label="SPIRAL AI documentation"
        >
          {/* sticky header */}
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/[0.07] bg-forge-bg/80 px-4 py-3 backdrop-blur-md sm:px-8">
            <p className="label-mono text-[10px] text-forge-muted/50">
              Docs — Chat API
            </p>
            <button
              onClick={onClose}
              aria-label="Close docs"
              className="ring-focus flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-forge-muted/80 transition hover:border-forge-lime/40 hover:bg-forge-lime/10 hover:text-forge-lime"
            >
              <CloseIcon width={15} height={15} />
            </button>
          </div>

          <div className="mx-auto max-w-4xl px-5 sm:px-8">
            {/* ————— hero ————— */}
            <header className="pb-10 pt-14 sm:pt-20">
              <motion.p
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                className="label-mono mb-5 flex items-center gap-2 text-[10px] text-forge-lime"
              >
                <SparkIcon width={12} height={12} />
                One endpoint · Transparent by default
              </motion.p>
              <motion.h1
                initial={{ opacity: 0, y: 22 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 }}
                className="text-4xl font-bold leading-[1.04] text-white sm:text-6xl"
              >
                The <span className="text-forge-gradient">/chat</span> contract
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.16 }}
                className="mt-6 max-w-2xl text-base leading-relaxed text-forge-muted/70 sm:text-lg"
              >
                Everything SPIRAL&apos;s frontend needs from your backend — a
                single POST that returns the answer <em>and</em> how confident
                the model is in it.
              </motion.p>
            </header>

            {/* ————— request / response ————— */}
            <section className="grid gap-4 border-t border-white/[0.07] py-10 lg:grid-cols-2">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
              >
                <CodeBlock code={REQUEST_EXAMPLE} label="Request" />
              </motion.div>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.06 }}
              >
                <CodeBlock code={RESPONSE_EXAMPLE} label="200 OK — response" />
              </motion.div>
            </section>

            {/* ————— field reference ————— */}
            <section className="border-t border-white/[0.07] py-10">
              <p className="label-mono mb-6 text-[10px] text-forge-muted/50">
                Field reference
              </p>
              {FIELDS.map((f, i) => (
                <motion.div
                  key={f.name}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-40px" }}
                  transition={{ delay: i * 0.03 }}
                  className="grid gap-1 border-t border-white/[0.06] py-4 sm:grid-cols-[220px_130px_1fr] sm:gap-6"
                >
                  <code className="font-mono text-[13px] font-semibold text-forge-lime">
                    {f.name}
                  </code>
                  <span className="label-mono text-[10px] text-forge-muted/50">
                    {f.where} · {f.type}
                  </span>
                  <p className="text-sm leading-relaxed text-forge-muted/65">
                    {f.note}
                  </p>
                </motion.div>
              ))}
            </section>

            {/* ————— error handling ————— */}
            <section className="border-t border-white/[0.07] py-10">
              <p className="label-mono mb-6 text-[10px] text-forge-muted/50">
                Error handling
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {ERRORS.map((e) => (
                  <div
                    key={e.code}
                    className="rounded-2xl border border-white/[0.08] bg-white/[0.03] px-4 py-3"
                  >
                    <code className="font-mono text-[12px] font-semibold text-forge-amber">
                      {e.code}
                    </code>
                    <p className="mt-1 text-sm text-forge-muted/65">{e.when}</p>
                  </div>
                ))}
              </div>
            </section>

            {/* ————— behavior notes ————— */}
            <section className="border-t border-white/[0.07] py-10">
              <p className="label-mono mb-6 text-[10px] text-forge-muted/50">
                Client behavior
              </p>
              <ul className="space-y-3 text-sm leading-relaxed text-forge-muted/65">
                {[
                  "Requests time out after 45 seconds; the composer disables while a call is in flight.",
                  "Offline or 5xx responses surface as friendly error bubbles with an inline Retry — raw errors are never shown.",
                  "Missing or malformed confidence data degrades to a polished \"no transparency data\" fallback in the stats panel.",
                  "conversation_id is stored in localStorage and replayed on every subsequent message.",
                ].map((line) => (
                  <li key={line} className="flex gap-3">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forge-lime" />
                    {line}
                  </li>
                ))}
              </ul>
            </section>

            {/* ————— footer note ————— */}
            <div className="flex flex-col items-center gap-3 border-t border-white/[0.07] py-12 text-center">
              <p className="label-mono text-[9px] text-forge-muted/40">
                POST /chat · JSON in · JSON out · nothing else required
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
