import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FlaskConical,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  X,
} from "lucide-react";
import clsx from "clsx";
import {
  api,
  type ProfileSample,
  type ProfileScope,
  type ProfileSpec,
  type ProfileValidation,
  type ProfileValidationIssue,
  type WorkProfile,
} from "@/lib/api";
import { Modal } from "@/components/common/Dialogs";
import { useI18n } from "@/i18n/I18nProvider";
import {
  policyLabel,
  povLabel,
  profileNameLabel,
  strictnessLabel,
  tenseLabel,
  validatorLabel,
} from "@/i18n/labels";

const VALIDATORS = ["citation", "length", "structure", "continuity"];
const PROMPT_FIELDS = ["system", "outline", "unit", "revise"] as const;

type PromptForm = {
  system: string;
  outline: string;
  unit: string;
  revise: string;
};

type EditorForm = {
  name: string;
  description: string;
  tagsText: string;
  unitName: string;
  unitPlural: string;
  minUnits: number;
  maxUnits: number;
  defaultWords: number;
  depth: number;
  sectionsMin: number;
  sectionsMax: number;
  requiresOutline: boolean;
  tone: string;
  pov: string;
  tense: string;
  forbiddenText: string;
  citationPolicy: string;
  allowWeb: boolean;
  glossary: boolean;
  settingBook: boolean;
  characterSheet: boolean;
  autoImages: boolean;
  maxImages: number;
  imageStyle: string;
  validators: string[];
  strictness: string;
  prompts: PromptForm;
};

const EMPTY_FORM: EditorForm = {
  name: "",
  description: "",
  tagsText: "",
  unitName: "Unit",
  unitPlural: "Units",
  minUnits: 1,
  maxUnits: 60,
  defaultWords: 900,
  depth: 2,
  sectionsMin: 2,
  sectionsMax: 5,
  requiresOutline: true,
  tone: "",
  pov: "third_limited",
  tense: "present",
  forbiddenText: "",
  citationPolicy: "optional",
  allowWeb: false,
  glossary: false,
  settingBook: false,
  characterSheet: false,
  autoImages: true,
  maxImages: 3,
  imageStyle: "",
  validators: ["citation"],
  strictness: "normal",
  prompts: { system: "", outline: "", unit: "", revise: "" },
};

function splitList(value: string): string[] {
  return value
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toInt(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/**
 * Number inputs that survive being emptied.
 *
 * Parsing on every keystroke with a hard-coded fallback makes a field snap back
 * to that fallback the moment the user selects everything and deletes it, so the
 * value can never be retyped. This keeps a draft string while editing, commits
 * only parseable numbers, and restores the last valid value on blur.
 */
function useNumberDraft(value: number, commit: (next: number) => void) {
  const [draft, setDraft] = useState<string | null>(null);
  const lastValid = useRef(value);
  useEffect(() => {
    lastValid.current = value;
  }, [value]);
  return {
    value: draft ?? String(value),
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      const raw = event.target.value;
      setDraft(raw);
      const parsed = Number.parseInt(raw, 10);
      if (raw.trim() !== "" && Number.isFinite(parsed)) {
        lastValid.current = parsed;
        commit(parsed);
      }
    },
    onBlur: () => {
      if (draft !== null && draft.trim() === "") commit(lastValid.current);
      setDraft(null);
    },
  };
}

function toBool(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function clampImages(value: number): number {
  if (!Number.isFinite(value)) return 3;
  return Math.min(6, Math.max(1, Math.round(value)));
}

function formFromProfile(profile: WorkProfile | null): EditorForm {
  if (!profile) return { ...EMPTY_FORM, prompts: { ...EMPTY_FORM.prompts } };
  const spec = profile.spec ?? {};
  const sections = spec.structure?.sections_per_unit ?? [];
  const strictness = spec.validation?.strictness ?? "normal";
  return {
    name: profile.name,
    description: profile.description ?? spec.meta?.description ?? "",
    tagsText: (spec.meta?.tags ?? []).join(", "),
    unitName: spec.unit?.name ?? "Unit",
    unitPlural: spec.unit?.plural ?? spec.unit?.name ?? "Units",
    minUnits: spec.unit?.min_units ?? 1,
    maxUnits: spec.unit?.max_units ?? 60,
    defaultWords: spec.unit?.default_words ?? 900,
    depth: spec.structure?.depth ?? 2,
    sectionsMin: sections[0] ?? 2,
    sectionsMax: sections[1] ?? 5,
    requiresOutline: toBool(spec.structure?.requires_outline, true),
    tone: spec.voice?.tone ?? "",
    pov: spec.voice?.pov ?? "third_limited",
    tense: spec.voice?.tense ?? "present",
    forbiddenText: (spec.voice?.forbidden_phrases ?? []).join(", "),
    citationPolicy: spec.grounding?.citation_policy ?? "optional",
    allowWeb: toBool(spec.grounding?.allow_web, false),
    glossary: toBool(spec.assets?.glossary, false),
    settingBook: toBool(spec.assets?.setting_book, false),
    characterSheet: toBool(spec.assets?.character_sheet, false),
    autoImages: toBool(spec.assets?.auto_images, true),
    maxImages: clampImages(spec.assets?.max_images ?? 3),
    imageStyle: spec.assets?.style ?? "",
    validators: spec.validation?.validators ?? ["citation"],
    strictness: strictness === "loose" ? "relaxed" : strictness,
    prompts: {
      system: spec.prompts?.system ?? "",
      outline: spec.prompts?.outline ?? "",
      unit: spec.prompts?.unit ?? "",
      revise: spec.prompts?.revise ?? "",
    },
  };
}

function buildSpec(form: EditorForm): ProfileSpec {
  return {
    meta: {
      name: form.name.trim(),
      description: form.description.trim(),
      tags: splitList(form.tagsText),
      icon: "book",
    },
    unit: {
      name: form.unitName.trim(),
      plural: form.unitPlural.trim() || form.unitName.trim(),
      min_units: form.minUnits,
      max_units: form.maxUnits,
      default_words: form.defaultWords,
    },
    structure: {
      depth: form.depth,
      sections_per_unit: [form.sectionsMin, form.sectionsMax],
      requires_outline: form.requiresOutline,
    },
    voice: {
      tone: form.tone.trim(),
      pov: form.pov,
      tense: form.tense,
      forbidden_phrases: splitList(form.forbiddenText),
    },
    grounding: {
      citation_policy: form.citationPolicy,
      allow_web: form.allowWeb,
    },
    assets: {
      glossary: form.glossary,
      setting_book: form.settingBook,
      character_sheet: form.characterSheet,
      auto_images: form.autoImages,
      max_images: form.maxImages,
      style: form.imageStyle.trim(),
    },
    validation: {
      validators: form.validators,
      strictness: form.strictness === "relaxed" ? "loose" : form.strictness,
    },
    prompts: {
      system: form.prompts.system,
      outline: form.prompts.outline,
      unit: form.prompts.unit,
      revise: form.prompts.revise,
    },
    export: {
      default_format: "md",
      include_citations: form.citationPolicy === "required",
    },
  };
}

function localErrors(form: EditorForm): ProfileValidationIssue[] {
  const issues: ProfileValidationIssue[] = [];
  if (!form.name.trim()) {
    issues.push({ path: "name", message: "PROFILE_NAME_REQUIRED" });
  }
  if (!form.unitName.trim()) {
    issues.push({ path: "unit.name", message: "PROFILE_UNIT_REQUIRED" });
  }
  if (form.maxUnits < form.minUnits) {
    issues.push({ path: "unit.max_units", message: "PROFILE_UNIT_RANGE" });
  }
  if (form.sectionsMax < form.sectionsMin) {
    issues.push({
      path: "structure.sections_per_unit",
      message: "PROFILE_SECTIONS_RANGE",
    });
  }
  if (form.depth < 1 || form.depth > 4) {
    issues.push({ path: "structure.depth", message: "PROFILE_DEPTH_RANGE" });
  }
  return issues;
}

function Section({
  title,
  children,
  hint,
}: {
  title: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <section className="rounded-2xl border border-white/60 bg-white/55 p-3.5 shadow-[0_10px_28px_-22px_rgba(15,23,42,0.45)] dark:border-white/10 dark:bg-white/[0.04]">
      <h3 className="text-[12px] font-semibold text-slate-700 dark:text-slate-200">
        {title}
      </h3>
      {hint ? (
        <p className="mt-0.5 text-[10.5px] leading-relaxed text-slate-400 dark:text-slate-500">
          {hint}
        </p>
      ) : null}
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[11.5px] text-slate-600 dark:text-slate-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 rounded border-slate-300 accent-indigo-500"
      />
      {label}
    </label>
  );
}

function SamplePanel({
  t,
  topic,
  onTopic,
  onStart,
  onCopy,
  onRegenerate,
  running,
  copied,
  error,
  sample,
  canRun,
}: {
  t: (path: string, vars?: Record<string, string | number>) => string;
  topic: string;
  onTopic: (value: string) => void;
  onStart: () => void;
  onCopy: () => void;
  onRegenerate: () => void;
  running: boolean;
  copied: boolean;
  error: string;
  sample: ProfileSample | null;
  canRun: boolean;
}) {
  const [openChip, setOpenChip] = useState<string | null>(null);
  const totalIssues = (sample?.validation?.results ?? []).reduce(
    (total, item) => total + item.issues.length,
    0,
  );
  const chipRowRef = useRef<HTMLDivElement | null>(null);
  const [summaryOffset, setSummaryOffset] = useState(0);
  useLayoutEffect(() => {
    const row = chipRowRef.current;
    if (!row) return;
    const chips = row.querySelectorAll("[data-sample-chip]");
    if (chips.length < 2) {
      setSummaryOffset(0);
      return;
    }
    setSummaryOffset(Math.round(chips[1].getBoundingClientRect().x - row.getBoundingClientRect().x));
  }, [sample, sample?.validation?.results?.length]);
  const openDetail = openChip
    ? (sample?.validation?.results ?? []).find((item) => item.name === openChip) ?? null
    : null;

  return (
    <div
      data-sample-panel="true"
      className="mb-2.5 min-w-0 rounded-2xl border border-white/60 bg-white/60 p-3 dark:border-white/10 dark:bg-white/[0.04]"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-slate-700 dark:text-slate-200">
          <FlaskConical size={12} className="text-indigo-500" />
          {t("profiles.sample")}
        </span>
        <span className="min-w-0 break-words text-[10px] text-slate-400 dark:text-slate-500">
          {t("profiles.sampleHint")}
        </span>
      </div>
      <div className="mt-2 flex min-w-0 flex-wrap items-end gap-2">
        <label className="min-w-0 flex-1 text-[10.5px] text-slate-500 dark:text-slate-400">
          {t("profiles.sampleTopic")}
          <input
            value={topic}
            onChange={(event) => onTopic(event.target.value)}
            className="input mt-1 h-8 text-[11.5px]"
            placeholder={t("profiles.sampleTopicPlaceholder")}
            data-field="sample.topic"
          />
        </label>
        <button
          type="button"
          onClick={onStart}
          disabled={running || !canRun}
          className="btn btn-primary px-2.5 py-1 text-[10.5px]"
          data-action="sample-start"
        >
          {running ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
          {running ? t("profiles.sampleRunning") : t("profiles.sampleStart")}
        </button>
      </div>

      {!canRun && !sample ? (
        <p className="mt-2 text-[10.5px] text-amber-600 dark:text-amber-300">
          {t("profiles.sampleNeedSave")}
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 break-words rounded-xl border border-rose-400/40 bg-rose-500/10 px-2.5 py-2 text-[10.5px] text-rose-700 dark:text-rose-300">
          {error}
        </p>
      ) : null}

      {running ? (
        <div className="mt-2 space-y-1.5" data-sample-loading="true">
          <div className="h-2.5 w-1/3 animate-pulse rounded-full bg-slate-200/80 dark:bg-white/10" />
          <div className="h-2.5 w-full animate-pulse rounded-full bg-slate-200/70 dark:bg-white/[0.08]" />
          <div className="h-2.5 w-11/12 animate-pulse rounded-full bg-slate-200/70 dark:bg-white/[0.08]" />
          <div className="h-2.5 w-9/12 animate-pulse rounded-full bg-slate-200/70 dark:bg-white/[0.08]" />
        </div>
      ) : null}

      {sample && !running ? (
        <div className="mt-2 min-w-0 space-y-2">
          <div className="rounded-xl border border-white/60 bg-white/70 p-2.5 dark:border-white/10 dark:bg-slate-950/40">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
                {t("profiles.sample")}
              </span>
              <span
                className="break-words font-mono text-[10px] text-slate-500 dark:text-slate-400"
                data-sample-meta="true"
              >
                {t("profiles.sampleMeta", {
                  chars: sample.chars,
                  secs: (sample.elapsed_ms / 1000).toFixed(1),
                  model: sample.model || "-",
                })}
              </span>
            </div>
            <div
              className="mt-1.5 max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-[11.5px] leading-relaxed text-slate-700 dark:text-slate-200"
              data-sample-text="true"
            >
              {sample.text}
            </div>
          </div>

          <div className="flex min-w-0 flex-wrap items-start gap-1.5" ref={chipRowRef}>
            {(sample.skipped ?? []).map((name) => (
              <span
                key={`skipped-${name}`}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300/60 bg-slate-500/5 px-2 py-0.5 font-mono text-[10px] text-slate-500 dark:border-white/10 dark:text-slate-400"
                data-sample-chip={name}
                data-verdict="skipped"
                title={t("profiles.sampleSkipped")}
              >
                {name}
                <span>{t("profiles.sampleSkippedChip")}</span>
              </span>
            ))}
            {(sample.validation?.results ?? []).map((item) => {
              const verdict = !item.passed
                ? "fail"
                : item.issues.some((issue) => issue.level === "warning")
                  ? "warn"
                  : "pass";
              const symbol = verdict === "pass" ? "✓" : verdict === "warn" ? "⚠" : "✗";
              const active = openChip === item.name;
              return (
                <div key={item.name} className="flex min-w-0 flex-col items-start gap-1">
                  <button
                    type="button"
                    onClick={() => setOpenChip(active ? null : item.name)}
                    className={clsx(
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] transition",
                      verdict === "pass"
                        ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        : verdict === "warn"
                          ? "border-amber-400/40 bg-amber-400/10 text-amber-700 dark:text-amber-300"
                          : "border-rose-400/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
                    )}
                    data-sample-chip={item.name}
                    data-verdict={verdict}
                  >
                    <span>{validatorLabel(t, item.name)}</span>
                    <span>{symbol}</span>
                  </button>
                  {active ? (
                    <div
                      className="max-w-[260px] break-words text-[10px] leading-relaxed text-slate-500 dark:text-slate-400"
                      data-sample-detail={item.name}
                    >
                      {item.issues.length === 0
                        ? t("profiles.sampleNoIssues")
                        : item.issues
                            .map((issue) =>
                              issue.where ? `${issue.where}: ${issue.message}` : issue.message,
                            )
                            .join(" · ")}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div
            className="mt-1 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400"
            style={{ paddingLeft: summaryOffset }}
            data-sample-summary="true"
          >
            {totalIssues === 0
              ? t("profiles.sampleNoIssues")
              : t("profiles.sampleIssues", { count: totalIssues })}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={onCopy}
              className="btn btn-quiet px-2 py-1 text-[10.5px]"
              data-action="sample-copy"
            >
              <Copy size={11} />
              {copied ? t("profiles.sampleCopied") : t("profiles.sampleCopy")}
            </button>
            <button
              type="button"
              onClick={onRegenerate}
              className="btn btn-quiet px-2 py-1 text-[10.5px]"
              data-action="sample-regenerate"
            >
              <RefreshCw size={11} />
              {t("profiles.sampleRegenerate")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function ProfileEditor({
  open,
  profile,
  onClose,
  onSaved,
  inline = false,
  scopeOptions,
  defaultScope = "user",
}: {
  open: boolean;
  profile: WorkProfile | null;
  onClose: () => void;
  onSaved: (profile: WorkProfile) => void;
  inline?: boolean;
  scopeOptions?: { value: ProfileScope; label: string }[];
  defaultScope?: ProfileScope;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<EditorForm>(EMPTY_FORM);
  const [scope, setScope] = useState<ProfileScope>(defaultScope);
  const [validation, setValidation] = useState<ProfileValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [savedNotice, setSavedNotice] = useState("");
  const [savedId, setSavedId] = useState("");
  const [showPrompts, setShowPrompts] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<{
    system_prompt: string;
    outline_prompt: string;
    unit_prompt: string;
  } | null>(null);
  const [sampleOpen, setSampleOpen] = useState(false);
  const [sampleTopic, setSampleTopic] = useState("");
  const [sample, setSample] = useState<ProfileSample | null>(null);
  const [sampleError, setSampleError] = useState("");
  const [sampling, setSampling] = useState(false);
  const [sampleCopied, setSampleCopied] = useState(false);

  const profileKey = profile?.id ?? "";

  useEffect(() => {
    if (!open) return;
    setForm(formFromProfile(profile));
    setScope((profile?.scope as ProfileScope) ?? defaultScope);
    setValidation(null);
    setFormError("");
    setSavedNotice("");
    setSavedId(profile?.id ?? "");
    setShowPrompts(false);
    setPreview(null);
    setSampleOpen(false);
    setSample(null);
    setSampleError("");
    setSampleTopic(profile ? profileNameLabel(t, profile) : "");
  }, [open, profileKey, defaultScope]);

  const spec = useMemo(() => buildSpec(form), [form]);
  const specJson = useMemo(() => JSON.stringify(spec, null, 2), [spec]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        if (cancelled) return;
        setValidating(true);
        try {
          const result = await api.validateWorkProfile(spec);
          if (!cancelled) setValidation(result);
        } catch (err) {
          if (!cancelled) {
            setValidation({
              ok: false,
              errors: [
                {
                  path: "",
                  message:
                    err instanceof Error ? err.message : t("profiles.validationFailed"),
                },
              ],
              warnings: [],
              spec,
            });
          }
        } finally {
          if (!cancelled) setValidating(false);
        }
      })();
    }, 500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, spec, t]);

  const errors = validation?.errors ?? [];
  const warnings = validation?.warnings ?? [];

  const errorsFor = (path: string) =>
    errors.filter((item) => item.path === path).map((item) => item.message);

  const minUnitsField = useNumberDraft(form.minUnits, (next) => update("minUnits", next));
  const maxUnitsField = useNumberDraft(form.maxUnits, (next) => update("maxUnits", next));
  const defaultWordsField = useNumberDraft(form.defaultWords, (next) =>
    update("defaultWords", next),
  );
  const depthField = useNumberDraft(form.depth, (next) => update("depth", next));
  const sectionsMinField = useNumberDraft(form.sectionsMin, (next) =>
    update("sectionsMin", next),
  );
  const sectionsMaxField = useNumberDraft(form.sectionsMax, (next) =>
    update("sectionsMax", next),
  );
  const fieldClass = (path: string, base = "input mt-1") =>
    clsx(base, errorsFor(path).length > 0 && "border-rose-400 ring-1 ring-rose-300/60");

  const errorText = (path: string) => {
    const list = errorsFor(path);
    if (list.length === 0) return null;
    return (
      <span className="mt-1 block text-[10.5px] text-rose-600 dark:text-rose-300">
        {list.map((message) => (message.startsWith("PROFILE_") ? t(`profiles.${message}`) : message)).join("；")}
      </span>
    );
  };

  const update = <K extends keyof EditorForm>(key: K, value: EditorForm[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSavedNotice("");
  };

  const updatePrompt = (key: keyof PromptForm, value: string) => {
    setForm((prev) => ({ ...prev, prompts: { ...prev.prompts, [key]: value } }));
    setSavedNotice("");
  };

  const toggleValidator = (value: string) => {
    setForm((prev) => ({
      ...prev,
      validators: prev.validators.includes(value)
        ? prev.validators.filter((item) => item !== value)
        : [...prev.validators, value],
    }));
    setSavedNotice("");
  };

  const save = async () => {
    setFormError("");
    setSavedNotice("");
    const local = localErrors(form);
    if (local.length > 0) {
      setValidation({
        ok: false,
        errors: local,
        warnings,
        spec,
      });
      setFormError(t("profiles.validationIssues", { count: local.length }));
      return;
    }
    setSaving(true);
    try {
      const remote = await api.validateWorkProfile(spec);
      setValidation(remote);
      if (!remote.ok) {
        setFormError(t("profiles.validationIssues", { count: remote.errors.length }));
        return;
      }
      const targetId = profile?.id || savedId;
      const base = {
        name: form.name.trim(),
        description: form.description.trim(),
        spec,
      };
      const saved = targetId
        ? await api.updateWorkProfile(targetId, base)
        : await api.createWorkProfile({ ...base, scope });
      setSavedId(saved.id);
      onSaved(saved);
      setSavedNotice(t("profiles.saved"));
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t("profiles.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const openPreview = async () => {
    setFormError("");
    const targetId = profile?.id || savedId;
    if (!targetId) {
      setFormError(t("profiles.previewUnavailable"));
      return;
    }
    setPreviewLoading(true);
    try {
      const data = await api.previewWorkProfile(targetId);
      setPreview({
        system_prompt: data.system_prompt ?? "",
        outline_prompt: data.outline_prompt ?? "",
        unit_prompt: data.unit_prompt ?? "",
      });
      setPreviewOpen(true);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t("profiles.previewFailed"));
    } finally {
      setPreviewLoading(false);
    }
  };

  const sampleReady = Boolean(profile?.id || savedId);

  const runSample = async () => {
    const targetId = profile?.id || savedId;
    if (!targetId) {
      setSampleError(t("profiles.sampleNeedSave"));
      return;
    }
    setSampling(true);
    setSampleError("");
    setSampleCopied(false);
    try {
      const data = await api.sampleWorkProfile(targetId, {
        topic: sampleTopic.trim() || form.name.trim(),
        chars: 300,
      });
      setSample(data);
    } catch (err) {
      setSampleError(err instanceof Error ? err.message : t("profiles.sampleFailed"));
    } finally {
      setSampling(false);
    }
  };

  const copySample = async () => {
    if (!sample?.text) return;
    try {
      await navigator.clipboard.writeText(sample.text);
      setSampleCopied(true);
      window.setTimeout(() => setSampleCopied(false), 2000);
    } catch {
      setSampleCopied(false);
    }
  };

  const toggleSample = () => {
    setSampleOpen((prev) => {
      if (!prev && !sampleTopic.trim()) setSampleTopic(form.name.trim());
      return !prev;
    });
  };

  const statusPill = validating ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/60 bg-white/70 px-2 py-0.5 text-[10.5px] text-slate-500 dark:border-white/10 dark:bg-white/[0.06] dark:text-slate-300">
      <Loader2 size={10} className="animate-spin" />
      {t("profiles.validating")}
    </span>
  ) : validation?.ok ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2 py-0.5 text-[10.5px] font-medium text-emerald-700 dark:text-emerald-300">
      <Check size={10} />
      {t("profiles.validationPassed")}
    </span>
  ) : validation ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-rose-400/40 bg-rose-500/10 px-2 py-0.5 text-[10.5px] font-medium text-rose-700 dark:text-rose-300">
      <AlertCircle size={10} />
      {t("profiles.validationIssues", { count: validation.errors.length })}
    </span>
  ) : null;

  const shell = (
    <div
      className={
        inline
          ? "flex min-w-0 flex-col overflow-hidden rounded-2xl border border-white/60 bg-white/55 dark:border-white/10 dark:bg-white/[0.04]"
          : "flex h-full w-full flex-col bg-[#f6f8fc] dark:bg-[#0b1020]"
      }
      data-profile-editor={inline ? "inline" : "overlay"}
    >
            <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/60 bg-white/70 px-3 py-2.5 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/70 sm:px-5">
              <div className="min-w-0">
                <h2 className="truncate text-[13px] font-semibold text-slate-800 dark:text-slate-100 sm:text-sm">
                  {profile ? t("profiles.editorTitleEdit") : t("profiles.editorTitleCreate")}
                </h2>
                <p className="mt-0.5 truncate text-[10.5px] text-slate-400">
                  {t("profiles.editorHint")}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="btn-quiet grid h-8 w-8 shrink-0 place-items-center rounded-full"
                aria-label={t("common.close")}
              >
                <X size={15} />
              </button>
            </header>

            <div className={inline ? "min-h-0 flex-1" : "min-h-0 flex-1 overflow-y-auto"}>
              <div className="grid gap-4 px-3 py-4 sm:px-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                <div className="min-w-0 space-y-3">
                  <Section title={t("profiles.basicSection")}>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldName")}
                      <input
                        value={form.name}
                        onChange={(event) => update("name", event.target.value)}
                        className={fieldClass("name")}
                        placeholder={t("profiles.namePlaceholder")}
                        data-field="name"
                      />
                      {errorText("name")}
                    </label>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldDescription")}
                      <input
                        value={form.description}
                        onChange={(event) => update("description", event.target.value)}
                        className={fieldClass("meta.description")}
                        placeholder={t("profiles.descriptionPlaceholder")}
                      />
                      {errorText("meta.description")}
                    </label>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldTags")}
                      <input
                        value={form.tagsText}
                        onChange={(event) => update("tagsText", event.target.value)}
                        className={fieldClass("meta.tags")}
                        placeholder={t("profiles.tagsPlaceholder")}
                      />
                      {errorText("meta.tags")}
                    </label>
                    {scopeOptions && scopeOptions.length > 0 ? (
                      <div data-field="scope">
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          {t("serverProfiles.scopeLabel")}
                        </p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                          {scopeOptions.map((option) => (
                            <label
                              key={option.value}
                              className={clsx(
                                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10.5px] transition",
                                scope === option.value
                                  ? "border-indigo-400/60 bg-indigo-500/15 text-indigo-700 dark:text-indigo-200"
                                  : "border-white/60 bg-white/50 text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400",
                                profile ? "opacity-70" : "cursor-pointer",
                              )}
                            >
                              <input
                                type="radio"
                                name="profile-scope"
                                value={option.value}
                                checked={scope === option.value}
                                disabled={Boolean(profile)}
                                onChange={() => setScope(option.value)}
                                className="h-3 w-3 accent-indigo-500"
                              />
                              {option.label}
                            </label>
                          ))}
                        </div>
                        {profile ? (
                          <p className="mt-1 text-[10px] text-slate-400 dark:text-slate-500">
                            {t("serverProfiles.scopeLocked")}
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </Section>

                  <Section title={t("profiles.unitSection")}>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldUnitName")}
                        <input
                          value={form.unitName}
                          onChange={(event) => update("unitName", event.target.value)}
                          className={fieldClass("unit.name")}
                          placeholder={t("profiles.unitNamePlaceholder")}
                          data-field="unit.name"
                        />
                        {errorText("unit.name")}
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldUnitPlural")}
                        <input
                          value={form.unitPlural}
                          onChange={(event) => update("unitPlural", event.target.value)}
                          className={fieldClass("unit.plural")}
                          placeholder={t("profiles.unitPluralPlaceholder")}
                        />
                        {errorText("unit.plural")}
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldMinUnits")}
                        <input
                          type="number"
                          min={1}
                          max={200}
                          {...minUnitsField}
                          className={fieldClass("unit.min_units")}
                        />
                        {errorText("unit.min_units")}
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldMaxUnits")}
                        <input
                          type="number"
                          min={1}
                          max={200}
                          {...maxUnitsField}
                          className={fieldClass("unit.max_units")}
                        />
                        {errorText("unit.max_units")}
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldDefaultWords")}
                        <input
                          type="number"
                          min={100}
                          max={20000}
                          step={100}
                          {...defaultWordsField}
                          className={fieldClass("unit.default_words")}
                          data-field="unit.default_words"
                        />
                        {errorText("unit.default_words")}
                      </label>
                    </div>
                  </Section>

                  <Section title={t("profiles.structureSection")}>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldDepth")}
                        <input
                          type="number"
                          min={1}
                          max={4}
                          {...depthField}
                          className={fieldClass("structure.depth")}
                        />
                        {errorText("structure.depth")}
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldSectionsMin")}
                        <input
                          type="number"
                          min={1}
                          max={20}
                          {...sectionsMinField}
                          className={fieldClass("structure.sections_per_unit")}
                        />
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldSectionsMax")}
                        <input
                          type="number"
                          min={1}
                          max={20}
                          {...sectionsMaxField}
                          className={fieldClass("structure.sections_per_unit")}
                        />
                      </label>
                    </div>
                    {errorText("structure.sections_per_unit")}
                    <Toggle
                      label={t("profiles.fieldRequiresOutline")}
                      checked={form.requiresOutline}
                      onChange={(next) => update("requiresOutline", next)}
                    />
                  </Section>

                  <Section title={t("profiles.voiceSection")}>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldTone")}
                      <input
                        value={form.tone}
                        onChange={(event) => update("tone", event.target.value)}
                        className={fieldClass("voice.tone")}
                        placeholder={t("profiles.tonePlaceholder")}
                      />
                      {errorText("voice.tone")}
                    </label>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldPov")}
                        <select
                          value={form.pov}
                          onChange={(event) => update("pov", event.target.value)}
                          className={fieldClass("voice.pov", "select mt-1")}
                        >
                          <option value="first">{povLabel(t, "first")}</option>
                          <option value="third_limited">
                            {povLabel(t, "third_limited")}
                          </option>
                          <option value="third_omniscient">
                            {povLabel(t, "third_omniscient")}
                          </option>
                        </select>
                        {errorText("voice.pov")}
                      </label>
                      <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldTense")}
                        <select
                          value={form.tense}
                          onChange={(event) => update("tense", event.target.value)}
                          className={fieldClass("voice.tense", "select mt-1")}
                        >
                          <option value="present">{tenseLabel(t, "present")}</option>
                          <option value="past">{tenseLabel(t, "past")}</option>
                        </select>
                        {errorText("voice.tense")}
                      </label>
                    </div>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldForbidden")}
                      <input
                        value={form.forbiddenText}
                        onChange={(event) => update("forbiddenText", event.target.value)}
                        className={fieldClass("voice.forbidden_phrases")}
                        placeholder={t("profiles.forbiddenPlaceholder")}
                      />
                      {errorText("voice.forbidden_phrases")}
                    </label>
                  </Section>

                  <Section title={t("profiles.groundingSection")}>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldCitation")}
                      <select
                        value={form.citationPolicy}
                        onChange={(event) => update("citationPolicy", event.target.value)}
                        className={fieldClass("grounding.citation_policy", "select mt-1 w-full")}
                        data-field="grounding.citation_policy"
                      >
                        <option value="required">{policyLabel(t, "required")}</option>
                        <option value="optional">{policyLabel(t, "optional")}</option>
                        <option value="forbidden">{policyLabel(t, "forbidden")}</option>
                      </select>
                      {errorText("grounding.citation_policy")}
                    </label>
                    <Toggle
                      label={t("profiles.fieldAllowWeb")}
                      checked={form.allowWeb}
                      onChange={(next) => update("allowWeb", next)}
                    />
                  </Section>

                  <Section title={t("profiles.assetsSection")}>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                      <Toggle
                        label={t("profiles.assetGlossary")}
                        checked={form.glossary}
                        onChange={(next) => update("glossary", next)}
                      />
                      <Toggle
                        label={t("profiles.assetSettingBook")}
                        checked={form.settingBook}
                        onChange={(next) => update("settingBook", next)}
                      />
                      <Toggle
                        label={t("profiles.assetCharacterSheet")}
                        checked={form.characterSheet}
                        onChange={(next) => update("characterSheet", next)}
                      />
                    </div>
                  </Section>

                  <Section
                    title={t("profiles.assetsTitle")}
                    hint={t("profiles.assetsHint")}
                  >
                    <div
                      className="flex flex-wrap items-center justify-between gap-3"
                      data-field="assets.auto_images"
                    >
                      <Toggle
                        label={t("profiles.assetsAuto")}
                        checked={form.autoImages}
                        onChange={(next) => update("autoImages", next)}
                      />
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.assetsMax")}
                        <input
                          type="number"
                          min={1}
                          max={6}
                          step={1}
                          value={form.maxImages}
                          disabled={!form.autoImages}
                          onChange={(event) =>
                            update("maxImages", clampImages(toInt(event.target.value, 3)))
                          }
                          className={fieldClass("assets.max_images", "input mt-0 h-8 w-16")}
                          data-field="assets.max_images"
                        />
                      </label>
                    </div>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.assetsStyle")}
                      <textarea
                        rows={2}
                        value={form.imageStyle}
                        disabled={!form.autoImages}
                        onChange={(event) => update("imageStyle", event.target.value)}
                        className={fieldClass("assets.style", "input mt-1 resize-y text-[11.5px]")}
                        placeholder={t("profiles.assetsStyleHint")}
                        data-field="assets.style"
                      />
                    </label>
                    <p className="text-[10.5px] leading-relaxed text-slate-400 dark:text-slate-500">
                      {t("profiles.assetsStyleHint")}
                    </p>
                  </Section>

                  <Section title={t("profiles.validationSection")}>
                    <div>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        {t("profiles.fieldValidators")}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {VALIDATORS.map((item) => {
                          const active = form.validators.includes(item);
                          return (
                            <button
                              key={item}
                              type="button"
                              onClick={() => toggleValidator(item)}
                              data-validator={item}
                              data-active={active ? "true" : "false"}
                              className={clsx(
                                "rounded-full border px-2.5 py-1 text-[10.5px] transition",
                                active
                                  ? "border-indigo-400/60 bg-indigo-500/15 text-indigo-700 dark:text-indigo-200"
                                  : "border-white/60 bg-white/50 text-slate-500 hover:text-indigo-600 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400",
                              )}
                            >
                              {validatorLabel(t, item)}
                            </button>
                          );
                        })}
                      </div>
                      {errorText("validation.validators")}
                    </div>
                    <label className="block text-[11px] text-slate-500 dark:text-slate-400">
                      {t("profiles.fieldStrictness")}
                      <select
                        value={form.strictness}
                        onChange={(event) => update("strictness", event.target.value)}
                        className={fieldClass("validation.strictness", "select mt-1")}
                      >
                        <option value="relaxed">
                          {strictnessLabel(t, "relaxed")}
                        </option>
                        <option value="normal">
                          {strictnessLabel(t, "normal")}
                        </option>
                        <option value="strict">
                          {strictnessLabel(t, "strict")}
                        </option>
                      </select>
                      {errorText("validation.strictness")}
                    </label>
                  </Section>

                  <section className="rounded-2xl border border-white/60 bg-white/55 p-3.5 dark:border-white/10 dark:bg-white/[0.04]">
                    <button
                      type="button"
                      onClick={() => setShowPrompts((prev) => !prev)}
                      className="flex w-full items-center justify-between gap-2 text-left"
                    >
                      <span className="text-[12px] font-semibold text-slate-700 dark:text-slate-200">
                        {t("profiles.promptsSection")}
                      </span>
                      {showPrompts ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    {showPrompts ? (
                      <div className="mt-3 space-y-3">
                        <p className="rounded-xl border border-indigo-400/25 bg-indigo-500/10 px-2.5 py-2 text-[10.5px] leading-relaxed text-indigo-700 dark:text-indigo-200">
                          {t("profiles.promptsVariables")}
                        </p>
                        {PROMPT_FIELDS.map((field) => (
                          <label
                            key={field}
                            className="block text-[11px] text-slate-500 dark:text-slate-400"
                          >
                            {t(`profiles.prompt_${field}`)}
                            <textarea
                              rows={3}
                              value={form.prompts[field]}
                              onChange={(event) => updatePrompt(field, event.target.value)}
                              className={fieldClass(`prompts.${field}`, "input mt-1 font-mono text-[11px]")}
                              placeholder={t("profiles.promptPlaceholder")}
                            />
                            {errorText(`prompts.${field}`)}
                          </label>
                        ))}
                      </div>
                    ) : null}
                  </section>

                      {sampleOpen ? (
                        <SamplePanel
                          t={t}
                          topic={sampleTopic}
                          onTopic={setSampleTopic}
                          onStart={() => void runSample()}
                          onCopy={() => void copySample()}
                          onRegenerate={() => void runSample()}
                          running={sampling}
                          copied={sampleCopied}
                          error={sampleError}
                          sample={sample}
                          canRun={sampleReady}
                        />
                      ) : null}
                </div>

                <aside className="min-w-0 space-y-3 lg:sticky lg:top-4 lg:self-start">
                  <div className="rounded-2xl border border-white/60 bg-white/60 p-3.5 dark:border-white/10 dark:bg-white/[0.04]">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-[12px] font-semibold text-slate-700 dark:text-slate-200">
                        {t("profiles.jsonPreview")}
                      </h3>
                      {statusPill}
                    </div>
                    <pre className="mt-2 max-h-[42vh] overflow-auto rounded-xl bg-slate-950/90 p-3 text-[10.5px] leading-relaxed text-slate-100 lg:max-h-[58vh]">
                      <code className="break-words whitespace-pre-wrap">{specJson}</code>
                    </pre>
                    {warnings.length > 0 ? (
                      <div className="mt-2 rounded-xl border border-amber-400/40 bg-amber-400/10 px-2.5 py-2 text-[10.5px] leading-relaxed text-amber-700 dark:text-amber-300">
                        <p className="font-medium">
                          {t("profiles.validationWarnings", { count: warnings.length })}
                        </p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-4">
                          {warnings.map((item, index) => (
                            <li key={`${item.path}-${index}`} className="break-words">
                              {item.path ? `${item.path}: ` : ""}
                              {item.message}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {errors.length > 0 ? (
                      <div className="mt-2 rounded-xl border border-rose-400/40 bg-rose-500/10 px-2.5 py-2 text-[10.5px] leading-relaxed text-rose-700 dark:text-rose-300">
                        <p className="font-medium">
                          {t("profiles.validationIssues", { count: errors.length })}
                        </p>
                        <ul className="mt-1 list-disc space-y-0.5 pl-4">
                          {errors.map((item, index) => (
                            <li key={`${item.path}-${index}`} className="break-words">
                              {item.path ? `${item.path}: ` : ""}
                              {item.message.startsWith("PROFILE_")
                                ? t(`profiles.${item.message}`)
                                : item.message}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                </aside>
              </div>
            </div>

            <footer className="shrink-0 border-t border-white/60 bg-white/75 px-3 py-2.5 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/75 sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 flex-1 text-[10.5px]">
                  {formError ? (
                    <p className="break-words text-rose-600 dark:text-rose-300">{formError}</p>
                  ) : savedNotice ? (
                    <p className="text-emerald-600 dark:text-emerald-300">{savedNotice}</p>
                  ) : (
                    <p className="text-slate-400">{t("profiles.editorFooterHint")}</p>
                  )}
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <button type="button" onClick={onClose} className="btn btn-quiet">
                    {t("common.cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void openPreview()}
                    disabled={previewLoading}
                    className="btn btn-ghost"
                    data-action="preview"
                  >
                    {previewLoading ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Sparkles size={13} />
                    )}
                    {t("profiles.previewPrompts")}
                  </button>
                  <button
                    type="button"
                    onClick={toggleSample}
                    className={clsx("btn btn-ghost", sampleOpen && "text-indigo-600 dark:text-indigo-300")}
                    data-action="sample"
                    aria-expanded={sampleOpen}
                  >
                    <FlaskConical size={13} />
                    {t("profiles.sample")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void save()}
                    disabled={saving}
                    className="btn btn-primary"
                    data-action="save"
                  >
                    {saving ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Save size={13} />
                    )}
                    {saving ? t("profiles.saving") : t("profiles.save")}
                  </button>
                </div>
              </div>
            </footer>
    </div>
  );

  const previewModal = (
    <Modal
        open={previewOpen}
        title={t("profiles.previewTitle")}
        onClose={() => setPreviewOpen(false)}
        wide
        layer="z-[100]"
      >
        <div className="space-y-3">
          {preview ? (
            [
              ["system_prompt", t("profiles.promptSystemBlock")],
              ["outline_prompt", t("profiles.promptOutlineBlock")],
              ["unit_prompt", t("profiles.promptUnitBlock")],
            ].map(([key, label]) => (
              <div key={key}>
                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  {label}
                </p>
                <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-950/90 p-2.5 text-[10.5px] leading-relaxed text-slate-100">
                  {preview[key as keyof typeof preview]}
                </pre>
              </div>
            ))
          ) : (
            <p className="text-[11px] text-slate-400">{t("profiles.loading")}</p>
          )}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setPreviewOpen(false)}
              className="btn btn-quiet"
            >
              {t("common.close")}
            </button>
          </div>
        </div>
      </Modal>
  );

  if (inline) {
    return (
      <>
        {open ? shell : null}
        {previewModal}
      </>
    );
  }

  return (
    <>
      <AnimatePresence>
        {open ? (
          <motion.div
            key="profile-editor"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[90] bg-slate-900/35 backdrop-blur-sm"
          >
            <motion.div
              initial={{ y: 24, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="flex h-full w-full flex-col"
            >
              {shell}
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {previewModal}
    </>
  );
}
