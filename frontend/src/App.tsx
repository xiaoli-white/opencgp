import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { SessionProvider } from "@/components/auth/SessionProvider";
import { I18nProvider } from "@/i18n/I18nProvider";

const HomePage = lazy(() => import("./pages/HomePage"));
const SeriesPage = lazy(() => import("./pages/SeriesPage"));
const KbPage = lazy(() => import("./pages/KbPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ProfileSettingsPage = lazy(() => import("./pages/settings/ProfileSettingsPage"));
const ServerSettingsPage = lazy(() => import("./pages/settings/ServerSettingsPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const ResearchPage = lazy(() => import("./pages/ResearchPage"));
const PiecesPage = lazy(() => import("./pages/PiecesPage"));
const PieceEditorPage = lazy(() => import("./pages/PieceEditorPage"));
const JobsPage = lazy(() => import("./pages/JobsPage"));
const MediaPage = lazy(() => import("./pages/MediaPage"));
const ReaderModePage = lazy(() => import("./pages/ReaderModePage"));
const PublicSharePage = lazy(() => import("./pages/PublicSharePage"));

function GlassSkeleton() {
  return (
    <div className="mx-auto w-full max-w-5xl animate-pulse space-y-4 py-6">
      <div className="glass h-20 rounded-3xl shadow-glass" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="glass h-40 rounded-3xl shadow-glass" />
        <div className="glass h-40 rounded-3xl shadow-glass" />
      </div>
      <div className="glass h-56 rounded-3xl shadow-glass" />
    </div>
  );
}

function AppRoutes() {
  const location = useLocation();

  if (location.pathname.startsWith("/s/")) {
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#f8fafc] dark:bg-[#0b1020]" />}>
        <Routes>
          <Route path="/s/:token" element={<PublicSharePage />} />
          <Route path="*" element={<PublicSharePage />} />
        </Routes>
      </Suspense>
    );
  }

  if (location.pathname.startsWith("/read/")) {
    return (
      <Suspense fallback={<div className="min-h-screen bg-[#f8fafc] dark:bg-[#0b1020]" />}>
        <Routes>
          <Route path="/read/:kind/:id" element={<ReaderModePage />} />
          <Route path="*" element={<ReaderModePage />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <SessionProvider>
      <AppShell>
        <Suspense fallback={<GlassSkeleton />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/series/:id" element={<SeriesPage />} />
            <Route path="/courses/:id" element={<LegacyRedirect prefix="/series" />} />
            <Route path="/courses" element={<LegacyRedirect prefix="/" />} />
            <Route path="/kb" element={<KbPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/pieces" element={<PiecesPage />} />
            <Route path="/pieces/:id" element={<PieceEditorPage />} />
            <Route path="/longforms" element={<LegacyRedirect prefix="/pieces" />} />
            <Route path="/longforms/:id" element={<LegacyRedirect prefix="/pieces" />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/media" element={<MediaPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/settings" element={<ProfileSettingsPage />} />
            <Route path="/settings/server" element={<ServerSettingsPage />} />
            <Route path="/settings/*" element={<NotFoundPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </AppShell>
    </SessionProvider>
  );
}

function LegacyRedirect({ prefix }: { prefix: string }) {
  const rest = useLocation().pathname.replace(/^\/(courses|longforms)/, "");
  const target = rest ? `${prefix}${rest}` : prefix;
  return <Navigate to={target} replace />;
}

export default function App() {
  return (
    <I18nProvider>
      <AppRoutes />
    </I18nProvider>
  );
}
