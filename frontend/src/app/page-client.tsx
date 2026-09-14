"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Message, StatsData } from "@/lib/types";
import { fetchSessions, friendlyError, renameSession, sendChatMessage } from "@/lib/api";
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
const SESSION_NAME_KEY = "cf:session-name";

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

function loadSessionName(): string | null {
  try {
    return window.localStorage.getItem(SESSION_NAME_KEY);
  } catch {
    return null;
  }
}

function saveSessionName(name: string | null): void {
  try {
    if (name) window.localStorage.setItem(SESSION_NAME_KEY, name);
    else window.localStorage.removeItem(SESSION_NAME_KEY);
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
  const [sessionName, setSessionName] = useState<string | null>(null);
  const sessionNameRef = useRef<string | null>(null);
  /** True once the backend has a session row for the current conversation. */
  const [sessionActive, setSessionActive] = useState(false);

  // Restore conversation id + last-known session name after mount.
  useEffect(() => {
    conversationIdRef.current = loadConversationId();
    setSessionName(loadSessionName());
  }, []);

  // Persist conversation id whenever it changes.
  const setConversationId = useCallback((id: string | null) => {
    conversationIdRef.current = id;
    saveConversationId(id);
  }, []);

  /** Core send flow: append user + pending bubble, call backend, resolve/reject. */
  const sendMessage = useCallback(
    async (text: string, files: File[] = []) => {
      if (busyRef.current || (!text.trim() && files.length === 0)) return;
      busyRef.current = true;
      setBusy(true);

      const now = new Date().toISOString();
      const userMsg: Message = {
        id: uid(),
        role: "user",
        content: text,
        timestamp: now,
        status: "sent",
        attachments: files.map((file) => ({
          filename: file.name,
          mime_type: file.type || "application/octet-stream",
          size_bytes: file.size,
          kind: file.type.startsWith("image/") ? ("image" as const) : ("document" as const),
        })),
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
        const result = await sendChatMessage(
          text,
          conversationIdRef.current,
          undefined,
          files.length > 0 ? files : undefined,
        );
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
          // The backend auto-creates a session row on the first message and
          // names it after the question. Fetch that server-assigned name once
          // per conversation so the header shows it (renamable).
          if (!sessionNameRef.current) {
            const convo = result.meta.conversation_id;
            void (async () => {
              const sessions = await fetchSessions();
              const match = sessions.find((s) => s.conversation_id === convo);
              if (match) {
                sessionNameRef.current = match.name;
                setSessionName(match.name);
                saveSessionName(match.name);
              }
              setSessionActive(true);
            })();
          } else {
            setSessionActive(true);
          }
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
      if (!text.trim() && !(prevMsg?.attachments?.length)) return;
      setMessages((prev) => prev.filter((m) => m.id !== id));
      void sendMessage(text);
    },
    [messages, sendMessage],
  );

  const handleOpenStats = useCallback((message: Message) => {
    setActiveStats(message.meta ?? null);
    setStatsOpen(true);
  }, []);

  /** Rename the current session on the backend and in the header. */
  const handleRenameSession = useCallback(
    (name: string) => {
      const convo = conversationIdRef.current;
      if (!convo) return;
      void (async () => {
        try {
          const updated = await renameSession(convo, name);
          const finalName = updated?.name ?? name;
          sessionNameRef.current = finalName;
          setSessionName(finalName);
          saveSessionName(finalName);
        } catch (error) {
          toast("error", friendlyError(error));
        }
      })();
    },
    [],
  );

  /** Fresh conversation: clear messages + identity; session becomes "New chat". */
  const handleNewChat = useCallback(() => {
    if (busyRef.current) return;
    setMessages([]);
    setConversationId(null);
    conversationIdRef.current = null;
    sessionNameRef.current = null;
    setSessionName(null);
    setSessionActive(false);
    saveSessionName(null);
  }, [setConversationId]);

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
                onSend={(text, files) => void sendMessage(text, files)}
                onRetry={handleRetry}
                onOpenStats={handleOpenStats}
                onSuggestion={(text) => void sendMessage(text)}
                onClose={handleCloseChat}
                sessionName={sessionName}
                sessionActive={sessionActive}
                onRenameSession={handleRenameSession}
                onNewChat={handleNewChat}
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
