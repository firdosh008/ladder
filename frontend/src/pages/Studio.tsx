import { useEffect, useState, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Paperclip,
  BookOpenText,
  Sparkle,
  CheckCircle,
  CaretDown,
  Download,
  ArrowsClockwise,
  MagnifyingGlassPlus,
} from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Pill } from "../components/ui/Pill";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";

type Section = {
  id: string;
  idx: string;
  title: string;
  mins: number;
  points: string[];
  transition: string;
};

const SCRIPT: Section[] = [
  {
    id: "intro",
    idx: "01",
    title: "Intro",
    mins: 2,
    points: [
      "open with the cost of *not* thinking about agents — the SaaS you pay for already does this, you just don't see it",
      "name the one line you're going to defend: SaaS pricing is the wrapper, not the product",
      "promise a diagram that slots together in 8 minutes",
    ],
    transition:
      "Here's where this stops being a take and starts being a map →",
  },
  {
    id: "problem",
    idx: "02",
    title: "Problem",
    mins: 3,
    points: [
      "per-seat pricing encodes a human-labor assumption that agents invalidate",
      "procurement departments can't yet price 'task completion' — there's no SKU for it",
      "so SaaS vendors add agent features on top instead of at the core",
    ],
    transition: "And this is where the framework starts earning its keep →",
  },
  {
    id: "framework",
    idx: "03",
    title: "Framework",
    mins: 8,
    points: [
      "draw the three layers: **interface / coordination / execution** — SaaS owns the interface, agents own execution, coordination is contested",
      "walk through how each of those layers gets unbundled, with one example per layer",
      "show the failure mode: vendors who try to own all three end up shipping worse versions of each",
    ],
    transition: "Let me show you what this looks like in practice →",
  },
  {
    id: "walk",
    idx: "04",
    title: "Walkthrough",
    mins: 5,
    points: [
      "real example: how we replaced three SaaS tools with one coordination layer + agents",
      "the cost chart — from $840/mo seats to $47/mo compute + coordination",
      "the part we kept: the interface was worth paying for. Agents aren't always the answer",
    ],
    transition: "So what do you do with all this on a Monday morning? →",
  },
  {
    id: "close",
    idx: "05",
    title: "Close",
    mins: 2,
    points: [
      "one concrete move: audit your top three SaaS tools for 'interface vs execution' — where is the value?",
      "the honest caveat: this takes 6–12 months, not a weekend",
      "the CTA: reply with the tool you're auditing first — I'll send the framework diagram",
    ],
    transition: "",
  },
];

const OUTLINE = [
  "Title card — 'SaaS is a wrapper'",
  "Three-layer diagram (interface / coordination / execution)",
  "Per-seat cost chart — annotated",
  "Case study — tool consolidation",
  "Close frame — your Monday move",
];

const CHAT_SEED: { role: "user" | "assistant"; text: string; time: string }[] = [
  {
    role: "assistant",
    text:
      "I pulled two nodes from your graph that sharpen this: *The knowledge graph monologue* and your note on Lenny's Apr 18 piece. Want me to weave either into the Framework section?",
    time: "11:42",
  },
  {
    role: "user",
    text: "The Lenny angle — but make it a counterpoint, not an endorsement.",
    time: "11:43",
  },
  {
    role: "assistant",
    text:
      "Noted. I'll re-stream Framework with Lenny as the foil — one beat of agreement, one beat of disagreement. Takes ~20s.",
    time: "11:43",
  },
];

export default function StudioPage() {
  const { id = "new" } = useParams();

  return (
    <Shell unconstrained>
      <StudioHeader sessionId={id} />
      <div className="flex-1 grid grid-cols-[1fr_1fr_380px] min-h-0 divide-x divide-hairline">
        <ScriptPanel />
        <ScenePanel />
        <ChatPanel />
      </div>
      <StudioFooter />
    </Shell>
  );
}

function StudioHeader({ sessionId }: { sessionId: string }) {
  return (
    <header className="flex items-center gap-3 px-5 h-12 border-b border-hairline bg-night shrink-0">
      <Link
        to="/videos"
        className="inline-flex items-center gap-1.5 h-7 px-2 rounded-md text-[12.5px] text-mist hover:text-white hover:bg-white/[0.04] transition-colors"
      >
        <ArrowLeft size={12} weight="bold" />
        Pipeline
      </Link>

      <span className="h-4 w-px bg-hairline" />

      <div className="flex items-center gap-1.5 min-w-0">
        <span className="font-display italic text-[15px] text-white truncate max-w-[340px]">
          Why AI agents will replace SaaS
        </span>
        <Badge tone="neutral" className="ml-1">
          <span className="h-1.5 w-1.5 rounded-full bg-cinnabar animate-pulse-dot" />
          streaming
        </Badge>
      </div>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        <Pill accent>Excalidraw</Pill>
        <Pill>Ladder</Pill>
        <Pill>~20 min</Pill>
        <span className="h-4 w-px bg-hairline mx-1" />
        <Button size="sm" variant="ghost" disabled title="Finish your scene first">
          <ImageIcon size={12} weight="regular" />
          Thumbnail
        </Button>
      </div>

      <span className="h-4 w-px bg-hairline mx-1" />

      <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
        session {sessionId}
      </span>
    </header>
  );
}

function ScriptPanel() {
  const [activeIdx, setActiveIdx] = useState(2);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Simulate streaming: advance active section every ~4s up to index 2 (framework),
    // then hold to give the user the "currently writing" feeling.
    if (activeIdx < 2) {
      const t = setTimeout(() => setActiveIdx((i) => i + 1), 4200);
      return () => clearTimeout(t);
    }
  }, [activeIdx]);

  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader
        title="Script"
        hint="stream_script · sonnet-4.5"
        right={
          <Button size="sm" variant="ghost">
            <ArrowsClockwise size={11} weight="bold" />
            Re-stream
          </Button>
        }
      />

      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-6 py-5 space-y-8"
      >
        {SCRIPT.map((sec, i) => {
          const state =
            i < activeIdx ? "done" : i === activeIdx ? "streaming" : "queued";
          return (
            <article
              key={sec.id}
              className={cn(
                "group relative",
                state === "queued" && "opacity-40",
              )}
            >
              <header className="flex items-baseline gap-3 mb-3 pb-2 border-b border-hairline">
                <span
                  className={cn(
                    "font-mono text-[10.5px] tabular-nums tracking-[0.18em] uppercase",
                    state === "streaming" ? "text-cinnabar" : "text-mist",
                  )}
                >
                  § {sec.idx}
                </span>
                <h2 className="font-display text-[22px] text-white leading-none tracking-tight">
                  {sec.title}
                </h2>
                <span className="font-mono text-[11px] text-mist">
                  · {sec.mins} min
                </span>
                <div className="flex-1" />
                {state === "streaming" ? (
                  <Badge tone="cinnabar">
                    <span className="h-1.5 w-1.5 rounded-full bg-white/90 animate-pulse-dot" />
                    writing
                  </Badge>
                ) : state === "done" ? (
                  <Badge tone="neutral">
                    <CheckCircle size={10} weight="fill" className="text-cinnabar" />
                    done
                  </Badge>
                ) : (
                  <Badge tone="muted">queued</Badge>
                )}
              </header>

              <ul className="space-y-2.5 pl-1">
                {sec.points.map((p, pi) => (
                  <li
                    key={pi}
                    className="flex gap-3 text-[14px] leading-[1.6] text-white/85"
                  >
                    <span className="text-cinnabar select-none mt-1">·</span>
                    <span
                      className="flex-1"
                      dangerouslySetInnerHTML={{
                        __html: p.replace(
                          /\*\*(.+?)\*\*/g,
                          '<em class="not-italic text-white font-medium">$1</em>',
                        ).replace(
                          /\*(.+?)\*/g,
                          '<em class="text-white italic">$1</em>',
                        ),
                      }}
                    />
                  </li>
                ))}
                {state === "streaming" ? (
                  <li className="flex gap-3 text-[14px] text-mist">
                    <span className="text-cinnabar select-none mt-1">·</span>
                    <span className="flex items-center gap-1">
                      <span className="italic">writing next point</span>
                      <span className="inline-block w-[7px] h-[14px] align-middle bg-cinnabar animate-pulse-dot ml-0.5" />
                    </span>
                  </li>
                ) : null}
              </ul>

              {sec.transition && state !== "queued" ? (
                <div className="mt-4 pl-5 border-l-2 border-cinnabar/40">
                  <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-cinnabar/80 mb-1">
                    transition
                  </div>
                  <p className="font-display italic text-[14.5px] text-white/90 leading-snug">
                    {sec.transition}
                  </p>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ScenePanel() {
  const [approved, setApproved] = useState(false);

  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader
        title="Scene"
        hint="excalidraw · v3"
        right={
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost">
              <MagnifyingGlassPlus size={11} weight="bold" />
              Open
            </Button>
            <Button size="sm" variant="ghost">
              <Download size={11} weight="bold" />
              .excalidraw
            </Button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto flex flex-col min-h-0">
        {/* Canvas preview */}
        <div className="mx-5 mt-5 rounded-lg border border-hairline bg-[#0a0a0a] relative overflow-hidden aspect-[16/10]">
          <div
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.12) 1px, transparent 0)",
              backgroundSize: "18px 18px",
            }}
          />
          <SceneSketch />
        </div>

        {/* Outline editor */}
        <div className="px-5 pt-5 pb-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1">
                outline · editable
              </div>
              <div className="text-[13.5px] text-white">
                Numbered frames · rebuilds scene when approved
              </div>
            </div>
            {approved ? (
              <Badge tone="cinnabar">approved</Badge>
            ) : (
              <Badge tone="muted">pending</Badge>
            )}
          </div>

          <ol className="space-y-2 mb-4">
            {OUTLINE.map((line, i) => (
              <li
                key={i}
                className="group flex items-center gap-3 rounded-md px-3 h-9 bg-surface border border-hairline hover:border-hairline-strong transition-colors"
              >
                <span className="font-mono mono-tab text-[11px] text-cinnabar/80 w-5 tabular-nums">
                  {(i + 1).toString().padStart(2, "0")}
                </span>
                <span className="text-[13px] text-white flex-1 truncate">
                  {line}
                </span>
                <button className="text-mist opacity-0 group-hover:opacity-100 hover:text-white transition-opacity text-[16px] leading-none">
                  ⋯
                </button>
              </li>
            ))}
          </ol>

          <Button
            onClick={() => setApproved((v) => !v)}
            className="w-full"
            variant={approved ? "secondary" : "primary"}
          >
            {approved ? (
              <>
                <ArrowsClockwise size={12} weight="bold" />
                Rebuild from outline
              </>
            ) : (
              <>
                <CheckCircle size={12} weight="fill" />
                Approve and build scene
              </>
            )}
          </Button>
          <p className="mt-2 font-mono text-[10.5px] text-mist text-center">
            build_scene · outline_approved required
          </p>
        </div>
      </div>
    </section>
  );
}

function SceneSketch() {
  return (
    <svg
      viewBox="0 0 520 330"
      className="absolute inset-0 w-full h-full"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <marker
          id="studio-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="#E8442A" />
        </marker>
      </defs>
      {/* Title */}
      <text
        x="32"
        y="42"
        fontFamily="'Playfair Display', serif"
        fontSize="18"
        fontStyle="italic"
        fill="#F5F1EA"
      >
        SaaS is a wrapper
      </text>
      {/* Three layers */}
      {[
        { x: 32, label: "Interface", sub: "owned by SaaS" },
        { x: 192, label: "Coordination", sub: "contested" },
        { x: 352, label: "Execution", sub: "owned by agents" },
      ].map((b, i) => (
        <g key={i}>
          <rect
            x={b.x}
            y="80"
            width="136"
            height="80"
            rx="3"
            stroke={i === 1 ? "#E8442A" : "#F5F1EA"}
            strokeWidth="1.6"
            fill={i === 1 ? "rgba(232,68,42,0.08)" : "rgba(21,21,21,0.6)"}
          />
          <text
            x={b.x + 12}
            y="108"
            fontFamily="'Playfair Display', serif"
            fontSize="15"
            fill={i === 1 ? "#E8442A" : "#F5F1EA"}
          >
            {b.label}
          </text>
          <text
            x={b.x + 12}
            y="128"
            fontFamily="'JetBrains Mono', monospace"
            fontSize="9"
            fill="#6B6B6B"
          >
            {b.sub}
          </text>
        </g>
      ))}
      {/* Arrows between layers */}
      <path
        d="M 168 120 C 180 120, 180 120, 192 120"
        stroke="#E8442A"
        strokeWidth="1.4"
        markerEnd="url(#studio-arrow)"
      />
      <path
        d="M 328 120 C 340 120, 340 120, 352 120"
        stroke="#E8442A"
        strokeWidth="1.4"
        markerEnd="url(#studio-arrow)"
      />
      {/* Cost strip */}
      <rect
        x="32"
        y="200"
        width="456"
        height="58"
        rx="3"
        stroke="#F5F1EA"
        strokeWidth="1.4"
        fill="rgba(21,21,21,0.6)"
      />
      <text
        x="44"
        y="226"
        fontFamily="'JetBrains Mono', monospace"
        fontSize="11"
        fill="#6B6B6B"
      >
        before
      </text>
      <text
        x="44"
        y="246"
        fontFamily="'JetBrains Mono', monospace"
        fontSize="14"
        fill="#F5F1EA"
      >
        $840 / mo · 14 seats
      </text>
      <line
        x1="260"
        y1="210"
        x2="260"
        y2="250"
        stroke="#3D3D3D"
        strokeWidth="1"
      />
      <text
        x="280"
        y="226"
        fontFamily="'JetBrains Mono', monospace"
        fontSize="11"
        fill="#E8442A"
      >
        after
      </text>
      <text
        x="280"
        y="246"
        fontFamily="'JetBrains Mono', monospace"
        fontSize="14"
        fill="#E8442A"
      >
        $47 / mo · compute
      </text>
      {/* Annotation */}
      <text
        x="32"
        y="296"
        fontFamily="'Playfair Display', serif"
        fontSize="11"
        fontStyle="italic"
        fill="#8B4A3A"
      >
        ← the honest number
      </text>
    </svg>
  );
}

function ChatPanel() {
  const [messages, setMessages] = useState(CHAT_SEED);
  const [draft, setDraft] = useState("");

  function send() {
    if (!draft.trim()) return;
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2, "0")}:${now
      .getMinutes()
      .toString()
      .padStart(2, "0")}`;
    setMessages((m) => [...m, { role: "user", text: draft.trim(), time }]);
    setDraft("");
    setTimeout(() => {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text:
            "Got it — applying as a scoped edit. I'll keep everything else frozen so you don't re-stream the whole thing.",
          time,
        },
      ]);
    }, 900);
  }

  return (
    <aside className="flex flex-col min-h-0 bg-night">
      <PanelHeader
        title="Sharpen"
        hint="chat · 15 turn context"
        right={
          <Button size="sm" variant="ghost">
            <Sparkle size={11} weight="fill" className="text-cinnabar" />
            Regenerate
          </Button>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <div className="text-center py-2">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
            session started · 11:41
          </span>
        </div>

        {messages.map((m, i) => (
          <div
            key={i}
            className={cn(
              "flex",
              m.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            <div
              className={cn(
                "max-w-[90%] rounded-xl px-3.5 py-2.5 text-[13px] leading-[1.55]",
                m.role === "user"
                  ? "bg-cinnabar/[0.12] text-white border border-cinnabar/25"
                  : "bg-surface text-white/90 border border-hairline",
              )}
            >
              <p>{m.text}</p>
              <div
                className={cn(
                  "mt-1.5 font-mono text-[10px]",
                  m.role === "user" ? "text-cinnabar/70" : "text-mist",
                )}
              >
                {m.time}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-hairline p-3">
        {/* Skill inject chip row */}
        <div className="flex items-center gap-2 mb-2">
          <button className="group inline-flex items-center gap-1.5 h-6 px-2 rounded-full bg-white/[0.04] border border-hairline hover:bg-white/[0.08] transition-colors">
            <BookOpenText size={10} weight="regular" className="text-cinnabar" />
            <span className="font-mono text-[10.5px] text-white/80">
              inject skill.md
            </span>
            <CaretDown size={9} className="text-mist" />
          </button>
          <button className="group inline-flex items-center gap-1.5 h-6 px-2 rounded-full bg-white/[0.04] border border-hairline hover:bg-white/[0.08] transition-colors">
            <Paperclip size={10} weight="bold" className="text-mist" />
            <span className="font-mono text-[10.5px] text-white/80">
              screenshot
            </span>
          </button>
          <div className="flex-1" />
          <span className="font-mono text-[10px] text-mist">~18k tok</span>
        </div>

        <div className="rounded-lg border border-hairline bg-surface-input focus-within:border-cinnabar transition-colors">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                send();
              }
            }}
            rows={2}
            placeholder="Tighten the framework, swap Lenny for a counterpoint, paste a screenshot…"
            className="w-full bg-transparent resize-none px-3 py-2.5 text-[13px] text-white placeholder:text-mist font-sans leading-[1.5] focus:outline-none"
          />
          <div className="flex items-center justify-between px-3 pb-2 pt-1">
            <span className="font-mono text-[10px] text-mist">
              ⌘↵ send · / commands
            </span>
            <Button
              size="sm"
              onClick={send}
              disabled={!draft.trim()}
              className="h-7 px-2.5"
            >
              Send
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}

function PanelHeader({
  title,
  hint,
  right,
}: {
  title: string;
  hint?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 h-10 px-5 border-b border-hairline bg-night shrink-0">
      <span className="font-sans font-semibold text-[13px] text-white">
        {title}
      </span>
      {hint ? (
        <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
          {hint}
        </span>
      ) : null}
      <div className="flex-1" />
      {right}
    </div>
  );
}

function StudioFooter() {
  return (
    <footer className="flex items-center gap-4 h-7 px-5 border-t border-hairline bg-night shrink-0 font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-cinnabar animate-pulse-dot" />
        writing · section 03
      </span>
      <span className="h-3 w-px bg-hairline" />
      <span>tokens · 8,412 in · 2,104 out</span>
      <span className="h-3 w-px bg-hairline" />
      <span>$0.47</span>
      <div className="flex-1" />
      <span>ctrl+k commands</span>
    </footer>
  );
}
