import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api, type Series } from "@/lib/api";
import { Modal } from "@/components/common/Dialogs";
import ProfileSelect, { useWorkProfiles } from "@/components/profiles/ProfileSelect";
import { useI18n } from "@/i18n/I18nProvider";
import { difficultyLabel, languageLabel } from "@/i18n/labels";

const DIFFICULTIES = ["beginner", "intermediate", "advanced"];
const LANGUAGES = ["zh", "en"];

export default function SeriesEditDialog({
  open,
  series,
  onClose,
  onSaved,
}: {
  open: boolean;
  series: Series | null;
  onClose: () => void;
  onSaved: (series: Series) => void;
}) {
  const { t } = useI18n();
  const { profiles } = useWorkProfiles();
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [brief, setBrief] = useState("");
  const [audience, setAudience] = useState("");
  const [difficulty, setDifficulty] = useState("beginner");
  const [language, setLanguage] = useState("zh");
  const [profileId, setProfileId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !series) return;
    setTitle(series.title);
    setSubtitle(series.subtitle ?? "");
    setBrief(series.brief ?? "");
    setAudience(series.audience ?? "");
    setDifficulty(series.difficulty || "beginner");
    setLanguage(series.language || "zh");
    setProfileId(series.profile_id ?? "");
    setError("");
  }, [open, series]);

  const submit = async () => {
    if (!series) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateSeries(series.id, {
        title: title.trim(),
        subtitle: subtitle.trim(),
        brief: brief.trim(),
        audience: audience.trim(),
        difficulty,
        language,
        profile_id: profileId,
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("series.edit.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("series.edit.title")}
      subtitle={t("series.edit.subtitle")}
      onClose={onClose}
    >
      <div className="space-y-3">
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("series.edit.seriesTitle")}
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="input mt-1"
            placeholder={t("series.edit.seriesTitlePlaceholder")}
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("series.edit.subtitleLabel")}
          <input
            value={subtitle}
            onChange={(event) => setSubtitle(event.target.value)}
            className="input mt-1"
            placeholder={t("series.edit.subtitlePlaceholder")}
          />
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("series.briefLabel")}
          <textarea
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            className="input mt-1 min-h-[7.5rem] resize-y"
            rows={5}
            placeholder={t("series.briefPlaceholder")}
          />
          <span className="mt-1 block text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
            {t("series.briefHint")}
          </span>
        </label>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("series.edit.audienceLabel")}
          <input
            value={audience}
            onChange={(event) => setAudience(event.target.value)}
            className="input mt-1"
            placeholder={t("series.edit.audiencePlaceholder")}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            {t("series.edit.difficulty")}
            <select
              value={difficulty}
              onChange={(event) => setDifficulty(event.target.value)}
              className="select mt-1"
            >
              {DIFFICULTIES.map((item) => (
                <option key={item} value={item}>
                  {difficultyLabel(t, item)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[11px] text-slate-500 dark:text-slate-400">
            {t("series.edit.language")}
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="select mt-1"
            >
              {LANGUAGES.map((item) => (
                <option key={item} value={item}>
                  {languageLabel(t, item)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-[11px] text-slate-500 dark:text-slate-400">
          {t("profiles.seriesProfileLabel")}
          <ProfileSelect value={profileId} profiles={profiles} onChange={setProfileId} />
        </label>
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
