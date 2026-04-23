import { motion } from "framer-motion";

const PHRASES = [
  "paste · pick · prompt",
  "script streams section by section",
  "scene renders itself",
  "screenshot → diff",
  "voice, not vibes",
  "no hard-coded context",
  "per-user knowledge graph",
  "byok from day one",
];

export default function Marquee() {
  const doubled = [...PHRASES, ...PHRASES];
  return (
    <section
      aria-hidden="true"
      className="relative py-10 border-y border-hairline bg-ink/40 overflow-hidden"
    >
      <motion.div
        className="flex gap-12 whitespace-nowrap"
        animate={{ x: ["0%", "-50%"] }}
        transition={{
          duration: 42,
          ease: "linear",
          repeat: Infinity,
        }}
      >
        {doubled.map((p, i) => (
          <span
            key={i}
            className="flex items-center gap-12 font-display italic text-[clamp(1.5rem,3.2vw,2.6rem)] text-bone/50"
          >
            <span>{p}</span>
            <span className="h-2 w-2 rounded-full bg-cinnabar/70 shrink-0" />
          </span>
        ))}
      </motion.div>
    </section>
  );
}
