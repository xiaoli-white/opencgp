import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  BookOpen,
  Clock3,
  Eye,
  FileQuestion,
  ShieldOff,
  TimerOff,
} from "lucide-react";
import { api, type Citation, type PublicShare } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import MarkdownReader from "@/components/reader/MarkdownReader";
import LocaleToggle from "@/components/i18n/LocaleToggle";
import { useI18n } from "@/i18n/I18nProvider";

type ErrorKind = "notFound" | "revoked" | "expired" | "rateLimited" | "unknown";

function kindOf(status: number): ErrorKind {
  if (status === 404) return "notFound";
  if (status === 403) return "revoked";
  if (status === 410) return "expired";
  if (status === 429) return "rateLimited";
  return "unknown";
}

function Skeleton() {
  return (
    <div className="mx-auto w-full max-w-[720px] animate-pulse space-y-4 py-4">
      <div className="glass h-8 w-2/3 rounded-2xl shadow-glass" />
      <div className="glass h-4 w-1/2 rounded-xl shadow-glass" />
      <div className="glass h-24 rounded-3xl shadow-glass" />
      <div className="glass h-4 w-full rounded-xl shadow-glass" />
      <div className="glass h-4 w-11/12 rounded-xl shadow-glass" />
      <div className="glass h-4 w-10/12 rounded-xl shadow-glass" />
      <div className="glass h-32 rounded-3xl shadow-glass" />
    </div>
  );
}

export default function PublicSharePage() {
  const { token = "" } = useParams<{ token: string }>();
  const { t } = useI18n();
  const [data, setData] = useState<PublicShare | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null);
  const [errorDetail, setErrorDetail] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErrorKind(null);
    setErrorDetail("");
    setData(null);
    api
      .getPublicShare(token)
      .then((payload) => {
        if (alive) setData(payload);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const status = typeof (err as { status?: number })?.status === "number"
          ? (err as { status: number }).status
          : 0;
        setErrorKind(kindOf(status));
        setErrorDetail(err instanceof Error ? err.message : "");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (data?.title) document.title = `${data.title} · OpenCGP`;
    return () => {
      document.title = "OpenCGP";
    };
  }, [data]);

  const citations = useMemo<Citation[]>(
    () =>
      (data?.citations ?? []).map((item, index) => ({
        source_id: "",
        source_name: item?.source_name ?? "",
        chunk_id: "",
        chunk_index:
          typeof item?.chunk_index === "number" ? item.chunk_index : index,
        text: "",
        snippet: "",
        score: 0,
        start: 0,
        end: 0,
        meta: {},
      })),
    [data],
  );

  const chapters = data?.chapters ?? [];
  const expiredLabel = data
    ? data.expires_at
      ? t("share.public.expiresAt", { time: formatDateTime(data.expires_at) })
      : t("share.public.permanent")
    : "";

  const errorCopy = errorKind
    ? {
        title: t(`share.public.${errorKind}`),
        desc: t(`share.public.${errorKind}Desc`),
      }
    : null;

  const errorIcon =
    errorKind === "revoked" ? (
      <ShieldOff size={18} />
    ) : errorKind === "expired" ? (
      <TimerOff size={18} />
    ) : errorKind === "notFound" ? (
      <FileQuestion size={18} />
    ) : (
      <AlertTriangle size={18} />
    );

  return (
    <div className="min-h-screen overflow-x-hidden pb-14">
      <header className="sticky top-0 z-30 border-b border-white/60 bg-white/70 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b1020]/70">
        <div className="mx-auto flex w-full max-w-[1120px] flex-wrap items-center gap-x-2.5 gap-y-1.5 px-4 py-2.5 sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-1.5">
            <span className="brand-gradient grid h-6 w-6 place-items-center rounded-lg text-[11px] font-semibold text-white">
              O
            </span>
            <span className="text-[12.5px] font-semibold tracking-tight text-slate-800 dark:text-slate-100">
              OpenCGP
            </span>
          </Link>
          <span className="shrink-0 rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-300">
            {t("share.public.badge")}
          </span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-slate-500 dark:text-slate-400">
            {data?.title ?? ""}
          </span>
          {data ? (
            <span className="hidden shrink-0 items-center gap-3 text-[10.5px] text-slate-400 dark:text-slate-500 md:flex">
              <span className="inline-flex items-center gap-1">
                <Clock3 size={11} />
                {expiredLabel}
              </span>
              <span className="inline-flex items-center gap-1">
                <Eye size={11} />
                {t("share.public.readCount", { count: data.view_count })}
              </span>
            </span>
          ) : null}
          <LocaleToggle />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1120px] px-4 py-6 sm:px-6 sm:py-10">
        {loading ? (
          <Skeleton />
        ) : errorCopy ? (
          <div className="flex min-h-[60vh] items-center justify-center">
            <div className="glass w-full max-w-md rounded-3xl p-7 text-center shadow-glass">
              <span className="mx-auto grid h-11 w-11 place-items-center rounded-2xl bg-rose-500/12 text-rose-600 dark:text-rose-300">
                {errorIcon}
              </span>
              <h1 className="mt-4 text-base font-semibold tracking-tight text-slate-900 dark:text-white">
                {errorCopy.title}
              </h1>
              <p className="mt-2 text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
                {errorCopy.desc}
              </p>
              {errorDetail && errorKind === "unknown" ? (
                <p className="mt-2 break-words rounded-xl border border-white/50 bg-white/50 px-3 py-2 text-[10.5px] text-slate-500 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-400">
                  {errorDetail}
                </p>
              ) : null}
              <Link to="/" className="btn btn-primary mt-5">
                <BookOpen size={13} />
                {t("share.public.home")}
              </Link>
            </div>
          </div>
        ) : data ? (
          <div
            className={
              chapters.length > 3
                ? "lg:grid lg:grid-cols-[minmax(0,720px)_200px] lg:justify-center lg:gap-10"
                : ""
            }
          >
            <article className="mx-auto w-full min-w-0 max-w-[720px]">
              <header className="border-b border-slate-200/70 pb-5 dark:border-white/10">
                <h1 className="text-[21px] font-semibold leading-snug tracking-tight text-slate-900 dark:text-white sm:text-[26px]">
                  {data.title}
                </h1>
                {data.subtitle ? (
                  <p className="mt-2 text-[12.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                    {data.subtitle}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-slate-400 dark:text-slate-500">
                  {data.created_at ? <span>{formatDateTime(data.created_at)}</span> : null}
                  {data.author ? <span>{data.author}</span> : null}
                  <span className="inline-flex items-center gap-1">
                    <Clock3 size={11} />
                    {expiredLabel}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Eye size={11} />
                    {t("share.public.readCount", { count: data.view_count })}
                  </span>
                </div>
              </header>

              {chapters.length === 0 ? (
                <p className="mt-8 rounded-2xl border border-dashed border-white/70 bg-white/40 px-4 py-6 text-center text-[12px] text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
                  {t("share.public.empty")}
                </p>
              ) : (
                <div className="mt-7 space-y-11">
                  {chapters.map((chapter, index) => (
                    <section
                      key={`${chapter.title}-${index}`}
                      id={`chapter-${index + 1}`}
                      className="min-w-0 scroll-mt-20"
                    >
                      <h2 className="text-[16.5px] font-semibold tracking-tight text-slate-900 dark:text-white sm:text-[18px]">
                        {index + 1}. {chapter.title || t("share.public.chapterNo", { index: index + 1 })}
                      </h2>
                      <div className="reader-surface mt-3 min-w-0">
                        <MarkdownReader
                          content={chapter.content}
                          citations={citations}
                          enableAsk={false}
                        />
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </article>

            {chapters.length > 3 ? (
              <aside className="hidden lg:block">
                <nav className="sticky top-20 max-h-[70vh] overflow-y-auto rounded-2xl border border-white/60 bg-white/55 p-3 dark:border-white/10 dark:bg-white/[0.04]">
                  <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    {t("share.public.toc")}
                  </p>
                  <ul className="mt-2 space-y-0.5">
                    {chapters.map((chapter, index) => (
                      <li key={`toc-${index}`}>
                        <a
                          href={`#chapter-${index + 1}`}
                          className="block truncate rounded-lg px-1.5 py-1 text-[11px] text-slate-500 transition hover:bg-indigo-500/10 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-200"
                          title={chapter.title}
                        >
                          {index + 1}. {chapter.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </nav>
              </aside>
            ) : null}
          </div>
        ) : null}
      </main>

      <footer className="mx-auto w-full max-w-[1120px] px-4 text-center text-[10.5px] text-slate-400 dark:text-slate-500 sm:px-6">
        {t("share.public.footer")}
      </footer>
    </div>
  );
}
