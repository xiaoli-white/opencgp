import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { SessionProvider } from "@/components/auth/SessionProvider";

const HomePage = lazy(() => import("./pages/HomePage"));
const CoursePage = lazy(() => import("./pages/CoursePage"));
const KbPage = lazy(() => import("./pages/KbPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ProfileSettingsPage = lazy(() => import("./pages/settings/ProfileSettingsPage"));
const ServerSettingsPage = lazy(() => import("./pages/settings/ServerSettingsPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const ResearchPage = lazy(() => import("./pages/ResearchPage"));
const LongformsPage = lazy(() => import("./pages/LongformsPage"));
const LongformEditorPage = lazy(() => import("./pages/LongformEditorPage"));
const JobsPage = lazy(() => import("./pages/JobsPage"));
const MediaPage = lazy(() => import("./pages/MediaPage"));

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

export default function App() {
  return (
    <SessionProvider>
      <AppShell>
        <Suspense fallback={<GlassSkeleton />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/courses/:id" element={<CoursePage />} />
            <Route path="/kb" element={<KbPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/longforms" element={<LongformsPage />} />
            <Route path="/longforms/:id" element={<LongformEditorPage />} />
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
