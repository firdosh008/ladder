import { motion } from "framer-motion";
import { fadeUp, stagger } from "../lib/motion";

const steps = [
  {
    idx: "01",
    title: "Paste, pick, or prompt",
    body:
      "Drop a tweet, a half-finished Notion doc, or one sentence. Pick from ideas the research agent deposited quietly all week.",
    chip: "3 ways in",
    rotate: -1.2,
  },
  {
    idx: "02",
    title: "Script streams in",
    body:
      "Section by section — Intro, Problem, Framework, Walkthrough, Close. In your voice, pulled from your profile and knowledge graph.",
    chip: "SSE",
    rotate: 0.6,
  },
  {
    idx: "03",
    title: "Scene renders itself",
    body:
      "A dark-canvas Excalidraw scene opens alongside the script. Paste a screenshot, type a correction, get a surgical diff back.",
    chip: "vision",
    rotate: -0.4,
  },
  {
    idx: "04",
    title: "Thumbnail lands",
    body:
      "Once the scene is approved, a thumbnail worth clicking is already in the artifact drawer. Pick a variant and hit record.",
    chip: "v3 DALL-E / NanoBanana",
    rotate: 1.6,
  },
];

export default function Workflow() {
  return (
    <section id="workflow" className="relative py-32 md:py-40 px-6 md:px-10">
      <div className="max-w-[1400px] mx-auto">
        <motion.div
          variants={stagger(0.1, 0.1)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          className="grid grid-cols-1 lg:grid-cols-12 gap-10 mb-20"
        >
          <motion.div variants={fadeUp} className="lg:col-span-5">
            <div className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 mb-6">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-bone/70">
                § 01 · the path
              </span>
            </div>
            <h2 className="font-display text-editorial text-bone text-balance">
              No button.
              <br />
              <span className="italic text-bone/60">Just</span>{" "}
              <span className="cinnabar-underline">a path</span>.
            </h2>
          </motion.div>

          <motion.div
            variants={fadeUp}
            className="lg:col-span-6 lg:col-start-7 lg:pt-6"
          >
            <p className="text-[17px] leading-[1.6] text-bone/65 max-w-[54ch]">
              Generate-button UIs optimise for demos, not for shipping. Ladder
              replaces the button with a <span className="text-bone">path</span>
              : the studio loads, two things happen at once — the script
              streams in and the scene outlines alongside. Your job is to
              approve, not to orchestrate.
            </p>
          </motion.div>
        </motion.div>

        {/* Z-axis cascade — slightly overlapping, lightly rotated */}
        <motion.div
          variants={stagger(0.1, 0.12)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.15 }}
          className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-x-8 md:gap-y-12 relative"
        >
          {steps.map((step, i) => (
            <motion.div
              key={step.idx}
              variants={fadeUp}
              style={{ rotate: `${step.rotate}deg` }}
              className={`relative md:even:mt-10 md:odd:-mt-2 ${
                i === 1 ? "md:translate-x-4" : ""
              } ${i === 2 ? "md:-translate-x-4" : ""}`}
            >
              <div className="bezel-shell hover:shadow-diffuse transition-shadow duration-700 ease-fluid">
                <div className="bezel-core p-8 md:p-10 relative overflow-hidden">
                  {/* corner index */}
                  <div className="flex items-start justify-between mb-10">
                    <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-bone/40">
                      step · {step.idx}
                    </span>
                    <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-cinnabar/80 border border-cinnabar/30 rounded-full px-2.5 py-1 bg-cinnabar-wash">
                      {step.chip}
                    </span>
                  </div>

                  <h3 className="font-display text-[28px] md:text-[34px] leading-[1.05] tracking-tight text-bone mb-5">
                    {step.title}
                  </h3>
                  <p className="text-[15.5px] leading-[1.62] text-bone/65 max-w-[46ch]">
                    {step.body}
                  </p>

                  {/* ornament — a rough line */}
                  <svg
                    viewBox="0 0 180 10"
                    className="mt-8 w-36 h-2"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M2 6 C 30 2, 60 8, 90 5 C 120 2, 150 8, 178 4"
                      stroke="rgba(232,68,42,0.55)"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
