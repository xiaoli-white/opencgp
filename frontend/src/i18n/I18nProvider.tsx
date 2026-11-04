import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { dicts, zh, type Dict } from "./dict";
import { setActiveTranslate } from "./labels";

export type Locale = "zh" | "en";
export type I18nVars = Record<string, string | number>;
export type InlineText = { zh: string; en: string };

type I18nValue = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (path: string, vars?: I18nVars) => string;
  tm: (map: InlineText) => string;
};

const STORAGE_KEY = "cs_locale";

const I18nContext = createContext<I18nValue | null>(null);

function detectLocale(): Locale {
  if (typeof window === "undefined") return "zh";
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "zh" || saved === "en") return saved;
  } catch {
    return "zh";
  }
  const lang = (window.navigator.language || "zh").toLowerCase();
  return lang.startsWith("zh") ? "zh" : "en";
}

function resolve(tree: Dict, path: string): string | undefined {
  let cursor: unknown = tree;
  for (const part of path.split(".")) {
    if (cursor === null || typeof cursor !== "object") return undefined;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return typeof cursor === "string" ? cursor : undefined;
}

import { setFormatLocale } from "@/lib/format";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    setFormatLocale(locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      return;
    }
  }, []);

  const t = useCallback(
    (path: string, vars?: I18nVars) => {
      const raw = resolve(dicts[locale], path) ?? resolve(zh, path);
      if (raw === undefined) {
        if (import.meta.env.DEV) {
          console.warn(`[i18n] missing key: ${path}`);
        }
        return path;
      }
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (match, key: string) =>
        key in vars ? String(vars[key]) : match,
      );
    },
    [locale],
  );

  const tm = useCallback(
    (map: InlineText) => (locale === "en" ? map.en : map.zh),
    [locale],
  );

  useEffect(() => {
    setActiveTranslate(t);
  }, [t]);

  const value = useMemo<I18nValue>(
    () => ({ locale, setLocale, t, tm }),
    [locale, setLocale, t, tm],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
