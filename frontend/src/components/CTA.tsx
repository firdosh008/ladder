import { motion, useMotionValue, useTransform } from "framer-motion";
import { ArrowUpRight } from "@phosphor-icons/react";
import type { MouseEvent } from "react";
import { fadeUp, stagger } from "../lib/motion";

export default function CTA() {
  return (
    <section id="cta" className="relative py-32 md:py-40 px-6 md:px-10">
      <div className="max-w-[1400px] mx-auto">
        <motion.div
          variants={stagger(0.1, 0.12)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          className="relative bezel-shell"
        >
          <div className="bezel-core p-10 md:p-20 relative overflow-hidden">
            <div
              className="absolute inset-0 pointer-events-none opacity-80"
              style={{
                backgroundImage:
                  "radial-gradient(800px 400px at 15% 10%, rgba(232,68,42,0.18), transparent 60%), radial-gradient(600px 300px at 90% 90%, rgba(139,74,58,0.12), transparent 60%)",
              }}
            />

            <motion.div
              variants={fadeUp}
              className="relative max-w-[860px]"
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-cinnabar/40 bg-cinnabar-wash px-3 py-1 mb-8">
                <span className="h-1.5 w-1.5 rounded-full bg-cinnabar animate-pulse-dot" />
                <span className="font-mono text-[10.5px] uppercase tracking-[0.24em] text-cinnabar">
                  9 seats · 3 open
                </span>
              </div>

              <h2 className="font-display text-[clamp(2.5rem,7vw,5.5rem)] leading-[0.95] tracking-tight text-bone text-balance">
                Don't{" "}
                <span className="relative inline-block">
                  <span className="line-through decoration-cinnabar decoration-[3px] underline-offset-[0.15em]">
                    generate
                  </span>
                </span>
                .
                <br />
                <span className="italic">Ladder.</span>
              </h2>

              <p className="mt-8 max-w-[56ch] text-[17px] leading-[1.6] text-bone/65">
                Private pilot for founder-operators shipping at least two
                videos a month. We provision your alias, your brand, your
                knowledge graph — and walk you through one full session before
                you're alone with it.
              </p>

              <motion.div variants={fadeUp} className="mt-10 flex flex-wrap gap-3">
                <MagneticApply />
                <a
                  href="mailto:pilot@ladder.so?subject=Ladder%20OS%20pilot"
                  className="inline-flex items-center gap-2.5 px-5 py-3 rounded-full border border-hairline-strong text-bone/90 text-[14px] font-medium hover:bg-white/[0.04] transition-colors duration-500 ease-fluid"
                >
                  <span>Just send the brief</span>
                  <span className="font-mono text-[11px] text-bone/50">
                    pilot@ladder.so
                  </span>
                </a>
              </motion.div>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function MagneticApply() {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const tx = useTransform(x, (v) => v * 0.35);
  const ty = useTransform(y, (v) => v * 0.35);

  function onMove(e: MouseEvent<HTMLAnchorElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    x.set(e.clientX - (r.left + r.width / 2));
    y.set(e.clientY - (r.top + r.height / 2));
  }
  function onLeave() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.a
      href="mailto:pilot@ladder.so?subject=Ladder%20OS%20pilot%20application"
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ x: tx, y: ty }}
      className="group inline-flex items-center gap-2 pl-5 pr-1.5 py-1.5 rounded-full bg-cinnabar text-night text-[14.5px] font-medium shadow-cinnabar transition-all duration-500 ease-spring active:scale-[0.97] hover:bg-[#F05434]"
    >
      <span className="pl-1 pr-1">Request a seat</span>
      <span className="flex items-center justify-center w-9 h-9 rounded-full bg-night/20 transition-transform duration-500 ease-spring group-hover:translate-x-1 group-hover:-translate-y-[1px]">
        <ArrowUpRight size={15} weight="bold" />
      </span>
    </motion.a>
  );
}
