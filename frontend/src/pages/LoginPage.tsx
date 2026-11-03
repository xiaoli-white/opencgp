import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, ArrowRight, Loader2, LogIn, Sparkles, UserPlus } from "lucide-react";
import clsx from "clsx";
import { api, tenantId, type AuthMode } from "@/lib/api";
import { setTenantId, setToken } from "@/lib/session";

type Tab = "login" | "register";

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const redirect = params.get("redirect") || "/";

  const [tab, setTab] = useState<Tab>("login");
  const [authMode, setAuthMode] = useState<AuthMode>("required");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .getMe()
      .then((data) => {
        if (!alive) return;
        setAuthMode(data.auth_mode);
      })
      .catch(() => {
        if (!alive) return;
        setAuthMode("required");
      });
    return () => {
      alive = false;
    };
  }, []);

  const go = useCallback(() => {
    navigate(redirect);
  }, [navigate, redirect]);

  const submit = useCallback(async () => {
    setError("");
    if (!email.trim() || !password) {
      setError("请填写邮箱与密码");
      return;
    }
    if (tab === "register" && password.length < 8) {
      setError("密码至少 8 位");
      return;
    }
    if (tab === "register" && !displayName.trim()) {
      setError("请填写显示名");
      return;
    }
    setBusy(true);
    try {
      const payload =
        tab === "login"
          ? await api.login({ email: email.trim(), password })
          : await api.register({
              email: email.trim(),
              password,
              display_name: displayName.trim(),
            });
      setToken(payload.token);
      const first = tenantId(payload.tenants?.[0]?.tenant);
      if (first) setTenantId(first, false);
      window.dispatchEvent(new Event("course-studio:refresh"));
      go();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    } finally {
      setBusy(false);
    }
  }, [tab, email, password, displayName, go]);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] w-full max-w-md flex-col justify-center px-1 py-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="glass rounded-3xl p-6 shadow-glass sm:p-8"
      >
        <div className="flex items-center gap-3">
          <span className="brand-gradient grid h-11 w-11 shrink-0 place-items-center rounded-2xl text-white shadow-brand">
            <Sparkles size={18} />
          </span>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">
              进入 OpenCGP
            </h1>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              {authMode === "disabled"
                ? "当前为单用户本地模式（AUTH_MODE=disabled）"
                : "当前为多用户模式，需要登录后访问"}
            </p>
          </div>
        </div>

        <div className="mt-5 inline-flex items-center gap-0.5 rounded-full border border-slate-200/70 bg-white/50 p-0.5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.05]">
          {(
            [
              { value: "login" as Tab, label: "登录", icon: LogIn },
              { value: "register" as Tab, label: "注册", icon: UserPlus },
            ]
          ).map((item) => {
            const active = tab === item.value;
            const Icon = item.icon;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  setTab(item.value);
                  setError("");
                }}
                className={clsx(
                  "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-medium transition",
                  active
                    ? "brand-gradient text-white shadow-[0_10px_22px_-14px_rgba(99,102,241,0.9)]"
                    : "text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-200",
                )}
              >
                <Icon size={12} />
                {item.label}
              </button>
            );
          })}
        </div>

        <form
          className="mt-5 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="block">
            <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              邮箱
            </span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className="input"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
              密码
            </span>
            <input
              type="password"
              autoComplete={tab === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={tab === "register" ? "至少 8 位" : "••••••••"}
              className="input"
            />
          </label>

          <AnimatePresence initial={false}>
            {tab === "register" && (
              <motion.label
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="block overflow-hidden"
              >
                <span className="mb-1.5 block text-[11px] font-medium text-slate-500 dark:text-slate-400">
                  显示名
                </span>
                <input
                  type="text"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="课程编辑者"
                  className="input"
                />
              </motion.label>
            )}
          </AnimatePresence>

          {error ? (
            <div className="flex items-start gap-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[11px] leading-relaxed text-rose-700 dark:text-rose-300">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span className="flex-1">{error}</span>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="btn btn-primary w-full"
          >
            {busy ? (
              <Loader2 size={14} className="animate-spin" />
            ) : tab === "login" ? (
              <LogIn size={14} />
            ) : (
              <UserPlus size={14} />
            )}
            {tab === "login" ? "登录" : "注册并进入"}
          </button>
        </form>

        {authMode === "disabled" ? (
          <div className="mt-4 rounded-2xl border border-indigo-400/25 bg-indigo-500/8 px-3.5 py-3">
            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
              当前为单用户本地模式，可直接进入工作台。
            </p>
            <button
              type="button"
              onClick={go}
              className="btn btn-ghost mt-2.5 w-full"
            >
              直接进入
              <ArrowRight size={13} />
            </button>
          </div>
        ) : null}
      </motion.div>
    </div>
  );
}
