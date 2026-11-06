import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import {
  AlertTriangle,
  BookMarked,
  Check,
  ClipboardCheck,
  Layers,
  Loader2,
  Network,
  Pencil,
  RefreshCw,
  Sparkles,
  Waypoints,
  X,
} from "lucide-react";
import {
  ApiError,
  api,
  type Blueprint,
  type GenerationMode,
  type GlossaryTerm,
  type Lesson,
} from "@/lib/api";
import { formatRelative, modeLabel } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import ModePicker from "@/components/course/ModePicker";
import type { VersionConflict } from "@/components/course/ConflictDialog";
import LearningPathTimeline from "@/components/blueprint/LearningPathTimeline";
import GlossaryGrid from "@/components/blueprint/GlossaryGrid";

type BlueprintBoardProps = {
  courseId: string;
  lessons: Lesson[];
  reloadKey: number;
  onOpenLesson: (lessonId: string) => void;
  onLessonsChanged: () => Promise<void>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  onProgressRefresh: () => void;
  onVersionConflict?: (conflict: VersionConflict) => void;
};

export default function BlueprintBoard({
  courseId,
  lessons,
  reloadKey,
  onOpenLesson,
  onLessonsChanged,
  onNotice,
  onError,
  onProgressRefresh,
  onVersionConflict,
}: BlueprintBoardProps) {
  const { can } = useSession();
  const readOnly = !can("write");
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<GenerationMode>("strict");
  const [focus, setFocus] = useState("");
  const [topK, setTopK] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [conflict, setConflict] = useState("");
  const [applying, setApplying] = useState(false);
  const [editingGlossary, setEditingGlossary] = useState(false);
  const [savingGlossary, setSavingGlossary] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const data = await api.getBlueprint(courseId);
      setBlueprint(data.exists ? data.blueprint : null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "蓝图加载失败");
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const lessonTitleMap = useMemo(() => {
    const map = new Map<string, string>();
    lessons.forEach((lesson) => map.set(lesson.id, lesson.title));
    return map;
  }, [lessons]);

  const blueprintVersion = blueprint?.version ?? null;

  const boundCount = useMemo(
    () => blueprint?.outline.filter((node) => node.lesson_id).length ?? 0,
    [blueprint],
  );

  const runGenerate = useCallback(
    async (overrideMode?: GenerationMode, expectedVersion?: number) => {
      const useMode = overrideMode ?? mode;
      const baseline = expectedVersion ?? blueprintVersion;
      setGenerating(true);
      setConflict("");
      onError("");
      try {
        const result = await api.generateBlueprint(courseId, {
          mode: useMode,
          top_k: topK,
          focus: focus.trim(),
          expected_version: baseline,
        });
        setBlueprint(result);
        setRegenerateOpen(false);
        onNotice(
          result.mode === "loose"
            ? "蓝图已生成 · 非严格模式，内容由大模型规划，请核对"
            : `蓝图已生成 v${result.version} · 引用知识库证据`,
        );
        onProgressRefresh();
      } catch (err) {
        const info = err instanceof ApiError ? err.conflict() : null;
        if (info && info.current_version !== undefined && onVersionConflict) {
          const current = info.current_version;
          onVersionConflict({
            expectedVersion: baseline ?? 0,
            currentVersion: current,
            label: "蓝图",
            retry: () => runGenerate(useMode, current),
          });
        } else if (err instanceof ApiError && err.status === 409) {
          setConflict(err.message);
        } else {
          onError(err instanceof Error ? err.message : "蓝图生成失败");
        }
      } finally {
        setGenerating(false);
      }
    },
    [
      blueprintVersion,
      courseId,
      focus,
      mode,
      onError,
      onNotice,
      onProgressRefresh,
      onVersionConflict,
      topK,
    ],
  );

  const handleApply = async () => {
    setApplying(true);
    onError("");
    try {
      const result = await api.applyBlueprint(courseId);
      setBlueprint(result.blueprint);
      onNotice(
        result.created_count > 0
          ? `已应用蓝图：新建 ${result.created_count} 讲`
          : "蓝图已应用：所有节点都已绑定讲次",
      );
      await onLessonsChanged();
      onProgressRefresh();
    } catch (err) {
      onError(err instanceof Error ? err.message : "应用蓝图失败");
    } finally {
      setApplying(false);
    }
  };

  const handleSaveGlossary = async (terms: GlossaryTerm[]) => {
    setSavingGlossary(true);
    onError("");
    try {
      const payload = await api.saveGlossary(courseId, terms);
      setBlueprint((prev) =>
        prev ? { ...prev, glossary: payload.glossary } : prev,
      );
      setEditingGlossary(false);
      onNotice(`术语表已保存 · ${payload.count} 个术语`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "术语表保存失败");
    } finally {
      setSavingGlossary(false);
    }
  };

  const generatePanel = (
    <div className="rounded-2xl border border-indigo-200/60 bg-indigo-500/5 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-indigo-600 dark:text-indigo-300">
          {mode === "loose"
            ? "非严格模式：允许模型自由规划，规划结果会标注由大模型编写"
            : "严格模式：先检索知识库证据，无证据时拒绝生成并提示资料不足"}
        </p>
        <span className="chip-muted">规划模式</span>
      </div>
      <div className="mt-3">
        <ModePicker value={mode} onChange={setMode} disabled={generating} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_120px_auto]">
        <input
          value={focus}
          onChange={(event) => setFocus(event.target.value)}
          placeholder="聚焦方向，如：只覆盖索引调优与量化"
          className="input"
        />
        <select
          value={topK}
          onChange={(event) => setTopK(Number(event.target.value))}
          className="select"
        >
          {[3, 5, 8, 12].map((value) => (
            <option key={value} value={value}>
              证据 {value} 条
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void runGenerate()}
          disabled={readOnly || generating}
          title={readOnly ? "当前角色只读" : ""}
          className="btn btn-primary"
        >
          {generating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Sparkles size={14} />
          )}
          生成蓝图
        </button>
      </div>
    </div>
  );

  const conflictBar = conflict ? (
    <div className="flex flex-wrap items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/15 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <span className="min-w-0 flex-1 whitespace-pre-line">{conflict}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => {
            setMode("loose");
            void runGenerate("loose");
          }}
          disabled={generating}
          className="btn btn-ghost !px-2.5 !py-1 text-[10.5px]"
        >
          {generating ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <RefreshCw size={11} />
          )}
          改用非严格模式重试
        </button>
        <button
          type="button"
          onClick={() => setConflict("")}
          className="grid h-6 w-6 place-items-center rounded-full text-amber-600/70 transition hover:bg-amber-500/15 hover:text-amber-700 dark:text-amber-300/70"
          aria-label="关闭提示"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  ) : null;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="glass h-40 animate-pulse rounded-3xl" />
        <div className="glass h-72 animate-pulse rounded-3xl" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="glass rounded-3xl p-8 text-center shadow-glass">
        <div className="mx-auto grid h-11 w-11 place-items-center rounded-2xl bg-rose-500/10 text-rose-500">
          <AlertTriangle size={18} />
        </div>
        <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
          蓝图无法加载
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {loadError}
        </p>
        <button type="button" onClick={() => void load()} className="btn btn-ghost mt-4">
          <RefreshCw size={13} />
          重试
        </button>
      </div>
    );
  }

  if (!blueprint) {
    return (
      <div className="space-y-4">
        <div className="glass rounded-3xl p-6 shadow-glass sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="brand-gradient grid h-9 w-9 place-items-center rounded-2xl text-white shadow-brand">
                  <Waypoints size={16} />
                </span>
                <div>
                  <p className="text-[15px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
                    还没有系列蓝图
                  </p>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    先生成一份学习路径蓝图，再逐讲审核与阅读
                  </p>
                </div>
              </div>
              <p className="mt-3 max-w-xl text-[12.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                蓝图会基于知识库证据规划学习阶段、大纲节点与术语表；生成后可以逐节点审阅、应用到系列，再回到阅读视图逐讲生成正文。
              </p>
            </div>
            <span className="chip-muted">{lessons.length} 个现有讲次</span>
          </div>

          <div className="mt-5 space-y-3">
            {conflictBar}
            {generatePanel}
          </div>
        </div>
      </div>
    );
  }

  const loose = blueprint.mode === "loose";

  return (
    <div className="space-y-4">
      <div className="glass rounded-3xl p-5 shadow-glass sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip">
                <Network size={11} />
                系列蓝图
              </span>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                  loose
                    ? "bg-amber-400/20 text-amber-700 ring-amber-400/30 dark:bg-amber-300/12 dark:text-amber-300 dark:ring-amber-300/20"
                    : "bg-indigo-500/12 text-indigo-600 ring-indigo-400/25 dark:bg-indigo-400/14 dark:text-indigo-300 dark:ring-indigo-300/25",
                )}
              >
                {modeLabel(blueprint.mode)}模式
              </span>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium ring-1",
                  blueprint.grounded
                    ? "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25"
                    : "bg-slate-400/15 text-slate-600 ring-slate-400/25 dark:bg-white/10 dark:text-slate-300 dark:ring-white/15",
                )}
              >
                {blueprint.grounded ? "有据可依" : "暂无证据"}
              </span>
              <span className="chip-muted">v{blueprint.version}</span>
              {blueprint.provider ? (
                <span className="chip-muted">{blueprint.provider}</span>
              ) : null}
              <span className="chip-muted">
                更新于 {formatRelative(blueprint.updated_at)}
              </span>
            </div>
            <div className="mt-3 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300 [&_p+p]:mt-2 [&_p]:leading-relaxed [&_strong]:font-semibold [&_strong]:text-slate-800 dark:[&_strong]:text-slate-100 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5">
              {blueprint.overview ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {blueprint.overview}
                </ReactMarkdown>
              ) : (
                <p className="text-slate-400 dark:text-slate-500">
                  这份蓝图还没有总览说明。
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {[
            {
              icon: Layers,
              label: "学习阶段",
              value: blueprint.learning_path.length,
            },
            { icon: Waypoints, label: "大纲节点", value: blueprint.outline.length },
            { icon: ClipboardCheck, label: "已绑定讲次", value: boundCount },
            { icon: BookMarked, label: "术语", value: blueprint.glossary.length },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-slate-200/70 bg-white/50 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
                <item.icon size={11} />
                {item.label}
              </p>
              <p className="mt-0.5 text-[17px] font-semibold text-slate-800 dark:text-slate-100">
                {item.value}
              </p>
            </div>
          ))}
        </div>

        {blueprint.warning || loose || !blueprint.grounded ? (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/12 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              {blueprint.warning
                ? blueprint.warning
                : loose
                  ? "本蓝图由大模型在非严格模式下规划，未逐条校验知识库证据，请人工核对后再应用。"
                  : "本蓝图未取得知识库证据，节点与阶段来自模型推断，请补充资料后重新生成。"}
            </span>
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-200/70 pt-3.5 dark:border-white/10">
          <button
            type="button"
            onClick={() => void handleApply()}
            disabled={readOnly || applying}
            title={readOnly ? "当前角色只读" : ""}
            className="btn btn-primary"
          >
            {applying ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            应用到系列
          </button>
          <button
            type="button"
            onClick={() => setRegenerateOpen((value) => !value)}
            disabled={readOnly || generating}
            title={readOnly ? "当前角色只读" : ""}
            className="btn btn-ghost"
          >
            {generating ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            重新生成
          </button>
          <button
            type="button"
            onClick={() => setEditingGlossary((value) => !value)}
            disabled={readOnly}
            title={readOnly ? "当前角色只读" : ""}
            className="btn btn-ghost"
          >
            <Pencil size={14} />
            {editingGlossary ? "退出编辑" : "编辑术语表"}
          </button>
          <span className="ml-auto text-[10.5px] text-slate-400 dark:text-slate-500">
            应用只会补齐未绑定的节点，不会覆盖已有正文
          </span>
        </div>

        <AnimatePresence initial={false}>
          {(regenerateOpen || conflict) && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.22 }}
              className="overflow-hidden"
            >
              <div className="mt-3 space-y-2.5">
                {conflictBar}
                {regenerateOpen ? generatePanel : null}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
          <div className="flex items-center justify-between px-1">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              <Waypoints size={12} />
              学习路径
            </p>
            <span className="chip-muted">
              {blueprint.learning_path.length} 阶段 · {blueprint.outline.length}{" "}
              节点
            </span>
          </div>
          <div className="mt-3">
            <LearningPathTimeline
              blueprint={blueprint}
              onOpenLesson={onOpenLesson}
            />
          </div>
        </div>

        <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
          <div className="flex items-center justify-between px-1">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
              <BookMarked size={12} />
              术语表
            </p>
            <span className="chip-muted">{blueprint.glossary.length} 条</span>
          </div>
          <div className="mt-3">
            <GlossaryGrid
              glossary={blueprint.glossary}
              editing={editingGlossary}
              saving={savingGlossary}
              onSave={(terms) => void handleSaveGlossary(terms)}
              onCancel={() => setEditingGlossary(false)}
            />
          </div>
          {!editingGlossary && blueprint.glossary.length > 0 ? (
            <p className="mt-2 px-1 text-[10px] text-slate-400 dark:text-slate-500">
              共 {blueprint.glossary.length} 条术语，相关讲次：
              {Array.from(
                new Set(
                  blueprint.glossary.flatMap((term) =>
                    term.node_ids
                      .map((nodeId) => {
                        const node = blueprint.outline.find(
                          (item) => item.id === nodeId,
                        );
                        return node?.lesson_id
                          ? lessonTitleMap.get(node.lesson_id) ?? ""
                          : "";
                      })
                      .filter(Boolean),
                  ),
                ),
              )
                .slice(0, 3)
                .join("、") || "暂无"}
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => onOpenLesson(lessons[0]?.id ?? "")}
          disabled={!lessons[0]?.id}
          className="btn-quiet"
        >
          回到阅读视图
        </button>
      </div>
    </div>
  );
}
