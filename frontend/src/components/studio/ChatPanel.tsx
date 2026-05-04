import { useCallback, useEffect, useRef, useState } from "react";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  PaperPlaneTilt,
  Sparkle,
  ArrowsClockwise,
  Plus,
  CaretDown,
  FileText,
  Lightning,
} from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";
import { fetchChatHistory, runChatStream } from "../../lib/agents";

type Mode = "text" | "screenshot" | "regenerate";

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
  hasScene?: boolean;
  onRegenerateScene?: () => void;
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
export function ChatPanel({ sessionId, hasScene, onRegenerateScene }: Props) {
  const [draft, setDraft] = useState("");
  const [pastedImage, setPastedImage] = useState<string | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [skill, setSkill] = useState<string | null>(null);
  const inferredMode = pastedImage ? "screenshot" : "text";
  const [isStreaming, setIsStreaming] = useState(false);
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
    const reader = new FileReader();
    reader.onload = (ev) => {
      if (ev.target?.result) {
        setPastedImage(ev.target.result as string);
      }
    };
    reader.readAsDataURL(file);
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    let active = true;
    fetchChatHistory(sessionId)
      .then((data) => {
        if (!active) return;
        const mapped: LocalMessage[] = data.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          mode: "text",
          imageUrl: m.has_image ? "(image preserved in db)" : null,
          createdAt: new Date(m.created_at).getTime(),
        }));
        setMessages(mapped);
      })
      .catch((err) => console.error("Failed to fetch chat history:", err));
    return () => {
      active = false;
    };
  }, [sessionId]);

  const send = async () => {
    const trimmed = draft.trim();
    if (!trimmed && !pastedImage) return;
    if (!sessionId) return;
    if (isStreaming) return;

    const id = `local-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const userMsg: LocalMessage = {
      id,
      role: "user",
      content: trimmed,
      mode: inferredMode,
      imageUrl: pastedImage,
      createdAt: Date.now(),
    };
    
    const astId = `${id}-r`;
    const astMsg: LocalMessage = {
      id: astId,
      role: "assistant",
      content: "",
      mode: inferredMode,
      createdAt: Date.now() + 1,
    };
    
    setMessages((prev) => [...prev, userMsg, astMsg]);
    setDraft("");
    const imgBase64 = pastedImage;
    setPastedImage(null);
    setIsStreaming(true);
    composerRef.current?.focus();

    try {
      await runChatStream(
        sessionId,
        {
          message: trimmed,
          mode: inferredMode,
          image_base64: imgBase64,
          skill,
        },
        (ev) => {
          if (ev.type === "text_delta") {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === astId);
              if (idx === -1) return prev;
              const next = [...prev];
              next[idx] = { ...next[idx], content: next[idx].content + (ev as any).content };
              return next;
            });
          }
        },
      );
    } catch (err) {
      console.error("Chat stream error:", err);
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === astId);
        if (idx === -1) return prev;
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          content: next[idx].content + `\n\n[Error: ${String(err)}]`,
        };
        return next;
      });
    } finally {
      setIsStreaming(false);
    }
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

      <div
        ref={threadRef}
        className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((m) => <MessageRow key={m.id} message={m} />)
        )}
      </div>

      <Composer
        hasScene={hasScene}
        onRegenerateScene={onRegenerateScene}
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
    </aside>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-hairline bg-surface p-5">
      <Sparkle size={16} weight="bold" className="text-mist mb-2" />
      <p className="text-[13.5px] text-white mb-1">Refine & Steer</p>
      <p className="text-[12px] text-mist font-mono leading-[1.6]">
        Talk to the agent to surgically edit the script or excalidraw layout.
      </p>
      <p className="mt-3 text-[11.5px] text-white/55 leading-[1.55]">
        This thread is scoped to this idea. The agent has full access to your script, outline, and scene.
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
  hasScene,
  onRegenerateScene,
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
  hasScene?: boolean;
  onRegenerateScene?: () => void;
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
  const placeholder = hasScene
    ? "Paste a screenshot to edit the scene, or type a message."
    : "Refine a section, beat, or transition…";

  return (
    <div className="border-t border-hairline shrink-0 px-3 py-2.5 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <SkillDropdown skill={skill} onSelect={onSelectSkill} />
        {hasScene ? (
          <Button size="sm" variant="secondary" onClick={onRegenerateScene}>
            <ArrowsClockwise size={11} weight="bold" />
            Regenerate scene
          </Button>
        ) : null}
      </div>

      <div className="relative">
        {pastedImage ? (
          <div className="relative inline-block mb-2">
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
      </div>

      <div className="flex items-center justify-end gap-2">
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
