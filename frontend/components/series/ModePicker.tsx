import clsx from "clsx";
import { Check, PenLine, ShieldCheck } from "lucide-react";
import type { GenerationMode } from "@/lib/api";

type ModeOption = {
  value: GenerationMode;
  label: string;
  short: string;
  desc: string;
  icon: typeof ShieldCheck;
};

const OPTIONS: ModeOption[] = [
  {
    value: "strict",
    label: "Strict mode",
    short: "Strict",
    desc: "Every section needs an [En] source; never write without evidence",
    icon: ShieldCheck,
  },
  {
    value: "loose",
    label: "Loose mode",
    short: "Loose",
    desc: "Let the model write freely; the body is marked as written by AI",
    icon: PenLine,
  },
];

type ModePickerProps = {
  value: GenerationMode;
  onChange: (mode: GenerationMode) => void;
  variant?: "cards" | "compact";
  disabled?: boolean;
  className?: string;
};

export default function ModePicker({
  value,
  onChange,
  variant = "cards",
  disabled = false,
  className,
}: ModePickerProps) {
  if (variant === "compact") {
    return (
      <div
        className={clsx(
          "inline-flex rounded-full border border-slate-200/70 bg-white/45 p-0.5 dark:border-white/10 dark:bg-white/[0.04]",
          className,
        )}
      >
        {OPTIONS.map((option) => {
          const active = option.value === value;
          const Icon = option.icon;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              disabled={disabled}
              className={clsx(
                "flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition",
                active
                  ? "brand-gradient text-white shadow-[0_8px_18px_-12px_rgba(99,102,241,0.9)]"
                  : "text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-200",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <Icon size={10} />
              {option.short}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className={clsx("grid gap-2 sm:grid-cols-2", className)}>
      {OPTIONS.map((option) => {
        const active = option.value === value;
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            disabled={disabled}
            className={clsx(
              "group relative flex flex-col items-start gap-1 rounded-2xl border px-3 py-2.5 text-left transition",
              active
                ? "border-indigo-400/60 bg-indigo-500/12 shadow-[0_14px_30px_-24px_rgba(99,102,241,0.95)] dark:border-indigo-400/45 dark:bg-indigo-400/14"
                : "border-slate-200/70 bg-white/45 hover:border-indigo-300/60 hover:bg-white/70 dark:border-white/10 dark:bg-white/[0.03] dark:hover:border-indigo-400/30 dark:hover:bg-white/[0.06]",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <span className="flex items-center gap-1.5">
              <span
                className={clsx(
                  "grid h-5 w-5 place-items-center rounded-lg transition",
                  active
                    ? "brand-gradient text-white"
                    : "bg-slate-200/70 text-slate-500 dark:bg-white/10 dark:text-slate-300",
                )}
              >
                <Icon size={11} />
              </span>
              <span
                className={clsx(
                  "text-[12px] font-medium",
                  active
                    ? "text-indigo-700 dark:text-indigo-200"
                    : "text-slate-600 dark:text-slate-300",
                )}
              >
                {option.label}
              </span>
              {option.value === "strict" ? (
                <span className="text-[9px] text-slate-400 dark:text-slate-500">
                  Default
                </span>
              ) : null}
            </span>
            <span className="text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
              {option.desc}
            </span>
            {active ? (
              <Check
                size={11}
                className="absolute right-3 top-3 text-indigo-500 dark:text-indigo-300"
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
