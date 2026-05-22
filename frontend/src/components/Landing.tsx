import Nav from "./Nav";
import Hero from "./Hero";
import Workflow from "./Workflow";
import Features from "./Features";
import Stack from "./Stack";
import CTA from "./CTA";
import Footer from "./Footer";
import Marquee from "./Marquee";

export default function Landing() {
  return (
    <main className="relative min-h-[100dvh] bg-night text-bone grain-overlay">
      <Nav />
      <Hero />
      <Marquee />
      <Workflow />
      <Features />
      <Stack />
      <CTA />
      <Footer />
    </main>
  );
}
