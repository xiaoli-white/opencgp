import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Course } from "@/lib/api";
import { Modal } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

const DIFFICULTIES = ["beginner", "intermediate", "advanced"];

const LANGUAGES: { value: string; label: { zh: string; en: string } }[] = [
  { value: "zh", label: { zh: "中文", en: "Chinese" } },
  { value: "en", label: { zh: "English", en: "English" } },
];

export default function CourseEditDialog({
  open,
  course,
  onClose,
  onSaved,
}: {
  open: boolean;
  course: Course | null;
  onClose: () => void;
  onSaved: (course: Course) => void;
}) {
  const { t, tm } = useI18n();
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [audience, setAudience] = useState("");
  const [difficulty, setDifficulty] = useState("beginner");
  const [language, setLanguage] = useState("zh");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !course) return;
    setTitle(course.title);
    setSubtitle(course.subtitle ?? "");
    setAudience(course.audience ?? "");
    setDifficulty(course.difficulty || "beginner");
    setLanguage(course.language || "zh");
    setError("");
  }, [open, course]);

  const submit = async () => {
    if (!course) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateCourse(course.id, {
        title: title.trim(),
        subtitle: subtitle.trim(),
        audience: audience.trim(),
        difficulty,
        language,
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("course.edit.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("course.edit.title")}
      subtitle={t("course.edit.subtitle")}
      onClose={onClose}
    >
      <div className="space-y-3">
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("course.edit.courseTitle")}
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="input mt-1"
            placeholder={t("course.edit.courseTitlePlaceholder")}
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("course.edit.subtitleLabel")}
          <input
            value={subtitle}
            onChange={(event) => setSubtitle(event.target.value)}
            className="input mt-1"
            placeholder={t("course.edit.subtitlePlaceholder")}
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("course.edit.audienceLabel")}
          <input
            value={audience}
            onChange={(event) => setAudience(event.target.value)}
            className="input mt-1"
            placeholder={t("course.edit.audiencePlaceholder")}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            {t("course.edit.difficulty")}
            <select
              value={difficulty}
              onChange={(event) => setDifficulty(event.target.value)}
              className="select mt-1"
            >
              {DIFFICULTIES.map((item) => (
                <option key={item} value={item}>
                  {t(`labels.difficulty.${item}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            {t("course.edit.language")}
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="select mt-1"
            >
              {LANGUAGES.map((item) => (
                <option key={item.value} value={item.value}>
                  {tm(item.label)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error ? (
          <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn btn-quiet">
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !title.trim()}
            className="btn btn-primary"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : null}
            {t("common.saveChanges")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
