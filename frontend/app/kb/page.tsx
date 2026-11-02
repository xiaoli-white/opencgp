"use client";

import { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Check,
  FileUp,
  Loader2,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  API_BASE,
  api,
  type Citation,
  type IngestResult,
  type SearchResponse,
} from "@/lib/api";
import { formatChars, sourceLabel } from "@/lib/format";

const SUGGESTIONS = ["向量检索的原理", "如何评估检索质量", "课程的写作流程"];

export default function KbPage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [sourceName, setSourceName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestResult | null>(null);
  const [uploadError, setUploadError] = useState("");

  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const maxScore = useMemo(() => {
    if (!searchResult?.citations.length) return 1;
    return Math.max(...searchResult.citations.map((item) => item.score), 0.0001);
  }, [searchResult]);

  const uploadFile = async (file?: File | null) => {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError("");
    setUploadResult(null);
    try {
      const result = await api.uploadKb(file, sourceName);
      setUploadResult(result);
      setSourceName("");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const runSearch = async () => {
    const text = query.trim();
    if (!text || searching) return;
    setSearching(true);
    setSearchError("");
    try {
      const result = await api.searchKb(text, topK);
      setSearchResult(result);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setSearching(false);
    }
  };

  const removeSource = async (citation: Citation) => {
    if (deleting) return;
    const confirmed = window.confirm(
      `删除来源「${citation.source_name}」的全部切片？该操作只影响知识库，不影响已生成的正文。`,
    );
    if (!confirmed) return;
    setDeleting(citation.source_id);
    setSearchError("");
    try {
      await api.deleteKbSource(citation.source_id);
      setSearchResult((prev) =>
        prev
          ? {
              ...prev,
              count: prev.citations.filter(
                (item) => item.source_id !== citation.source_id,
              ).length,
              citations: prev.citations.filter(
                (item) => item.source_id !== citation.source_id,
              ),
            }
          : prev,
      );
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-5">
      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass relative overflow-hidden rounded-[2rem] p-6 shadow-glass sm:p-8"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-indigo-400/25 to-violet-400/20 blur-3xl" />
        <div className="relative">
          <span className="chip">
            <Sparkles size={11} />
            RAG · 引用溯源
          </span>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[28px]">
            知识库：写作与追问的证据底座
          </h1>
          <p className="mt-2 max-w-2xl font-reading text-[15px] leading-relaxed text-slate-600 dark:text-slate-300">
            上传资料后会解析、分块并索引。生成正文与追问时只基于检索到的证据写作，每段带 [En] 引用标记，可 hover 查看来源。
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="chip-muted">API · {API_BASE}</span>
            <span className="chip-muted">支持 PDF / Markdown / docx / 文本</span>
          </div>
        </div>
      </motion.section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="glass rounded-3xl p-5 shadow-glass">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-indigo-500/12 text-indigo-600 dark:text-indigo-300">
              <Upload size={15} />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                上传资料
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                入库后即可被生成与追问引用
              </p>
            </div>
          </div>

          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              uploadFile(event.dataTransfer.files?.[0]);
            }}
            className={clsx(
              "mt-4 rounded-2xl border border-dashed px-4 py-8 text-center transition",
              dragOver
                ? "border-indigo-400 bg-indigo-500/10"
                : "border-slate-300/70 bg-white/35 dark:border-white/15 dark:bg-white/[0.03]",
            )}
          >
            <div className="brand-gradient mx-auto grid h-11 w-11 place-items-center rounded-2xl text-white shadow-brand">
              {uploading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <FileUp size={18} />
              )}
            </div>
            <p className="mt-3 text-[13px] font-medium text-slate-600 dark:text-slate-300">
              {uploading ? "正在解析并写入索引…" : "拖拽文件到此处，或选择本地文件"}
            </p>
            <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
              解析 → 分块 → 索引，完成后可直接检索测试
            </p>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={(event) => uploadFile(event.target.files?.[0])}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="btn btn-primary mt-4"
            >
              {uploading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              选择文件
            </button>
          </div>

          <div className="mt-3">
            <label className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              来源显示名（可选）
            </label>
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="例如：内部技术手册 v2"
              className="input"
            />
          </div>

          {uploadError && (
            <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-700 dark:text-rose-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span className="flex-1">{uploadError}</span>
            </div>
          )}

          <AnimatePresence>
            {uploadResult && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-3 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-3.5"
              >
                <p className="flex items-center gap-1.5 text-[12px] font-medium text-emerald-700 dark:text-emerald-300">
                  <Check size={13} />
                  已入库 · {uploadResult.source_name}
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-emerald-800/80 dark:text-emerald-200/80">
                  <span>解析器 · {uploadResult.parser}</span>
                  <span>{uploadResult.chunk_count} 个切片</span>
                  <span>{formatChars(uploadResult.char_count)}</span>
                  <span className="truncate">ID · {uploadResult.source_id}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setQuery(sourceName || uploadResult.source_name);
                    runSearch();
                  }}
                  className="btn-quiet mt-2 px-0"
                >
                  <Search size={12} />
                  用这个来源试检索
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        <section className="glass rounded-3xl p-5 shadow-glass">
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-violet-500/12 text-violet-600 dark:text-violet-300">
              <Search size={15} />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                检索测试
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                验证证据能否被生成流程命中
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_120px_auto]">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") runSearch();
              }}
              placeholder="输入一个问题或关键词…"
              className="input"
            />
            <select
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
              className="select"
            >
              {[3, 5, 8, 12].map((value) => (
                <option key={value} value={value}>
                  返回 {value} 条
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={runSearch}
              disabled={searching || !query.trim()}
              className="btn btn-primary"
            >
              {searching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Search size={14} />
              )}
              检索
            </button>
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setQuery(item)}
                className="rounded-full border border-slate-200/80 px-2.5 py-1 text-[10px] text-slate-500 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:text-slate-400 dark:hover:border-indigo-400/40 dark:hover:text-indigo-200"
              >
                {item}
              </button>
            ))}
          </div>

          {searchError && (
            <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-700 dark:text-rose-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span className="flex-1">{searchError}</span>
            </div>
          )}

          <div className="no-scrollbar mt-4 max-h-[calc(100vh-24rem)] space-y-2 overflow-y-auto pr-1">
            {searching ? (
              <div className="space-y-2">
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-20 animate-pulse rounded-2xl bg-slate-200/50 dark:bg-white/5"
                  />
                ))}
              </div>
            ) : searchResult ? (
              searchResult.citations.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300/70 px-4 py-10 text-center text-[11px] leading-relaxed text-slate-400 dark:border-white/15 dark:text-slate-500">
                  <X size={16} className="mx-auto mb-2 opacity-60" />
                  没有命中切片。换一个更具体的问法，或先上传相关资料。
                </div>
              ) : (
                <>
                  <p className="px-1 text-[11px] text-slate-400 dark:text-slate-500">
                    「{searchResult.query}」命中 {searchResult.count} 条证据
                  </p>
                  {searchResult.citations.map((citation) => (
                    <div
                      key={citation.chunk_id}
                      className="rounded-2xl border border-slate-200/70 bg-white/40 p-3 transition hover:border-indigo-300/60 hover:bg-white/70 dark:border-white/10 dark:bg-white/[0.03] dark:hover:border-indigo-400/30"
                    >
                      <div className="flex items-center gap-2">
                        <span className="truncate text-[11px] font-medium text-indigo-600 dark:text-indigo-300">
                          {sourceLabel(citation.source_name)}
                        </span>
                        <span className="chip-muted">#{citation.chunk_index}</span>
                        <span className="ml-auto text-[10px] text-slate-400">
                          {citation.score.toFixed(3)}
                        </span>
                        <button
                          type="button"
                          onClick={() => removeSource(citation)}
                          disabled={deleting === citation.source_id}
                          className="text-slate-300 transition hover:text-rose-500 dark:text-slate-600 dark:hover:text-rose-400"
                          aria-label="删除该来源"
                        >
                          {deleting === citation.source_id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Trash2 size={12} />
                          )}
                        </button>
                      </div>
                      <p className="mt-1.5 line-clamp-3 font-reading text-[12.5px] leading-relaxed text-slate-600 dark:text-slate-300">
                        {citation.snippet || citation.text}
                      </p>
                      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-200/70 dark:bg-white/10">
                        <div
                          className="brand-gradient h-full rounded-full"
                          style={{
                            width: `${Math.max(6, Math.min(100, (citation.score / maxScore) * 100))}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </>
              )
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-300/70 px-4 py-10 text-center text-[11px] leading-relaxed text-slate-400 dark:border-white/15 dark:text-slate-500">
                <Search size={16} className="mx-auto mb-2 opacity-60" />
                检索结果会显示来源、切片与匹配度，用于判断生成是否有据可依。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
