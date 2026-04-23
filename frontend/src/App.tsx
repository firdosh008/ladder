import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./components/Landing";
import OnboardingPage from "./pages/Onboarding";
import MakePage from "./pages/Make";
import VideosPage from "./pages/Videos";
import LibraryPage from "./pages/Library";
import SettingsPage from "./pages/Settings";
import StudioPage from "./pages/Studio";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/make" element={<MakePage />} />
        <Route path="/videos" element={<VideosPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/studio/:id" element={<StudioPage />} />
        <Route path="/studio" element={<StudioPage />} />
      </Routes>
    </BrowserRouter>
  );
}
