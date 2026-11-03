import { Route, Routes } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { SessionProvider } from "@/components/auth/SessionProvider";
import HomePage from "./pages/HomePage";
import CoursePage from "./pages/CoursePage";
import KbPage from "./pages/KbPage";
import LoginPage from "./pages/LoginPage";
import ProfileSettingsPage from "./pages/settings/ProfileSettingsPage";
import WorkspaceSettingsPage from "./pages/settings/WorkspaceSettingsPage";
import ServerSettingsPage from "./pages/settings/ServerSettingsPage";
import NotFoundPage from "./pages/NotFoundPage";

export default function App() {
  return (
    <SessionProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/courses/:id" element={<CoursePage />} />
          <Route path="/kb" element={<KbPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/settings" element={<ProfileSettingsPage />} />
          <Route path="/settings/workspace" element={<WorkspaceSettingsPage />} />
          <Route path="/settings/server" element={<ServerSettingsPage />} />
          <Route path="/settings/*" element={<NotFoundPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </SessionProvider>
  );
}
