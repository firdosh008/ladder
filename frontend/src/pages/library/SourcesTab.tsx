import { useState } from "react";
import {
  Plus,
  Copy,
  Check,
  Rss,
  CaretDown,
  CaretRight,
  Trash,
  ToggleRight,
  ToggleLeft,
} from "@phosphor-icons/react";
import { Badge } from "../../components/ui/Badge";
import { cn } from "../../lib/cn";
import { useAuth } from "../../lib/auth";
import {
  useSources,
  useSourceItems,
  type Source,
  type NewsletterItem,
} from "../../lib/useSources";

export default function SourcesTab() {
  const { profile } = useAuth();
  const alias = profile?.forwarding_alias ?? null;
  const [copied, setCopied] = useState(false);

  function copy() {
    if (!alias) return;
    navigator.clipboard.writeText(alias);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="space-y-4 max-w-[1100px]">
      {/* Forwarding alias card */}
      <div
        className={cn(
          "rounded-xl border p-5",
          alias
            ? "border-cinnabar/30 bg-cinnabar/[0.04]"
            : "border-hairline bg-surface",
        )}
      >
        <div className="flex items-center justify-between mb-1">
          <span
            className={cn(
              "font-mono text-[10.5px] uppercase tracking-[0.22em]",
              alias ? "text-cinnabar" : "text-mist",
            )}
          >
            your forwarding alias
          </span>
          {alias ? (
            <Badge tone="cinnabar">active</Badge>
          ) : (
            <Badge tone="muted">pending</Badge>
          )}
        </div>
        <h3 className="font-display text-[22px] text-white leading-tight mb-1">
          Forward any newsletter here.
        </h3>
        <p className="text-[13px] text-mist mb-4 max-w-[60ch]">
          Every forwarded email is extracted, chunked, embedded, and added to
          your graph. No setup — just forward.
        </p>
        {alias ? (
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-[13px] text-white bg-night border border-hairline rounded-md px-3 h-9 flex items-center">
              {alias}
            </code>
            <button
              onClick={copy}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md bg-white/[0.06] border border-hairline hover:bg-white/[0.1] transition-colors text-[12.5px] text-white font-medium"
            >
              {copied ? (
                <>
                  <Check size={12} weight="bold" className="text-cinnabar" />
                  copied
                </>
              ) : (
                <>
                  <Copy size={12} weight="bold" />
                  copy
                </>
              )}
            </button>
          </div>
        ) : (
          <p className="font-mono text-[11.5px] text-mist">
            Alias will be provisioned on first newsletter-source addition.
          </p>
        )}
      </div>

      {/* Sources table + add form */}
      <SourcesList />
    </div>
  );
}

function SourcesList() {
  const {
    sources,
    loading,
    error,
    refresh,
    createSource,
    toggleSource,
    deleteSource,
  } = useSources();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState("newsletter");
  const [senderEmail, setSenderEmail] = useState("");
  const [autoExtract, setAutoExtract] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function handleAdd() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await createSource({
        name: name.trim(),
        source_type: sourceType,
        sender_email: senderEmail.trim() || undefined,
        auto_extract: autoExtract,
      });
      setName("");
      setSenderEmail("");
      setShowForm(false);
    } catch {
      // error surfaced via hook
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[13px] text-white font-medium">
          Connected sources
        </h3>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className={cn(
              "inline-flex items-center gap-1.5 h-8 px-3 rounded-md",
              "bg-white/[0.06] border border-hairline",
              "text-[12.5px] text-white font-medium",
              "hover:bg-white/[0.1] transition-colors",
            )}
          >
            <Plus size={12} weight="bold" />
            Add source
          </button>
        )}
      </div>

      {/* Inline add form */}
      {showForm && (
        <div className="rounded-lg border border-hairline bg-white/[0.02] p-4 mb-3 space-y-3">
          <div className="grid grid-cols-[1fr_1fr] gap-3">
            <div>
              <label className="block font-mono text-[10.5px] text-mist mb-1">
                Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Lenny's Newsletter"
                className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 h-9 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
              />
            </div>
            <div>
              <label className="block font-mono text-[10.5px] text-mist mb-1">
                Type
              </label>
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value)}
                className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 h-9 text-[13px] text-white focus:outline-none focus:border-white/20"
              >
                <option value="newsletter">Newsletter</option>
                <option value="youtube">YouTube Channel</option>
                <option value="x">X Account</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block font-mono text-[10.5px] text-mist mb-1">
              Sender email or handle
            </label>
            <input
              type="text"
              value={senderEmail}
              onChange={(e) => setSenderEmail(e.target.value)}
              placeholder={
                sourceType === "newsletter"
                  ? "newsletter@example.com"
                  : sourceType === "youtube"
                    ? "@channel"
                    : "@handle"
              }
              className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 h-9 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAutoExtract(!autoExtract)}
              className="text-mist hover:text-white transition-colors"
            >
              {autoExtract ? (
                <ToggleRight size={18} weight="fill" className="text-cinnabar" />
              ) : (
                <ToggleLeft size={18} weight="fill" />
              )}
            </button>
            <span className="text-[12.5px] text-mist">
              Auto-extract ideas from incoming emails (recommended)
            </span>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleAdd}
              disabled={saving || !name.trim()}
              className="inline-flex items-center gap-1.5 h-8 px-4 rounded-md bg-cinnabar hover:bg-cinnabar-hover text-white text-[12.5px] font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {saving ? "Adding..." : "Add source"}
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setName("");
                setSenderEmail("");
              }}
              className="h-8 px-3 rounded-md text-[12.5px] text-mist hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && sources.length === 0 && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-12 rounded-lg bg-white/[0.04] animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-hairline bg-surface p-4 text-center">
          <p className="text-[12.5px] text-sienna mb-2">{error}</p>
          <button
            onClick={refresh}
            className="text-[12px] text-cinnabar hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && sources.length === 0 && (
        <div className="rounded-lg border border-hairline bg-surface p-8 text-center">
          <Rss size={18} className="text-mist mx-auto mb-2" />
          <p className="text-[13px] text-white mb-1">
            No sources connected yet.
          </p>
          <p className="text-[12px] text-mist">
            Add a newsletter, YouTube channel, or X account to pipe content into
            your knowledge graph.
          </p>
        </div>
      )}

      {/* Source rows */}
      {sources.length > 0 && (
        <div className="rounded-lg border border-hairline bg-surface overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-[1fr_120px_100px_80px_64px] gap-3 px-4 py-2.5 border-b border-hairline font-mono text-[10.5px] text-mist uppercase tracking-[0.15em]">
            <span>Name</span>
            <span>Last received</span>
            <span>Ideas / mo</span>
            <span>Status</span>
            <span />
          </div>
          {sources.map((source) => (
            <SourceRow
              key={source.id}
              source={source}
              expanded={expandedId === source.id}
              onToggle={() =>
                setExpandedId(expandedId === source.id ? null : source.id)
              }
              onToggleStatus={() =>
                toggleSource(
                  source.id,
                  source.status === "active" ? "paused" : "active",
                )
              }
              onDelete={() => deleteSource(source.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceRow({
  source,
  expanded,
  onToggle,
  onToggleStatus,
  onDelete,
}: {
  source: Source;
  expanded: boolean;
  onToggle: () => void;
  onToggleStatus: () => void;
  onDelete: () => void;
}) {
  const { items, ideasCount, loading: itemsLoading } = useSourceItems(
    expanded ? source.id : null,
  );
  const [confirmDelete, setConfirmDelete] = useState(false);

  function handleDelete() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    onDelete();
  }

  const typeLabel =
    source.source_type === "youtube"
      ? "YouTube"
      : source.source_type === "x"
        ? "X"
        : "Newsletter";

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full grid grid-cols-[1fr_120px_100px_80px_64px] gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors text-left items-center"
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? (
            <CaretDown size={11} className="text-mist shrink-0" />
          ) : (
            <CaretRight size={11} className="text-mist shrink-0" />
          )}
          <div className="min-w-0">
            <div className="text-[13px] text-white truncate">
              {source.name}
            </div>
            <div className="font-mono text-[10.5px] text-mist">{typeLabel}</div>
          </div>
        </div>
        <span className="font-mono text-[11px] text-mist truncate">
          {source.last_received_at
            ? new Date(source.last_received_at).toLocaleDateString()
            : "—"}
        </span>
        <span className="font-mono text-[11px] text-mist">
          {source.ideas_extracted_this_month}
        </span>
        <span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleStatus();
            }}
            className={cn(
              "font-mono text-[10.5px] rounded px-2 py-0.5 transition-colors",
              source.status === "active"
                ? "text-green-400 bg-green-500/10"
                : "text-amber-400 bg-amber-500/10",
            )}
          >
            {source.status === "active" ? "active" : "paused"}
          </button>
        </span>
        <div className="flex justify-end">
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDelete();
            }}
            className={cn(
              "p-1 rounded transition-colors",
              confirmDelete
                ? "bg-sienna/20 text-sienna"
                : "text-mist hover:text-white hover:bg-white/[0.06]",
            )}
            title={confirmDelete ? "Click again to confirm" : "Delete"}
          >
            <Trash size={12} weight="regular" />
          </button>
        </div>
      </button>

      {/* Expanded items */}
      <div
        className={cn(
          "overflow-hidden transition-all",
          expanded ? "max-h-96 border-t border-hairline" : "max-h-0",
        )}
      >
        {expanded && (
          <div className="px-10 py-3 bg-white/[0.01]">
            {itemsLoading ? (
              <div className="space-y-1.5">
                {[1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-8 rounded bg-white/[0.04] animate-pulse"
                  />
                ))}
              </div>
            ) : items.length === 0 ? (
              <p className="text-[12px] text-mist">
                No items received yet.
              </p>
            ) : (
              <div className="space-y-2">
                <p className="font-mono text-[10.5px] text-mist uppercase tracking-[0.15em]">
                  Last {items.length} items · {ideasCount} ideas extracted this
                  month
                </p>
                {items.map((item) => (
                  <NewsletterRow key={item.id} item={item} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function NewsletterRow({ item }: { item: NewsletterItem }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-white/80 truncate flex-1">
        {item.subject || "No subject"}
      </span>
      <span className="font-mono text-[11px] text-mist shrink-0 ml-3">
        {item.received_at
          ? new Date(item.received_at).toLocaleDateString()
          : ""}
      </span>
    </div>
  );
}
