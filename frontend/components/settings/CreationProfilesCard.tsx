import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus, Trash2, Wand2 } from "lucide-react";
import clsx from "clsx";
import { api, type CreationProfile } from "@/lib/api";
import { ConfirmDialog, Modal } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";

const GENRES: { value: string; labelKey: string }[] = [
  { value: "article", labelKey: "profiles.genreArticle" },
  { value: "report", labelKey: "profiles.genreReport" },
  { value: "essay", labelKey: "profiles.genreEssay" },
  { value: "tutorial", labelKey: "profiles.genreTutorial" },
  { value: "custom", labelKey: "profiles.genreCustom" },
];

const POLICIES: { value: string; labelKey: string }[] = [
  { value: "required", labelKey: "profiles.citeRequired" },
  { value: "optional", labelKey: "profiles.citeOptional" },
  { value: "forbidden", labelKey: "profiles.citeForbidden" },
];

const emptyForm = {
  id: "",
  name: "",
  genre: "article",
  tone: "",
  audience: "",
  pov: "",
  citationPolicy: "optional",
  targetWords: 3000,
  isShared: false,
};

export default function CreationProfilesCard({
  canWrite,
  onNotice,
  onError,
}: {
  canWrite: boolean;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<CreationProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<typeof emptyForm | null>(null);
  const [removing, setRemoving] = useState<CreationProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listCreationProfiles();
      setItems(data.profiles);
    } catch (err) {
      onError(err instanceof Error ? err.message : t("profiles.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [onError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setDialogError("");
    const payload = {
      name: form.name.trim(),
      genre: form.genre,
      tone: form.tone.trim(),
      audience: form.audience.trim(),
      pov: form.pov.trim(),
      citation_policy: form.citationPolicy,
      target_words: Number(form.targetWords) || 0,
      is_shared: form.isShared,
    };
    try {
      if (form.id) {
        await api.updateCreationProfile(form.id, payload);
        onNotice(t("profiles.updated"));
      } else {
        await api.createCreationProfile(payload);
        onNotice(t("profiles.created"));
      }
      setForm(null);
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("profiles.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!removing) return;
    setBusy(true);
    setDialogError("");
    try {
      await api.deleteCreationProfile(removing.id);
      setRemoving(null);
      onNotice(t("profiles.deleted"));
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : t("profiles.deleteFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="creation-profiles" className="glass rounded-3xl p-5 shadow-glass">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <Wand2 size={15} className="text-indigo-500" />
          {t("profiles.title")}
          <span className="chip-muted">{t("common.count", { count: items.length })}</span>
        </h2>
        <button
          type="button"
          onClick={() => {
            setDialogError("");
            setForm({ ...emptyForm });
          }}
          disabled={!canWrite}
          title={!canWrite ? t("common.readOnlyRole") : undefined}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
        >
          <Plus size={12} />
          {t("profiles.new")}
        </button>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        {t("profiles.hint")}
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          {t("profiles.loading")}
        </div>
      ) : items.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-white/50 bg-white/40 px-3 py-6 text-center text-[11px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-500">
          {t("profiles.empty")}
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {items.map((profile) => (
            <div
              key={profile.id}
              className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/50 bg-white/45 px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.04]"
            >
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] font-medium text-slate-700 dark:text-slate-200">
                  {profile.name}
                  <span className="chip-muted">
                    {GENRES.find((item) => item.value === profile.genre)
                      ? t(GENRES.find((item) => item.value === profile.genre)!.labelKey)
                      : profile.genre}
                  </span>
                  {profile.is_shared ? <span className="chip">{t("profiles.shared")}</span> : null}
                  {profile.is_owner ? (
                    <span className="chip-muted">{t("profiles.mine")}</span>
                  ) : (
                    <span className="chip-muted">{t("profiles.others")}</span>
                  )}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
                  <span>
                    {POLICIES.find((item) => item.value === profile.citation_policy)
                      ? t(
                          POLICIES.find((item) => item.value === profile.citation_policy)!
                            .labelKey,
                        )
                      : profile.citation_policy}
                  </span>
                  <span>·</span>
                  <span>{t("profiles.words", { count: profile.target_words })}</span>
                  {profile.audience ? (
                    <>
                      <span>·</span>
                      <span>{t("profiles.audience", { name: profile.audience })}</span>
                    </>
                  ) : null}
                </p>
              </div>
              <div
                className={clsx(
                  "flex shrink-0 items-center gap-1",
                  !profile.is_owner && "hidden",
                )}
              >
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setForm({
                      id: profile.id,
                      name: profile.name,
                      genre: profile.genre,
                      tone: profile.tone ?? "",
                      audience: profile.audience ?? "",
                      pov: profile.pov ?? "",
                      citationPolicy: profile.citation_policy ?? "optional",
                      targetWords: profile.target_words ?? 0,
                      isShared: Boolean(profile.is_shared),
                    });
                  }}
                  disabled={!canWrite}
                  className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-white/70 hover:text-indigo-600 disabled:opacity-40 dark:hover:bg-white/10 dark:hover:text-indigo-300"
                  aria-label={t("profiles.edit")}
                >
                  <Pencil size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDialogError("");
                    setRemoving(profile);
                  }}
                  disabled={!canWrite}
                  className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-600 disabled:opacity-40"
                  aria-label={t("profiles.delete")}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={Boolean(form)}
        title={form?.id ? t("profiles.editTitle") : t("profiles.addTitle")}
        onClose={() => setForm(null)}
      >
        {form ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              {t("profiles.name")}
              <input
                autoFocus
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                className="input mt-1"
                placeholder={t("profiles.namePlaceholder")}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.genre")}
                <select
                  value={form.genre}
                  onChange={(event) => setForm({ ...form, genre: event.target.value })}
                  className="select mt-1"
                >
                  {GENRES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {t(item.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.citationPolicy")}
                <select
                  value={form.citationPolicy}
                  onChange={(event) =>
                    setForm({ ...form, citationPolicy: event.target.value })
                  }
                  className="select mt-1"
                >
                  {POLICIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {t(item.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.tone")}
                <input
                  value={form.tone}
                  onChange={(event) => setForm({ ...form, tone: event.target.value })}
                  className="input mt-1"
                  placeholder={t("profiles.tonePlaceholder")}
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.audienceLabel")}
                <input
                  value={form.audience}
                  onChange={(event) => setForm({ ...form, audience: event.target.value })}
                  className="input mt-1"
                  placeholder={t("profiles.audiencePlaceholder")}
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.pov")}
                <input
                  value={form.pov}
                  onChange={(event) => setForm({ ...form, pov: event.target.value })}
                  className="input mt-1"
                  placeholder={t("profiles.povPlaceholder")}
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                {t("profiles.targetWords")}
                <input
                  type="number"
                  value={form.targetWords}
                  onChange={(event) =>
                    setForm({ ...form, targetWords: Number(event.target.value) })
                  }
                  className="input mt-1"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <input
                type="checkbox"
                checked={form.isShared}
                onChange={(event) => setForm({ ...form, isShared: event.target.checked })}
                className="h-3.5 w-3.5 rounded border-slate-300"
              />
              {t("profiles.shareToSpace")}
            </label>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setForm(null)} className="btn btn-quiet">
                {t("profiles.cancel")}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={busy || !form.name.trim()}
                className="btn btn-primary"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : null}
                {t("profiles.save")}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(removing)}
        title={t("profiles.deleteTitle")}
        description={t("profiles.deleteDesc", { name: removing?.name ?? "" })}
        busy={busy}
        error={dialogError}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(null)}
      />
    </section>
  );
}
