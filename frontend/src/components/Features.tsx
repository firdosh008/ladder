import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import {
  Graph,
  Waveform,
  BookOpenText,
  Pulse,
  Sparkle,
} from "@phosphor-icons/react";
import { fadeUp, stagger, popIn } from "../lib/motion";

export default function Features() {
  return (
    <section id="mind" className="relative py-32 md:py-40 px-6 md:px-10">
      <div className="max-w-[1400px] mx-auto">
        <motion.div
          variants={stagger(0.1, 0.1)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          className="grid grid-cols-1 lg:grid-cols-12 gap-10 mb-16"
        >
          <motion.div variants={fadeUp} className="lg:col-span-5">
            <div className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 mb-6">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-bone/70">
                § 02 · intelligence
              </span>
            </div>
            <h2 className="font-display text-editorial text-bone">
              It already knows
              <br />
              how <span className="italic text-cinnabar">you</span> sound.
            </h2>
          </motion.div>

          <motion.div
            variants={fadeUp}
            className="lg:col-span-6 lg:col-start-7 lg:pt-5"
          >
            <p className="text-[17px] leading-[1.6] text-bone/65 max-w-[52ch]">
              Every session is scoped to you. A per-user knowledge graph. Your
              voice, your audience, your never-say list. Drop in a{" "}
              <code className="font-mono text-[13.5px] px-1.5 py-0.5 rounded bg-white/5 border border-hairline text-bone">
                skill.md
              </code>{" "}
              and the next script treats it as load-bearing.
            </p>
          </motion.div>
        </motion.div>

        {/* Bento 2.0 — asymmetric grid */}
        <motion.div
          variants={stagger(0.05, 0.1)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.15 }}
          className="grid grid-cols-1 md:grid-cols-6 grid-rows-[auto] gap-5"
        >
          {/* 1 — Intelligent list (large) */}
          <motion.div
            variants={popIn}
            className="md:col-span-4 md:row-span-2 bezel-shell"
          >
            <div className="bezel-core p-8 md:p-10 h-full relative overflow-hidden">
              <CardLabel icon={<Graph size={14} weight="duotone" />}>
                per-user knowledge graph
              </CardLabel>
              <h3 className="font-display text-[30px] md:text-[36px] leading-[1.04] text-bone tracking-tight mt-4">
                Your past work,
                <br />
                retrievable at the section level.
              </h3>
              <p className="mt-5 text-[15px] leading-[1.6] text-bone/60 max-w-[46ch]">
                Ingested newsletters, published videos, skill.md uploads —
                chunked, embedded, scoped to you by RLS. Script generation
                pulls the top-K nodes at call time.
              </p>
              <KnowledgeList />
            </div>
          </motion.div>

          {/* 2 — Command input with typewriter */}
          <motion.div variants={popIn} className="md:col-span-2 md:row-span-1 bezel-shell">
            <div className="bezel-core p-7 h-full relative overflow-hidden">
              <CardLabel icon={<Sparkle size={14} weight="duotone" />}>
                sharpen-this chat
              </CardLabel>
              <h3 className="font-display text-[22px] leading-tight text-bone tracking-tight mt-3 mb-5">
                Refine in the same breath.
              </h3>
              <CommandTypewriter />
            </div>
          </motion.div>

          {/* 3 — Live status */}
          <motion.div variants={popIn} className="md:col-span-2 md:row-span-1 bezel-shell">
            <div className="bezel-core p-7 h-full relative overflow-hidden">
              <CardLabel icon={<Pulse size={14} weight="duotone" />}>
                usage log · always on
              </CardLabel>
              <h3 className="font-display text-[22px] leading-tight text-bone tracking-tight mt-3 mb-4">
                Every call, logged.
              </h3>
              <LiveStatus />
            </div>
          </motion.div>

          {/* 4 — Voice profile */}
          <motion.div variants={popIn} className="md:col-span-3 bezel-shell">
            <div className="bezel-core p-8 h-full relative overflow-hidden">
              <CardLabel icon={<Waveform size={14} weight="duotone" />}>
                voice profile
              </CardLabel>
              <h3 className="font-display text-[26px] leading-[1.08] text-bone tracking-tight mt-4 mb-5">
                No hard-coded context.
                <br />
                Ever.
              </h3>
              <VoiceRows />
            </div>
          </motion.div>

          {/* 5 — Skill.md injection */}
          <motion.div variants={popIn} className="md:col-span-3 bezel-shell">
            <div className="bezel-core p-8 h-full relative overflow-hidden">
              <CardLabel icon={<BookOpenText size={14} weight="duotone" />}>
                skill.md injection
              </CardLabel>
              <h3 className="font-display text-[26px] leading-[1.08] text-bone tracking-tight mt-4 mb-5">
                Drop a framework.
                <br />
                Watch it load-bear.
              </h3>
              <SkillFile />
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

function CardLabel({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="inline-flex items-center gap-1.5 text-bone/55">
      <span className="text-cinnabar">{icon}</span>
      <span className="font-mono text-[10.5px] uppercase tracking-[0.22em]">
        {children}
      </span>
    </div>
  );
}

// --- Intelligent List with layoutId reorder loop ---
const NODES = [
  { id: "a", title: "the knowledge graph monologue", score: 0.94 },
  { id: "b", title: "why founders dread voiceover", score: 0.88 },
  { id: "c", title: "thumbnail as the first scene", score: 0.82 },
  { id: "d", title: "scenes you don't render twice", score: 0.76 },
];

function KnowledgeList() {
  const [order, setOrder] = useState(NODES);

  useEffect(() => {
    const id = setInterval(() => {
      setOrder((prev) => {
        const next = [...prev];
        const first = next.shift()!;
        next.push(first);
        return next;
      });
    }, 2800);
    return () => clearInterval(id);
  }, []);

  return (
    <ul className="mt-8 space-y-2">
      {order.map((n, i) => (
        <motion.li
          layout
          layoutId={n.id}
          key={n.id}
          transition={{ type: "spring", stiffness: 220, damping: 28 }}
          className={`group relative flex items-center justify-between gap-4 pl-4 pr-3 py-3 rounded-xl border ${
            i === 0
              ? "border-cinnabar/40 bg-cinnabar-wash"
              : "border-hairline bg-white/[0.015]"
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span
              className={`font-mono mono-tab text-[10.5px] tracking-wider ${
                i === 0 ? "text-cinnabar" : "text-bone/40"
              }`}
            >
              0{i + 1}
            </span>
            <span
              className={`font-display italic text-[16.5px] truncate ${
                i === 0 ? "text-bone" : "text-bone/75"
              }`}
            >
              {n.title}
            </span>
          </div>
          <span className="font-mono mono-tab text-[11.5px] text-bone/45 shrink-0">
            sim {n.score.toFixed(2)}
          </span>
        </motion.li>
      ))}
    </ul>
  );
}

// --- Command Typewriter ---
const PROMPTS = [
  "tighten the framework section",
  "rewrite intro — less corporate",
  "make the close more honest",
  "swap walkthrough for a 60s teardown",
];

function CommandTypewriter() {
  const [pIdx, setPIdx] = useState(0);
  const [txt, setTxt] = useState("");
  const [erasing, setErasing] = useState(false);

  useEffect(() => {
    const full = PROMPTS[pIdx];
    if (!erasing && txt.length < full.length) {
      const t = setTimeout(() => setTxt(full.slice(0, txt.length + 1)), 55);
      return () => clearTimeout(t);
    }
    if (!erasing && txt.length === full.length) {
      const t = setTimeout(() => setErasing(true), 1500);
      return () => clearTimeout(t);
    }
    if (erasing && txt.length > 0) {
      const t = setTimeout(() => setTxt(txt.slice(0, -1)), 24);
      return () => clearTimeout(t);
    }
    if (erasing && txt.length === 0) {
      setErasing(false);
      setPIdx((i) => (i + 1) % PROMPTS.length);
    }
  }, [txt, erasing, pIdx]);

  return (
    <div className="mt-2 rounded-xl border border-hairline bg-night/60 p-4">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[11px] text-cinnabar">›</span>
        <span className="font-mono text-[13.5px] text-bone/95">
          {txt}
          <span className="inline-block w-[7px] h-[14px] align-middle bg-cinnabar animate-pulse-dot ml-0.5" />
        </span>
      </div>
      <div className="mt-3 pl-5 font-mono text-[11px] text-bone/40">
        ↵ send · ⌘K commands
      </div>
    </div>
  );
}

// --- Live Status ---
function LiveStatus() {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setPhase((p) => (p + 1) % 3), 2200);
    return () => clearInterval(id);
  }, []);

  const rows = [
    { fn: "stream_script", model: "haiku-4.5", cost: "$0.04" },
    { fn: "gen_outline", model: "haiku-4.5", cost: "$0.01" },
    { fn: "build_scene", model: "haiku-4.5", cost: "$0.10" },
  ];

  return (
    <div className="mt-2 space-y-2">
      {rows.map((r, i) => (
        <div
          key={r.fn}
          className="flex items-center justify-between text-[12px] font-mono mono-tab"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                i === phase ? "bg-cinnabar animate-pulse-dot" : "bg-bone/25"
              }`}
            />
            <span className="text-bone/85 truncate">{r.fn}</span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-bone/40">{r.model}</span>
            <span className="text-bone/90">{r.cost}</span>
          </div>
        </div>
      ))}
      <AnimatePresence>
        <motion.div
          key={phase}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="pt-3 mt-2 border-t border-hairline font-mono text-[10.5px] uppercase tracking-[0.18em] text-bone/40"
        >
          usage_log · writing
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// --- Voice profile rows ---
const VOICE = [
  { k: "positioning", v: "builds AI agents, ships videos about it" },
  { k: "audience", v: "founder-operators, 1–20 person co's" },
  { k: "voice", v: "dry · structural · low-ceremony" },
  { k: "avoid", v: "filler words, capital-F frameworks" },
];

function VoiceRows() {
  return (
    <div className="rounded-xl border border-hairline divide-y divide-hairline overflow-hidden">
      {VOICE.map((row) => (
        <div
          key={row.k}
          className="flex items-start gap-3 px-4 py-3 text-[13px]"
        >
          <span className="font-mono uppercase tracking-[0.16em] text-[10px] text-bone/40 w-20 shrink-0 pt-0.5">
            {row.k}
          </span>
          <span className="text-bone/85 font-display italic text-[15.5px] leading-snug">
            {row.v}
          </span>
        </div>
      ))}
    </div>
  );
}

// --- Skill.md file ---
function SkillFile() {
  return (
    <div className="rounded-xl border border-hairline bg-night/60 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-hairline">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
          <span className="font-mono text-[11px] text-bone/80">
            hormozi-hook.skill.md
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-cinnabar/80">
          injected
        </span>
      </div>
      <div className="px-4 py-3 space-y-1.5 font-mono text-[12px] leading-relaxed">
        <div>
          <span className="text-cinnabar">#</span>{" "}
          <span className="text-bone/90">Hook framework</span>
        </div>
        <div className="text-bone/60">
          <span className="text-cinnabar/70">—</span> open with the cost of
          ignorance
        </div>
        <div className="text-bone/60">
          <span className="text-cinnabar/70">—</span> name the one thing
          competitors hide
        </div>
        <div className="text-bone/60">
          <span className="text-cinnabar/70">—</span> promise a specific,
          measurable shift
        </div>
        <div className="pt-2 text-bone/35">
          <span className="text-cinnabar/60">›</span> 7 more rules · 2.1 KB
        </div>
      </div>
    </div>
  );
}
