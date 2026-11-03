import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Check,
  CircleSlash,
  Loader2,
  MessageSquareWarning,
  Send,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type CourseProgress,
  type Lesson,
  type LessonReview,
} from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";

type ReviewControlsProps = {
  lesson: Lesson;
  progress: CourseProgress | null;
  onReviewed: () => Promise<void> | void;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
  locked?: boolean;
  lockedReason?: string;
};

export default function ReviewControls({
  lesson,
  progress,
  onReviewed,
  onNotice,
  onError,
  locked = false,
  lockedReason = "",
}: ReviewControlsProps) {
  const { can } = useSession();
  const readOnly = !can("review");
  const writeTitle = readOnly
    ? "当前角色只读"
    : locked
      ? lockedReason || "该讲正被他人编辑"
      : "";
  const writeBlocked = readOnly || locked;
  const [reviews, setReviews] = useState<LessonReview[]>([]);
  const [busy, setBusy] = useState<"approve" | "request_revision" | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [reviewsLoading, setReviewsLoading] = useState(false);

  const loadReviews = useCallback(async () => {
    setReviewsLoading(true);
    try {
      const data = await api.listLessonReviews(lesson.id);
      setReviews(data.reviews);
    } catch {
      setReviews([]);
    } finally {
      setReviewsLoading(false);
    }
  }, [lesson.id]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews, lesson.status, lesson.current_version]);

  const hasContent = Boolean(lesson.content);
  const total = progress?.total ?? 0;
  const approved = progress?.approved ?? 0;
  const ratio = total > 0 ? Math.round((approved / total) * 100) : 0;
  const latest = reviews[0];

  const submit = async (action: "approve" | "request_revision") => {
    if (writeBlocked) return;
    setBusy(action);
    onError("");
    try {
      await api.reviewLesson(
        lesson.id,
        action,
        action === "request_revision" ? note.trim() : "",
      );
      setNote("");
      setNoteOpen(false);
      onNotice(
        action === "approve"
          ? `已通过《${lesson.title}》审核`
          : `已退回《${lesson.title}》并要求修改`,
      );
      await loadReviews();
      await onReviewed();
    } catch (err) {
      onError(err instanceof Error ? err.message : "审核操作失败");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mt-4 rounded-2xl border border-slate-200/70 bg-white/45 p-3.5 dark:border-white/10 dark:bg-white/[0.04]">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <div className="h-1.5 min-w-[80px] flex-1 overflow-hidden rounded-full bg-slate-200/80 dark:bg-white/10">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${ratio}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className="brand-gradient h-full rounded-full"
            />
          </div>
          <span className="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            已通过 {approved}/{total || 0}
          </span>
          {progress ? (
            <span className="hidden shrink-0 text-[10px] text-slate-400 dark:text-slate-500 sm:inline">
              待审核 {progress.pending_review}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => void submit("approve")}
            disabled={writeBlocked || !hasContent || busy !== null}
            title={
              writeTitle ||
              (hasContent ? "通过本讲审核" : "先生成本讲正文再审核")
            }
            className={clsx(
              "inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[11.5px] font-medium ring-1 transition",
              hasContent
                ? "bg-emerald-500/14 text-emerald-700 ring-emerald-500/30 hover:bg-emerald-500/22 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25 dark:hover:bg-emerald-400/22"
                : "cursor-not-allowed bg-slate-200/50 text-slate-400 ring-slate-300/40 dark:bg-white/5 dark:text-slate-500 dark:ring-white/10",
            )}
          >
            {busy === "approve" ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Check size={12} />
            )}
            通过审核
          </button>
          <button
            type="button"
            onClick={() => setNoteOpen((value) => !value)}
            disabled={writeBlocked || busy !== null}
            title={writeTitle}
            className="inline-flex items-center gap-1 rounded-full bg-amber-400/18 px-3 py-1.5 text-[11.5px] font-medium text-amber-700 ring-1 ring-amber-500/30 transition hover:bg-amber-400/26 disabled:opacity-50 dark:bg-amber-300/14 dark:text-amber-300 dark:ring-amber-300/25 dark:hover:bg-amber-300/20"
          >
            <MessageSquareWarning size={12} />
            退回修改
          </button>
        </div>
      </div>

      {!hasContent ? (
        <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
          <CircleSlash size={11} />
          这一讲还没有正文，「通过审核」暂时不可用。
        </p>
      ) : null}

      <AnimatePresence initial={false}>
        {noteOpen ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2.5 space-y-2 rounded-2xl border border-amber-400/35 bg-amber-400/10 p-2.5 dark:border-amber-300/20 dark:bg-amber-300/[0.07]">
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder="修改意见（可选）：哪一段要补证据、哪里需要重写"
                className="input resize-none text-[12px] leading-relaxed"
              />
              <div className="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setNoteOpen(false);
                    setNote("");
                  }}
                  className="btn-quiet"
                >
                  <X size={11} />
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void submit("request_revision")}
                  disabled={writeBlocked || busy !== null}
                  title={writeTitle}
                  className="btn btn-primary !px-3 !py-1.5 text-[11px]"
                >
                  {busy === "request_revision" ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Send size={12} />
                  )}
                  确认退回
                </button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {lesson.status === "needs_revision" ? (
        <div className="mt-2.5 flex items-start gap-2 rounded-2xl border border-amber-400/40 bg-amber-400/12 px-3 py-2 text-[11px] leading-relaxed text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-200">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span className="min-w-0">
            <span className="font-semibold">待修改</span>
            {reviewsLoading ? (
              <span className="ml-1.5 text-amber-600/70 dark:text-amber-300/70">
                正在读取最近意见…
              </span>
            ) : latest?.note ? (
              <span className="ml-1.5">
                · {latest.note}
                <span className="ml-1 text-[10px] text-amber-600/70 dark:text-amber-300/60">
                  （{formatRelative(latest.created_at)}）
                </span>
              </span>
            ) : (
              <span className="ml-1.5">· 尚未填写具体修改意见</span>
            )}
          </span>
        </div>
      ) : null}

      {lesson.status === "approved" ? (
        <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-emerald-600 dark:text-emerald-400">
          <Check size={11} />
          本讲已通过审核
          {latest?.created_at ? ` · ${formatRelative(latest.created_at)}` : ""}
        </p>
      ) : null}
    </div>
  );
}
