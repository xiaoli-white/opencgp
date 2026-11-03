import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus, Trash2, Wand2 } from "lucide-react";
import clsx from "clsx";
import { api, type CreationProfile } from "@/lib/api";
import { ConfirmDialog, Modal } from "@/components/common/Dialogs";

const GENRES: { value: string; label: string }[] = [
  { value: "article", label: "文章" },
  { value: "report", label: "报告" },
  { value: "essay", label: "随笔" },
  { value: "tutorial", label: "教程" },
  { value: "custom", label: "自定义" },
];

const POLICIES: { value: string; label: string }[] = [
  { value: "required", label: "必须引用" },
  { value: "optional", label: "引用可选" },
  { value: "forbidden", label: "不引用" },
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
      onError(err instanceof Error ? err.message : "创作规则加载失败");
    } finally {
      setLoading(false);
    }
  }, [onError]);

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
        onNotice("创作规则已更新");
      } else {
        await api.createCreationProfile(payload);
        onNotice("创作规则已创建");
      }
      setForm(null);
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "保存失败");
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
      onNotice("创作规则已删除");
      await load();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="creation-profiles" className="glass rounded-3xl p-5 shadow-glass">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 dark:text-slate-100">
          <Wand2 size={15} className="text-indigo-500" />
          创作规则
          <span className="chip-muted">{items.length} 个</span>
        </h2>
        <button
          type="button"
          onClick={() => {
            setDialogError("");
            setForm({ ...emptyForm });
          }}
          disabled={!canWrite}
          title={!canWrite ? "当前角色只读" : undefined}
          className="btn btn-primary px-3 py-1.5 text-[11px]"
        >
          <Plus size={12} />
          新建规则
        </button>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
        规则模板记住体裁、口吻、目标读者、引用策略与目标字数，新建长篇时一键套用。
      </p>

      {loading ? (
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          加载中…
        </div>
      ) : items.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-white/50 bg-white/40 px-3 py-6 text-center text-[11px] text-slate-400 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-500">
          还没有创作规则，新建一个可在长篇写作页直接套用。
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
                    {GENRES.find((item) => item.value === profile.genre)?.label ??
                      profile.genre}
                  </span>
                  {profile.is_shared ? <span className="chip">共享</span> : null}
                  {profile.is_owner ? (
                    <span className="chip-muted">我的</span>
                  ) : (
                    <span className="chip-muted">他人</span>
                  )}
                </p>
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
                  <span>
                    {POLICIES.find((item) => item.value === profile.citation_policy)
                      ?.label ?? profile.citation_policy}
                  </span>
                  <span>·</span>
                  <span>{profile.target_words} 字</span>
                  {profile.audience ? (
                    <>
                      <span>·</span>
                      <span>读者 {profile.audience}</span>
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
                  aria-label="编辑规则"
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
                  aria-label="删除规则"
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
        title={form?.id ? "编辑创作规则" : "新建创作规则"}
        onClose={() => setForm(null)}
      >
        {form ? (
          <div className="space-y-3">
            <label className="block text-[11px] text-slate-500 dark:text-slate-400">
              规则名称
              <input
                autoFocus
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                className="input mt-1"
                placeholder="例如：技术教程 · 严谨"
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                体裁
                <select
                  value={form.genre}
                  onChange={(event) => setForm({ ...form, genre: event.target.value })}
                  className="select mt-1"
                >
                  {GENRES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                引用策略
                <select
                  value={form.citationPolicy}
                  onChange={(event) =>
                    setForm({ ...form, citationPolicy: event.target.value })
                  }
                  className="select mt-1"
                >
                  {POLICIES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                口吻
                <input
                  value={form.tone}
                  onChange={(event) => setForm({ ...form, tone: event.target.value })}
                  className="input mt-1"
                  placeholder="例如：冷静克制"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目标读者
                <input
                  value={form.audience}
                  onChange={(event) => setForm({ ...form, audience: event.target.value })}
                  className="input mt-1"
                  placeholder="例如：后端工程师"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                视角
                <input
                  value={form.pov}
                  onChange={(event) => setForm({ ...form, pov: event.target.value })}
                  className="input mt-1"
                  placeholder="例如：第二人称"
                />
              </label>
              <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                目标字数
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
              共享给空间成员使用
            </label>
            {dialogError ? (
              <p className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-700 dark:text-rose-300">
                {dialogError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setForm(null)} className="btn btn-quiet">
                取消
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={busy || !form.name.trim()}
                className="btn btn-primary"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : null}
                保存
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(removing)}
        title="删除创作规则"
        description={`将删除规则「${removing?.name ?? ""}」，已创建的长篇不受影响。`}
        busy={busy}
        error={dialogError}
        onConfirm={() => void remove()}
        onClose={() => setRemoving(null)}
      />
    </section>
  );
}
