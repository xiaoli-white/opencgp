"use client";

import { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import clsx from "clsx";
import { FileText } from "lucide-react";
import type { Citation, Evidence } from "@/lib/api";

type MarkdownReaderProps = {
  content: string;
  citations?: Citation[];
  evidence?: Evidence[];
  variant?: "reader" | "compact";
  className?: string;
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
}: MarkdownReaderProps) {
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
      className={clsx(
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
    </div>
  );
}
