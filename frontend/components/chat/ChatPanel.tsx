import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Loader2,
  MessageSquare,
  PenLine,
  Quote,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, ApiError, type AmendResult, type GenerationMode, type Message } from "@/lib/api";
import { contentLength, formatRelative, modeLabel, sourceLabel } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import ModePicker from "@/components/series/ModePicker";
import type { VersionConflict } from "@/components/series/ConflictDialog";

type ChatPanelProps = {
  open: boolean;
  unitId: string | null;
  unitTitle: string;
  currentVersion: number;
  initialSelection?: string;
  onSelectionConsumed?: () => void;
  onClose: () => void;
  onApplied: () => void | Promise<void>;
  onNotice: (text: string) => void;
  onVersionConflict?: (conflict: VersionConflict) => void;
};

type Tab = "ask" | "amend";

type ChatMessage = Message & { quoted?: string };

const AMEND_PRESETS = [
  "Trim this section and remove repetition",
  "Add a real-world example",
  "Rewrite it in a more hands-on style",
  "Split it into clearer subsections",
];

const ASK_PRESETS = [
  "What is the key takeaway of this unit?",
  "Why is this part covered first?",
  "How does this map to scenarios in my project?",
];

export default function ChatPanel({
  open,
  unitId,
  unitTitle,
  currentVersion,
  initialSelection,
  onSelectionConsumed,
  onClose,
  onApplied,
  onNotice,
  onVersionConflict,
}: ChatPanelProps) {
  const [tab, setTab] = useState<Tab>("ask");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState("");
  const [amendMode, setAmendMode] = useState<GenerationMode>("strict");
  const [amendInfo, setAmendInfo] = useState<AmendResult | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const trimmed = initialSelection?.trim();
    if (trimmed) setSelection(trimmed);
  }, [initialSelection]);

  useEffect(() => {
    setSelection("");
    setInput("");
    setAmendMode("strict");
  }, [unitId]);

  useEffect(() => {
    if (!open) setSelection("");
  }, [open]);

  useEffect(() => {
    if (!open || !unitId) return;
    let cancelled = false;
    setLoadingThread(true);
    setError("");
    api
      .getThread(unitId)
      .then((view) => {
        if (!cancelled) setMessages(view.messages ?? []);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setMessages([]);
          setError(err instanceof Error ? err.message : "Failed to load the thread");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingThread(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, unitId]);

  useEffect(() => {
    if (!open) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, open, busy]);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!unitId || !text || busy) return;
    setError("");
    setAmendInfo(null);

    if (tab === "ask") {
      const quoted = selection.trim() || undefined;
      const localMessage: ChatMessage = {
        id: `local-${Date.now()}`,
        thread_id: "",
        role: "user",
        content: text,
        citations: [],
        created_at: Date.now() / 1000,
        quoted,
      };
      setMessages((prev) => [...prev, localMessage]);
      setInput("");
      setBusy(true);
      try {
        const result = await api.askUnit(unitId, text, quoted);
        setMessages((prev) => [
          ...prev,
          {
            id: result.assistant_message_id,
            thread_id: result.thread_id,
            role: "assistant",
            content: result.answer,
            citations: result.citations,
            created_at: Date.now() / 1000,
          },
        ]);
        if (quoted) {
          setSelection("");
          onSelectionConsumed?.();
        }
        if (!result.grounded) {
          setError(
            "This answer found no knowledge-base evidence and was produced from the model's own knowledge. Please verify it.",
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to ask a follow-up");
        setInput(text);
      } finally {
        setBusy(false);
      }
      return;
    }

    setBusy(true);
    void runAmend(text, currentVersion);
  };

  const runAmend = async (text: string, expectedVersion: number) => {
    if (!unitId) return;
    setBusy(true);
    try {
      const result = await api.amendUnit(
        unitId,
        text,
        undefined,
        amendMode,
        expectedVersion,
      );
      setAmendInfo(result);
      setInput("");
      onNotice(
        `Change applied. Generated v${result.version} (from v${result.previous_version} · ${modeLabel(result.mode)} mode)`,
      );
      await onApplied();
    } catch (err) {
      const info = err instanceof ApiError ? err.conflict() : null;
      if (info && info.current_version !== undefined && onVersionConflict) {
        const current = info.current_version;
        onVersionConflict({
          expectedVersion,
          currentVersion: current,
          label: "This change",
          retry: () => runAmend(text, current),
        });
      } else {
        setError(err instanceof Error ? err.message : "Failed to apply the change");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: 480 }}
            animate={{ x: 0 }}
            exit={{ x: 480 }}
            transition={{ type: "spring", stiffness: 300, damping: 32 }}
            className="glass absolute inset-0 flex w-full flex-col rounded-t-[1.5rem] border-t border-white/50 shadow-glass sm:inset-y-0 sm:right-0 sm:left-auto sm:w-[470px] sm:rounded-none sm:rounded-l-3xl sm:border-l sm:border-t-0 dark:border-white/10"
          >
            <header className="sticky top-0 z-10 flex items-start gap-3 border-b border-slate-200/70 bg-white/70 px-4 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/60 sm:bg-transparent sm:px-5 sm:py-4 sm:backdrop-blur-none dark:sm:bg-transparent">
              <div className="brand-gradient mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-2xl text-white">
                <MessageSquare size={16} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                  Ask & Amend
                </p>
                <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {unitTitle || "Select a unit"} · v{currentVersion}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                aria-label="Close the chat panel"
              >
                <X size={16} />
              </button>
            </header>

            <AnimatePresence initial={false}>
              {selection ? (
                <motion.div
                  initial={{ opacity: 0, y: -6, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: "auto" }}
                  exit={{ opacity: 0, y: -6, height: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className="overflow-hidden"
                >
                  <div className="mx-5 mt-4 flex items-start gap-2 rounded-2xl border border-indigo-300/45 bg-indigo-500/10 px-3 py-2 dark:border-indigo-400/25 dark:bg-indigo-400/10">
                    <Quote size={13} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-300" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-indigo-500 dark:text-indigo-300">
                        Quoted selection
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                        {selection}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setSelection("");
                        onSelectionConsumed?.();
                      }}
                      className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                      aria-label="Clear the quoted selection"
                    >
                      <X size={12} />
                    </button>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>

            <div className="flex gap-1 px-5 pt-4">
              <div className="flex w-full rounded-2xl border border-slate-200/70 bg-white/45 p-1 dark:border-white/10 dark:bg-white/[0.04]">
                <button
                  type="button"
                  onClick={() => {
                    setTab("ask");
                    setError("");
                  }}
                  className={clsx(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition",
                    tab === "ask"
                      ? "bg-white text-indigo-600 shadow-sm dark:bg-white/10 dark:text-indigo-200"
                      : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
                  )}
                >
                  <MessageSquare size={13} />
                  Ask
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTab("amend");
                    setError("");
                  }}
                  className={clsx(
                    "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition",
                    tab === "amend"
                      ? "bg-white text-indigo-600 shadow-sm dark:bg-white/10 dark:text-indigo-200"
                      : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
                  )}
                >
                  <PenLine size={13} />
                  Amend
                </button>
              </div>
            </div>

            <div className="no-scrollbar flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {tab === "ask" ? (
                loadingThread ? (
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Loader2 size={13} className="animate-spin" />
                    Loading the thread…
                  </div>
                ) : messages.length === 0 ? (
                  <div className="glass-soft rounded-2xl p-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    Ask about this unit and the AI answers with knowledge-base evidence; answers can also be folded back into the body text.
                  </div>
                ) : (
                  messages.map((message) => {
                    const isUser = message.role === "user";
                    return (
                      <div
                        key={message.id}
                        className={clsx("flex", isUser ? "justify-end" : "justify-start")}
                      >
                        <div
                          className={clsx(
                            "max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px]",
                            isUser
                              ? "brand-gradient text-white shadow-brand"
                              : "glass-soft text-slate-600 dark:text-slate-300",
                          )}
                        >
                          {isUser ? (
                            <div className="space-y-1.5">
                              <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                              {message.quoted ? (
                                <p className="rounded-xl border border-white/25 bg-white/15 px-2 py-1 text-[11px] leading-relaxed text-white/85 line-clamp-3">
                                  Quoted: {message.quoted}
                                </p>
                              ) : null}
                            </div>
                          ) : (
                            <MarkdownReader
                              content={message.content}
                              citations={message.citations}
                              variant="compact"
                            />
                          )}
                          {message.citations?.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {message.citations.slice(0, 4).map((citation) => (
                                <span
                                  key={`${message.id}-${citation.chunk_id}`}
                                  className="rounded-full bg-white/60 px-2 py-0.5 text-[10px] text-indigo-600 dark:bg-white/10 dark:text-indigo-200"
                                  title={citation.snippet}
                                >
                                  {sourceLabel(citation.source_name)}
                                </span>
                              ))}
                            </div>
                          )}
                          <p
                            className={clsx(
                              "mt-1.5 text-[10px]",
                              isUser ? "text-white/70" : "text-slate-400 dark:text-slate-500",
                            )}
                          >
                            {formatRelative(message.created_at)}
                          </p>
                        </div>
                      </div>
                    );
                  })
                )
              ) : (
                <div className="space-y-3">
                  <div className="glass-soft rounded-2xl p-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                    Describe the change in plain language. The AI rewrites this unit as a new version, and the previous version can still be rolled back.
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                      Writing mode
                    </span>
                    <ModePicker
                      value={amendMode}
                      onChange={setAmendMode}
                      variant="compact"
                      disabled={busy}
                    />
                  </div>
                  {amendMode === "loose" ? (
                    <p className="text-[10px] leading-relaxed text-amber-700 dark:text-amber-300">
                      Loose mode: the model may rewrite from its own knowledge; the body keeps a “Written by AI” notice at the top.
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5">
                    {AMEND_PRESETS.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => setInput(preset)}
                        className="chip transition hover:bg-indigo-500/20"
                      >
                        <Sparkles size={11} />
                        {preset}
                      </button>
                    ))}
                  </div>
                  {amendInfo && (
                    <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-300">
                      <p className="font-medium">
                        Generated v{amendInfo.version} (from v{amendInfo.previous_version} ·{" "}
                        {modeLabel(amendInfo.mode)} mode)
                      </p>
                      <p className="mt-1 text-[11px] leading-relaxed opacity-80">
                        {amendInfo.note || amendInfo.instruction} ·{" "}
                        {contentLength(amendInfo.content)} chars ·{" "}
                        {amendInfo.citations.length} citations
                      </p>
                    </div>
                  )}
                  {messages.length > 0 && (
                    <div className="space-y-2 border-t border-slate-200/70 pt-3 dark:border-white/10">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                        Unit thread
                      </p>
                      {messages.slice(-4).map((message) => (
                        <p
                          key={message.id}
                          className={clsx(
                            "truncate text-[11px]",
                            message.role === "user"
                              ? "text-indigo-600 dark:text-indigo-300"
                              : "text-slate-500 dark:text-slate-400",
                          )}
                        >
                          {message.role === "user" ? "Q · " : "A · "}
                          {message.content.slice(0, 80)}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {busy && tab === "ask" && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 size={13} className="animate-spin" />
                  Retrieving evidence and drafting an answer…
                </div>
              )}
              {busy && tab === "amend" && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Loader2 size={13} className="animate-spin" />
                  Rewriting the body and creating a new version…
                </div>
              )}
              {error && (
                <div className="flex items-start gap-2 rounded-2xl border border-amber-400/30 bg-amber-500/10 p-3 text-[11px] leading-relaxed text-amber-700 dark:text-amber-300">
                  <AlertCircle size={13} className="mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <footer className="safe-bottom sticky bottom-0 z-10 border-t border-slate-200/70 bg-white/70 px-4 py-3 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/60 sm:bg-transparent sm:px-5 sm:py-4 sm:backdrop-blur-none dark:sm:bg-transparent">
              {tab === "ask" && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {ASK_PRESETS.map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => setInput(preset)}
                      className="rounded-full border border-slate-200/80 px-2 py-0.5 text-[10px] text-slate-500 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:text-slate-400 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
                    >
                      {preset}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      send();
                    }
                  }}
                  placeholder={
                    tab === "ask"
                      ? "Ask about this unit… (Ctrl/⌘ + Enter to send)"
                      : "Describe the change, e.g. make paragraph 2 more hands-on… (Ctrl/⌘ + Enter)"
                  }
                  className="input max-h-32 min-h-[3.2rem]"
                  rows={2}
                />
                <button
                  type="button"
                  onClick={send}
                  disabled={busy || !input.trim()}
                  className="btn btn-primary h-[3.2rem] w-12 shrink-0 px-0"
                  aria-label="Send"
                >
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                </button>
              </div>
            </footer>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
