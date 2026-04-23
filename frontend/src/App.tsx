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

export default function App() {
  return (
    <BrowserRouter>
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
