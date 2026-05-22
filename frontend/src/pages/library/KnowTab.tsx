import { useMemo, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, X, Plus } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import { useAuth, type Profile } from "../../lib/auth";
import { api } from "../../lib/api";
import TopicTerritory from "./TopicTerritory";

const PROFILE_FIELDS: {
  key: keyof Profile;
  label: string;
  hint: string;
  improvement: string;
  multiline?: boolean;
}[] = [
  {
    key: "display_name",
    label: "Display name",
    hint: "Shown on dashboard + signatures.",
    improvement: "Your name as it should appear everywhere in Ladder.",
  },
  {
    key: "positioning",
    label: "Positioning",
    hint: "One sentence on what you do and for whom.",
    improvement: "One sentence that tells agents who you are and what you talk about.",
    multiline: true,
  },
  {
    key: "audience",
    label: "Audience",
    hint: "Who the videos are for.",
    improvement: "Who you're talking to — founders, engineers, operators, etc.",
  },
  {
    key: "voice",
    label: "Voice",
    hint: "How you sound. Auto-refined from script edits.",
    improvement: "How you sound — conversational, analytical, provocative, etc.",
    multiline: true,
  },
  {
    key: "things_to_avoid",
    label: "Things to avoid",
    hint: "Topics, phrasings, or framings to skip.",
    improvement: "Topics, phrasings, or framings you want to stay away from.",
    multiline: true,
  },
];

function completenessFor(profile: Profile | null): {
  pct: number;
  filled: number;
  total: number;
} {
  const keys: (keyof Profile)[] = [
    "display_name",
    "positioning",
    "audience",
    "voice",
    "things_to_avoid",
    "creators_followed",
  ];
  if (!profile) return { pct: 0, filled: 0, total: keys.length };
  const filled = keys.filter((k) => {
    const v = profile[k];
    if (Array.isArray(v)) return v.length > 0;
    return typeof v === "string" && v.trim().length > 0;
  }).length;
  return {
    pct: Math.round((filled / keys.length) * 100),
    filled,
    total: keys.length,
  };
}

export default function KnowTab() {
  const { profile, loading, refreshProfile } = useAuth();
  const { pct, filled, total } = useMemo(
    () => completenessFor(profile),
    [profile],
  );
  const creators = profile?.creators_followed ?? [];

  const missingFields = PROFILE_FIELDS.filter(({ key }) => {
    if (key === "creators_followed") return creators.length === 0;
    const v = profile?.[key];
    return !(typeof v === "string" && v.trim().length > 0);
  });

  return (
    <div className="space-y-4 max-w-[1100px]">
      {/* Profile completeness card */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1">
              profile completeness
            </div>
            <div className="font-display text-[28px] text-white leading-none tabular-nums">
              {pct}%
            </div>
          </div>
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 text-[12.5px] text-mist hover:text-white transition-colors"
          >
            Edit in settings
            <ArrowRight size={11} weight="bold" />
          </Link>
        </div>
        <div className="h-1 rounded-full bg-white/[0.04] overflow-hidden">
          <div
            className="h-full bg-cinnabar transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-3 font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist">
          {filled} / {total} fields filled
        </p>

        {missingFields.length > 0 && (
          <div className="mt-4 pt-3 border-t border-hairline space-y-1.5">
            {missingFields.map(({ key, label, improvement }) => (
              <div
                key={key}
                className="flex items-start gap-2 text-[12px] text-mist"
              >
                <span className="text-cinnabar mt-0.5 shrink-0">—</span>
                <span>
                  Set your{" "}
                  <strong className="text-white/85">{label}</strong> —{" "}
                  {improvement}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Profile fields table with inline editing */}
      <div className="rounded-xl border border-hairline bg-surface">
        <div className="px-5 py-3 border-b border-hairline flex items-center justify-between">
          <span className="text-[13px] text-white font-medium">
            What the agents see about you
          </span>
          <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
            interpolated into every prompt
          </span>
        </div>
        {loading && !profile ? (
          <div className="px-5 py-8 font-mono text-[11.5px] text-mist">
            loading profile…
          </div>
        ) : (
          <ul className="divide-y divide-hairline">
            {PROFILE_FIELDS.map(({ key, label, hint, multiline }) => (
              <InlineEditField
                key={key}
                fieldKey={key as string}
                label={label}
                hint={hint}
                multiline={multiline}
                value={
                  typeof profile?.[key] === "string"
                    ? (profile[key] as string)
                    : ""
                }
                onSaved={refreshProfile}
              />
            ))}
            <CreatorsEditor
              creators={creators}
              onSaved={refreshProfile}
            />
          </ul>
        )}
      </div>

      {/* Topic territory */}
      <TopicTerritory />
    </div>
  );
}

function InlineEditField({
  fieldKey,
  label,
  hint,
  multiline,
  value,
  onSaved,
}: {
  fieldKey: string;
  label: string;
  hint: string;
  multiline?: boolean;
  value: string;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = useCallback(() => {
    setLocal(value);
    setEditing(true);
    setError(null);
  }, [value]);

  const handleSave = useCallback(async () => {
    if (local === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.patch("/auth/profile", { [fieldKey]: local });
      onSaved();
      setEditing(false);
    } catch (e: any) {
      setError(e?.message ?? "Failed to save");
      setLocal(value); // rollback
    } finally {
      setSaving(false);
    }
  }, [fieldKey, local, value, onSaved]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setLocal(value);
      setEditing(false);
      setError(null);
    }
    if (e.key === "Enter" && !multiline) {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <li className="px-5 py-3.5 grid grid-cols-[180px_1fr] gap-4 items-start">
      <div>
        <div className="text-[13px] text-white">{label}</div>
        <div className="font-mono text-[11px] text-mist mt-0.5">{hint}</div>
      </div>
      <div>
        {editing ? (
          <div className="space-y-1.5">
            {multiline ? (
              <textarea
                value={local}
                onChange={(e) => setLocal(e.target.value)}
                onBlur={handleSave}
                onKeyDown={handleKeyDown}
                autoFocus
                rows={3}
                className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 py-2 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20 resize-y"
                disabled={saving}
              />
            ) : (
              <input
                type="text"
                value={local}
                onChange={(e) => setLocal(e.target.value)}
                onBlur={handleSave}
                onKeyDown={handleKeyDown}
                autoFocus
                className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 h-9 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
                disabled={saving}
              />
            )}
            {error && (
              <p className="text-[11.5px] text-sienna">{error}</p>
            )}
            <p className="font-mono text-[10.5px] text-mist">
              {saving
                ? "saving…"
                : "Enter to save · Esc to cancel · Click away to save"}
            </p>
          </div>
        ) : (
          <button
            onClick={startEdit}
            className={cn(
              "text-left w-full text-[13px] leading-[1.55] rounded px-1.5 py-0.5 -mx-1.5 -my-0.5",
              "hover:bg-white/[0.04] transition-colors",
              value ? "text-white/85" : "text-mist italic",
              multiline ? "whitespace-pre-wrap" : "",
            )}
          >
            {value || "click to set"}
          </button>
        )}
      </div>
    </li>
  );
}

function CreatorsEditor({
  creators,
  onSaved,
}: {
  creators: string[];
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [local, setLocal] = useState<string[]>(creators);
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = useCallback(() => {
    setLocal([...creators]);
    setEditing(true);
    setError(null);
  }, [creators]);

  const save = useCallback(
    async (updated: string[]) => {
      setSaving(true);
      setError(null);
      try {
        await api.patch("/auth/profile", {
          creators_followed: updated,
        });
        onSaved();
      } catch (e: any) {
        setError(e?.message ?? "Failed to save");
        setLocal([...creators]);
      } finally {
        setSaving(false);
      }
    },
    [creators, onSaved],
  );

  function addCreator() {
    const name = input.trim();
    if (!name || local.includes(name)) return;
    const updated = [...local, name];
    setLocal(updated);
    setInput("");
    save(updated);
    inputRef.current?.focus();
  }

  function removeCreator(name: string) {
    const updated = local.filter((c) => c !== name);
    setLocal(updated);
    save(updated);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      addCreator();
    }
    if (e.key === "Escape") {
      setLocal([...creators]);
      setEditing(false);
      setError(null);
    }
  }

  return (
    <li className="px-5 py-3.5 grid grid-cols-[180px_1fr] gap-4 items-start">
      <div>
        <div className="text-[13px] text-white">
          Creators you sound closest to
        </div>
        <div className="font-mono text-[11px] text-mist mt-0.5">
          Seeds the voice profile.
        </div>
      </div>
      <div>
        {editing ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1.5">
              {local.length === 0 && (
                <span className="text-[13px] text-mist italic">
                  no creators yet
                </span>
              )}
              {local.map((c) => (
                <span
                  key={c}
                  className="inline-flex items-center gap-1 font-mono text-[11px] text-white/85 border border-hairline rounded px-2 py-0.5"
                >
                  {c}
                  <button
                    onClick={() => removeCreator(c)}
                    disabled={saving}
                    className="text-mist hover:text-white disabled:opacity-40"
                  >
                    <X size={10} weight="bold" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Add a creator name…"
                className="flex-1 bg-white/[0.06] border border-hairline rounded-md px-3 h-8 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
                disabled={saving}
              />
              <button
                onClick={addCreator}
                disabled={!input.trim() || saving}
                className="inline-flex items-center gap-1 h-8 px-2.5 rounded-md bg-white/[0.06] border border-hairline text-[12px] text-white hover:bg-white/[0.1] transition-colors disabled:opacity-40"
              >
                <Plus size={12} weight="bold" />
                Add
              </button>
            </div>
            {error && (
              <p className="text-[11.5px] text-sienna">{error}</p>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setLocal([...creators]);
                  setEditing(false);
                  setError(null);
                }}
                className="text-[12px] text-mist hover:text-white transition-colors"
              >
                Done
              </button>
              <span className="font-mono text-[10.5px] text-mist">
                {saving ? "saving…" : "Add or remove to save immediately"}
              </span>
            </div>
          </div>
        ) : (
          <button
            onClick={startEdit}
            className="text-left w-full rounded px-1.5 py-0.5 -mx-1.5 -my-0.5 hover:bg-white/[0.04] transition-colors"
          >
            {creators.length === 0 ? (
              <span className="text-[13px] text-mist italic">
                click to set
              </span>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {creators.map((c) => (
                  <span
                    key={c}
                    className="font-mono text-[11px] text-white/85 border border-hairline rounded px-2 py-0.5"
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </button>
        )}
      </div>
    </li>
  );
}
