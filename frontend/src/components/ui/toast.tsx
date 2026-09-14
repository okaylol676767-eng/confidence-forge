"use client";

/**
 * Minimal, dependency-free toast system with Framer Motion animations.
 * Renders toasts from anywhere via `toast()`; no context provider needed.
 */
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { CloseIcon } from "../icons";

export type ToastKind = "info" | "error" | "success";

export interface ToastPayload {
  id: string;
  kind: ToastKind;
  message: string;
}

type Listener = (toast: ToastPayload) => void;

const listeners = new Set<Listener>();
let counter = 0;

/** Fire a toast imperatively from any component or plain function. */
export function toast(kind: ToastKind, message: string): void {
  counter += 1;
  const payload: ToastPayload = { id: `t${counter}`, kind, message };
  listeners.forEach((listener) => listener(payload));
}

const KIND_STYLES: Record<
  ToastKind,
  { ring: string; glow: string; dot: string; label: string }
> = {
  error: {
    ring: "border-forge-red/40",
    glow: "shadow-[0_0_32px_rgba(248,113,113,0.22)]",
    dot: "bg-forge-red",
    label: "Error",
  },
  success: {
    ring: "border-forge-green/40",
    glow: "shadow-[0_0_32px_rgba(52,211,153,0.22)]",
    dot: "bg-forge-green",
    label: "Success",
  },
  info: {
    ring: "border-forge-lime/40",
    glow: "shadow-[0_0_32px_rgba(198,255,77,0.2)]",
    dot: "bg-forge-lime",
    label: "Info",
  },
};

export function Toaster() {
  const [toasts, setToasts] = useState<ToastPayload[]>([]);

  useEffect(() => {
    const listener: Listener = (payload) => {
      setToasts((prev) => [...prev.slice(-2), payload]);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const dismiss = (id: string) =>
    setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-4 z-[90] flex flex-col items-center gap-2 px-4 sm:bottom-auto sm:top-4 sm:items-end"
      aria-live="polite"
    >
      <AnimatePresence>
        {toasts.map((t) => {
          const styles = KIND_STYLES[t.kind];
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 14, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.96 }}
              transition={{ type: "spring", stiffness: 420, damping: 32 }}
              className={`pointer-events-auto glass flex w-full max-w-sm items-start gap-3 rounded-2xl px-4 py-3 ${styles.ring} ${styles.glow}`}
              role="status"
            >
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${styles.dot} animate-pulse-glow`} />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-forge-muted/60">
                  {styles.label}
                </p>
                <p className="mt-0.5 text-sm leading-snug text-forge-muted">{t.message}</p>
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="ring-focus rounded-lg p-1 text-forge-muted/60 transition hover:bg-white/5 hover:text-white"
                aria-label="Dismiss notification"
              >
                <CloseIcon width={14} height={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
