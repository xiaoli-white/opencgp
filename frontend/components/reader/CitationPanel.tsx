import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  FileText,
  Globe,
  Upload,
  X,
} from "lucide-react";
import clsx from "clsx";
import type { Citation } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

export type CitationEntry = {
  marker: string;
  citation: Citation;
};

export type CitationSourceKind = "kb" | "web" | "upload";

type CitationNavValue = {
  activeMarker: string | null;
  openAt: (marker: string, element: HTMLElement | null) => void;
};

const CitationNavContext = createContext<CitationNavValue | null>(null);

export function CitationNavProvider({
  activeMarker,
  openAt,
  children,
}: {
  activeMarker: string | null;
  openAt: (marker: string, element: HTMLElement | null) => void;
  children: React.ReactNode;
}) {
  const value = useMemo<CitationNavValue>(
    () => ({ activeMarker, openAt }),
    [activeMarker, openAt],
  );
  return (
    <CitationNavContext.Provider value={value}>
      {children}
    </CitationNavContext.Provider>
  );
}

export function useCitationNav(): CitationNavValue | null {
  return useContext(CitationNavContext);
}

/** Existing dict entries win; these fallbacks keep the panel usable until
 * the owner merges the citation.* dictionary block. */
const FALLBACK: Record<string, { zh: string; en: string }> = {
  "citation.panelTitle": { zh: "证据详情", en: "Evidence" },
  "citation.source": { zh: "来源", en: "Source" },
  "citation.passage": { zh: "引用原文", en: "Cited passage" },
  "citation.position": {
    zh: "切片 #{index} · 字符 {start}–{end}",
    en: "Chunk #{index} · chars {start}–{end}",
  },
  "citation.openInKb": { zh: "在知识库中打开", en: "Open in knowledge base" },
  "citation.openOriginal": { zh: "打开原网页", en: "Open original page" },
  "citation.copy": { zh: "复制原文", en: "Copy passage" },
  "citation.prev": { zh: "上一条", en: "Previous" },
  "citation.next": { zh: "下一条", en: "Next" },
  "citation.close": { zh: "关闭", en: "Close" },
  "citation.sourcesTitle": { zh: "参考来源", en: "Sources" },
  "citation.noCitations": {
    zh: "本文没有可回溯的引用。",
    en: "No traceable citations in this article.",
  },
  "citation.kindKb": { zh: "知识库文档", en: "Knowledge-base document" },
  "citation.kindWeb": { zh: "网页", en: "Web page" },
  "citation.kindUpload": { zh: "上传文件", en: "Upload" },
};

export function useCitationText() {
  const { t, locale } = useI18n();
  return useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const value = t(key, vars);
      if (value !== key) return value;
      const entry = FALLBACK[key];
      if (!entry) return value;
      let text = entry[locale];
      if (vars) {
        text = text.replace(/\{(\w+)\}/g, (match, name: string) =>
          name in vars ? String(vars[name]) : match,
        );
      }
      return text;
    },
    [t, locale],
  );
}

export function citationKind(citation: Citation): CitationSourceKind {
  const meta = citation.meta ?? {};
  const kind = String(meta.kind ?? "").toLowerCase();
  if (kind === "web" || typeof meta.url === "string") return "web";
  if (
    kind === "upload" ||
    typeof meta.object_key === "string" ||
    meta.upload === true
  ) {
    return "upload";
  }
  return "kb";
}

export function citationKindLabel(kind: CitationSourceKind): string {
  if (kind === "web") return "citation.kindWeb";
  if (kind === "upload") return "citation.kindUpload";
  return "citation.kindKb";
}

export function citationWebUrl(citation: Citation): string {
  const meta = citation.meta ?? {};
  const candidates = [meta.url, meta.href, citation.source_id];
  for (const candidate of candidates) {
    if (typeof candidate !== "string") continue;
    const value = candidate.trim();
    if (/^https?:\/\//i.test(value)) return value;
  }
  return "";
}

/** The KB page can consume these params once it grows a deep-link handler;
 * source + chunk identify the document and chunk, the hash is the anchor. */
export function citationKbHref(citation: Citation): string {
  const params = new URLSearchParams();
  if (citation.source_id) params.set("source", citation.source_id);
  if (Number.isFinite(citation.chunk_index)) {
    params.set("chunk", String(citation.chunk_index));
  }
  const query = params.toString();
  const hash = citation.chunk_id
    ? `#chunk-${encodeURIComponent(citation.chunk_id)}`
    : "";
  return `/kb${query ? `?${query}` : ""}${hash}`;
}

function clampRange(
  text: string,
  start: number,
  end: number,
): { before: string; mark: string; after: string } {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return { before: text, mark: "", after: "" };
  }
  const from = Math.trunc(start);
  const to = Math.trunc(end);
  if (from >= 0 && to <= text.length && to > from) {
    return {
      before: text.slice(0, from),
      mark: text.slice(from, to),
      after: text.slice(to),
    };
  }
  // Chunk citations store document offsets rather than offsets inside the
  // chunk, so the cited range is the whole retrieved passage.
  return { before: "", mark: text, after: "" };
}

function CopyButton({ text }: { text: string }) {
  const tr = useCitationText();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        document.body.removeChild(area);
      }
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex h-8 items-center gap-1.5 rounded-full border border-slate-200/80 bg-white/70 px-3 text-[11px] font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
      aria-label={tr("citation.copy")}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {tr("citation.copy")}
    </button>
  );
}

function SourceKindIcon({ kind }: { kind: CitationSourceKind }) {
  if (kind === "web") return <Globe size={12} />;
  if (kind === "upload") return <Upload size={12} />;
  return <BookOpen size={12} />;
}

export function CitationEvidencePanel({
  entries,
  activeMarker,
  onSelect,
  onClose,
}: {
  entries: CitationEntry[];
  activeMarker: string | null;
  onSelect: (marker: string) => void;
  onClose: () => void;
}) {
  const tr = useCitationText();
  const panelRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const openedRef = useRef(false);

  const index = useMemo(
    () => entries.findIndex((entry) => entry.marker === activeMarker),
    [entries, activeMarker],
  );
  const entry = index >= 0 ? entries[index] : null;

  useEffect(() => {
    if (!entry) {
      openedRef.current = false;
      return;
    }
    if (openedRef.current) return;
    openedRef.current = true;
    const node = closeRef.current;
    if (node) node.focus({ preventScroll: true });
  }, [entry]);

  useEffect(() => {
    if (!entry) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === "Tab") {
        const panel = panelRef.current;
        if (!panel) return;
        const focusable = Array.from(
          panel.querySelectorAll<HTMLElement>(
            'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
          ),
        ).filter((node) => node.offsetParent !== null || node === document.activeElement);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [entry, onClose]);

  if (typeof document === "undefined") return null;

  const citation = entry?.citation;
  const passage = citation ? citation.text || citation.snippet || "" : "";
  const kind = citation ? citationKind(citation) : "kb";
  const webUrl = citation ? citationWebUrl(citation) : "";
  const range = citation ? clampRange(passage, citation.start, citation.end) : null;

  return createPortal(
    <AnimatePresence>
      {entry && citation ? (
        <div key="citation-evidence" className="fixed inset-0 z-[90]">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 bg-slate-950/45 backdrop-blur-[2px]"
            onClick={onClose}
            aria-hidden="true"
          />
          <motion.section
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="citation-panel-title"
            data-citation-panel="true"
            data-active-citation={entry.marker}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 36 }}
            className="absolute inset-y-0 right-0 flex w-[27rem] max-w-[92vw] flex-col border-l border-white/60 bg-white/95 font-sans shadow-[-24px_0_60px_-30px_rgba(15,23,42,0.55)] backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/95 max-[640px]:inset-0 max-[640px]:w-full max-[640px]:max-w-none max-[640px]:border-l-0"
          >
            <header className="flex shrink-0 items-start gap-3 border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
              <span className="brand-gradient mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl text-[12px] font-semibold text-white shadow-brand">
                {entry.marker.replace(/^E/, "")}
              </span>
              <div className="min-w-0 flex-1">
                <p
                  id="citation-panel-title"
                  className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white"
                >
                  {tr("citation.panelTitle")}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-slate-500 dark:text-slate-400">
                  {entry.marker} · {index + 1} / {entries.length}
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                aria-label={tr("citation.close")}
                className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-500 dark:hover:bg-white/10 dark:hover:text-slate-200"
              >
                <X size={16} />
              </button>
            </header>

            <div className="shrink-0 border-b border-slate-200/70 px-5 py-2.5 dark:border-white/10">
              <div className="no-scrollbar flex gap-1 overflow-x-auto">
                {entries.map((item) => {
                  const active = item.marker === entry.marker;
                  return (
                    <button
                      key={item.marker}
                      type="button"
                      onClick={() => onSelect(item.marker)}
                      aria-current={active ? "true" : undefined}
                      className={clsx(
                        "h-7 min-w-7 shrink-0 rounded-full px-2 text-[10px] font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                        active
                          ? "brand-gradient text-white shadow-[0_6px_16px_-10px_rgba(99,102,241,0.9)]"
                          : "bg-slate-100 text-slate-500 hover:text-indigo-600 dark:bg-white/[0.07] dark:text-slate-400 dark:hover:text-indigo-200",
                      )}
                    >
                      {item.marker.replace(/^E/, "")}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div className="rounded-2xl border border-slate-200/70 bg-white/55 p-3.5 dark:border-white/10 dark:bg-white/[0.04]">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {tr("citation.source")}
                </p>
                <p className="mt-1 break-words text-[13px] font-semibold leading-relaxed text-slate-800 dark:text-slate-100">
                  {citation.source_name || "—"}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px]">
                  <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/10 px-2 py-0.5 font-medium text-indigo-600 dark:bg-indigo-400/15 dark:text-indigo-200">
                    <SourceKindIcon kind={kind} />
                    {tr(citationKindLabel(kind))}
                  </span>
                  {kind === "web" && webUrl ? (
                    <a
                      href={webUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200/80 px-2 py-0.5 font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
                    >
                      <ExternalLink size={10} />
                      {tr("citation.openOriginal")}
                    </a>
                  ) : (
                    <a
                      href={citationKbHref(citation)}
                      className="inline-flex items-center gap-1 rounded-full border border-slate-200/80 px-2 py-0.5 font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
                    >
                      <FileText size={10} />
                      {tr("citation.openInKb")}
                    </a>
                  )}
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between gap-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {tr("citation.passage")}
                </p>
                <CopyButton text={passage} />
              </div>
              <div
                data-active="true"
                className="mt-2 rounded-2xl border border-indigo-300/60 bg-indigo-50/50 p-3.5 ring-2 ring-indigo-500/15 dark:border-indigo-400/25 dark:bg-indigo-400/[0.06]"
              >
                <p className="whitespace-pre-wrap break-words font-reading text-[13.5px] leading-[1.85] text-slate-700 dark:text-slate-200">
                  {range ? (
                    <>
                      {range.before}
                      {range.mark ? (
                        <mark className="rounded bg-amber-200/80 px-0.5 text-slate-900 dark:bg-amber-300/30 dark:text-amber-100">
                          {range.mark}
                        </mark>
                      ) : null}
                      {range.after}
                    </>
                  ) : (
                    passage
                  )}
                </p>
              </div>

              {kind === "web" ? (
                <div
                  data-testid="citation-archived-notice"
                  className="mt-2 rounded-xl border border-amber-300/50 bg-amber-50/60 px-3 py-2 text-[10.5px] leading-relaxed text-amber-800 dark:border-amber-300/20 dark:bg-amber-400/10 dark:text-amber-200"
                >
                  <p>{tr("citation.archivedPassage")}</p>
                  {typeof citation.meta?.retrieved_at === "string" &&
                  citation.meta.retrieved_at ? (
                    <p className="mt-0.5 opacity-80">
                      {tr("citation.retrievedAt", {
                        time: citation.meta.retrieved_at,
                      })}
                    </p>
                  ) : null}
                </div>
              ) : null}

              <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10.5px] tabular-nums text-slate-400 dark:text-slate-500">
                <span>
                  {tr("citation.position", {
                    index: citation.chunk_index,
                    start: citation.start,
                    end: citation.end,
                  })}
                </span>
                {citation.chunk_id ? (
                  <span className="truncate">· {citation.chunk_id}</span>
                ) : null}
              </p>
            </div>

            <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-slate-200/70 px-5 py-3 dark:border-white/10">
              <button
                type="button"
                onClick={() => onSelect(entries[index - 1].marker)}
                disabled={index <= 0}
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-slate-200/80 px-3.5 text-[11px] font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-35 dark:border-white/10 dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
              >
                <ChevronLeft size={13} />
                {tr("citation.prev")}
              </button>
              <button
                type="button"
                onClick={() => onSelect(entries[index + 1].marker)}
                disabled={index >= entries.length - 1}
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-slate-200/80 px-3.5 text-[11px] font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-35 dark:border-white/10 dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
              >
                {tr("citation.next")}
                <ChevronRight size={13} />
              </button>
            </footer>
          </motion.section>
        </div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}
