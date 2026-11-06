import { useCallback, useEffect, useState } from "react";
import { api, type WorkProfile } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

export function useWorkProfiles() {
  const [profiles, setProfiles] = useState<WorkProfile[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listWorkProfiles();
      setProfiles(data.profiles ?? []);
    } catch {
      setProfiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { profiles, loading, reload };
}

export function profileGenre(profile: WorkProfile | null | undefined): string {
  if (!profile) return "article";
  const id = profile.id.toLowerCase();
  if (id.includes("tutorial")) return "tutorial";
  if (id.includes("report")) return "report";
  if (id.includes("essay")) return "essay";
  if (id.includes("article")) return "article";
  const tags = profile.spec?.meta?.tags ?? [];
  // Built-in profiles may carry localized tags. Chinese keywords are written as
  // escapes so this file stays ASCII-only; English keywords are matched too.
  const hasTag = (...keywords: string[]) =>
    tags.some((tag) => keywords.some((keyword) => tag.includes(keyword)));
  if (hasTag("tutorial", "\u6559\u7a0b")) return "tutorial";
  if (hasTag("report", "research", "\u62a5\u544a", "\u7814\u7a76")) return "report";
  if (hasTag("essay", "\u968f\u7b14", "\u6563\u6587")) return "essay";
  if (hasTag("article", "long-form", "\u957f\u6587", "\u6280\u672f")) return "article";
  return "custom";
}

export default function ProfileSelect({
  value,
  profiles,
  onChange,
  disabled,
  allowNone = true,
}: {
  value: string;
  profiles: WorkProfile[];
  onChange: (profileId: string, profile: WorkProfile | null) => void;
  disabled?: boolean;
  allowNone?: boolean;
}) {
  const { t } = useI18n();
  const builtin = profiles.filter((item) => item.is_builtin);
  const mine = profiles.filter((item) => !item.is_builtin && item.is_owner);
  const shared = profiles.filter((item) => !item.is_builtin && !item.is_owner);

  const handleChange = (next: string) => {
    onChange(next, profiles.find((item) => item.id === next) ?? null);
  };

  return (
    <select
      value={value}
      onChange={(event) => handleChange(event.target.value)}
      disabled={disabled}
      className="select"
      data-profile-select="true"
    >
      {allowNone ? <option value="">{t("profiles.profileNone")}</option> : null}
      {builtin.length > 0 ? (
        <optgroup label={t("profiles.builtinGroup")}>
          {builtin.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.spec?.unit?.name ?? ""} ·{" "}
              {t("profiles.words", { count: item.spec?.unit?.default_words ?? 0 })}
            </option>
          ))}
        </optgroup>
      ) : null}
      {mine.length > 0 ? (
        <optgroup label={t("profiles.mineGroup")}>
          {mine.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.spec?.unit?.name ?? ""} ·{" "}
              {t("profiles.words", { count: item.spec?.unit?.default_words ?? 0 })}
            </option>
          ))}
        </optgroup>
      ) : null}
      {shared.length > 0 ? (
        <optgroup label={t("profiles.sharedGroup")}>
          {shared.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.spec?.unit?.name ?? ""} ·{" "}
              {t("profiles.words", { count: item.spec?.unit?.default_words ?? 0 })}
            </option>
          ))}
        </optgroup>
      ) : null}
    </select>
  );
}
