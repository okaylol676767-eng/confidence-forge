"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { AttachIcon, CloseIcon, SendIcon } from "../icons";

interface ChatInputProps {
  busy: boolean;
  onSend: (text: string, files: File[]) => void;
}

const MAX_CHARS = 4000;
export const MAX_ATTACHMENTS = 4;
const MAX_FILE_MB = 8;
const ACCEPT = "image/*,.pdf,.txt,.md,.csv,.json";

export function ChatInput({ busy, onSend }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-grow the textarea up to a cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const canSend = (value.trim().length > 0 || files.length > 0) && !busy;

  const addFiles = (incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return;
    const accepted: File[] = [];
    let error: string | null = null;
    for (const file of Array.from(incoming)) {
      if (files.length + accepted.length >= MAX_ATTACHMENTS) {
        error = `Up to ${MAX_ATTACHMENTS} files at once.`;
        break;
      }
      if (file.size > MAX_FILE_MB * 1024 * 1024) {
        error = `"${file.name}" is larger than ${MAX_FILE_MB} MB.`;
        continue;
      }
      accepted.push(file);
    }
    if (accepted.length > 0) {
      setFiles((prev) => [...prev, ...accepted].slice(0, MAX_ATTACHMENTS));
    }
    setFileError(error);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setFileError(null);
  };

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim(), files);
    setValue("");
    setFiles([]);
    setFileError(null);
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
        className="glass flex flex-col rounded-2xl p-2.5 shadow-[0_18px_48px_rgba(0,0,0,0.65)]"
      >
        {/* attachment chips */}
        {files.length > 0 && (
          <motion.div layout className="mb-2 flex flex-wrap gap-1.5 px-1 pt-1">
            {files.map((file, index) => (
              <span
                key={`${file.name}-${index}`}
                className="inline-flex max-w-[220px] items-center gap-1.5 rounded-full border border-forge-lime/30 bg-forge-lime/[0.08] py-1 pl-2.5 pr-1.5 text-[10px] font-medium text-forge-muted"
              >
                <AttachIcon width={11} height={11} className="shrink-0 text-forge-lime" />
                <span className="truncate">{file.name}</span>
                <button
                  onClick={() => removeFile(index)}
                  aria-label={`Remove ${file.name}`}
                  disabled={busy}
                  className="ring-focus shrink-0 rounded-full p-0.5 text-forge-muted/50 transition hover:bg-white/10 hover:text-forge-red disabled:opacity-40"
                >
                  <CloseIcon width={10} height={10} />
                </button>
              </span>
            ))}
          </motion.div>
        )}

        <div className="flex items-end gap-2">
          {/* attach button */}
          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            aria-label="Attach image or document"
            title="Attach image or document (max 4 files, 8 MB each)"
            className="ring-focus flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 text-forge-muted/70 transition hover:bg-forge-lime/10 hover:text-forge-lime disabled:cursor-not-allowed disabled:opacity-40"
          >
            <AttachIcon width={17} height={17} />
          </motion.button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = ""; // allow re-selecting the same file
            }}
          />

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
            className="nice-scrollbar max-h-40 flex-1 resize-none bg-transparent px-1 py-2.5 font-mono text-sm text-forge-muted placeholder:text-forge-muted/40 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
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
        </div>

        {fileError && (
          <p className="px-2 pt-1.5 text-[10px] text-forge-amber">{fileError}</p>
        )}
      </motion.div>
      <div className="label-mono mt-1.5 flex justify-between px-2 text-[9px] text-forge-muted/40">
        <span>enter to send · shift+enter newline · 📎 images &amp; docs</span>
        <span className={value.length > MAX_CHARS - 200 ? "text-forge-amber" : ""}>
          {value.length > 0 ? `${value.length}/${MAX_CHARS}` : ""}
        </span>
      </div>
    </div>
  );
}
