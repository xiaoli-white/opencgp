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
import { api, type Series } from "@/lib/api";
import { difficultyLabel, formatRelative } from "@/lib/format";
import { useSession } from "@/components/auth/SessionProvider";
import ProfileSelect, { useWorkProfiles } from "@/components/profiles/ProfileSelect";
import { useI18n } from "@/i18n/I18nProvider";

const FLOW = [
  "home.flow.createSeries",
  "home.flow.createUnit",
  "home.flow.research",
  "home.flow.generate",
  "home.flow.revise",
  "home.flow.rollback",
];

export default function HomePage() {
  const { can, visibleSeriesIds } = useSession();
  const { t } = useI18n();
  const navigate = useNavigate();
  const { profiles } = useWorkProfiles();
  const [series, setSeries] = useState<Series[]>([]);
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
    profileId: "profile_builtin_tutorial",
  });

  useEffect(() => {
    if (profiles.length === 0) return;
    const exists = profiles.some((item) => item.id === form.profileId);
    if (!exists) {
      const fallback =
        profiles.find((item) => item.id === "profile_builtin_tutorial") ?? profiles[0];
      setForm((prev) => ({ ...prev, profileId: fallback.id }));
    }
  }, [profiles, form.profileId]);

  useEffect(() => {
    let cancelled = false;
    api
      .listSeries()
      .then((data) => {
        if (!cancelled) setSeries(data.series);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : t("home.loadFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const createSeries = async (event: React.FormEvent) => {
    event.preventDefault();
    const title = form.title.trim();
    if (!title || creating) return;
    setCreating(true);
    setError("");
    try {
      const series = await api.createSeries({
        title,
        subtitle: form.subtitle.trim(),
        audience: form.audience.trim(),
        difficulty: form.difficulty,
        language: form.language,
        profile_id: form.profileId,
      });
      window.dispatchEvent(new Event("series-studio:refresh"));
      navigate(`/series/${series.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("home.createFailed"));
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
        className="glass relative overflow-hidden rounded-[1.5rem] p-5 shadow-glass sm:rounded-[2rem] sm:p-9"
      >
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-gradient-to-br from-indigo-400/30 to-violet-400/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-56 w-56 rounded-full bg-gradient-to-tr from-violet-300/30 to-indigo-300/10 blur-3xl" />
        <div className="relative">
          <span className="chip">
            <Sparkles size={11} />
            {t("home.badge")}
          </span>
          <h1 className="mt-3 max-w-2xl text-2xl font-semibold leading-tight tracking-tight text-slate-900 dark:text-white sm:mt-4 sm:text-[38px]">
            {t("home.heroTitle")}
            <span className="text-gradient">{t("home.heroAccent")}</span>
          </h1>
          <p className="mt-3 max-w-2xl font-reading text-[14px] leading-relaxed text-slate-600 dark:text-slate-300 sm:text-base">
            {t("home.heroSubtitle")}
          </p>
          <div className="mt-5 flex flex-col gap-2 sm:mt-6 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2.5">
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              disabled={!can("write")}
              title={can("write") ? "" : t("common.readOnlyRole")}
              className="btn btn-primary w-full justify-center sm:w-auto"
            >
              <Plus size={15} />
              {t("home.newSeries")}
            </button>
            <Link to="/kb" className="btn btn-ghost w-full justify-center sm:w-auto">
              <BookOpen size={14} />
              {t("home.openKb")}
            </Link>
            <span className="text-center text-[11px] text-slate-400 dark:text-slate-500 sm:text-left">
              {t("home.seriesCountInline", { count: series.length })}
            </span>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-1.5">
            {FLOW.map((step, index) => (
              <span key={step} className="flex items-center gap-1.5">
                <span className="rounded-full border border-white/60 bg-white/45 px-2.5 py-1 text-[11px] text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  {t(step)}
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
              onSubmit={createSeries}
              className="glass rounded-3xl p-5 shadow-glass sm:p-6"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {t("home.form.title")}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    {t("home.form.desc")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="grid h-8 w-8 place-items-center rounded-full text-slate-400 transition hover:bg-white/70 hover:text-slate-600 dark:hover:bg-white/10"
                  aria-label={t("home.form.close")}
                >
                  <X size={15} />
                </button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {t("home.form.seriesTitle")}
                  </span>
                  <input
                    autoFocus
                    value={form.title}
                    onChange={(event) =>
                      setForm({ ...form, title: event.target.value })
                    }
                    placeholder={t("home.form.seriesTitlePlaceholder")}
                    className="input"
                  />
                </label>
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {t("home.form.subtitle")}
                  </span>
                  <input
                    value={form.subtitle}
                    onChange={(event) =>
                      setForm({ ...form, subtitle: event.target.value })
                    }
                    placeholder={t("home.form.subtitlePlaceholder")}
                    className="input"
                  />
                </label>
                <label>
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {t("home.form.audience")}
                  </span>
                  <input
                    value={form.audience}
                    onChange={(event) =>
                      setForm({ ...form, audience: event.target.value })
                    }
                    placeholder={t("home.form.audiencePlaceholder")}
                    className="input"
                  />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label>
                    <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      {t("home.form.difficulty")}
                    </span>
                    <select
                      value={form.difficulty}
                      onChange={(event) =>
                        setForm({ ...form, difficulty: event.target.value })
                      }
                      className="select w-full"
                    >
                      <option value="beginner">{difficultyLabel("beginner")}</option>
                      <option value="intermediate">
                        {difficultyLabel("intermediate")}
                      </option>
                      <option value="advanced">{difficultyLabel("advanced")}</option>
                    </select>
                  </label>
                  <label>
                    <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      {t("home.form.language")}
                    </span>
                    <select
                      value={form.language}
                      onChange={(event) =>
                        setForm({ ...form, language: event.target.value })
                      }
                      className="select w-full"
                    >
                      <option value="zh">{t("home.form.languageZh")}</option>
                      <option value="en">{t("home.form.languageEn")}</option>
                      <option value="bilingual">
                        {t("home.form.languageBilingual")}
                      </option>
                    </select>
                  </label>
                </div>
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                    {t("profiles.seriesProfileLabel")}
                  </span>
                  <ProfileSelect
                    value={form.profileId}
                    profiles={profiles}
                    onChange={(profileId) => setForm({ ...form, profileId })}
                  />
                </label>
              </div>
              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setFormOpen(false)}
                  className="btn btn-ghost"
                >
                  {t("common.cancel")}
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
                  {t("home.form.submit")}
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
            aria-label={t("common.close")}
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
              {t("home.libraryTitle")}
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              {t("home.libraryDesc")}
            </p>
          </div>
          <span className="text-[11px] text-slate-400 dark:text-slate-500">
            {t("home.seriesCount", { count: series.length })}
          </span>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className="glass h-48 animate-pulse rounded-3xl"
              />
            ))}
          </div>
        ) : series.length === 0 ? (
          <div className="glass rounded-3xl px-6 py-14 text-center shadow-glass">
            <div className="brand-gradient mx-auto grid h-12 w-12 place-items-center rounded-2xl text-white shadow-brand">
              <BookOpen size={20} />
            </div>
            <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-200">
              {t("home.emptyTitle")}
            </p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              {t("home.emptyDesc")}
            </p>
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="btn btn-primary mt-4"
            >
              <Plus size={14} />
              {t("home.createFirst")}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {series.map((series, index) => (
              <motion.article
                key={series.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.3) }}
                whileHover={{ y: -4 }}
                className="group glass relative overflow-hidden rounded-3xl p-5 shadow-glass transition-shadow"
              >
                <div className="pointer-events-none absolute -right-10 -top-12 h-32 w-32 rounded-full bg-gradient-to-br from-indigo-400/25 to-violet-400/15 blur-2xl transition-transform duration-500 group-hover:scale-125" />
                <div className="relative flex items-center justify-between">
                  <span className="chip">{difficultyLabel(series.difficulty)}</span>
                  {visibleSeriesIds !== "all" &&
                  visibleSeriesIds.includes(series.id) ? (
                    <span className="chip">{t("home.restricted")}</span>
                  ) : null}
                  <span className="text-[10px] text-slate-400 dark:text-slate-500">
                    {formatRelative(series.updated_at)}
                  </span>
                </div>
                <h3 className="relative mt-4 line-clamp-2 text-lg font-semibold leading-snug tracking-tight text-slate-800 transition group-hover:text-indigo-600 dark:text-slate-100 dark:group-hover:text-indigo-300">
                  {series.title}
                </h3>
                <p className="relative mt-1.5 line-clamp-2 min-h-[2.5rem] text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                  {series.subtitle || t("home.noSubtitle")}
                </p>
                <div className="relative mt-5 flex items-center justify-between border-t border-slate-200/60 pt-3 text-[11px] text-slate-400 dark:border-white/10 dark:text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <BookOpen size={12} />
                    {series.audience || t("home.genericAudience")}
                  </span>
                  <span className="inline-flex items-center gap-1 text-indigo-500 opacity-0 transition group-hover:opacity-100 dark:text-indigo-300">
                    {t("home.open")}
                    <ArrowUpRight size={12} />
                  </span>
                </div>
                <Link
                  to={`/series/${series.id}`}
                  aria-label={series.title}
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
