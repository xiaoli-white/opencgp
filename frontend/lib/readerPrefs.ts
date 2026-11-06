export type ReaderTheme = "system" | "light" | "dark";

export type ReaderPrefs = {
  fontSize: number;
  width: number;
  theme: ReaderTheme;
  citations: boolean;
};

const STORAGE_KEY = "cs_reader";

export const FONT_MIN = 15;
export const FONT_MAX = 22;
export const WIDTHS = [640, 720, 760, 880];

export const DEFAULT_PREFS: ReaderPrefs = {
  fontSize: 17,
  width: 720,
  theme: "system",
  citations: true,
};

function clampFont(value: unknown): number {
  const size = Number(value);
  if (!Number.isFinite(size)) return DEFAULT_PREFS.fontSize;
  return Math.min(FONT_MAX, Math.max(FONT_MIN, Math.round(size)));
}

function normalizeWidth(value: unknown): number {
  const width = Number(value);
  return WIDTHS.includes(width) ? width : DEFAULT_PREFS.width;
}

function normalizeTheme(value: unknown): ReaderTheme {
  return value === "light" || value === "dark" ? value : "system";
}

export function loadReaderPrefs(): ReaderPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw) as Partial<ReaderPrefs>;
    return {
      fontSize: clampFont(parsed.fontSize),
      width: normalizeWidth(parsed.width),
      theme: normalizeTheme(parsed.theme),
      citations: parsed.citations !== false,
    };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function saveReaderPrefs(prefs: ReaderPrefs): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    return;
  }
}

export function prefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

export function applyReaderTheme(theme: ReaderTheme): void {
  const dark = theme === "system" ? prefersDark() : theme === "dark";
  document.documentElement.classList.toggle("dark", dark);
}

export const THEME_LABEL: Record<ReaderTheme, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};
