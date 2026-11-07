import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ChevronRight, FileText, MessageSquareQuote } from "lucide-react";
import type { Citation, Evidence, GenerationMode } from "@/lib/api";
import { splitLooseNotice } from "@/lib/format";
import { mediaSrc } from "@/lib/media";
import MermaidDiagram from "@/components/reader/MermaidDiagram";
import {
  CitationEvidencePanel,
  CitationNavProvider,
  useCitationNav,
  useCitationText,
  type CitationEntry,
} from "@/components/reader/CitationPanel";
import { useI18n } from "@/i18n/I18nProvider";

type MarkdownReaderProps = {
  content: string;
  citations?: Citation[];
  evidence?: Evidence[];
  variant?: "reader" | "compact";
  mode?: GenerationMode | "";
  className?: string;
  onAskSelection?: (text: string) => void;
  enableAsk?: boolean;
  showCitations?: boolean;
};

type SelectionAnchor = {
  text: string;
  top: number;
  left: number;
};

const MARKER_PATTERN = /^\[E(\d+)\]$/;

function CiteMark({
  marker,
  source,
  anchorId,
}: {
  marker: string;
  source?: Citation;
  anchorId: string;
}) {
  const tr = useCitationText();
  const nav = useCitationNav();
  if (!source) {
    return <span className="text-slate-400">[{marker}]</span>;
  }
  const active = nav?.activeMarker === marker;
  return (
    <button
      id={anchorId}
      type="button"
      data-citation-marker={marker}
      data-reader-ask-ignore
      aria-haspopup="dialog"
      aria-expanded={active}
      aria-label={`${tr("citation.panelTitle")} [${marker}]`}
      title={source.source_name || undefined}
      onMouseDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        window.getSelection()?.removeAllRanges();
        nav?.openAt(marker, event.currentTarget);
      }}
      className="group relative inline-block border-0 bg-transparent p-0 align-super font-sans leading-none focus:outline-none"
    >
      <span
        className={clsx(
          "cite-mark !cursor-pointer transition-[background-color,color,box-shadow] group-focus-visible:ring-2 group-focus-visible:ring-indigo-500 group-focus-visible:ring-offset-2 dark:group-focus-visible:ring-offset-slate-950",
          active &&
            "!border-indigo-600 !bg-indigo-600 !text-white shadow-[0_0_0_3px_rgba(99,102,241,0.24)]",
        )}
      >
        {marker.replace("E", "")}
      </span>
    </button>
  );
}

function decorate(
  node: React.ReactNode,
  lookup: Map<string, Citation>,
  showCitations: boolean,
  occurrences: Map<string, number>,
): React.ReactNode {
  if (typeof node === "string") {
    const parts = node.split(/(\[E\d+\])/g);
    if (parts.length === 1) return node;
    return parts.map((part, index) => {
      const match = MARKER_PATTERN.exec(part);
      if (!match) return part;
      if (!showCitations) return null;
      const marker = `E${match[1]}`;
      const occurrence = (occurrences.get(marker) ?? 0) + 1;
      occurrences.set(marker, occurrence);
      const anchorId =
        occurrence === 1 ? `cite-${marker}` : `cite-${marker}-${occurrence}`;
      return (
        <CiteMark
          key={`${marker}-${index}`}
          marker={marker}
          source={lookup.get(marker)}
          anchorId={anchorId}
        />
      );
    });
  }
  if (Array.isArray(node)) {
    return node.map((child) => decorate(child, lookup, showCitations, occurrences));
  }
  return node;
}

function CitationSources({
  entries,
  activeMarker,
  onJump,
}: {
  entries: CitationEntry[];
  activeMarker: string | null;
  onJump: (marker: string) => void;
}) {
  const tr = useCitationText();
  return (
    <details className="group mt-10 rounded-2xl border border-slate-200/70 bg-white/40 font-sans shadow-[0_18px_40px_-36px_rgba(15,23,42,0.45)] dark:border-white/10 dark:bg-white/[0.03]">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3.5 py-2.5 text-[11.5px] font-medium text-slate-600 transition hover:text-indigo-600 dark:text-slate-300 dark:hover:text-indigo-200 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          size={13}
          className="shrink-0 text-slate-400 transition-transform group-open:rotate-90"
        />
        <FileText size={12} className="shrink-0 text-indigo-500 dark:text-indigo-300" />
        <span>{tr("citation.sourcesTitle")}</span>
        <span className="chip-muted ml-auto tabular-nums">{entries.length}</span>
      </summary>
      <ol className="space-y-1 border-t border-slate-200/70 px-2.5 py-2.5 dark:border-white/10">
        {entries.map(({ marker, citation }) => {
          const active = marker === activeMarker;
          return (
            <li key={marker}>
              <a
                href={`#cite-${marker}`}
                aria-current={active ? "true" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  onJump(marker);
                }}
                className={clsx(
                  "flex items-center gap-2 rounded-xl px-2 py-1.5 text-[11px] transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                  active
                    ? "bg-indigo-500/10 text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-200"
                    : "text-slate-600 hover:bg-indigo-500/[0.07] hover:text-indigo-600 dark:text-slate-300 dark:hover:bg-indigo-400/10 dark:hover:text-indigo-200",
                )}
              >
                <span
                  className={clsx(
                    "cite-mark shrink-0",
                    active && "!border-indigo-600 !bg-indigo-600 !text-white",
                  )}
                >
                  {marker.replace(/^E/, "")}
                </span>
                <span className="min-w-0 flex-1 truncate">
                  {citation.source_name || "—"}
                </span>
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-slate-400 dark:text-slate-500">
                  #{citation.chunk_index}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

export default function MarkdownReader({
  content,
  citations = [],
  evidence,
  variant = "reader",
  mode,
  className,
  onAskSelection,
  enableAsk = true,
  showCitations = true,
}: MarkdownReaderProps) {
  const { t } = useI18n();
  const tr = useCitationText();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [anchor, setAnchor] = useState<SelectionAnchor | null>(null);
  const [activeMarker, setActiveMarker] = useState<string | null>(null);
  const originRef = useRef<{ anchorId: string; scrollY: number } | null>(null);
  const restoreRef = useRef<{ anchorId: string; scrollY: number } | null>(null);
  const occurrencesRef = useRef(new Map<string, number>());
  occurrencesRef.current = new Map();
  const askEnabled = enableAsk && Boolean(onAskSelection);

  const dismiss = useCallback(() => setAnchor(null), []);

  useEffect(() => {
    dismiss();
  }, [content, dismiss]);

  const { body, notice } = useMemo(
    () =>
      variant === "reader"
        ? splitLooseNotice(content)
        : { body: content, notice: "" },
    [content, variant],
  );

  const entries = useMemo<CitationEntry[]>(() => {
    const map = new Map<string, Citation>();
    citations.forEach((citation, index) => {
      map.set(`E${index + 1}`, citation);
    });
    evidence?.forEach((item) => {
      map.set(item.marker, item.citation);
    });
    const inline = new Set(
      Array.from(body.matchAll(/\[E(\d+)\]/g), (match) => `E${match[1]}`),
    );
    return Array.from(map, ([marker, citation]) => ({ marker, citation }))
      .filter((entry) => inline.has(entry.marker))
      .sort((a, b) => Number(a.marker.slice(1)) - Number(b.marker.slice(1)));
  }, [body, citations, evidence]);

  const lookup = useMemo(
    () => new Map(entries.map((entry) => [entry.marker, entry.citation])),
    [entries],
  );

  const openAt = useCallback(
    (marker: string, element: HTMLElement | null) => {
      if (!activeMarker) {
        originRef.current = {
          anchorId: element?.id || `cite-${marker}`,
          scrollY: window.scrollY,
        };
      }
      dismiss();
      setActiveMarker(marker);
    },
    [activeMarker, dismiss],
  );

  const closePanel = useCallback(() => {
    if (originRef.current) restoreRef.current = originRef.current;
    originRef.current = null;
    setActiveMarker(null);
  }, []);

  useEffect(() => {
    if (activeMarker !== null) return;
    const origin = restoreRef.current;
    if (!origin) return;
    restoreRef.current = null;
    // Wait one beat so ReactMarkdown has committed the re-rendered markers
    // after the panel unmounts; focusing an about-to-be-replaced node would
    // otherwise leave focus on <body>.
    const timer = window.setTimeout(() => {
      const target = document.getElementById(origin.anchorId);
      target?.focus({ preventScroll: true });
      window.scrollTo(0, origin.scrollY);
    }, 160);
    return () => window.clearTimeout(timer);
  }, [activeMarker]);

  useEffect(() => {
    if (!activeMarker) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [activeMarker]);

  useEffect(() => {
    if (!activeMarker) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        // Reader mode binds Escape to "leave reader" on window; stop it here
        // before the page-level shortcut can navigate away from the article.
        event.stopImmediatePropagation();
        closePanel();
        return;
      }
      const index = entries.findIndex((entry) => entry.marker === activeMarker);
      if (event.key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        event.stopImmediatePropagation();
        setActiveMarker(entries[index - 1].marker);
      } else if (
        event.key === "ArrowRight" &&
        index >= 0 &&
        index < entries.length - 1
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        setActiveMarker(entries[index + 1].marker);
      } else if (event.key === "f" || event.key === "t") {
        event.stopImmediatePropagation();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [activeMarker, entries, closePanel]);

  const jumpToMarker = useCallback((marker: string) => {
    const target = document.getElementById(`cite-${marker}`);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => target.focus({ preventScroll: true }), 280);
  }, []);

  useEffect(() => {
    if (!askEnabled) return;
    const host = hostRef.current;
    if (!host) return;

    const read = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        dismiss();
        return;
      }
      const text = selection.toString().replace(/\s+/g, " ").trim();
      if (!text) {
        dismiss();
        return;
      }
      const range = selection.getRangeAt(0);
      const { startContainer, endContainer } = range;
      if (!host.contains(startContainer) || !host.contains(endContainer)) {
        dismiss();
        return;
      }
      const startElement =
        startContainer.nodeType === Node.ELEMENT_NODE
          ? (startContainer as Element)
          : startContainer.parentElement;
      if (startElement?.closest("[data-reader-ask-ignore]")) {
        dismiss();
        return;
      }
      const rects = Array.from(range.getClientRects()).filter(
        (rect) => rect.width > 0 || rect.height > 0,
      );
      const last = rects[rects.length - 1] ?? range.getBoundingClientRect();
      const hostRect = host.getBoundingClientRect();
      if (!last.width && !last.height) {
        dismiss();
        return;
      }
      const half = Math.min(96, Math.max(hostRect.width / 2, 48));
      const rawLeft = last.left - hostRect.left + last.width / 2;
      const left = Math.min(Math.max(rawLeft, half), Math.max(hostRect.width - half, half));
      setAnchor({ text, top: last.bottom - hostRect.top + 8, left });
    };

    let frame = 0;
    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        read();
      });
    };

    const onPointerUp = (event: MouseEvent) => {
      const target = event.target as Element | null;
      if (target?.closest("[data-reader-ask-ignore]")) return;
      schedule();
    };

    document.addEventListener("selectionchange", schedule);
    document.addEventListener("mouseup", onPointerUp);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      document.removeEventListener("selectionchange", schedule);
      document.removeEventListener("mouseup", onPointerUp);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [askEnabled, onAskSelection, dismiss]);

  const loose = variant === "reader" && (mode === "loose" || Boolean(notice));

  const components = useMemo<Components>(
    () => ({
      p({ children }) {
        return (
          <p>{decorate(children, lookup, showCitations, occurrencesRef.current)}</p>
        );
      },
      h1({ children }) {
        return (
          <h1>{decorate(children, lookup, showCitations, occurrencesRef.current)}</h1>
        );
      },
      h2({ children }) {
        return (
          <h2>{decorate(children, lookup, showCitations, occurrencesRef.current)}</h2>
        );
      },
      h3({ children }) {
        return (
          <h3>{decorate(children, lookup, showCitations, occurrencesRef.current)}</h3>
        );
      },
      h4({ children }) {
        return (
          <h4>{decorate(children, lookup, showCitations, occurrencesRef.current)}</h4>
        );
      },
      li({ children }) {
        return (
          <li>{decorate(children, lookup, showCitations, occurrencesRef.current)}</li>
        );
      },
      td({ children }) {
        return (
          <td>{decorate(children, lookup, showCitations, occurrencesRef.current)}</td>
        );
      },
      a({ href, children }) {
        return (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        );
      },
      img({ src, alt, title }) {
        return (
          <img
            src={mediaSrc(src ?? "")}
            alt={alt ?? ""}
            title={title}
            loading="lazy"
            className="mx-auto my-4 h-auto max-w-full rounded-2xl border border-slate-200/70 shadow-sm dark:border-white/10"
          />
        );
      },
      pre({ children }) {
        const list = Array.isArray(children) ? children : [children];
        const hasMermaid = list.some(
          (child) =>
            (child as { props?: Record<string, unknown> } | null)?.props?.[
              "data-mermaid"
            ] === "1",
        );
        if (hasMermaid) return <>{children}</>;
        return <pre>{children}</pre>;
      },
      code({ className, children, ...rest }) {
        const language = /language-([\w-]+)/.exec(className ?? "")?.[1];
        if (language === "mermaid") {
          return (
            <span data-mermaid="1" className="block">
              <MermaidDiagram code={String(children)} />
            </span>
          );
        }
        return (
          <code className={className} {...rest}>
            {children}
          </code>
        );
      },
    }),
    [lookup, showCitations],
  );

  return (
    <div
      ref={hostRef}
      className={clsx(
        "relative",
        variant === "compact" ? "reader reader-compact" : "reader",
        className,
      )}
    >
      {loose ? (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.26, ease: "easeOut" }}
          className="flex items-start gap-2 rounded-2xl border border-amber-400/45 bg-amber-400/15 px-3.5 py-2.5 font-sans text-[12px] leading-relaxed shadow-[0_14px_30px_-26px_rgba(217,119,6,0.9)] backdrop-blur-xl dark:border-amber-300/25 dark:bg-amber-300/10"
          role="note"
        >
          <AlertTriangle
            size={14}
            className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-300"
          />
          <span className="text-amber-800 dark:text-amber-200">
            <span className="font-semibold">{t("reader.looseTitle")}</span>
            <span className="mx-1.5 text-amber-500/70 dark:text-amber-300/50">
              /
            </span>
            {notice
              ? notice.replace(/^⚠️?\s*/, "")
              : t("reader.looseFallback")}
          </span>
        </motion.div>
      ) : null}
      <CitationNavProvider activeMarker={activeMarker} openAt={openAt}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
          components={components}
        >
          {body}
        </ReactMarkdown>
      </CitationNavProvider>
      {/* The article carries its own inline markers; the separate sources box is
          not shown because readers open evidence from the marker itself. */}
      <CitationEvidencePanel
        entries={entries}
        activeMarker={activeMarker}
        onSelect={setActiveMarker}
        onClose={closePanel}
      />
      {askEnabled ? (
        <AnimatePresence>
          {anchor ? (
            <motion.button
              type="button"
              data-reader-ask-ignore
              initial={{ opacity: 0, x: "-50%", y: 6, scale: 0.94 }}
              animate={{ opacity: 1, x: "-50%", y: 0, scale: 1 }}
              exit={{ opacity: 0, x: "-50%", y: 4, scale: 0.96 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                const text = anchor.text;
                onAskSelection?.(text);
                window.getSelection()?.removeAllRanges();
                dismiss();
              }}
              style={{ top: anchor.top, left: anchor.left }}
              className="brand-gradient absolute z-30 !mt-0 flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 font-sans text-[11px] font-medium text-white shadow-[0_14px_30px_-16px_rgba(99,102,241,0.95)] ring-1 ring-white/45 transition-[filter] hover:brightness-105 dark:ring-white/20"
            >
              <MessageSquareQuote size={13} />
              {t("reader.askSelection")}
            </motion.button>
          ) : null}
        </AnimatePresence>
      ) : null}
    </div>
  );
}
