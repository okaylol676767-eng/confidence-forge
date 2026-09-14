"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Message, StatsData } from "@/lib/types";
import { friendlyError, sendChatMessage } from "@/lib/api";
import { AmbientBackground } from "@/components/AmbientBackground";
import { VideoBackground } from "@/components/VideoBackground";
import { RobotStage } from "@/components/RobotStage";
import { ThoughtBubble } from "@/components/ThoughtBubble";
import { NavBar } from "@/components/NavBar";
import { About } from "@/components/About";
import { Docs } from "@/components/Docs";
import { StatsModal } from "@/components/StatsModal";
import { Toaster, toast } from "@/components/ui/toast";
import { ChatPanel } from "@/components/chat/ChatPanel";

const CONVERSATION_KEY = "cf:conversation-id";

function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function loadConversationId(): string | null {
  try {
    return window.localStorage.getItem(CONVERSATION_KEY);
  } catch {
    return null;
  }
}

function saveConversationId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(CONVERSATION_KEY, id);
    else window.localStorage.removeItem(CONVERSATION_KEY);
  } catch {
    /* private mode — non-fatal */
  }
}

export default function HomeClient({
  robotSlot,
}: {
  robotSlot?: React.ReactNode;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);
  const [activeStats, setActiveStats] = useState<StatsData | null>(null);
  /** Landing screen is minimal; the chat only exists after "Launch". */
  const [launched, setLaunched] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);

  const conversationIdRef = useRef<string | null>(null);
  const busyRef = useRef(false);

  // Restore conversation id after mount (client-only storage).
  useEffect(() => {
    conversationIdRef.current = loadConversationId();
  }, []);

  // Persist conversation id whenever it changes.
  const setConversationId = useCallback((id: string | null) => {
    conversationIdRef.current = id;
    saveConversationId(id);
  }, []);

  /** Core send flow: append user + pending bubble, call backend, resolve/reject. */
  const sendMessage = useCallback(
    async (text: string) => {
      if (busyRef.current || !text.trim()) return;
      busyRef.current = true;
      setBusy(true);

      const now = new Date().toISOString();
      const userMsg: Message = {
        id: uid(),
        role: "user",
        content: text,
        timestamp: now,
        status: "sent",
      };
      const assistantId = uid();
      const pendingMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: null,
        status: "pending",
      };

      setMessages((prev) => [...prev, userMsg, pendingMsg]);

      try {
        const result = await sendChatMessage(text, conversationIdRef.current);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: result.content,
                  timestamp: result.meta.timestamp ?? new Date().toISOString(),
                  status: "sent",
                  meta: result.meta,
                }
              : m,
          ),
        );
        if (result.meta.conversation_id) {
          setConversationId(result.meta.conversation_id);
        }
      } catch (error) {
        const friendly = friendlyError(error);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, status: "failed", error: friendly }
              : m,
          ),
        );
        toast("error", friendly);
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [setConversationId],
  );

  /** Retry a failed assistant message by resending the preceding user text. */
  const handleRetry = useCallback(
    (id: string) => {
      if (busyRef.current) return;
      const idx = messages.findIndex((m) => m.id === id);
      if (idx === -1) return;
      const prevMsg = messages[idx - 1];
      const text = prevMsg && prevMsg.role === "user" ? prevMsg.content : "";
      if (!text.trim()) return;
      setMessages((prev) => prev.filter((m) => m.id !== id));
      void sendMessage(text);
    },
    [messages, sendMessage],
  );

  const handleOpenStats = useCallback((message: Message) => {
    setActiveStats(message.meta ?? null);
    setStatsOpen(true);
  }, []);

  /** "How it works" doubles as a live demo of the transparency panel. */
  const handleHowItWorks = useCallback(() => {
    setActiveStats({
      confidence: 0.93,
      confidence_reason:
        "SPIRAL AI evaluates every reply against the evidence it retrieved, the clarity of your question, and the boundaries of its knowledge. This intro is fully deterministic — so it's sure of itself.",
      uncertainty_factors: [
        "Demo content",
        "Live answers depend on the backend model",
      ],
      timestamp: new Date().toISOString(),
    });
    setStatsOpen(true);
  }, []);

  const handleLaunch = useCallback(() => setLaunched(true), []);
  const handleCloseChat = useCallback(() => setLaunched(false), []);
  const handleOpenAbout = useCallback(() => setAboutOpen(true), []);
  const handleCloseAbout = useCallback(() => setAboutOpen(false), []);
  const handleOpenDocs = useCallback(() => setDocsOpen(true), []);
  const handleCloseDocs = useCallback(() => setDocsOpen(false), []);
  /** Home: leave chat + overlays, return to the minimal landing. */
  const handleHome = useCallback(() => {
    setLaunched(false);
    setAboutOpen(false);
    setDocsOpen(false);
    setStatsOpen(false);
  }, []);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-forge-bg text-forge-muted">
      <VideoBackground src="/background.mp4" />
      <AmbientBackground />
      <RobotStage scene={robotSlot} busy={busy} />
      <NavBar
        onHowItWorks={handleHowItWorks}
        onLaunch={handleLaunch}
        onAbout={handleOpenAbout}
        onDocs={handleOpenDocs}
        onHome={handleHome}
      />

      {/* ————— Landing: intentionally minimal (robot + navbar only) ————— */}

      {/* ————— Fullscreen chat, opened via Launch ————— */}
      <AnimatePresence>
        {launched && (
          <motion.div
            key="chat-fullscreen"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-50 flex flex-col p-2 sm:p-4"
            role="dialog"
            aria-modal="true"
            aria-label="Chat with SPIRAL"
          >
            <motion.div
              initial={{ scale: 0.97, y: 24 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.97, y: 24 }}
              transition={{ type: "spring", stiffness: 260, damping: 28 }}
              className="flex min-h-0 flex-1 flex-col"
            >
              <ChatPanel
                fullscreen
                messages={messages}
                busy={busy}
                onSend={(text) => void sendMessage(text)}
                onRetry={handleRetry}
                onOpenStats={handleOpenStats}
                onSuggestion={(text) => void sendMessage(text)}
                onClose={handleCloseChat}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <StatsModal
        open={statsOpen}
        stats={activeStats}
        onClose={() => setStatsOpen(false)}
      />
      <About
        open={aboutOpen}
        onClose={handleCloseAbout}
        onLaunch={handleLaunch}
      />
      <Docs open={docsOpen} onClose={handleCloseDocs} />
      <Toaster />
    </main>
  );
}
