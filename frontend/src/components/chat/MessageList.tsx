"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "@/lib/types";
import { MessageBubble } from "./MessageBubble";
import { SpiralLoader } from "../SpiralLoader";

const SUGGESTIONS = [
  "What can you help me with?",
  "How confident are you about the weather tomorrow?",
  "Explain quantum computing simply",
  "Tell me something you're unsure about",
];

interface MessageListProps {
  messages: Message[];
  busy: boolean;
  onRetry: (id: string) => void;
  onOpenStats: (message: Message) => void;
  onSuggestion: (text: string) => void;
}

export function MessageList({
  messages,
  busy,
  onRetry,
  onOpenStats,
  onSuggestion,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  // Track whether the user has scrolled away from the latest message.
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distance < 90;
    setShowJump(distance > 220);
  }, []);

  // Auto-scroll whenever content grows, if the user is at (or near) the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const scrollToBottom = () => {
    stickToBottomRef.current = true;
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="nice-scrollbar flex-1 space-y-5 overflow-y-auto px-1 py-2"
        role="log"
        aria-label="Conversation"
        aria-live="polite"
      >
        {messages.length === 0 && !busy && (
          <EmptyState onSuggestion={onSuggestion} />
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onRetry={onRetry}
              onOpenStats={onOpenStats}
            />
          ))}
        </AnimatePresence>

        {busy && <TypingIndicator />}
      </div>

      {/* jump-to-latest */}
      <AnimatePresence>
        {showJump && (
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            onClick={scrollToBottom}
            className="glass ring-focus absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border-forge-lime/40 px-4 py-1.5 text-xs font-semibold text-forge-lime shadow-[0_0_20px_rgba(198,255,77,0.25)]"
          >
            ↓ Jump to latest
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex justify-start"
    >
      <div className="glass flex items-center gap-3 rounded-2xl rounded-bl-md px-4 py-3 shadow-[0_10px_30px_rgba(2,4,14,0.45)]">
        <SpiralLoader size={26} />
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-white">SPIRAL is thinking</span>
          <span className="flex items-center gap-1.5 text-[11px] text-forge-muted/60">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function EmptyState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  return (
    <div className="flex min-h-[42vh] flex-col items-center justify-center gap-6 py-10 text-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="relative"
      >
        <div className="absolute inset-0 -z-10 rounded-full bg-forge-lime/20 blur-2xl" />
        <img
          src="/spiral-robot.png"
          alt=""
          aria-hidden
          className="h-14 w-14 rounded-2xl border border-white/10 object-cover"
        />
      </motion.div>
      <div className="space-y-2">
        <h2 className="text-xl font-semibold text-white sm:text-2xl">
          Meet <span className="text-forge-gradient">SPIRAL</span>
        </h2>
        <p className="max-w-sm text-sm leading-relaxed text-forge-muted/60">
          A transparent AI that shows how confident it is in every single
          answer. Ask something — and open the stats to see the reasoning.
        </p>
      </div>
      <div className="flex max-w-md flex-wrap items-center justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <motion.button
            key={s}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onSuggestion(s)}
            className="ring-focus glass-soft rounded-full px-3.5 py-1.5 text-xs text-forge-muted/80 transition hover:border-forge-lime/40 hover:text-white"
          >
            {s}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
