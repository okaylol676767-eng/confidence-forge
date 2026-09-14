"use client";

import type { Message } from "@/lib/types";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { CloseIcon } from "../icons";
import { SpiralLoader } from "../SpiralLoader";

interface ChatPanelProps {
  /** Fullscreen mode: fills the viewport instead of the desktop column. */
  fullscreen?: boolean;
  messages: Message[];
  busy: boolean;
  onSend: (text: string) => void;
  onRetry: (id: string) => void;
  onOpenStats: (message: Message) => void;
  onSuggestion: (text: string) => void;
  onClose?: () => void;
}

export function ChatPanel({
  fullscreen = false,
  messages,
  busy,
  onSend,
  onRetry,
  onOpenStats,
  onSuggestion,
  onClose,
}: ChatPanelProps) {
  return (
    <section
      className={`glass relative z-10 flex flex-col overflow-hidden rounded-3xl shadow-[0_24px_80px_rgba(2,4,14,0.6)] ${
        fullscreen
          ? "h-full w-full"
          : "h-[calc(100dvh-2rem)] w-full sm:h-[calc(100dvh-3rem)] lg:w-[clamp(380px,36vw,600px)] lg:max-w-none"
      }`}
      aria-label="Chat with SPIRAL"
    >
      {/* panel header */}
      <header className="flex items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-xl border transition-colors ${
                busy
                  ? "border-transparent bg-transparent"
                  : "border-white/10 bg-white/5"
              }`}
            >
              {busy ? <SpiralLoader size={34} /> : <img src="/spiral-robot.png" alt="" aria-hidden className="h-7 w-7 object-contain" />}
            </div>
            <span
              className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-forge-panel transition-colors ${
                busy ? "bg-forge-amber animate-pulse-glow" : "bg-forge-lime"
              }`}
              aria-hidden
            />
          </div>
          <div className="leading-tight">
            <p className="font-display text-sm font-semibold text-white">SPIRAL</p>
            <p className="label-mono text-[9px] text-forge-muted/60">
              {busy ? "forging an answer…" : "online · rates every answer"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="label-mono hidden rounded-full border border-forge-lime/25 bg-forge-lime/[0.07] px-3 py-1 text-[9px] font-semibold text-forge-lime sm:block">
            Transparent mode
          </span>
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close chat"
              className="ring-focus flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/5 text-forge-muted/80 transition hover:border-forge-lime/40 hover:bg-forge-lime/10 hover:text-forge-lime"
            >
              <CloseIcon width={15} height={15} />
            </button>
          )}
        </div>
      </header>

      {/* messages */}
      <div
        className={`flex min-h-0 flex-1 flex-col px-3 pt-2 sm:px-5 ${
          fullscreen ? "mx-auto w-full max-w-3xl" : ""
        }`}
      >
        <MessageList
          messages={messages}
          busy={busy}
          onRetry={onRetry}
          onOpenStats={onOpenStats}
          onSuggestion={onSuggestion}
        />
      </div>

      {/* composer */}
      <div
        className={`px-3 pb-3 pt-2 sm:px-5 sm:pb-5 ${
          fullscreen ? "mx-auto w-full max-w-3xl" : ""
        }`}
      >
        <ChatInput busy={busy} onSend={onSend} />
      </div>
    </section>
  );
}
