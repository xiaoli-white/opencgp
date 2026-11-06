"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, PlayCircle, XCircle } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";

type Block = {
  index: number;
  language: string;
  ok: boolean;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
};

type Result = {
  unit_id: string;
  blocks: Block[];
  summary: { total: number; executed: number; passed: number; failed: number; skipped: number; backend: string };
};

export default function CodeCheckPanel({ unitId, disabled }: { unitId: string; disabled?: boolean }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      const data = (await api.checkUnitCode(unitId)) as Result;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("series.code.failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          if (!open && !result) void run();
        }}
        disabled={disabled}
        className="btn btn-ghost"
        title={disabled ? t("series.guardReadOnly") : t("series.code.title")}
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
        {t("series.code.button")}
      </button>

      {open && (
        <div className="mt-3 rounded-2xl border border-slate-200/70 bg-white/60 p-4 dark:border-white/10 dark:bg-white/[0.04]">
          {error ? (
            <p className="flex items-start gap-2 text-xs text-rose-600 dark:text-rose-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              {error}
            </p>
          ) : null}
          {loading ? (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t("series.code.running")}
            </p>
          ) : null}
          {result && !loading ? (
            <>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                <span className="chip-muted">{result.summary.backend}</span>
                <span>{t("series.code.blocks", { count: result.summary.total })}</span>
                <span className="text-emerald-600 dark:text-emerald-400">
                  {t("series.code.passed", { count: result.summary.passed })}
                </span>
                <span className="text-rose-600 dark:text-rose-400">
                  {t("series.code.failedCount", { count: result.summary.failed })}
                </span>
                {result.summary.skipped > 0 ? (
                  <span>{t("series.code.skipped", { count: result.summary.skipped })}</span>
                ) : null}
              </div>
              <div className="mt-3 space-y-2">
                {result.blocks.map((block) => (
                  <div
                    key={block.index}
                    className="rounded-xl border border-slate-200/60 bg-white/70 p-3 dark:border-white/10 dark:bg-white/[0.03]"
                  >
                    <div className="flex items-center gap-2 text-[11px]">
                      {block.ok ? (
                        <CheckCircle2 size={13} className="text-emerald-500" />
                      ) : (
                        <XCircle size={13} className="text-rose-500" />
                      )}
                      <span className="font-medium text-slate-600 dark:text-slate-300">
                        {t("series.code.block", { index: block.index + 1 })} ·{" "}
                        {block.language}
                      </span>
                      <span className="text-slate-400">
                        exit {block.exit_code} · {block.duration_ms}ms
                      </span>
                    </div>
                    {block.stdout ? (
                      <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-900/90 p-2 text-[11px] leading-relaxed text-slate-100">
                        {block.stdout}
                      </pre>
                    ) : null}
                    {block.stderr ? (
                      <pre
                        className={clsx(
                          "mt-1 max-h-32 overflow-auto rounded-lg p-2 text-[11px] leading-relaxed",
                          "bg-rose-500/10 text-rose-700 dark:text-rose-300",
                        )}
                      >
                        {block.stderr}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
