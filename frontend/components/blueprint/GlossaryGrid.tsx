"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BookMarked,
  Check,
  Loader2,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import type { GlossaryTerm } from "@/lib/api";

type GlossaryGridProps = {
  glossary: GlossaryTerm[];
  editing: boolean;
  saving: boolean;
  onSave: (terms: GlossaryTerm[]) => void;
  onCancel: () => void;
};

type DraftTerm = {
  term: string;
  definition: string;
  aliases: string;
  node_ids: string[];
};

function toDraft(terms: GlossaryTerm[]): DraftTerm[] {
  return terms.map((term) => ({
    term: term.term,
    definition: term.definition,
    aliases: term.aliases.join("、"),
    node_ids: term.node_ids,
  }));
}

function fromDraft(drafts: DraftTerm[]): GlossaryTerm[] {
  return drafts
    .map((draft) => ({
      term: draft.term.trim(),
      definition: draft.definition.trim(),
      aliases: draft.aliases
        .split(/[,，、;；]/)
        .map((alias) => alias.trim())
        .filter(Boolean),
      node_ids: draft.node_ids,
    }))
    .filter((term) => term.term.length > 0);
}

export default function GlossaryGrid({
  glossary,
  editing,
  saving,
  onSave,
  onCancel,
}: GlossaryGridProps) {
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<DraftTerm[]>(() => toDraft(glossary));

  useEffect(() => {
    if (editing) setDrafts(toDraft(glossary));
  }, [editing, glossary]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return glossary;
    return glossary.filter((term) => {
      const haystack = [term.term, term.definition, ...term.aliases]
        .join(" ")
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [glossary, query]);

  const patchDraft = (index: number, patch: Partial<DraftTerm>) => {
    setDrafts((prev) =>
      prev.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );
  };

  if (editing) {
    return (
      <div className="space-y-2.5">
        {drafts.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-slate-300/70 px-4 py-6 text-center text-[11.5px] text-slate-500 dark:border-white/15 dark:text-slate-400">
            术语表为空，点下方「新增术语」补一条。
          </p>
        ) : null}
        {drafts.map((draft, index) => (
          <div
            key={`draft-${index}`}
            className="rounded-2xl border border-slate-200/70 bg-white/55 p-3 dark:border-white/10 dark:bg-white/[0.04]"
          >
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1 space-y-2">
                <input
                  value={draft.term}
                  onChange={(event) =>
                    patchDraft(index, { term: event.target.value })
                  }
                  placeholder="术语，如：HNSW"
                  className="input text-[13px]"
                />
                <textarea
                  value={draft.definition}
                  onChange={(event) =>
                    patchDraft(index, { definition: event.target.value })
                  }
                  placeholder="一句话定义"
                  rows={2}
                  className="input resize-none text-[12.5px] leading-relaxed"
                />
                <input
                  value={draft.aliases}
                  onChange={(event) =>
                    patchDraft(index, { aliases: event.target.value })
                  }
                  placeholder="别名，用顿号或逗号分隔"
                  className="input text-[12px]"
                />
              </div>
              <button
                type="button"
                onClick={() =>
                  setDrafts((prev) => prev.filter((_, pos) => pos !== index))
                }
                className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-500"
                aria-label="删除术语"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <button
            type="button"
            onClick={() =>
              setDrafts((prev) => [
                ...prev,
                { term: "", definition: "", aliases: "", node_ids: [] },
              ])
            }
            className="btn btn-ghost"
          >
            <Plus size={13} />
            新增术语
          </button>
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={onCancel} className="btn-quiet">
              <X size={12} />
              取消
            </button>
            <button
              type="button"
              onClick={() => onSave(fromDraft(drafts))}
              disabled={saving}
              className="btn btn-primary"
            >
              {saving ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Check size={13} />
              )}
              保存术语表
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="relative">
        <Search
          size={13}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
        />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索术语、定义或别名"
          className="input pl-8 text-[12.5px]"
        />
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300/70 px-4 py-8 text-center dark:border-white/15">
          <BookMarked
            size={18}
            className="mx-auto text-slate-400 dark:text-slate-500"
          />
          <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
            {glossary.length === 0
              ? "还没有术语，生成蓝图或手动补充。"
              : "没有匹配的术语。"}
          </p>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {filtered.map((term, index) => (
            <motion.div
              key={`${term.term}-${index}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: Math.min(index * 0.02, 0.16) }}
              className={clsx(
                "rounded-2xl border border-slate-200/70 bg-white/50 p-3 transition hover:border-indigo-300/60 hover:bg-white/70",
                "dark:border-white/10 dark:bg-white/[0.04] dark:hover:border-indigo-400/30 dark:hover:bg-white/[0.07]",
              )}
            >
              <p className="text-[13px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                {term.term}
              </p>
              {term.definition ? (
                <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {term.definition}
                </p>
              ) : null}
              {term.aliases.length > 0 ? (
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  {term.aliases.map((alias) => (
                    <span key={alias} className="chip-muted !text-[9.5px]">
                      {alias}
                    </span>
                  ))}
                </div>
              ) : null}
              {term.node_ids.length > 0 ? (
                <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                  关联 {term.node_ids.length} 个节点
                </p>
              ) : null}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
