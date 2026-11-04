import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BookOpen,
  ChevronDown,
  Clock3,
  Eye,
  FileText,
  GitCompare,
  History,
  Layers,
  ImagePlus,
  Loader2,
  PenLine,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Share2,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  ApiError,
  api,
  type GenerationMode,
  type Longform,
  type LongformVersion,
} from "@/lib/api";
import { cancelJob, runJob } from "@/lib/jobs";
import { contentLength, formatChars, formatDateTime } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import VersionDiffDialog from "@/components/reader/VersionDiffDialog";
import VersionPreviewDialog from "@/components/reader/VersionPreviewDialog";
import { useSession } from "@/components/auth/SessionProvider";
import SharePanel, { type ShareMember } from "@/components/sharing/SharePanel";
import ExportMenu from "@/components/export/ExportMenu";
import ImagePickerDrawer from "@/components/media/ImagePickerDrawer";
import {
  ConfirmDialog,
  Modal,
  PromptDialog,
  RowMenu,
} from "@/components/common/Dialogs";

const GENRE_LABELS: Record<string, string> = {
  article: "文章",
  report: "报告",
  essay: "随笔",
  tutorial: "教程",
  custom: "自定义",
};

function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  const startedRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return;
    }
    startedRef.current = Date.now();
    setSeconds(0);
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [active]);

  return seconds;
}

export default function LongformEditorPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { can, roleName, tenant } = useSession();
  const writable = can("write");

  const [longform, setLongform] = useState<Longform | null>(null);
  const [versions, setVersions] = useState<LongformVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [busy, setBusy] = useState("");
  const [jobProgress, setJobProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const elapsed = useElapsed(Boolean(busy));

  const [outlineOpen, setOutlineOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [previewVersion, setPreviewVersion] = useState<number | null>(null);
  const [versionDiffOpen, setVersionDiffOpen] = useState(false);
  const [versionDiffAnchor, setVersionDiffAnchor] = useState<number | null>(null);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [rewriteMode, setRewriteMode] = useState<GenerationMode>("loose");

  const [shareOpen, setShareOpen] = useState(false);
  const [shareMembers, setShareMembers] = useState<ShareMember[]>([]);
  const [shareLevels, setShareLevels] = useState<Record<string, string | null>>({});
  const [shareLoading, setShareLoading] = useState(false);
  const [shareSaving, setShareSaving] = useState(false);
  const [shareError, setShareError] = useState("");
  const [pickOpen, setPickOpen] = useState(false);

  const [titleEditOpen, setTitleEditOpen] = useState(false);
  const [targetEditOpen, setTargetEditOpen] = useState(false);
  const [sectionRename, setSectionRename] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [sectionForm, setSectionForm] = useState<{
    id: string;
    title: string;
    summary: string;
    targetWords: number;
    content: string;
  } | null>(null);
  const [sectionCreate, setSectionCreate] = useState<{
    afterId: string | null;
    title: string;
    summary: string;
    targetWords: number;
  } | null>(null);
  const [sectionDelete, setSectionDelete] = useState<{ id: string; title: string } | null>(
    null,
  );
  const [manualOpen, setManualOpen] = useState(false);
  const [manualText, setManualText] = useState("");
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const canShare = can("manage_members");

  const openShare = useCallback(async () => {
    if (!id) return;
    setShareOpen(true);
    setShareLoading(true);
    setShareError("");
    try {
      const [memberList, grantList] = await Promise.all([
        tenant ? api.listMembers(tenant) : Promise.resolve({ count: 0, members: [] }),
        api.getLongformGrants(id),
      ]);
      setShareMembers(
        (memberList.members ?? []).map((member) => ({
          user_id: member.user_id,
          user_email: member.user_email,
          user_display_name: member.user_display_name,
          avatar_url: member.avatar_url,
          note: "空间成员",
        })),
      );
      const next: Record<string, string | null> = {};
      for (const member of memberList.members ?? []) next[member.user_id] = null;
      for (const grant of grantList.grants ?? []) {
        next[grant.user_id] = grant.level === "write" ? "write" : "read";
      }
      setShareLevels(next);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : "共享信息加载失败");
    } finally {
      setShareLoading(false);
    }
  }, [id, tenant]);

  const saveShare = useCallback(
    async (entries: { user_id: string; level: string }[]) => {
      if (!id) return;
      setShareSaving(true);
      setShareError("");
      try {
        await api.saveLongformGrants(id, entries);
        setNotice("共享权限已保存");
        setShareOpen(false);
      } catch (err) {
        setShareError(err instanceof Error ? err.message : "保存失败");
      } finally {
        setShareSaving(false);
      }
    },
    [id],
  );

  const contentRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!id) return;
      if (!quiet) setLoading(true);
      try {
        const [detail, versionData] = await Promise.all([
          api.getLongform(id),
          api.listLongformVersions(id),
        ]);
        setLongform(detail);
        setVersions(versionData.versions);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载长篇失败");
      } finally {
        setLoading(false);
      }
    },
    [id],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const words = useMemo(
    () => (longform?.content ? contentLength(longform.content) : 0),
    [longform],
  );

  const generateAll = async () => {
    if (!longform || busy) return;
    if (!writable) {
      setError("当前角色只读，无法生成正文");
      return;
    }
    setBusy("all");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Longform | null = null;
      try {
        await runJob(
          "longform_generate",
          { longform_id: longform.id },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getLongform(longform.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.generateLongform(longform.id, {
          mode: (longform.last_mode as GenerationMode) || "loose",
          expected_version: longform.current_version,
        });
      }
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(`全文已生成 · ${seconds} 秒 · v${updated.current_version}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const generateOne = async (sectionId: string) => {
    if (!longform || busy) return;
    if (!writable) {
      setError("当前角色只读，无法生成章节");
      return;
    }
    setBusy(sectionId);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      const result = await api.generateSection(longform.id, sectionId, {
        mode: (longform.last_mode as GenerationMode) || "loose",
      });
      setLongform(result.longform);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(`本节已生成 · ${seconds} 秒`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成章节失败");
    } finally {
      setBusy("");
    }
  };

  const submitRewrite = async () => {
    const text = instruction.trim();
    if (!longform || !text || busy) return;
    if (!writable) {
      setError("当前角色只读，无法重写正文");
      return;
    }
    setBusy("rewrite");
    setJobProgress(0);
    setJobId(null);
    setError("");
    setNotice("");
    const startedAt = Date.now();
    try {
      let updated: Longform | null = null;
      try {
        await runJob(
          "longform_rewrite",
          { longform_id: longform.id, instruction: text },
          {
            onProgress: setJobProgress,
            onJob: (created) => setJobId(created.id),
          },
        );
        updated = await api.getLongform(longform.id);
      } catch (queueErr) {
        const queueable =
          queueErr instanceof ApiError &&
          (queueErr.status === 400 || queueErr.status === 404 || queueErr.status === 422);
        if (!queueable) throw queueErr;
        updated = await api.rewriteLongform(longform.id, {
          instruction: text,
          mode: rewriteMode,
          expected_version: longform.current_version,
        });
      }
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setRewriteOpen(false);
      setInstruction("");
      const seconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      setNotice(`重写完成 · ${seconds} 秒 · v${updated.current_version}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重写失败");
    } finally {
      setBusy("");
      setJobId(null);
    }
  };

  const cancelActive = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
      setNotice("已请求取消任务");
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消失败");
    }
  };

  const openVersionDiff = (version: number) => {
    setVersionDiffAnchor(version);
    setVersionDiffOpen(true);
  };

  const loadVersionPreview = async (version: number) => {
    const detail = await api.getLongformVersion(id, version);
    return {
      content: detail.version.content ?? "",
      citations: detail.version.citations ?? [],
    };
  };

  const fetchVersionDiff = async (from: number, to: number) => {
    return api.diffLongformVersions(id, from, to);
  };

  const revert = async (version: number) => {
    if (!longform || busy) return;
    if (!writable) return;
    const confirmed = window.confirm(`回滚到 v${version}？回滚会生成一个新的版本记录。`);
    if (!confirmed) return;
    setBusy(`revert-${version}`);
    setError("");
    try {
      const updated = await api.revertLongform(longform.id, version);
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setNotice(`已回滚到 v${version}（当前 v${updated.current_version}）`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "回滚失败");
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    if (!longform || !writable) return;
    const confirmed = window.confirm(`删除长篇「${longform.title}」？该操作不可撤销。`);
    if (!confirmed) return;
    try {
      await api.deleteLongform(longform.id);
      navigate("/longforms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const scrollToSection = (title: string) => {
    const root = contentRef.current;
    if (!root || !title) return;
    const headings = Array.from(root.querySelectorAll("h1,h2,h3,h4"));
    const target = headings.find((node) =>
      (node.textContent ?? "").includes(title.slice(0, 12)),
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      root.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setOutlineOpen(false);
  };

  const openManual = () => {
    if (!longform) return;
    setDialogError("");
    setManualText(longform.content ?? "");
    setManualOpen(true);
  };

  const saveManual = async () => {
    if (!longform) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.saveLongformContent(longform.id, {
        content: manualText,
        note: "手动编辑",
        expected_version: longform.current_version,
      });
      setLongform(updated);
      const versionData = await api.listLongformVersions(longform.id);
      setVersions(versionData.versions);
      setManualOpen(false);
      setNotice(`已保存为 v${updated.current_version}`);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTitle = async (value: string) => {
    if (!longform) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongform(longform.id, { title: value });
      setLongform(updated);
      setTitleEditOpen(false);
      setNotice("标题已更新");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "更新失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const saveTargetWords = async (value: string) => {
    if (!longform) return;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setDialogError("请输入大于 0 的目标字数");
      return;
    }
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongform(longform.id, {
        target_words: Math.round(parsed),
      });
      setLongform(updated);
      setTargetEditOpen(false);
      setNotice("目标字数已更新");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "更新失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const renameSection = async (value: string) => {
    if (!longform || !sectionRename) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongformSection(longform.id, sectionRename.id, {
        title: value,
      });
      setLongform(updated);
      setSectionRename(null);
      setNotice("章节已重命名");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "重命名失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const saveSectionForm = async () => {
    if (!longform || !sectionForm) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.updateLongformSection(longform.id, sectionForm.id, {
        title: sectionForm.title.trim(),
        summary: sectionForm.summary,
        target_words: Number(sectionForm.targetWords) || 0,
        content: sectionForm.content,
      });
      setLongform(updated);
      setSectionForm(null);
      setNotice("章节内容已保存");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const createSection = async () => {
    if (!longform || !sectionCreate) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const result = await api.createLongformSection(longform.id, {
        title: sectionCreate.title.trim(),
        summary: sectionCreate.summary,
        target_words: Number(sectionCreate.targetWords) || 0,
        after_id: sectionCreate.afterId,
      });
      setLongform(result.longform);
      setSectionCreate(null);
      setNotice("已新增章节");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "新增失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const deleteSection = async () => {
    if (!longform || !sectionDelete) return;
    setDialogBusy(true);
    setDialogError("");
    try {
      const updated = await api.deleteLongformSection(longform.id, sectionDelete.id);
      setLongform(updated);
      setSectionDelete(null);
      setNotice("章节已删除");
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDialogBusy(false);
    }
  };

  const moveSection = async (sectionId: string, direction: -1 | 1) => {
    if (!longform) return;
    const ids = longform.outline.map((section) => section.id);
    const index = ids.indexOf(sectionId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    next[index] = ids[target];
    next[target] = ids[index];
    try {
      const updated = await api.reorderLongformSections(longform.id, next);
      setLongform(updated);
      setNotice("章节顺序已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "排序失败");
    }
  };

  const sectionMenuItems = (sectionId: string, sectionTitle: string, index: number) => [
    {
      label: "重命名",
      icon: <Pencil size={11} />,
      onClick: () => {
        setDialogError("");
        setSectionRename({ id: sectionId, title: sectionTitle });
      },
    },
    {
      label: "编辑目录信息 / 正文",
      icon: <FileText size={11} />,
      onClick: () => {
        const target = longform?.outline.find((item) => item.id === sectionId);
        if (!target) return;
        setDialogError("");
        setSectionForm({
          id: target.id,
          title: target.title,
          summary: target.summary ?? "",
          targetWords: target.target_words ?? 0,
          content: target.content ?? "",
        });
      },
    },
    {
      label: "在下方加一节",
      icon: <Plus size={11} />,
      onClick: () => {
        setDialogError("");
        setSectionCreate({
          afterId: sectionId,
          title: "",
          summary: "",
          targetWords: 400,
        });
      },
    },
    {
      label: "上移",
      icon: <ArrowUp size={11} />,
      disabled: index === 0,
      onClick: () => void moveSection(sectionId, -1),
    },
    {
      label: "下移",
      icon: <ArrowDown size={11} />,
      disabled: index === (longform?.outline.length ?? 0) - 1,
      onClick: () => void moveSection(sectionId, 1),
    },
    {
      label: "删除本节",
      icon: <Trash2 size={11} />,
      danger: true,
      onClick: () => {
        setDialogError("");
        setSectionDelete({ id: sectionId, title: sectionTitle });
      },
    },
  ];

  if (loading) {    return (
      <div className="glass grid place-items-center rounded-3xl p-16 shadow-glass">
        <Loader2 size={20} className="animate-spin text-indigo-500" />
      </div>
    );
  }

  if (!longform) {
    return (
      <div className="glass rounded-3xl p-10 text-center shadow-glass">
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
          长篇不存在或已被删除
        </p>
        {error ? (
          <p className="mt-2 break-words text-xs text-rose-600 dark:text-rose-300">{error}</p>
        ) : null}
        <Link to="/longforms" className="btn btn-quiet mx-auto mt-4">
          <ArrowLeft size={13} />
          返回长篇列表
        </Link>
      </div>
    );
  }

  const modeText = longform.last_mode === "loose" ? "非严格" : "严格";
  const progress = longform.target_words
    ? Math.min(100, Math.round((words / longform.target_words) * 100))
    : 0;

  return (
    <div className="space-y-4">
      <div className="glass rounded-3xl p-4 shadow-glass sm:p-5">
        <div className="flex flex-wrap items-start gap-3">
          <Link
            to="/longforms"
            className="btn-quiet grid h-9 w-9 shrink-0 place-items-center rounded-full"
            title="返回列表"
          >
            <ArrowLeft size={15} />
          </Link>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip">{GENRE_LABELS[longform.profile?.genre ?? ""] ?? "文章"}</span>
              <span
                className={clsx(
                  "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1",
                  longform.last_mode === "loose"
                    ? "bg-amber-400/20 text-amber-700 ring-amber-500/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25"
                    : "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25",
                )}
              >
                {modeText}
              </span>
              <span className="chip-muted">v{longform.current_version}</span>
              <span className="chip-muted">{longform.outline.length} 节</span>
            </div>
            <h1 className="mt-2 flex items-center gap-1.5 text-lg font-semibold tracking-tight text-slate-800 dark:text-slate-100 sm:text-xl">
              <span className="min-w-0 break-words">{longform.title}</span>
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setTitleEditOpen(true);
                  }}
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                  aria-label="编辑标题"
                >
                  <Pencil size={13} />
                </button>
              ) : null}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="tabular-nums">
                {formatChars(words)} / 目标 {formatChars(longform.target_words)}
              </span>
              {writable ? (
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setTargetEditOpen(true);
                  }}
                  className="rounded-full px-1.5 py-0.5 text-[10px] text-indigo-600 transition hover:bg-indigo-500/10 dark:text-indigo-300"
                >
                  改目标
                </button>
              ) : null}
              <span className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-500/15 dark:bg-white/10">
                <span
                  className="block h-full brand-gradient transition-all"
                  style={{ width: `${progress}%` }}
                />
              </span>
              <span>{progress}%</span>
              <span className="text-slate-400 dark:text-slate-500">
                更新 {formatDateTime(longform.updated_at || longform.created_at)}
              </span>
            </div>
          </div>

          <div className="no-scrollbar flex w-full shrink-0 items-center gap-2 overflow-x-auto lg:w-auto">
            <button
              type="button"
              onClick={generateAll}
              disabled={Boolean(busy) || !writable}
              className="btn btn-primary whitespace-nowrap"
              title={!writable ? "当前角色只读" : undefined}
            >
              {busy === "all" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Play size={13} />
              )}
              全文生成
            </button>
            <a
              href={`/read/longform/${longform.id}`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-quiet whitespace-nowrap"
              title="在新标签页打开独立阅读模式"
            >
              <BookOpen size={13} />
              阅读模式
            </a>
            <button
              type="button"
              onClick={() => setRewriteOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? "当前角色只读" : undefined}
            >
              <Wand2 size={13} />
              重写
            </button>
            <button
              type="button"
              onClick={() => void openShare()}
              disabled={!canShare}
              className="btn btn-quiet whitespace-nowrap"
              title={canShare ? "共享给空间成员" : "需要成员管理权限"}
            >
              <Share2 size={13} />
              共享
            </button>
            <button
              type="button"
              onClick={openManual}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? "当前角色只读" : "手动编辑整篇 Markdown"}
            >
              <PenLine size={13} />
              手动编辑整篇
            </button>
            <button
              type="button"
              onClick={() => setPickOpen(true)}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap"
              title={!writable ? "当前角色只读" : "从图片库插入图片到章节末尾"}
            >
              <ImagePlus size={13} />
              插入图片
            </button>
            <ExportMenu
              sourceType="longform"
              sourceId={longform.id}
              fallbackName={longform.title}
            />
            <button
              type="button"
              onClick={() => void load(true)}
              disabled={Boolean(busy)}
              className="btn btn-quiet whitespace-nowrap"
            >
              <RotateCcw size={13} />
              刷新
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={Boolean(busy) || !writable}
              className="btn btn-quiet whitespace-nowrap text-rose-600 dark:text-rose-300"
            >
              <X size={13} />
              删除
            </button>
          </div>
        </div>

        {busy ? (
          <div className="mt-3 rounded-2xl border border-indigo-300/40 bg-indigo-50/60 px-4 py-2.5 text-xs text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-400/10 dark:text-indigo-200">
            <span className="flex items-center gap-2 font-medium">
              <Loader2 size={13} className="animate-spin" />
              {busy === "all"
                ? "正在生成全文，逐节写作中…"
                : busy === "rewrite"
                  ? "正在按指令重写…"
                  : busy.startsWith("revert-")
                    ? "正在回滚…"
                    : "正在生成这一节…"}
              <span className="ml-auto inline-flex items-center gap-1 tabular-nums">
                <Clock3 size={12} />
                已耗时 {elapsed}s
              </span>
            </span>
            {busy === "all" || busy === "rewrite" ? (
              <div className="mt-2 flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/60 dark:bg-white/10">
                  <div
                    className="brand-gradient h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(6, Math.round(jobProgress * 100))}%` }}
                  />
                </div>
                <span className="tabular-nums opacity-80">{Math.round(jobProgress * 100)}%</span>
                {jobId ? (
                  <button
                    type="button"
                    onClick={() => void cancelActive()}
                    className="rounded-full border border-current/30 px-2 py-0.5 text-[11px] font-medium"
                  >
                    取消
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-rose-300/50 bg-rose-50/70 px-4 py-2.5 text-xs text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        ) : null}

        {notice ? (
          <div className="mt-3 rounded-2xl border border-emerald-300/50 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
            {notice}
          </div>
        ) : null}

        {!writable ? (
          <div className="mt-3 rounded-2xl border border-amber-300/50 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-300">
            你以 {roleName || "只读"} 身份访问，仅可阅读
          </div>
        ) : null}
      </div>

      <div className="lg:hidden">
        <button
          type="button"
          onClick={() => setOutlineOpen((prev) => !prev)}
          className="btn btn-quiet w-full justify-between"
        >
          <span className="flex items-center gap-1.5">
            <Layers size={13} />
            大纲 · {longform.outline.length} 节
          </span>
          <ChevronDown size={14} className={clsx("transition", outlineOpen && "rotate-180")} />
        </button>
        <AnimatePresence initial={false}>
          {outlineOpen ? (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="glass mt-2 space-y-1.5 rounded-3xl p-3 shadow-glass">
                {longform.outline.map((section, index) => (
                  <div
                    key={section.id}
                    className="rounded-xl border border-white/45 bg-white/45 p-2.5 dark:border-white/10 dark:bg-white/[0.04]"
                  >
                    <button
                      type="button"
                      onClick={() => scrollToSection(section.title)}
                      className="block w-full text-left"
                    >
                      <span className="flex items-center gap-1.5 text-[12px] font-medium text-slate-700 dark:text-slate-200">
                        <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                          {index + 1}
                        </span>
                        {section.title}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-400 dark:text-slate-500">
                        <span>{section.target_words} 字</span>
                        <span>·</span>
                        <span>{section.content ? "已写" : "待写"}</span>
                      </span>
                    </button>
                    <div className="mt-1.5 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => void generateOne(section.id)}
                        disabled={Boolean(busy) || !writable}
                        className="btn-quiet flex-1 text-[11px]"
                      >
                        {busy === section.id ? (
                          <Loader2 size={11} className="animate-spin" />
                        ) : (
                          <Sparkles size={11} />
                        )}
                        生成本节
                      </button>
                      {writable ? (
                        <RowMenu
                          label={`章节 ${section.title} 操作`}
                          items={sectionMenuItems(section.id, section.title, index)}
                        />
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        {writable ? (
          <button
            type="button"
            onClick={() => {
              setDialogError("");
              setSectionCreate({
                afterId: null,
                title: "",
                summary: "",
                targetWords: 400,
              });
            }}
            className="btn-quiet mt-2 w-full text-[11px]"
          >
            <Plus size={11} />
            在末尾加一节
          </button>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)_220px]">
        <aside className="glass hidden h-fit rounded-3xl p-3.5 shadow-glass lg:block">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <Layers size={12} />
            大纲
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[70vh] space-y-1.5 overflow-y-auto pr-1">
            {longform.outline.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">还没有大纲。</p>
            ) : (
              longform.outline.map((section, index) => (
                <div
                  key={section.id}
                  className="rounded-xl border border-white/45 bg-white/45 p-2.5 transition hover:border-indigo-300/50 dark:border-white/10 dark:bg-white/[0.04]"
                >
                  <button
                    type="button"
                    onClick={() => scrollToSection(section.title)}
                    className="block w-full text-left"
                  >
                    <span className="flex items-start gap-1.5 text-[12px] font-medium leading-snug text-slate-700 dark:text-slate-200">
                      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full brand-gradient text-[9px] font-semibold text-white">
                        {index + 1}
                      </span>
                      <span className="min-w-0">{section.title}</span>
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
                      <span>{section.target_words} 字</span>
                      <span
                        className={clsx(
                          "rounded-full px-1.5 py-0.5 font-medium",
                          section.content
                            ? "bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300"
                            : "bg-slate-500/10 text-slate-500 dark:bg-white/10 dark:text-slate-400",
                        )}
                      >
                        {section.content ? "已写" : "待写"}
                      </span>
                    </span>
                  </button>
                  <div className="mt-1.5 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void generateOne(section.id)}
                      disabled={Boolean(busy) || !writable}
                      className="btn-quiet flex-1 text-[11px]"
                      title={!writable ? "当前角色只读" : undefined}
                    >
                      {busy === section.id ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : (
                        <Sparkles size={11} />
                      )}
                      生成本节
                    </button>
                    {writable ? (
                      <RowMenu
                        label={`章节 ${section.title} 操作`}
                        items={sectionMenuItems(section.id, section.title, index)}
                      />
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
          {writable ? (
            <button
              type="button"
              onClick={() => {
                setDialogError("");
                setSectionCreate({
                  afterId: null,
                  title: "",
                  summary: "",
                  targetWords: 400,
                });
              }}
              className="btn-quiet mt-1.5 w-full text-[11px]"
            >
              <Plus size={11} />
              在末尾加一节
            </button>
          ) : null}
        </aside>

        <section className="glass min-w-0 rounded-3xl p-4 shadow-glass sm:p-6">
          <div ref={contentRef}>
            {longform.content ? (
              <MarkdownReader content={longform.content} citations={longform.citations} />
            ) : (
              <div className="py-12 text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl brand-gradient text-white shadow-brand">
                  <PenLine size={20} />
                </div>
                <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                  正文还是空的
                </p>
                <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                  点右上「全文生成」一次写完，或在左侧逐节生成。生成过程是同步请求，可能需要 10–40 秒。
                </p>
                <button
                  type="button"
                  onClick={generateAll}
                  disabled={Boolean(busy) || !writable}
                  className="btn btn-primary mx-auto mt-4"
                >
                  {busy === "all" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Play size={13} />
                  )}
                  全文生成
                </button>
              </div>
            )}
          </div>
        </section>

        <aside className="glass h-fit rounded-3xl p-3.5 shadow-glass">
          <h2 className="flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
            <History size={12} />
            版本
          </h2>
          <div className="no-scrollbar mt-2.5 max-h-[60vh] space-y-1.5 overflow-y-auto pr-1">
            {versions.length === 0 ? (
              <p className="px-1 py-2 text-[11px] text-slate-400">还没有版本记录。</p>
            ) : (
              [...versions]
                .sort((a, b) => b.version - a.version)
                .map((version) => {
                  const active = selectedVersion === version.version;
                  const current = version.version === longform.current_version;
                  return (
                    <div
                      key={version.id}
                      className={clsx(
                        "rounded-xl border p-2.5 transition",
                        active
                          ? "border-indigo-400/60 bg-indigo-50/70 dark:border-indigo-300/30 dark:bg-indigo-400/10"
                          : "border-white/45 bg-white/45 hover:border-indigo-300/50 dark:border-white/10 dark:bg-white/[0.04]",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedVersion(active ? null : version.version)
                        }
                        className="block w-full text-left"
                      >
                        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-700 dark:text-slate-200">
                          v{version.version}
                          {current ? (
                            <span className="rounded-full bg-emerald-500/12 px-1.5 py-0.5 text-[9px] font-medium text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300">
                              当前
                            </span>
                          ) : null}
                          {version.mode ? (
                            <span className="text-[9px] font-normal text-slate-400">
                              {version.mode === "loose" ? "非严格" : "严格"}
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-0.5 block text-[10px] text-slate-400 dark:text-slate-500">
                          {formatChars(version.content_length)} ·{" "}
                          {formatDateTime(version.created_at)}
                        </span>
                        {version.note ? (
                          <span className="mt-0.5 block truncate text-[10px] text-slate-500 dark:text-slate-400">
                            {version.note}
                          </span>
                        ) : null}
                      </button>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setPreviewVersion(version.version)}
                          className="btn-quiet px-2 py-1 text-[10.5px]"
                        >
                          <Eye size={11} />
                          预览
                        </button>
                        <button
                          type="button"
                          onClick={() => openVersionDiff(version.version)}
                          className="btn-quiet px-2 py-1 text-[10.5px]"
                        >
                          <GitCompare size={11} />
                          对比
                        </button>
                      </div>
                      {active && !current ? (
                        <button
                          type="button"
                          onClick={() => void revert(version.version)}
                          disabled={Boolean(busy) || !writable}
                          className="btn-quiet mt-1.5 w-full text-[11px]"
                          title={!writable ? "当前角色只读" : undefined}
                        >
                          {busy === `revert-${version.version}` ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <RotateCcw size={11} />
                          )}
                          回滚到此版本
                        </button>
                      ) : null}
                    </div>
                  );
                })
            )}
          </div>
          <p className="mt-2 px-1 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
            版本列表只返回元信息，预览与对比会按需拉取完整内容。
          </p>
        </aside>
      </div>

      <AnimatePresence>
        {rewriteOpen ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/30 p-4 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              className="glass my-8 w-full max-w-lg rounded-3xl p-5 shadow-glass"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
                    <Wand2 size={14} className="text-indigo-500" />
                    整篇重写
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    写清要改什么，例如「更口语化」「加一个真实案例」「删掉第二部分」。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setRewriteOpen(false)}
                  className="btn-quiet grid h-8 w-8 place-items-center rounded-full"
                >
                  <X size={14} />
                </button>
              </div>
              <label className="mt-4 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  重写指令
                </span>
                <textarea
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  rows={4}
                  className="input resize-y"
                  placeholder="更口语化，并给每节加一句结论"
                />
              </label>
              <label className="mt-3 block">
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  生成模式
                </span>
                <select
                  value={rewriteMode}
                  onChange={(event) =>
                    setRewriteMode(event.target.value as GenerationMode)
                  }
                  className="select"
                >
                  <option value="loose">非严格 · 允许自由补全</option>
                  <option value="strict">严格 · 必须有出处</option>
                </select>
              </label>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setRewriteOpen(false)}
                  className="btn btn-quiet"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={submitRewrite}
                  disabled={Boolean(busy) || !instruction.trim()}
                  className="btn btn-primary"
                >
                  {busy === "rewrite" ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <FileText size={13} />
                  )}
                  开始重写
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <SharePanel
        open={shareOpen}
        title="共享这篇长篇"
        subtitle={longform ? longform.title : undefined}
        members={shareMembers}
        value={shareLevels}
        options={[
          { value: "read", label: "可读", desc: "可查看正文与版本" },
          { value: "write", label: "可写", desc: "可生成、重写与回滚" },
        ]}
        loading={shareLoading}
        saving={shareSaving}
        error={shareError}
        onClose={() => setShareOpen(false)}
        onChange={(userId, level) =>
          setShareLevels((prev) => ({ ...prev, [userId]: level }))
        }
        onSave={saveShare}
      />

      <ImagePickerDrawer
        open={pickOpen}
        longform={longform}
        onClose={() => setPickOpen(false)}
        onInserted={(message) => {
          setNotice(message);
          void load(true);
        }}
      />

      <PromptDialog
        open={titleEditOpen}
        title="编辑标题"
        label="长篇标题"
        initial={longform?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTitle(value)}
        onClose={() => setTitleEditOpen(false)}
      />

      <PromptDialog
        open={targetEditOpen}
        title="修改目标字数"
        label="目标字数"
        initial={String(longform?.target_words ?? 0)}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void saveTargetWords(value)}
        onClose={() => setTargetEditOpen(false)}
      />

      <PromptDialog
        open={Boolean(sectionRename)}
        title="重命名章节"
        label="章节标题"
        initial={sectionRename?.title ?? ""}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={(value) => void renameSection(value)}
        onClose={() => setSectionRename(null)}
      />

      <Modal
        open={Boolean(sectionForm)}
        title="编辑章节"
        subtitle="可修改目录信息与本节正文，保存后写回大纲。"
        onClose={() => setSectionForm(null)}
        wide
      >
        {sectionForm ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              标题
              <input
                value={sectionForm.title}
                onChange={(event) =>
                  setSectionForm({ ...sectionForm, title: event.target.value })
                }
                className="input mt-1"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目录摘要
                <input
                  value={sectionForm.summary}
                  onChange={(event) =>
                    setSectionForm({ ...sectionForm, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目标字数
                <input
                  type="number"
                  value={sectionForm.targetWords}
                  onChange={(event) =>
                    setSectionForm({
                      ...sectionForm,
                      targetWords: Number(event.target.value),
                    })
                  }
                  className="input mt-1"
                />
              </label>
            </div>
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              本节正文（Markdown）
              <textarea
                value={sectionForm.content}
                onChange={(event) =>
                  setSectionForm({ ...sectionForm, content: event.target.value })
                }
                rows={10}
                className="input mt-1 font-mono text-[12px] leading-relaxed"
              />
            </label>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSectionForm(null)}
                className="btn btn-quiet"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void saveSectionForm()}
                disabled={dialogBusy || !sectionForm.title.trim()}
                className="btn btn-primary"
              >
                {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
                保存章节
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(sectionCreate)}
        title="新增章节"
        onClose={() => setSectionCreate(null)}
      >
        {sectionCreate ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              章节标题
              <input
                autoFocus
                value={sectionCreate.title}
                onChange={(event) =>
                  setSectionCreate({ ...sectionCreate, title: event.target.value })
                }
                className="input mt-1"
                placeholder="例如：实战案例"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-[1fr_130px]">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目录摘要
                <input
                  value={sectionCreate.summary}
                  onChange={(event) =>
                    setSectionCreate({ ...sectionCreate, summary: event.target.value })
                  }
                  className="input mt-1"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目标字数
                <input
                  type="number"
                  value={sectionCreate.targetWords}
                  onChange={(event) =>
                    setSectionCreate({
                      ...sectionCreate,
                      targetWords: Number(event.target.value),
                    })
                  }
                  className="input mt-1"
                />
              </label>
            </div>
            <p className="text-[10.5px] text-slate-400 dark:text-slate-500">
              {sectionCreate.afterId ? "将插入到选中章节之后" : "将追加到大纲末尾"}
            </p>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSectionCreate(null)}
                className="btn btn-quiet"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void createSection()}
                disabled={dialogBusy || !sectionCreate.title.trim()}
                className="btn btn-primary"
              >
                {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
                新增章节
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(sectionDelete)}
        title="删除章节"
        description={`将删除「${sectionDelete?.title ?? ""}」及其正文，至少需保留 1 节。`}
        busy={dialogBusy}
        error={dialogError}
        onConfirm={() => void deleteSection()}
        onClose={() => setSectionDelete(null)}
      />

      <Modal
        open={manualOpen}
        title="手动编辑整篇"
        subtitle={`将保存为新版本（当前 v${longform?.current_version ?? 0}）。`}
        onClose={() => setManualOpen(false)}
        wide
      >
        <div className="space-y-3">
          <textarea
            value={manualText}
            onChange={(event) => setManualText(event.target.value)}
            rows={16}
            className="input w-full font-mono text-[12px] leading-relaxed"
            placeholder="# 标题&#10;&#10;正文内容…"
          />
          <div className="flex items-center justify-between gap-2 text-[10.5px] text-slate-400 dark:text-slate-500">
            <span>{manualText.length} 字符</span>
            {dialogError ? (
              <span className="text-rose-600 dark:text-rose-300">{dialogError}</span>
            ) : null}
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setManualOpen(false)}
              className="btn btn-quiet"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void saveManual()}
              disabled={dialogBusy}
              className="btn btn-primary"
            >
              {dialogBusy ? <Loader2 size={13} className="animate-spin" /> : null}
              保存为新版本
            </button>
          </div>
        </div>
      </Modal>

      <VersionPreviewDialog
        open={previewVersion !== null}
        version={previewVersion}
        load={loadVersionPreview}
        onClose={() => setPreviewVersion(null)}
        onCompare={() => {
          const target = previewVersion;
          setPreviewVersion(null);
          if (target !== null) openVersionDiff(target);
        }}
      />

      <VersionDiffDialog
        open={versionDiffOpen}
        versions={versions.map((item) => item.version)}
        initialFrom={
          versionDiffAnchor !== null
            ? Math.max(1, versionDiffAnchor - 1)
            : versions.length > 1
              ? [...versions].sort((a, b) => a.version - b.version)[0].version
              : 1
        }
        initialTo={
          versionDiffAnchor ??
          (longform?.current_version ||
            versions.reduce((max, item) => Math.max(max, item.version), 1))
        }
        fetchDiff={fetchVersionDiff}
        onClose={() => setVersionDiffOpen(false)}
      />
    </div>
  );
}
