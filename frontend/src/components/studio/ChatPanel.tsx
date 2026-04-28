import { useCallback, useEffect, useRef, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  PaperPlaneTilt,
  Sparkle,
  Image as ImageIcon,
  ArrowsClockwise,
  Plus,
  CaretDown,
  FileText,
  Lightning,
} from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";

type Mode = "text" | "screenshot" | "regenerate";

const MODES: {
  key: Mode;
  label: string;
  hint: string;
  icon: React.ElementType;
}[] = [
  {
    key: "text",
    label: "Refine text",
    hint: "Sharpen a section, beat, or transition.",
    icon: Sparkle,
  },
  {
    key: "screenshot",
    label: "Screenshot to edit",
    hint: "Paste a screenshot — describe the change.",
    icon: ImageIcon,
  },
  {
    key: "regenerate",
    label: "Regenerate scene",
    hint: "Steer the next scene build with a note.",
    icon: ArrowsClockwise,
  },
];

type LocalMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode: Mode;
  imageUrl?: string | null;
  createdAt: number;
};

type Props = {
  sessionId: string | null;
};

/**
 * Right-pane chat shell.
 *
 * Always visible, scoped to this idea — full context (script + outline +
 * scene) is pre-loaded server-side once the backend chat endpoint lands.
 * For now this is a UI-only shell: messages live in component state and
 * the "send" path emits a stubbed assistant reply so the founder can see
 * the conversation shape. Wiring to the real `sharpen_this` endpoint is
 * the next milestone.
 */
export function ChatPanel({ sessionId }: Props) {
  const [mode, setMode] = useState<Mode>("text");
  const [draft, setDraft] = useState("");
  const [pastedImage, setPastedImage] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [skill, setSkill] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({
      top: threadRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length]);

  const onPaste = useCallback((e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const item = Array.from(e.clipboardData.items).find((i) =>
      i.type.startsWith("image/"),
    );
    if (!item) return;
    const file = item.getAsFile();
    if (!file) return;
    e.preventDefault();
    const url = URL.createObjectURL(file);
    setPastedImage(url);
    if (mode !== "screenshot") setMode("screenshot");
  }, [mode]);

  const send = () => {
    const trimmed = draft.trim();
    if (!trimmed && !pastedImage) return;
    const id = `local-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const userMsg: LocalMessage = {
      id,
      role: "user",
      content: trimmed,
      mode,
      imageUrl: pastedImage,
      createdAt: Date.now(),
    };
    const stub: LocalMessage = {
      id: `${id}-r`,
      role: "assistant",
      content:
        mode === "text"
          ? "(stub) text refinement crew will land here once /sharpen ships."
          : mode === "screenshot"
            ? "(stub) screenshot-to-edit will diff the canvas against your note."
            : "(stub) the next scene build will pick up this steer.",
      mode,
      createdAt: Date.now() + 1,
    };
    setMessages((prev) => [...prev, userMsg, stub]);
    setDraft("");
    setPastedImage(null);
    composerRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      send();
    }
  };

  return (
    <aside className="flex flex-col min-h-0 bg-night h-full">
      <div className="flex items-center gap-2 h-10 px-4 border-b border-hairline shrink-0">
        <span className="font-sans font-semibold text-[13px] text-white">
          Sharpen
        </span>
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full shrink-0",
            sessionId ? "bg-cinnabar" : "bg-white/20",
          )}
          title={sessionId ? "Scoped to this idea" : "Waiting for session"}
        />
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
          {sessionId ? "scoped to this idea" : "no session yet"}
        </span>
      </div>

      <Tabs.Root
        value={mode}
        onValueChange={(v) => setMode(v as Mode)}
        className="flex flex-col min-h-0 flex-1"
      >
        <Tabs.List className="flex items-stretch border-b border-hairline shrink-0 px-2">
          {MODES.map((m) => (
            <Tabs.Trigger
              key={m.key}
              value={m.key}
              className={cn(
                "group inline-flex items-center gap-1.5 px-2.5 py-2",
                "text-[12px] text-mist hover:text-white/85 transition-colors",
                "data-[state=active]:text-white",
                "relative",
              )}
            >
              <m.icon size={11} weight="bold" />
              {m.label}
              <span
                className={cn(
                  "absolute left-2 right-2 -bottom-px h-px bg-cinnabar opacity-0",
                  "group-data-[state=active]:opacity-100 transition-opacity",
                )}
              />
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <div
          ref={threadRef}
          className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3"
        >
          {messages.length === 0 ? (
            <EmptyState mode={mode} />
          ) : (
            messages.map((m) => <MessageRow key={m.id} message={m} />)
          )}
        </div>

        <Composer
          mode={mode}
          draft={draft}
          onDraftChange={setDraft}
          onSend={send}
          onPaste={onPaste}
          onKeyDown={onKeyDown}
          pastedImage={pastedImage}
          onClearImage={() => setPastedImage(null)}
          skill={skill}
          onSelectSkill={setSkill}
          composerRef={composerRef}
        />
      </Tabs.Root>
    </aside>
  );
}

function EmptyState({ mode }: { mode: Mode }) {
  const m = MODES.find((x) => x.key === mode)!;
  return (
    <div className="rounded-lg border border-hairline bg-surface p-5">
      <m.icon size={16} weight="bold" className="text-mist mb-2" />
      <p className="text-[13.5px] text-white mb-1">{m.label}</p>
      <p className="text-[12px] text-mist font-mono leading-[1.6]">{m.hint}</p>
      <p className="mt-3 text-[11.5px] text-white/55 leading-[1.55]">
        Full context (script + outline + scene) is preloaded once the backend
        crew is wired. This thread stays scoped to this idea.
      </p>
    </div>
  );
}

function MessageRow({ message }: { message: LocalMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[88%] rounded-lg px-3 py-2 text-[13px] leading-[1.55]",
          isUser
            ? "bg-cinnabar/[0.12] text-white border border-cinnabar/30"
            : "bg-surface text-white/85 border border-hairline",
        )}
      >
        {message.imageUrl ? (
          <img
            src={message.imageUrl}
            alt="pasted screenshot"
            className="max-w-full max-h-48 rounded mb-2 border border-hairline"
          />
        ) : null}
        {message.content ? <span>{message.content}</span> : null}
      </div>
    </div>
  );
}

function Composer({
  mode,
  draft,
  onDraftChange,
  onSend,
  onPaste,
  onKeyDown,
  pastedImage,
  onClearImage,
  skill,
  onSelectSkill,
  composerRef,
}: {
  mode: Mode;
  draft: string;
  onDraftChange: (v: string) => void;
  onSend: () => void;
  onPaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  pastedImage: string | null;
  onClearImage: () => void;
  skill: string | null;
  onSelectSkill: (v: string | null) => void;
  composerRef: React.MutableRefObject<HTMLTextAreaElement | null>;
}) {
  const placeholder =
    mode === "screenshot"
      ? "Paste a screenshot, then describe the change…"
      : mode === "regenerate"
        ? "How should the next scene differ from this one?"
        : "Refine a section, beat, or transition…";

  return (
    <div className="border-t border-hairline shrink-0 px-3 py-2.5 space-y-2">
      {pastedImage ? (
        <div className="relative inline-block">
          <img
            src={pastedImage}
            alt="pasted screenshot"
            className="max-h-32 rounded border border-cinnabar/30"
          />
          <button
            type="button"
            onClick={onClearImage}
            className={cn(
              "absolute top-1 right-1 inline-flex items-center justify-center",
              "h-5 w-5 rounded-full bg-night/80 border border-hairline text-mist",
              "hover:text-white",
            )}
            title="Remove screenshot"
          >
            <Plus size={10} weight="bold" className="rotate-45" />
          </button>
        </div>
      ) : null}
      <textarea
        ref={composerRef}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        rows={3}
        placeholder={placeholder}
        className={cn(
          "w-full resize-none rounded-md border border-hairline bg-surface",
          "px-3 py-2 text-[13px] text-white outline-none",
          "focus:border-cinnabar/40 focus:ring-1 focus:ring-cinnabar/40",
          "placeholder:text-mist",
        )}
      />
      <div className="flex items-center gap-2">
        <SkillDropdown skill={skill} onSelect={onSelectSkill} />
        <span className="flex-1" />
        <span className="font-mono text-[10px] text-mist">
          {navigator.platform.toLowerCase().includes("mac") ? "⌘" : "Ctrl"}+↵
        </span>
        <Button size="sm" variant="primary" onClick={onSend}>
          <PaperPlaneTilt size={12} weight="bold" />
          Send
        </Button>
      </div>
    </div>
  );
}

function SkillDropdown({
  skill,
  onSelect,
}: {
  skill: string | null;
  onSelect: (skill: string | null) => void;
}) {
  // Stub list — real catalog comes from the user's skill_files rows.
  const SKILLS = [
    { id: "voice.md", label: "voice.md", hint: "Founder voice + tone" },
    { id: "research.md", label: "research.md", hint: "Sourcing rules" },
    { id: "structure.md", label: "structure.md", hint: "Section scaffolds" },
  ];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1.5 h-7 px-2 rounded-md",
            "border border-hairline bg-surface text-mist",
            "hover:text-white hover:border-hairline-strong transition-colors",
            "text-[11.5px] font-mono",
            skill && "text-white border-cinnabar/40",
          )}
        >
          <FileText size={11} weight="bold" />
          {skill ?? "Inject skill.md"}
          <CaretDown size={9} weight="bold" className="opacity-70" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className={cn(
            "z-30 min-w-[220px] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-bottom-left",
          )}
        >
          <div className="px-3 pt-2.5 pb-2 border-b border-hairline">
            <div className="flex items-center gap-1.5">
              <Lightning size={10} weight="bold" className="text-mist" />
              <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist">
                Inject context
              </span>
            </div>
            <p className="mt-1 text-[11.5px] text-white/70 leading-[1.5]">
              Pin a skill.md file so every refinement reads it before
              drafting.
            </p>
          </div>
          <ul className="py-1">
            {skill ? (
              <li>
                <button
                  type="button"
                  onClick={() => onSelect(null)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-[12px] text-mist hover:bg-white/[0.04] hover:text-white text-left"
                >
                  Clear injection
                </button>
              </li>
            ) : null}
            {SKILLS.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onSelect(s.id)}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-1.5 text-left",
                    "hover:bg-white/[0.04]",
                  )}
                >
                  <span className="text-[12px] text-white/85 font-mono w-[88px] shrink-0">
                    {s.label}
                  </span>
                  <span className="text-[11.5px] text-mist truncate">
                    {s.hint}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
