import { motion } from "framer-motion";
import { fadeUp, stagger } from "../lib/motion";

const ROWS = [
  { layer: "script", provider: "Claude Sonnet 4.5", via: "SSE stream" },
  { layer: "scene", provider: "Claude Sonnet 4.5", via: ".excalidraw JSON" },
  { layer: "edit", provider: "Claude Vision", via: "screenshot → diff" },
  { layer: "research", provider: "GPT-4o + TubeLab", via: "weekly cron" },
  { layer: "extract", provider: "Gemini 1.5 Pro", via: "content rewrite" },
  { layer: "thumbnail", provider: "NanoBanana Pro / DALL-E 3", via: "byok" },
  { layer: "knowledge", provider: "pgvector · per-user", via: "RLS enforced" },
  { layer: "ingest", provider: "n8n + Cloudflare Email", via: "alias per user" },
];

export default function Stack() {
  return (
    <section id="stack" className="relative py-32 md:py-40 px-6 md:px-10">
      <div className="max-w-[1400px] mx-auto">
        <motion.div
          variants={stagger(0.1, 0.1)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-end mb-14"
        >
          <motion.div variants={fadeUp} className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 mb-6">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-bone/70">
                § 03 · stack
              </span>
            </div>
            <h2 className="font-display text-editorial text-bone">
              BYOK. Per-user.{" "}
              <span className="italic text-bone/55">From day one.</span>
            </h2>
          </motion.div>
          <motion.p
            variants={fadeUp}
            className="lg:col-span-5 text-[15.5px] leading-[1.62] text-bone/60 max-w-[48ch]"
          >
            Every function runs on a model you configure. Keys encrypted in
            Supabase vault. Cross-user data isolation is enforced at the
            database and application layer — a unit test attempts the leak and
            must fail.
          </motion.p>
        </motion.div>

        <motion.div
          variants={stagger(0.05, 0.05)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.1 }}
          className="rounded-squircle border border-hairline overflow-hidden divide-y divide-hairline bg-ink/60"
        >
          <div className="hidden md:grid grid-cols-12 gap-6 px-7 py-4 font-mono text-[10.5px] uppercase tracking-[0.22em] text-bone/40">
            <div className="col-span-1">#</div>
            <div className="col-span-3">layer</div>
            <div className="col-span-5">provider</div>
            <div className="col-span-3">notes</div>
          </div>
          {ROWS.map((row, i) => (
            <motion.div
              variants={fadeUp}
              key={row.layer}
              className="grid grid-cols-1 md:grid-cols-12 gap-2 md:gap-6 px-7 py-5 hover:bg-white/[0.02] transition-colors duration-500 ease-fluid group"
            >
              <div className="md:col-span-1 font-mono mono-tab text-[12px] text-cinnabar/80">
                {(i + 1).toString().padStart(2, "0")}
              </div>
              <div className="md:col-span-3 font-display italic text-[19px] text-bone leading-tight">
                {row.layer}
              </div>
              <div className="md:col-span-5 font-mono text-[13px] text-bone/85">
                {row.provider}
              </div>
              <div className="md:col-span-3 font-mono text-[12px] text-bone/45 group-hover:text-bone/70 transition-colors duration-500 ease-fluid">
                {row.via}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
