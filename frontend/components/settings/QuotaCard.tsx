import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Loader2, ShieldCheck } from "lucide-react";
import { api, type Quota, type QuotaUsage } from "@/lib/api";
import { useSession } from "@/components/auth/SessionProvider";
import { useI18n } from "@/i18n/I18nProvider";

function formatBytes(value: number): string {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function QuotaCard({
  onNotice,
  onError,
}: {
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { can, roleName } = useSession();
  const { t } = useI18n();
  const canQuota = can("manage_quota");

  const [quota, setQuota] = useState<Quota | null>(null);
  const [busy, setBusy] = useState(false);
  const [limits, setLimits] = useState<QuotaUsage>({
    monthly_generations: 0,
    monthly_uploads: 0,
    storage_bytes: 0,
  });
  const [unlimited, setUnlimited] = useState({
    generations: false,
    uploads: false,
    storage: false,
  });

  const applyQuota = useCallback((next: Quota) => {
    setQuota(next);
    setLimits(next.limits);
    setUnlimited({
      generations:
        Boolean(next.unlimited?.generations) || (next.limits?.monthly_generations ?? 1) <= 0,
      uploads: Boolean(next.unlimited?.uploads) || (next.limits?.monthly_uploads ?? 1) <= 0,
      storage: Boolean(next.unlimited?.storage) || (next.limits?.storage_bytes ?? 1) <= 0,
    });
  }, []);

  const load = useCallback(async () => {
    try {
      applyQuota(await api.getQuota());
    } catch (err) {
      onError(err instanceof Error ? err.message : t("quotas.loadFailed"));
    }
  }, [applyQuota, onError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const saveQuota = async () => {
    setBusy(true);
    onError("");
    onNotice("");
    try {
      const next = await api.updateQuota({
        monthly_generations: unlimited.generations ? 0 : limits.monthly_generations,
        monthly_uploads: unlimited.uploads ? 0 : limits.monthly_uploads,
        storage_bytes: unlimited.storage ? 0 : limits.storage_bytes,
      });
      applyQuota(next);
      onNotice(t("quotas.updated"));
    } catch (err) {
      onError(err instanceof Error ? err.message : t("quotas.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl p-5 shadow-glass"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={15} className="text-indigo-500 dark:text-indigo-300" />
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">
          {t("quotas.title")}
        </h2>
        {quota ? <span className="chip-muted">{t("quotas.period", { period: quota.period })}</span> : null}
        <span className="chip-muted">{roleName || t("common.readOnly")}</span>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {[
          {
            key: "monthly_generations" as const,
            flag: "generations" as const,
            usageKey: "generations" as const,
            label: t("quotas.generations"),
          },
          {
            key: "monthly_uploads" as const,
            flag: "uploads" as const,
            usageKey: "uploads" as const,
            label: t("quotas.uploads"),
          },
          {
            key: "storage_bytes" as const,
            flag: "storage" as const,
            usageKey: "storage_bytes" as const,
            label: t("quotas.storage"),
          },
        ].map((field) => {
          const isUnlimited = unlimited[field.flag];
          const limitValue = limits[field.key];
          const remaining = quota?.remaining?.[field.usageKey];
          const used = quota?.usage?.[field.usageKey] ?? 0;
          const unlimitedFlag =
            Boolean(quota?.unlimited?.[field.flag]) ||
            (limitValue ?? 0) <= 0 ||
            (remaining ?? 0) < 0;
          const percent =
            unlimitedFlag || !limitValue
              ? 100
              : Math.min(100, Math.round((used / limitValue) * 100));
          return (
            <div key={field.key} className="block">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[11px] text-slate-500 dark:text-slate-400">
                  {field.label}
                  {field.key === "storage_bytes" ? t("quotas.storageMb") : ""}
                </span>
                <label className="flex cursor-pointer items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                  <input
                    type="checkbox"
                    checked={isUnlimited}
                    onChange={(event) =>
                      setUnlimited((prev) => ({ ...prev, [field.flag]: event.target.checked }))
                    }
                    disabled={!canQuota}
                    className="h-3 w-3 accent-indigo-500"
                  />
                  {t("quotas.unlimited")}
                </label>
              </div>
              <input
                type="number"
                min={0}
                step={1}
                value={
                  field.key === "storage_bytes"
                    ? Number((limitValue / 1024 / 1024).toFixed(1))
                    : limitValue
                }
                onChange={(event) => {
                  const raw = Number(event.target.value) || 0;
                  setLimits((prev) => ({
                    ...prev,
                    [field.key]:
                      field.key === "storage_bytes" ? Math.round(raw * 1024 * 1024) : raw,
                  }));
                }}
                disabled={!canQuota || isUnlimited}
                className="input disabled:opacity-50"
                placeholder={isUnlimited ? t("quotas.unlimitedShort") : ""}
              />
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-400/20">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <span className="mt-1 block text-[10px] text-slate-400">
                {unlimitedFlag
                  ? t("quotas.usedUnlimited", {
                      used: field.key === "storage_bytes" ? formatBytes(used) : used,
                    })
                  : t("quotas.usedOf", {
                      used: field.key === "storage_bytes" ? formatBytes(used) : used,
                      limit:
                        field.key === "storage_bytes" ? formatBytes(limitValue) : limitValue,
                    })}
              </span>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={() => void saveQuota()}
        disabled={!canQuota || busy}
        title={canQuota ? "" : t("quotas.noQuota")}
        className="btn btn-primary mt-4"
      >
        {busy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
        {t("quotas.save")}
      </button>
    </motion.section>
  );
}
