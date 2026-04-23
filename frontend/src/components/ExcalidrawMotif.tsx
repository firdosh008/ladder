import { motion } from "framer-motion";
import { drawLine, stagger, fadeUp } from "../lib/motion";

/**
 * Hand-drawn scene motif — mirrors the Excalidraw scenes the product produces.
 * Boxes labeled like script sections, arrows between, wobble filter for rough feel.
 */
export default function ExcalidrawMotif() {
  return (
    <motion.div
      variants={stagger(0.4, 0.18)}
      initial="hidden"
      animate="show"
      className="relative w-full h-full"
    >
      <svg
        viewBox="0 0 640 520"
        className="w-full h-full hand-drawn"
        fill="none"
        aria-hidden="true"
      >
        <defs>
          <filter id="wobble" x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="7" />
            <feDisplacementMap in="SourceGraphic" scale="2.4" />
          </filter>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0,0 L10,5 L0,10 z" fill="#E8442A" />
          </marker>
          <pattern id="dot" width="18" height="18" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.9" fill="rgba(255,255,255,0.08)" />
          </pattern>
        </defs>

        <rect width="640" height="520" fill="url(#dot)" opacity="0.6" />

        {/* INTRO */}
        <motion.g variants={fadeUp}>
          <rect
            x="40"
            y="40"
            width="170"
            height="78"
            rx="4"
            stroke="#F5F1EA"
            strokeWidth="2.2"
            strokeLinejoin="round"
            fill="rgba(21,21,21,0.6)"
          />
          <text
            x="58"
            y="76"
            fontFamily="'Playfair Display', serif"
            fontSize="22"
            fontStyle="italic"
            fill="#F5F1EA"
          >
            Intro
          </text>
          <text
            x="58"
            y="100"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="11"
            fill="#6B6B6B"
          >
            2 min · hook
          </text>
        </motion.g>

        {/* PROBLEM */}
        <motion.g variants={fadeUp}>
          <rect
            x="240"
            y="40"
            width="170"
            height="78"
            rx="4"
            stroke="#F5F1EA"
            strokeWidth="2.2"
            strokeLinejoin="round"
            fill="rgba(21,21,21,0.6)"
          />
          <text
            x="258"
            y="76"
            fontFamily="'Playfair Display', serif"
            fontSize="22"
            fontStyle="italic"
            fill="#F5F1EA"
          >
            Problem
          </text>
          <text
            x="258"
            y="100"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="11"
            fill="#6B6B6B"
          >
            3 min · stakes
          </text>
        </motion.g>

        {/* FRAMEWORK — highlighted */}
        <motion.g variants={fadeUp}>
          <rect
            x="120"
            y="180"
            width="270"
            height="120"
            rx="4"
            stroke="#E8442A"
            strokeWidth="2.6"
            strokeLinejoin="round"
            fill="rgba(232,68,42,0.08)"
          />
          <text
            x="144"
            y="224"
            fontFamily="'Playfair Display', serif"
            fontSize="30"
            fill="#E8442A"
          >
            Framework
          </text>
          <text
            x="144"
            y="250"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="12"
            fill="#F5F1EA"
          >
            8 min · the diagram
          </text>
          <text
            x="144"
            y="272"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="11"
            fill="#6B6B6B"
          >
            architectural explainer
          </text>
        </motion.g>

        {/* WALKTHROUGH */}
        <motion.g variants={fadeUp}>
          <rect
            x="440"
            y="180"
            width="160"
            height="78"
            rx="4"
            stroke="#F5F1EA"
            strokeWidth="2.2"
            strokeLinejoin="round"
            fill="rgba(21,21,21,0.6)"
          />
          <text
            x="458"
            y="216"
            fontFamily="'Playfair Display', serif"
            fontSize="22"
            fontStyle="italic"
            fill="#F5F1EA"
          >
            Walk-thru
          </text>
          <text
            x="458"
            y="240"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="11"
            fill="#6B6B6B"
          >
            5 min · proof
          </text>
        </motion.g>

        {/* CLOSE */}
        <motion.g variants={fadeUp}>
          <rect
            x="240"
            y="360"
            width="170"
            height="78"
            rx="4"
            stroke="#F5F1EA"
            strokeWidth="2.2"
            strokeLinejoin="round"
            fill="rgba(21,21,21,0.6)"
          />
          <text
            x="258"
            y="396"
            fontFamily="'Playfair Display', serif"
            fontSize="22"
            fontStyle="italic"
            fill="#F5F1EA"
          >
            Close
          </text>
          <text
            x="258"
            y="420"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="11"
            fill="#6B6B6B"
          >
            2 min · CTA
          </text>
        </motion.g>

        {/* Arrows drawing in */}
        <motion.path
          variants={drawLine}
          d="M 210 80 C 228 80, 228 80, 240 80"
          stroke="#E8442A"
          strokeWidth="2"
          strokeLinecap="round"
          markerEnd="url(#arrow)"
        />
        <motion.path
          variants={drawLine}
          d="M 300 120 C 290 150, 270 160, 250 180"
          stroke="#E8442A"
          strokeWidth="2"
          strokeLinecap="round"
          markerEnd="url(#arrow)"
        />
        <motion.path
          variants={drawLine}
          d="M 390 240 C 410 240, 420 240, 440 230"
          stroke="#E8442A"
          strokeWidth="2"
          strokeLinecap="round"
          markerEnd="url(#arrow)"
        />
        <motion.path
          variants={drawLine}
          d="M 300 300 C 300 330, 300 340, 310 360"
          stroke="#E8442A"
          strokeWidth="2"
          strokeLinecap="round"
          markerEnd="url(#arrow)"
        />

        {/* Annotation — the messy margin note */}
        <motion.g variants={fadeUp}>
          <text
            x="440"
            y="340"
            fontFamily="'Playfair Display', serif"
            fontSize="14"
            fontStyle="italic"
            fill="#8B4A3A"
          >
            ← the whole point
          </text>
          <path
            d="M 438 336 C 420 324, 400 310, 390 298"
            stroke="#8B4A3A"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeDasharray="3 4"
            fill="none"
          />
        </motion.g>

        {/* Streaming tag above Framework box — scales with SVG */}
        <motion.g variants={fadeUp}>
          <rect
            x="120"
            y="156"
            width="96"
            height="18"
            rx="9"
            fill="#1f0f0c"
            stroke="#E8442A"
            strokeWidth="1.2"
          />
          <circle cx="131" cy="165" r="2.6" fill="#E8442A">
            <animate
              attributeName="opacity"
              values="1;0.4;1"
              dur="1.8s"
              repeatCount="indefinite"
            />
          </circle>
          <text
            x="140"
            y="169"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="9.5"
            letterSpacing="1.4"
            fill="#E8442A"
          >
            STREAMING
          </text>
        </motion.g>

        {/* Handwritten timestamp */}
        <motion.g variants={fadeUp}>
          <text
            x="40"
            y="490"
            fontFamily="'Playfair Display', serif"
            fontSize="13"
            fontStyle="italic"
            fill="#6B6B6B"
          >
            scene · v3 · approved
          </text>
        </motion.g>
      </svg>
    </motion.div>
  );
}
