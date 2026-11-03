"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import clsx from "clsx";
import { AnimatePresence, motion } from "framer-motion";
import { FileText, MessageSquareQuote } from "lucide-react";
import type { Citation, Evidence } from "@/lib/api";

type MarkdownReaderProps = {
  content: string;
  citations?: Citation[];
  evidence?: Evidence[];
  variant?: "reader" | "compact";
  className?: string;
  onAskSelection?: (text: string) => void;
};

type SelectionAnchor = {
  text: string;
  top: number;
  left: number;
};

const MARKER_PATTERN = /^\[E(\d+)\]$/;

function CiteMark({ marker, source }: { marker: string; source?: Citation }) {
  if (!source) {
    return <span className="text-slate-400">[{marker}]</span>;
  }
  return (
    <span className="group relative inline-block align-super">
      <span className="cite-mark">{marker.replace("E", "")}</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-40 mb-2 hidden w-72 -translate-x-1/2 rounded-2xl border border-white/60 bg-white/95 p-3 text-left font-sans text-[11px] font-normal not-italic leading-relaxed text-slate-600 shadow-xl backdrop-blur-xl group-hover:block dark:border-white/15 dark:bg-slate-900/95 dark:text-slate-300">
        <span className="mb-1 flex items-center gap-1 font-semibold text-indigo-600 dark:text-indigo-300">
          <FileText size={11} />
          {source.source_name || "知识源"}
        </span>
        <span className="block max-h-32 overflow-hidden">
          {source.snippet || source.text}
        </span>
        <span className="mt-1.5 block text-[10px] text-slate-400 dark:text-slate-500">
          匹配度 {source.score.toFixed(2)} · 片段 #{source.chunk_index}
        </span>
      </span>
    </span>
  );
}

function decorate(
  node: React.ReactNode,
  lookup: Map<string, Citation>,
): React.ReactNode {
  if (typeof node === "string") {
    const parts = node.split(/(\[E\d+\])/g);
    if (parts.length === 1) return node;
    return parts.map((part, index) => {
      const match = MARKER_PATTERN.exec(part);
      if (!match) return part;
      const marker = `E${match[1]}`;
      return <CiteMark key={`${marker}-${index}`} marker={marker} source={lookup.get(marker)} />;
    });
  }
  if (Array.isArray(node)) {
    return node.map((child) => decorate(child, lookup));
  }
  return node;
}

export default function MarkdownReader({
  content,
  citations = [],
  evidence,
  variant = "reader",
  className,
  onAskSelection,
}: MarkdownReaderProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [anchor, setAnchor] = useState<SelectionAnchor | null>(null);

  const dismiss = useCallback(() => setAnchor(null), []);

  useEffect(() => {
    dismiss();
  }, [content, dismiss]);

  useEffect(() => {
    if (!onAskSelection) return;
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
  }, [onAskSelection, dismiss]);

  const lookup = useMemo(() => {
    const map = new Map<string, Citation>();
    evidence?.forEach((item) => {
      map.set(item.marker, item.citation);
    });
    citations.forEach((citation, index) => {
      const marker = `E${index + 1}`;
      if (!map.has(marker)) map.set(marker, citation);
    });
    return map;
  }, [citations, evidence]);

  const components = useMemo<Components>(
    () => ({
      p({ children }) {
        return <p>{decorate(children, lookup)}</p>;
      },
      li({ children }) {
        return <li>{decorate(children, lookup)}</li>;
      },
      td({ children }) {
        return <td>{decorate(children, lookup)}</td>;
      },
      a({ href, children }) {
        return (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        );
      },
    }),
    [lookup],
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
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
      {onAskSelection ? (
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
                onAskSelection(text);
                window.getSelection()?.removeAllRanges();
                dismiss();
              }}
              style={{ top: anchor.top, left: anchor.left }}
              className="brand-gradient absolute z-30 !mt-0 flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 font-sans text-[11px] font-medium text-white shadow-[0_14px_30px_-16px_rgba(99,102,241,0.95)] ring-1 ring-white/45 transition-[filter] hover:brightness-105 dark:ring-white/20"
            >
              <MessageSquareQuote size={13} />
              针对这段提问
            </motion.button>
          ) : null}
        </AnimatePresence>
      ) : null}
    </div>
  );
}
