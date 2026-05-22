import { motion, useMotionValue, useTransform } from "framer-motion";
import { ArrowUpRight } from "@phosphor-icons/react";
import type { MouseEvent } from "react";
import { Link } from "react-router-dom";

const MotionLink = motion(Link);

const links = [
  { label: "Studio", href: "#studio" },
  { label: "Ladder", href: "#workflow" },
  { label: "Mind", href: "#mind" },
  { label: "Stack", href: "#stack" },
];

export default function Nav() {
  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
      className="fixed top-0 inset-x-0 z-50 pt-6 px-4"
    >
      <div className="mx-auto w-max max-w-[calc(100vw-2rem)]">
        <div className="glass-pill rounded-full flex items-center gap-1 pl-5 pr-1.5 py-1.5">
          <a href="#" className="flex items-center gap-2 pr-4 py-1.5">
            <LadderMark />
            <span className="font-display text-[17px] tracking-tight text-bone">
              Ladder
            </span>
            <span className="hidden sm:inline font-mono text-[10px] uppercase tracking-[0.18em] text-mist">
              /OS
            </span>
          </a>

          <span className="hidden md:block h-5 w-px bg-hairline mx-1" />

          <nav className="hidden md:flex items-center">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="relative px-3.5 py-2 text-[13.5px] text-bone/70 hover:text-bone transition-colors duration-500 ease-fluid"
              >
                {l.label}
              </a>
            ))}
          </nav>

          <MagneticCTA />
        </div>
      </div>
    </motion.header>
  );
}

function LadderMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true">
      <path
        d="M8 22 L16 8 L24 22"
        stroke="#E8442A"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <line
        x1="11"
        y1="17"
        x2="21"
        y2="17"
        stroke="#E8442A"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MagneticCTA() {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const tx = useTransform(x, (v) => v * 0.3);
  const ty = useTransform(y, (v) => v * 0.3);

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
    <MotionLink
      to="/auth"
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ x: tx, y: ty }}
      className="group flex items-center gap-2 pl-4 pr-1.5 py-1.5 rounded-full bg-cinnabar text-night text-[13px] font-medium transition-all duration-500 ease-spring active:scale-[0.97] hover:bg-[#F05434]"
    >
      <span>Open studio</span>
      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-night/15 transition-transform duration-500 ease-spring group-hover:translate-x-0.5 group-hover:-translate-y-px">
        <ArrowUpRight size={13} weight="bold" />
      </span>
    </MotionLink>
  );
}
