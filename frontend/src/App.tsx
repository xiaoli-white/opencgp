import { Route, Routes } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { SessionProvider } from "@/components/auth/SessionProvider";
import HomePage from "./pages/HomePage";
import CoursePage from "./pages/CoursePage";
import KbPage from "./pages/KbPage";
import LoginPage from "./pages/LoginPage";
import SettingsPage from "./pages/SettingsPage";
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
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </SessionProvider>
  );
}
