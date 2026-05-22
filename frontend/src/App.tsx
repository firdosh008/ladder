import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./components/Landing";
import AuthPage from "./pages/Auth";
import AuthCallback from "./pages/AuthCallback";
import ResetPassword from "./pages/ResetPassword";
import OnboardingPage from "./pages/Onboarding";
import MakePage from "./pages/Make";
import VideosPage from "./pages/Videos";
import LibraryPage from "./pages/Library";
import SettingsPage from "./pages/Settings";
import StudioPage from "./pages/Studio";
import { AuthProvider, RequireAuth } from "./lib/auth";

/** Apply theme + font-scale from localStorage before profile loads. */
function ThemeBootstrap() {
  useEffect(() => {
    const theme = localStorage.getItem("theme") ?? "dark";
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";

    const fs = localStorage.getItem("font-scale") ?? "default";
    const scales: Record<string, string> = { compact: "0.875", default: "1.0", comfortable: "1.125" };
    document.documentElement.style.setProperty("--font-scale", scales[fs] ?? "1.0");
  }, []);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeBootstrap />
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/auth" element={<AuthPage />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route path="/auth/reset-password" element={<ResetPassword />} />

          <Route
            path="/onboarding"
            element={
              <RequireAuth>
                <OnboardingPage />
              </RequireAuth>
            }
          />
          <Route
            path="/make"
            element={
              <RequireAuth>
                <MakePage />
              </RequireAuth>
            }
          />
          <Route
            path="/videos"
            element={
              <RequireAuth>
                <VideosPage />
              </RequireAuth>
            }
          />
          <Route
            path="/library"
            element={
              <RequireAuth>
                <LibraryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <SettingsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/studio/:id"
            element={
              <RequireAuth>
                <StudioPage />
              </RequireAuth>
            }
          />
          <Route
            path="/studio"
            element={
              <RequireAuth>
                <StudioPage />
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
