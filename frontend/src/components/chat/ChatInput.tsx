"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { SendIcon } from "../icons";

interface ChatInputProps {
  busy: boolean;
  onSend: (text: string) => void;
}

const MAX_CHARS = 4000;

export function ChatInput({ busy, onSend }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to a cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    textareaRef.current?.focus();
  };

  return (
    <div className="relative">
      {/* glow halo */}
      <div
        aria-hidden
        className="absolute -inset-1 -z-10 rounded-[22px] bg-forge-lime/10 opacity-50 blur-lg transition-opacity duration-500"
      />
      <motion.div
        layout
        className="glass flex items-end gap-2 rounded-2xl p-2.5 shadow-[0_18px_48px_rgba(0,0,0,0.65)]"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={busy ? "SPIRAL is answering…" : "Ask SPIRAL anything…"}
          aria-label="Message"
          disabled={busy}
          className="nice-scrollbar max-h-40 flex-1 resize-none bg-transparent px-3 py-2.5 font-mono text-sm text-forge-muted placeholder:text-forge-muted/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />

        <div className="flex flex-col items-center gap-1 pb-0.5 pr-1">
          <motion.button
            whileHover={canSend ? { scale: 1.06 } : undefined}
            whileTap={canSend ? { scale: 0.94 } : undefined}
            onClick={submit}
            disabled={!canSend}
            aria-label="Send message"
            className={`ring-focus flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-300 ${
              canSend
                ? "bg-forge-lime text-forge-bg shadow-[0_0_24px_rgba(198,255,77,0.45)]"
                : "cursor-not-allowed bg-white/5 text-forge-muted/40"
            }`}
          >
            {busy ? (
              <svg width="18" height="18" viewBox="0 0 24 24" className="animate-spin-slow" aria-hidden>
                <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
                <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
            ) : (
              <SendIcon width={17} height={17} />
            )}
          </motion.button>
        </div>
      </motion.div>
      <div className="label-mono mt-1.5 flex justify-between px-2 text-[9px] text-forge-muted/40">
        <span>enter to send · shift+enter newline</span>
        <span className={value.length > MAX_CHARS - 200 ? "text-forge-amber" : ""}>
          {value.length > 0 ? `${value.length}/${MAX_CHARS}` : ""}
        </span>
      </div>
    </div>
  );
}
