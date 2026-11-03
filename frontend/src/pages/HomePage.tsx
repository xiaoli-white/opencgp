import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowUpRight,
  BookOpen,
  Loader2,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { api, type Course } from "@/lib/api";
import { difficultyLabel, formatRelative } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";

const FLOW = ["建课", "建讲", "检索取证", "逐讲生成", "追问 / 改版", "版本回滚"];

export default function HomePage() {
  const { can, visibleCourseIds } = useSession();
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    subtitle: "",
    audience: "",
    difficulty: "intermediate",
    language: "zh",
  });

  useEffect(() => {
    let cancelled = false;
    api
      .listCourses()
      .then((data) => {
        if (!cancelled) setCourses(data.courses);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "课程列表加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const createCourse = async (event: React.FormEvent) => {
    event.preventDefault();
    const title = form.title.trim();
    if (!title || creating) return;
    setCreating(true);
    setError("");
    try {
      const course = await api.createCourse({
        title,
        subtitle: form.subtitle.trim(),
        audience: form.audience.trim(),
        difficulty: form.difficulty,
        language: form.language,
      });
      window.dispatchEvent(new Event("course-studio:refresh"));
      navigate(`/courses/${course.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建课程失败");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="glass relative overflow-hidden rounded-[2rem] p-6 shadow-glass sm:p-9"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-indigo-400/30 to-violet-400/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-gradient-to-tr from-violet-300/30 to-indigo-300/10 blur-3xl" />
        <div className="relative">
          <span className="chip">
            <Sparkles size={11} />
            对话即作者 · 课程即活文档
          </span>
          <h1 className="mt-4 max-w-2xl text-[28px] font-semibold leading-tight tracking-tight text-slate-900 dark:text-white sm:text-[38px]">
            把知识，写成一门
            <span className="text-gradient">会生长的课程</span>
          </h1>
          <p className="mt-3 max-w-2xl font-reading text-[15px] leading-relaxed text-slate-600 dark:text-slate-300 sm:text-base">
            AI 先检索证据、逐段带引用写作，再陪你追问与局部修改。每一次改动都沉淀为可对比、可回滚的版本——课程不是一次性产物，而是一份持续打磨的活文档。
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              disabled={!can("write")}
              title={can("write") ? "" : "当前角色只读"}
              className="btn btn-primary"
            >
              <Plus size={15} />
              新建课程
            </button>
            <Link to="/kb" className="btn btn-ghost">
              <BookOpen size={14} />
              打开知识库
            </Link>
            <span className="text-[11px] text-slate-400 dark:text-slate-500">
              已有 {courses.length} 门课程
            </span>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-1.5">
            {FLOW.map((step, index) => (
              <span key={step} className="flex items-center gap-1.5">
                <span className="rounded-full border border-white/60 bg-white/45 px-2.5 py-1 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  {step}
                </span>
                {index < FLOW.length - 1 && (
                  <span className="text-[10px] text-slate-300 dark:text-slate-600">→</span>
                )}
              </span>
            ))}
          </div>
        </div>
      </motion.section>

      <AnimatePresence initial={false}>
        {formOpen && (
          <motion.section
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <form
              onSubmit={createCourse}
              className="glass rounded-3xl p-5 shadow-glass sm:p-6"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    新建课程
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    先给课程一个骨架，正文按讲次逐步生成。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="grid h-8 w-8 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10"
                  aria-label="关闭新建表单"
                >
                  <X size={15} />
                </button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    课程标题
                  </span>
                  <input
                    autoFocus
                    value={form.title}
                    onChange={(event) =>
                      setForm({ ...form, title: event.target.value })
                    }
                    placeholder="例如：从零理解向量检索"
                    className="input"
                  />
                </label>
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    副标题
                  </span>
                  <input
                    value={form.subtitle}
                    onChange={(event) =>
                      setForm({ ...form, subtitle: event.target.value })
                    }
                    placeholder="一句话说明这门课解决什么问题"
                    className="input"
                  />
                </label>
                <label>
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    目标受众
                  </span>
                  <input
                    value={form.audience}
                    onChange={(event) =>
                      setForm({ ...form, audience: event.target.value })
                    }
                    placeholder="例如：后端工程师 / 产品经理"
                    className="input"
                  />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label>
                    <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      难度
                    </span>
                    <select
                      value={form.difficulty}
                      onChange={(event) =>
                        setForm({ ...form, difficulty: event.target.value })
                      }
                      className="select w-full"
                    >
                      <option value="beginner">入门</option>
                      <option value="intermediate">进阶</option>
                      <option value="advanced">高级</option>
                    </select>
                  </label>
                  <label>
                    <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      内容语言
                    </span>
                    <select
                      value={form.language}
                      onChange={(event) =>
                        setForm({ ...form, language: event.target.value })
                      }
                      className="select w-full"
                    >
                      <option value="zh">中文</option>
                      <option value="en">English</option>
                      <option value="bilingual">中英对照</option>
                    </select>
                  </label>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="btn btn-ghost"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating || !form.title.trim()}
                  className="btn btn-primary"
                >
                  {creating ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Plus size={14} />
                  )}
                  创建课程
                </button>
              </div>
            </form>
          </motion.section>
        )}
      </AnimatePresence>

      {error && (
        <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-xs leading-relaxed text-rose-700 dark:text-rose-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            aria-label="关闭错误提示"
            className="text-rose-400 transition hover:text-rose-600"
          >
            <X size={13} />
          </button>
        </div>
      )}

      <section>
        <div className="mb-3 flex items-end justify-between px-1">
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100">
              课程库
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              每门课都是可以继续追问与改写的活文档
            </p>
          </div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">
            {courses.length} 门
          </span>
        </div>

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className="glass h-48 animate-pulse rounded-3xl"
              />
            ))}
          </div>
        ) : courses.length === 0 ? (
          <div className="glass rounded-3xl px-6 py-14 text-center shadow-glass">
            <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
              <BookOpen size={20} />
            </div>
            <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
              还没有课程
            </p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              先从主题建一门课，添加第一讲，让 AI 基于知识库证据生成正文。
            </p>
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="btn btn-primary mt-4"
            >
              <Plus size={14} />
              新建第一门课程
            </button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {courses.map((course, index) => (
              <motion.article
                key={course.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.3) }}
                whileHover={{ y: -4 }}
                className="group glass relative overflow-hidden rounded-3xl p-5 shadow-glass transition-shadow"
              >
                <div className="pointer-events-none absolute -right-10 -top-12 h-32 w-32 rounded-full bg-gradient-to-br from-indigo-400/25 to-violet-400/15 blur-2xl transition-transform duration-500 group-hover:scale-125" />
                <div className="relative flex items-center justify-between">
                  <span className="chip">{difficultyLabel(course.difficulty)}</span>
                  {visibleCourseIds !== "all" &&
                  visibleCourseIds.includes(course.id) ? (
                    <span className="chip">授权可见</span>
                  ) : null}
                  <span className="text-[10px] text-slate-400 dark:text-slate-500">
                    {formatRelative(course.updated_at)}
                  </span>
                </div>
                <h3 className="relative mt-4 line-clamp-2 text-lg font-semibold leading-snug tracking-tight text-slate-800 transition group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-300">
                  {course.title}
                </h3>
                <p className="relative mt-1.5 line-clamp-2 min-h-[2.5rem] text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {course.subtitle || "尚未填写副标题"}
                </p>
                <div className="relative mt-5 flex items-center justify-between border-t border-slate-200/60 pt-3 text-[11px] text-slate-400 dark:border-white/10 dark:text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <BookOpen size={12} />
                    {course.audience || "通用受众"}
                  </span>
                  <span className="inline-flex items-center gap-1 text-indigo-500 opacity-0 transition group-hover:opacity-100 dark:text-indigo-300">
                    打开
                    <ArrowUpRight size={12} />
                  </span>
                </div>
                <Link
                  to={`/courses/${course.id}`}
                  aria-label={course.title}
                  className="absolute inset-0 rounded-3xl"
                />
              </motion.article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
