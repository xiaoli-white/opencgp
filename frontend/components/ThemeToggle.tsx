import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "course-studio-theme";

export default function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      return;
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "切换到亮色主题" : "切换到暗色主题"}
      className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/60 bg-white/60 text-slate-500 transition hover:text-indigo-600 hover:shadow-sm dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:text-indigo-300"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}
