import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  FilePlus2,
  Layers,
  Loader2,
  PenLine,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api, type CreationProfile, type Longform } from "@/lib/api";
import { formatChars, formatDateTime } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";

const GENRE_OPTIONS = [
  { value: "article", label: "文章", badge: "文章" },
  { value: "report", label: "报告", badge: "报告" },
  { value: "essay", label: "随笔", badge: "随笔" },
  { value: "tutorial", label: "教程", badge: "教程" },
  { value: "custom", label: "自定义", badge: "自定义" },
];

const CITATION_OPTIONS = [
  { value: "required", label: "必须带出处" },
  { value: "optional", label: "可用可不用" },
  { value: "forbidden", label: "不引用" },
];

const MODE_OPTIONS = [
  { value: "strict", label: "严格 · 只写有据可查的内容" },
  { value: "loose", label: "非严格 · 允许自由补全" },
];

function genreLabel(value: string): string {
  return GENRE_OPTIONS.find((item) => item.value === value)?.badge ?? (value || "文章");
}

export default function LongformsPage() {
  const navigate = useNavigate();
  const { can, roleName } = useSession();
  const writable = can("write");

  const [items, setItems] = useState<Longform[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("article");
  const [tone, setTone] = useState("");
  const [audience, setAudience] = useState("");
  const [pov, setPov] = useState("");
  const [citationPolicy, setCitationPolicy] = useState("optional");
  const [targetWords, setTargetWords] = useState(3000);
  const [mode, setMode] = useState<"strict" | "loose">("loose");
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<CreationProfile[]>([]);

  useEffect(() => {
    api
      .listCreationProfiles()
      .then((data) => setProfiles(data.profiles))
      .catch(() => setProfiles([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listLongforms();
      setItems(data.longforms);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载长篇列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    const name = title.trim();
    if (!name || creating) return;
    if (!writable) {
      setError("当前角色只读，无法新建长篇");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const created = await api.createLongform({
        title: name,
        genre,
        tone: tone.trim(),
        audience: audience.trim(),
        pov: pov.trim(),
        citation_policy: citationPolicy,
        target_words: targetWords,
        mode,
        ...(profileId ? { profile_id: profileId } : {}),
      });
      setItems((prev) => [created, ...prev]);
      setOpen(false);
      setTitle("");
      setToneless();
      setNotice("已创建，进入编辑器继续");
      navigate(`/longforms/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  function setToneless() {
    setTone("");
    setAudience("");
    setPov("");
    setTargetWords(3000);
    setMode("loose");
    setCitationPolicy("optional");
    setGenre("article");
  }

  const remove = async (item: Longform) => {
    if (!writable || deleting) return;
    const confirmed = window.confirm(`删除长篇「${item.title}」？该操作不可撤销。`);
    if (!confirmed) return;
    setDeleting(item.id);
    setError("");
    try {
      await api.deleteLongform(item.id);
      setItems((prev) => prev.filter((row) => row.id !== item.id));
      setNotice("已删除");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-5">
      {!writable ? (
        <div className="rounded-2xl border border-amber-300/50 bg-amber-50/70 px-4 py-2.5 text-xs text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-300">
          你以 {roleName || "只读"} 身份访问，仅可查看长篇草稿
        </div>
      ) : null}

      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass relative overflow-hidden rounded-[2rem] p-6 shadow-glass sm:p-8"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-violet-400/25 to-indigo-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <span className="chip">
              <PenLine size={11} />
              单页长篇
            </span>
            <h1 className="mt-3 text-xl font-semibold tracking-tight text-slate-800 dark:text-slate-100 sm:text-2xl">
              一块画布，写完一整篇长文
            </h1>
            <p className="mt-2 max-w-xl text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              先出大纲，再逐节生成，最后统一重写润色。每一次生成都会存档成新版本，可随时回滚。
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={!writable}
            className="btn btn-primary shrink-0"
            title={!writable ? "当前角色只读" : undefined}
          >
            <FilePlus2 size={14} />
            新建长篇
          </button>
        </div>

        {error ? (
          <div className="relative mt-4 flex items-start gap-2 rounded-2xl border border-rose-300/50 bg-rose-50/70 px-4 py-2.5 text-xs text-rose-700 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-300">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        ) : null}

        {notice ? (
          <div className="relative mt-4 rounded-2xl border border-emerald-300/50 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-300">
            {notice}
          </div>
        ) : null}
      </motion.section>

      {loading ? (
        <div className="glass grid place-items-center rounded-3xl p-10 shadow-glass">
          <Loader2 size={20} className="animate-spin text-indigo-500" />
        </div>
      ) : items.length === 0 ? (
        <div className="glass rounded-3xl p-8 text-center shadow-glass">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl brand-gradient text-white shadow-brand">
            <Layers size={20} />
          </div>
          <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
            还没有长篇作品
          </p>
          <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            新建时会先生成一份大纲。填好体裁、读者与目标字数，模型会据此安排每一节的篇幅。
          </p>
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={!writable}
            className="btn btn-quiet mx-auto mt-4"
          >
            <FilePlus2 size={13} />
            新建第一篇
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="glass group flex flex-col rounded-3xl p-5 shadow-glass transition hover:-translate-y-0.5 hover:shadow-xl"
            >
              <div className="flex items-start gap-2">
                <span className="chip">{genreLabel(item.profile?.genre ?? "article")}</span>
                {item.last_mode ? (
                  <span
                    className={clsx(
                      "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1",
                      item.last_mode === "loose"
                        ? "bg-amber-400/20 text-amber-700 ring-amber-500/30 dark:bg-amber-300/15 dark:text-amber-300 dark:ring-amber-300/25"
                        : "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:bg-emerald-400/15 dark:text-emerald-300 dark:ring-emerald-300/25",
                    )}
                  >
                    {item.last_mode === "loose" ? "非严格" : "严格"}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => void remove(item)}
                  disabled={!writable || deleting === item.id}
                  className="btn-quiet ml-auto grid h-7 w-7 place-items-center rounded-full text-rose-500 opacity-0 transition group-hover:opacity-100 disabled:opacity-40"
                  title={writable ? "删除" : "当前角色只读"}
                >
                  {deleting === item.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Trash2 size={12} />
                  )}
                </button>
              </div>

              <Link to={`/longforms/${item.id}`} className="mt-2.5 block">
                <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-slate-800 transition group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-300">
                  {item.title}
                </h3>
              </Link>

              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500 dark:text-slate-400">
                <span className="chip-muted">
                  {formatChars(item.content ? item.content.length : 0)} / 目标{" "}
                  {formatChars(item.target_words)}
                </span>
                <span className="chip-muted">v{item.current_version}</span>
                <span className="chip-muted">{item.outline.length} 节</span>
              </div>

              <div className="mt-auto flex items-center justify-between pt-4">
                <span className="text-[10px] text-slate-400 dark:text-slate-500">
                  {formatDateTime(item.updated_at || item.created_at)}
                </span>
                <Link
                  to={`/longforms/${item.id}`}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-600 dark:text-indigo-300"
                >
                  打开编辑器
                  <ArrowRight size={11} />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {open ? (
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
                    <Sparkles size={14} className="text-indigo-500" />
                    新建长篇
                  </h3>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    创建后会先生成大纲，正文可逐节或一次性生成。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="btn-quiet grid h-8 w-8 place-items-center rounded-full"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="mt-4 space-y-3">
                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    标题
                  </span>
                  <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    className="input"
                    placeholder="例如：向量检索的工程实践"
                  />
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    使用规则模板
                  </span>
                  <select
                    value={profileId}
                    onChange={(event) => {
                      const next = event.target.value;
                      setProfileId(next);
                      const picked = profiles.find((item) => item.id === next);
                      if (!picked) return;
                      setGenre(picked.genre || "article");
                      setTone(picked.tone ?? "");
                      setAudience(picked.audience ?? "");
                      setPov(picked.pov ?? "");
                      setCitationPolicy(picked.citation_policy || "optional");
                      setTargetWords(picked.target_words || 3000);
                    }}
                    className="select"
                  >
                    <option value="">不使用（手动填写）</option>
                    {profiles.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · {item.genre} · {item.target_words} 字
                      </option>
                    ))}
                  </select>
                </label>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      体裁
                    </span>
                    <select
                      value={genre}
                      onChange={(event) => setGenre(event.target.value)}
                      className="select"
                    >
                      {GENRE_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      引用策略
                    </span>
                    <select
                      value={citationPolicy}
                      onChange={(event) => setCitationPolicy(event.target.value)}
                      className="select"
                    >
                      {CITATION_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      口吻
                    </span>
                    <input
                      value={tone}
                      onChange={(event) => setTone(event.target.value)}
                      className="input"
                      placeholder="冷静克制"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      目标读者
                    </span>
                    <input
                      value={audience}
                      onChange={(event) => setAudience(event.target.value)}
                      className="input"
                      placeholder="后端工程师"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      视角
                    </span>
                    <input
                      value={pov}
                      onChange={(event) => setPov(event.target.value)}
                      className="input"
                      placeholder="第一人称"
                    />
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      目标字数
                    </span>
                    <input
                      type="number"
                      min={200}
                      max={50000}
                      step={100}
                      value={targetWords}
                      onChange={(event) => setTargetWords(Number(event.target.value))}
                      className="input"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      生成模式
                    </span>
                    <select
                      value={mode}
                      onChange={(event) => setMode(event.target.value as "strict" | "loose")}
                      className="select"
                    >
                      {MODE_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => setOpen(false)} className="btn btn-quiet">
                  取消
                </button>
                <button
                  type="button"
                  onClick={submit}
                  disabled={creating || !title.trim()}
                  className="btn btn-primary"
                >
                  {creating ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Sparkles size={13} />
                  )}
                  {creating ? "正在生成大纲…" : "创建并生成大纲"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
