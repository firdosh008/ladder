import { motion } from "framer-motion";
import { ArrowUpRight, PlayCircle } from "@phosphor-icons/react";
import ExcalidrawMotif from "./ExcalidrawMotif";
import { fadeUp, stagger } from "../lib/motion";

export default function Hero() {
  return (
    <section className="relative min-h-[100dvh] pt-36 pb-24 px-6 md:px-10 overflow-hidden">
      {/* Background mesh + grid */}
      <div
        className="absolute inset-0 bg-mesh pointer-events-none"
        aria-hidden="true"
      />
      <div
        className="absolute inset-0 opacity-[0.18] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          maskImage:
            "radial-gradient(ellipse 80% 70% at 60% 40%, black 40%, transparent 100%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 70% at 60% 40%, black 40%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      <motion.div
        variants={stagger(0.25, 0.12)}
        initial="hidden"
        animate="show"
        className="relative max-w-[1400px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-8 items-center"
      >
        {/* LEFT — editorial typography block */}
        <div className="lg:col-span-7 xl:col-span-7">
          <motion.div
            variants={fadeUp}
            className="inline-flex items-center gap-2 rounded-full border border-hairline pl-2 pr-3 py-1 mb-10"
          >
            <span className="flex h-1.5 w-1.5 rounded-full bg-cinnabar animate-pulse-dot" />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-bone/70">
              for founder-operators · v0.3 preview
            </span>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="font-display text-mega text-bone text-balance"
          >
            Videos that
            <br />
            <span className="italic text-cinnabar">ladder</span>{" "}
            <span className="relative">
              up
              <svg
                viewBox="0 0 220 14"
                className="absolute -bottom-1 left-0 w-full h-3"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M4 9 C 40 2, 100 12, 160 6 C 190 3, 210 8, 216 9"
                  stroke="#E8442A"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            .
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mt-8 max-w-[54ch] text-[17.5px] leading-[1.55] text-bone/70"
          >
            A production OS for operators who ship videos next to shipping
            product. From a scrawled idea to a Loom-ready Excalidraw scene and a
            thumbnail worth clicking — without pressing{" "}
            <span className="font-mono text-[15px] px-1.5 py-0.5 rounded bg-white/5 border border-hairline text-bone/90">
              generate
            </span>
            .
          </motion.p>

          <motion.div variants={fadeUp} className="mt-10 flex flex-wrap gap-3">
            <a
              href="#cta"
              className="group inline-flex items-center gap-2 pl-5 pr-1.5 py-1.5 rounded-full bg-cinnabar text-night text-[14px] font-medium shadow-cinnabar transition-all duration-500 ease-spring active:scale-[0.98] hover:bg-[#F05434]"
            >
              <span className="pl-1 pr-1">Start a studio session</span>
              <span className="flex items-center justify-center w-8 h-8 rounded-full bg-night/15 transition-transform duration-500 ease-spring group-hover:translate-x-0.5 group-hover:-translate-y-[1px]">
                <ArrowUpRight size={14} weight="bold" />
              </span>
            </a>

            <a
              href="#tour"
              className="group inline-flex items-center gap-2.5 pl-4 pr-5 py-3 rounded-full border border-hairline-strong text-bone/90 text-[14px] font-medium hover:bg-white/[0.04] transition-colors duration-500 ease-fluid"
            >
              <PlayCircle size={16} weight="duotone" className="text-cinnabar" />
              <span>Watch a 90-second tour</span>
            </a>
          </motion.div>

          <motion.div
            variants={fadeUp}
            className="mt-14 flex flex-wrap items-center gap-x-8 gap-y-3 text-[12px] text-bone/50"
          >
            <MetricTick label="avg. idea → scene" value="11m 42s" />
            <span className="h-4 w-px bg-hairline hidden sm:inline-block" />
            <MetricTick label="founders in pilot" value="9 of 12" />
            <span className="h-4 w-px bg-hairline hidden sm:inline-block" />
            <MetricTick label="streams per session" value="2.3" />
          </motion.div>
        </div>

        {/* RIGHT — hand-drawn motif in double-bezel enclosure */}
        <motion.div
          variants={fadeUp}
          className="lg:col-span-5 xl:col-span-5 relative"
        >
          <div className="bezel-shell shadow-diffuse">
            <div className="bezel-core relative aspect-[4/3.4] overflow-hidden">
              <div className="absolute inset-0 p-5 sm:p-7">
                <ExcalidrawMotif />
              </div>

              {/* top-bar ornament */}
              <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-white/20" />
                  <span className="h-2 w-2 rounded-full bg-white/20" />
                  <span className="h-2 w-2 rounded-full bg-cinnabar/80" />
                </div>
                <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-bone/40">
                  studio · session 041
                </span>
              </div>
            </div>
          </div>

          {/* Floating tag — "approved by voice" — sits in the gap between Intro and Framework rows */}
          <motion.div
            initial={{ opacity: 0, x: -12, rotate: -2 }}
            animate={{ opacity: 1, x: 0, rotate: -2 }}
            transition={{ delay: 1.1, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="absolute -left-3 sm:-left-10 md:-left-14 top-[32%] glass-pill rounded-2xl px-4 py-3 animate-float shadow-diffuse"
          >
            <div className="flex items-center gap-2.5">
              <span className="h-2 w-2 rounded-full bg-cinnabar animate-pulse-dot" />
              <div className="flex flex-col">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-bone/50">
                  voice match
                </span>
                <span className="font-display italic text-[15px] text-bone whitespace-nowrap">
                  sounds like you
                </span>
              </div>
            </div>
          </motion.div>

          {/* Floating chip — cost — sits below the card, bottom-right corner */}
          <motion.div
            initial={{ opacity: 0, y: 12, rotate: 3 }}
            animate={{ opacity: 1, y: 0, rotate: 3 }}
            transition={{ delay: 1.3, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="absolute -right-3 sm:-right-6 md:-right-10 -bottom-4 md:-bottom-6 glass-pill rounded-2xl px-4 py-3 shadow-diffuse"
          >
            <div className="flex items-center gap-3">
              <div className="flex flex-col">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-bone/50">
                  this run
                </span>
                <span className="font-mono mono-tab text-[15px] text-bone whitespace-nowrap">
                  $0.47 · 8,412 tok
                </span>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </motion.div>
    </section>
  );
}

function MetricTick({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-mono uppercase tracking-[0.2em] text-[9.5px] text-bone/40">
        {label}
      </span>
      <span className="font-mono mono-tab text-[15px] text-bone/90 mt-1">
        {value}
      </span>
    </div>
  );
}
