import { useEffect, useState, useRef, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router-dom";
import * as Tabs from "@radix-ui/react-tabs";
import {
  User,
  Palette,
  Cpu,
  FileMd,
  LinkSimple,
  Check,
  Copy,
  Warning,
  Sun,
  ShieldCheck,
  PencilSimple,
  Trash,
  Upload,
  Eye,
  EyeSlash,
  Plus,
  FloppyDisk,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Input, FieldLabel, Textarea } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";
import { useAuth } from "../lib/auth";
import { api, ApiError } from "../lib/api";

const TABS = [
  { id: "profile", label: "Profile", icon: User, adminOnly: false },
  { id: "brands", label: "Brands", icon: Palette, adminOnly: false },
  { id: "models", label: "Models", icon: Cpu, adminOnly: false },
  { id: "skills", label: "Skill files", icon: FileMd, adminOnly: false },
  { id: "integrations", label: "Integrations", icon: LinkSimple, adminOnly: false },
  { id: "appearance", label: "Appearance", icon: Sun, adminOnly: false },
  { id: "admin", label: "Admin", icon: ShieldCheck, adminOnly: true },
] as const;

type SettingsTabId = (typeof TABS)[number]["id"];

const SETTINGS_TAB_IDS = TABS.map((t) => t.id) as readonly SettingsTabId[];

export default function SettingsPage() {
  const { is_admin } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: SettingsTabId = SETTINGS_TAB_IDS.includes(tabParam as SettingsTabId)
    ? (tabParam as SettingsTabId)
    : "profile";

  function setTab(tab: SettingsTabId) {
    setSearchParams(tab === "profile" ? {} : { tab }, { replace: true });
  }

  const visibleTabs = TABS.filter((t) => !t.adminOnly || is_admin);

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /settings"
          title="Settings"
          description="Your profile, brands, model routing, skill files, and integrations. All keys stored encrypted."
        />

        <Tabs.Root value={activeTab} onValueChange={(v) => setTab(v as SettingsTabId)}>
          <Tabs.List className="flex items-center gap-1 border-b border-hairline mb-8 overflow-x-auto">
            {visibleTabs.map((t) => {
              const Icon = t.icon;
              return (
                <Tabs.Trigger
                  key={t.id}
                  value={t.id}
                  className={cn(
                    "group inline-flex items-center gap-2 px-3 h-9 text-[13px] shrink-0",
                    "text-mist hover:text-white transition-colors relative",
                    "data-[state=active]:text-white",
                  )}
                >
                  <Icon size={13} />
                  <span>{t.label}</span>
                  <span className="absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-cinnabar opacity-0 group-data-[state=active]:opacity-100 transition-opacity" />
                </Tabs.Trigger>
              );
            })}
          </Tabs.List>

          <Tabs.Content value="profile"><ProfileTab /></Tabs.Content>
          <Tabs.Content value="brands"><BrandsTab /></Tabs.Content>
          <Tabs.Content value="models"><ModelsTab /></Tabs.Content>
          <Tabs.Content value="skills"><SkillsTab /></Tabs.Content>
          <Tabs.Content value="integrations"><IntegrationsTab /></Tabs.Content>
          <Tabs.Content value="appearance"><AppearanceTab /></Tabs.Content>
          {is_admin ? <Tabs.Content value="admin"><AdminTab /></Tabs.Content> : null}
        </Tabs.Root>
      </PageContainer>
    </Shell>
  );
}

// ── Shared ────────────────────────────────────────────────────────────────────

function EmptyPanel({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ElementType;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-10 text-center max-w-[820px]">
      <Icon size={18} className="text-mist mx-auto mb-2" />
      <p className="text-[13.5px] text-white mb-1">{title}</p>
      <p className="text-[12px] text-mist font-mono leading-[1.6] max-w-[52ch] mx-auto">{body}</p>
    </div>
  );
}

function SectionHeading({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-[14px] text-white font-semibold">{label}</h3>
      {hint ? <span className="text-[11px] text-mist font-mono">{hint}</span> : null}
    </div>
  );
}

// ── Profile Tab ───────────────────────────────────────────────────────────────

function ProfileTab() {
  const { profile, user, refreshProfile, loading } = useAuth();
  const [form, setForm] = useState({
    display_name: "",
    positioning: "",
    audience: "",
    voice: "",
    things_to_avoid: "",
    creators_followed: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [aliasCopied, setAliasCopied] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!profile) {
      if (!loading) refreshProfile();
      return;
    }
    setForm({
      display_name: profile.display_name ?? "",
      positioning: profile.positioning ?? "",
      audience: profile.audience ?? "",
      voice: profile.voice ?? "",
      things_to_avoid: profile.things_to_avoid ?? "",
      creators_followed: (profile.creators_followed ?? []).join(", "),
    });
  }, [profile, loading, refreshProfile]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/onboard", {
        display_name: form.display_name,
        positioning: form.positioning,
        audience: form.audience,
        voice: form.voice,
        things_to_avoid: form.things_to_avoid,
        creators_followed: form.creators_followed.split(",").map((s) => s.trim()).filter(Boolean),
      });
      await refreshProfile();
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt((t) => (t && Date.now() - t >= 2000 ? null : t)), 2100);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  function copyAlias() {
    if (!profile?.forwarding_alias) return;
    navigator.clipboard.writeText(profile.forwarding_alias);
    setAliasCopied(true);
    setTimeout(() => setAliasCopied(false), 1800);
  }

  async function handleAvatarUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await api.post("/auth/avatar", formData, true);
      await refreshProfile();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Avatar upload failed.");
    } finally {
      setAvatarUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const avatarUrl = profile?.avatar_storage_path
    ? `${import.meta.env.VITE_SUPABASE_URL}/storage/v1/object/public/avatars/${profile.avatar_storage_path}`
    : null;

  const showSaved = savedAt !== null && Date.now() - savedAt < 2000;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-[1100px]">
      <div className="space-y-5">
        {/* Avatar */}
        <div>
          <FieldLabel htmlFor="avatar">Avatar</FieldLabel>
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full border-2 border-hairline bg-surface overflow-hidden shrink-0">
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                <div className="h-full w-full flex items-center justify-center text-mist">
                  <User size={24} />
                </div>
              )}
            </div>
            <div>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                onChange={handleAvatarUpload}
                className="hidden"
                id="avatar-upload"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => fileRef.current?.click()}
                disabled={avatarUploading}
              >
                <Upload size={12} />
                {avatarUploading ? "Uploading…" : "Upload photo"}
              </Button>
              <p className="text-[11px] text-mist mt-1">PNG, JPG, GIF or WebP. Max 5MB.</p>
            </div>
          </div>
        </div>

        <div>
          <FieldLabel htmlFor="email" hint="from your sign-in identity">Email</FieldLabel>
          <Input id="email" value={user?.email ?? ""} readOnly className="opacity-80" />
        </div>
        <div>
          <FieldLabel htmlFor="alias" hint="forward newsletters here">Forwarding alias</FieldLabel>
          <div className="flex items-center gap-2">
            <Input
              id="alias"
              value={profile?.forwarding_alias ?? ""}
              placeholder="not configured"
              readOnly
              className="opacity-80 flex-1"
            />
            {profile?.forwarding_alias ? (
              <button
                type="button"
                onClick={copyAlias}
                className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md bg-white/[0.06] border border-hairline hover:bg-white/[0.1] transition-colors text-[12.5px] text-white font-medium"
              >
                {aliasCopied ? (
                  <><Check size={12} weight="bold" className="text-cinnabar" />copied</>
                ) : (
                  <><Copy size={12} weight="bold" />copy</>
                )}
              </button>
            ) : null}
          </div>
        </div>
        <div>
          <FieldLabel htmlFor="name">Display name</FieldLabel>
          <Input
            id="name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="pos">Positioning</FieldLabel>
          <Textarea
            id="pos" rows={2}
            value={form.positioning}
            onChange={(e) => setForm({ ...form, positioning: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="aud">Audience</FieldLabel>
          <Input
            id="aud"
            value={form.audience}
            onChange={(e) => setForm({ ...form, audience: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="voice">Voice</FieldLabel>
          <Textarea
            id="voice" rows={2}
            value={form.voice}
            onChange={(e) => setForm({ ...form, voice: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="creators" hint="comma separated">Creators you sound closest to</FieldLabel>
          <Input
            id="creators"
            value={form.creators_followed}
            onChange={(e) => setForm({ ...form, creators_followed: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="avoid" hint="never do">Things to avoid</FieldLabel>
          <Textarea
            id="avoid" rows={2}
            value={form.things_to_avoid}
            onChange={(e) => setForm({ ...form, things_to_avoid: e.target.value })}
          />
        </div>

        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-sienna/40 bg-sienna/10 px-3 py-2 text-[12.5px] text-sienna">
            <Warning size={13} weight="bold" className="mt-[2px] shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={busy}>
            {busy ? "· saving ·" : "Save profile"}
          </Button>
          {showSaved ? (
            <Badge tone="cinnabar">
              <Check size={10} weight="bold" />saved
            </Badge>
          ) : null}
        </div>

        <div className="pt-2">
          <Link
            to="/library?tab=knowledge"
            className="inline-flex items-center gap-1.5 text-[13px] text-cinnabar hover:underline font-medium"
          >
            View your full knowledge profile <span className="text-mist">→</span>
          </Link>
        </div>
      </div>

      <div className="rounded-xl border border-hairline bg-surface p-5 h-fit sticky top-6">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
          how this is used
        </div>
        <p className="text-[13.5px] text-white/80 leading-[1.6]">
          Every agent prompt interpolates these fields at call time. No agent has them
          hard-coded — a pre-commit lint on the agents directory enforces this.
        </p>
        <ul className="mt-4 space-y-1.5 font-mono text-[11.5px] text-mist">
          <li><span className="text-cinnabar">›</span> <span className="text-white/80">research_agent</span> <span className="text-mist">(live)</span></li>
          <li><span className="text-cinnabar">›</span> <span className="text-white/80">stream_script</span> <span className="text-mist">(next)</span></li>
          <li><span className="text-cinnabar">›</span> <span className="text-white/80">sharpen_this</span> <span className="text-mist">(next)</span></li>
          <li><span className="text-cinnabar">›</span> <span className="text-white/80">content_extract</span> <span className="text-mist">(next)</span></li>
        </ul>
      </div>
    </div>
  );
}

// ── Brands Tab ────────────────────────────────────────────────────────────────

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const DEFAULT_BRAND_COLOR = "#E8442A";

function normalizeBrandHex(raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  const h = v.startsWith("#") ? v : `#${v}`;
  return HEX_COLOR.test(h) ? h.toUpperCase() : null;
}

function ColorInput({
  id,
  value,
  onChange,
  label,
}: {
  id: string;
  value: string;
  onChange: (hex: string) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="color"
        value={value.startsWith("#") ? value : DEFAULT_BRAND_COLOR}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        className="h-9 w-14 cursor-pointer rounded border border-hairline bg-transparent p-0.5 shrink-0"
        aria-label={label}
      />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-[120px] font-mono text-[12.5px]"
        placeholder="#E8442A"
        spellCheck={false}
      />
    </div>
  );
}

function BrandsTab() {
  type BrandRow = {
    id: string;
    name: string;
    primary_color: string | null;
    secondary_color: string | null;
    context_description: string | null;
  };

  const [rows, setRows] = useState<BrandRow[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");
  const [name, setName] = useState("");
  const [primaryHex, setPrimaryHex] = useState(DEFAULT_BRAND_COLOR);
  const [secondaryHex, setSecondaryHex] = useState("#3D3D3D");
  const [context, setContext] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const reload = async () => {
    setLoadState("loading");
    try {
      const data = await api.get<BrandRow[]>("/brands");
      setRows(data ?? []);
      setLoadState("idle");
    } catch {
      setLoadState("error");
    }
  };

  useEffect(() => { void reload(); }, []);

  function resetForm() {
    setName("");
    setPrimaryHex(DEFAULT_BRAND_COLOR);
    setSecondaryHex("#3D3D3D");
    setContext("");
    setEditingId(null);
  }

  function startEdit(b: BrandRow) {
    setName(b.name);
    setPrimaryHex(b.primary_color ?? DEFAULT_BRAND_COLOR);
    setSecondaryHex(b.secondary_color ?? "#3D3D3D");
    setContext(b.context_description ?? "");
    setEditingId(b.id);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { setFormError("Brand name is required."); return; }
    const p = normalizeBrandHex(primaryHex);
    if (!p) { setFormError("Primary color must be a value like #E8442A."); return; }
    const s = normalizeBrandHex(secondaryHex);
    if (secondaryHex.trim() && !s) { setFormError("Secondary color must be a hex value."); return; }
    setFormError(null);
    setBusy(true);
    try {
      const payload = {
        name: trimmed,
        primary_color: p,
        secondary_color: s,
        context_description: context.trim() || null,
      };
      if (editingId) {
        await api.patch(`/brands/${editingId}`, payload);
      } else {
        await api.post("/brands", payload);
      }
      resetForm();
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
      await reload();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Could not save brand.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete(id: string) {
    setDeletingId(id);
    try {
      await api.delete(`/brands/${id}`);
      await reload();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Could not delete brand.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-[1100px]">
      {/* Form */}
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist mb-1">
          {editingId ? "edit brand" : "new brand"}
        </div>
        <h3 className="text-[14px] text-white mb-4">
          {editingId ? `Editing: ${name}` : "Create a brand"}
        </h3>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div>
            <FieldLabel htmlFor="brand-name">Name</FieldLabel>
            <Input
              id="brand-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Org"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <FieldLabel htmlFor="brand-primary" hint="scene + studio accent">Primary color</FieldLabel>
              <ColorInput id="brand-primary" value={primaryHex} onChange={setPrimaryHex} label="Pick primary color" />
            </div>
            <div>
              <FieldLabel htmlFor="brand-secondary" hint="secondary accent">Secondary color</FieldLabel>
              <ColorInput id="brand-secondary" value={secondaryHex} onChange={setSecondaryHex} label="Pick secondary color" />
            </div>
          </div>
          <div>
            <FieldLabel htmlFor="brand-ctx" hint="optional · used in prompts">Brand context</FieldLabel>
            <Textarea
              id="brand-ctx"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              rows={4}
              placeholder="One paragraph: what you publish, tone, positioning…"
            />
          </div>
          {formError ? (
            <p className="text-[12px] text-cinnabar flex items-start gap-1.5">
              <Warning size={14} className="shrink-0 mt-0.5" />{formError}
            </p>
          ) : null}
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : editingId ? "Update brand" : "Add brand"}
            </Button>
            {editingId ? (
              <Button type="button" variant="ghost" onClick={resetForm}>Cancel</Button>
            ) : null}
            {savedFlash ? (
              <p className="text-[11.5px] text-mist font-mono">saved ✓</p>
            ) : null}
          </div>
        </form>
      </div>

      {/* List */}
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist mb-3">your brands</div>
        {loadState === "loading" ? (
          <p className="text-[13px] text-mist font-mono">loading…</p>
        ) : loadState === "error" ? (
          <p className="text-[13px] text-cinnabar">Could not load brands.</p>
        ) : rows.length === 0 ? (
          <EmptyPanel icon={Palette} title="No brands yet." body="Use the form to add one. Brands power the accent color in Studio and carry context into scene generation." />
        ) : (
          <ul className="space-y-2">
            {rows.map((b) => {
              const pri = normalizeBrandHex(String(b.primary_color ?? "")) ?? DEFAULT_BRAND_COLOR;
              const sec = normalizeBrandHex(String(b.secondary_color ?? "")) ?? null;
              return (
                <li key={b.id} className="rounded-xl border border-hairline bg-surface px-4 py-3">
                  <div className="flex gap-3 items-start">
                    <div className="flex gap-1 shrink-0 mt-0.5">
                      <span
                        aria-hidden
                        className="h-8 w-5 rounded-l-md border border-white/15"
                        style={{ backgroundColor: pri }}
                      />
                      {sec ? (
                        <span
                          aria-hidden
                          className="h-8 w-5 rounded-r-md border border-white/15"
                          style={{ backgroundColor: sec }}
                        />
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] text-white truncate">{b.name}</div>
                      {b.context_description ? (
                        <p className="mt-1 text-[12px] text-mist leading-[1.55] line-clamp-2">{b.context_description}</p>
                      ) : null}
                      <div className="mt-1.5 font-mono text-[10.5px] text-mist/80 flex gap-3">
                        <span>{pri}</span>
                        {sec ? <span>{sec}</span> : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => startEdit(b)}
                        className="h-7 w-7 flex items-center justify-center rounded hover:bg-white/[0.06] text-mist hover:text-white transition-colors"
                        title="Edit brand"
                      >
                        <PencilSimple size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => confirmDelete(b.id)}
                        disabled={deletingId === b.id}
                        className="h-7 w-7 flex items-center justify-center rounded hover:bg-sienna/20 text-mist hover:text-sienna transition-colors"
                        title="Delete brand"
                      >
                        <Trash size={13} />
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// ── Models Tab ────────────────────────────────────────────────────────────────

const FUNCTION_LABELS: Record<string, string> = {
  script_generation: "Script generation",
  scene_generation: "Scene generation",
  scene_editing: "Scene editing (Vision)",
  research_agent: "Research agent",
  refine_chat: "Refine / Chat",
  content_extraction: "Content extraction",
  thumbnail_generation: "Thumbnail generation",
  newsletter_extraction: "Newsletter extraction",
};

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google AI",
  image: "Image",
};

const AVAILABLE_MODELS: Record<string, string[]> = {
  anthropic: ["Claude Opus 4.5", "Claude Sonnet 4.5", "Claude Haiku"],
  openai: ["GPT-4o", "GPT-4o Mini", "GPT-4-turbo"],
  google: ["Gemini 1.5 Pro", "Gemini 1.5 Flash"],
  image: ["DALL-E 3", "NanoBanana Pro"],
};

interface KeyInfo {
  provider: string;
  has_key: boolean;
  masked: string | null;
}

interface ModelPrefRow {
  function_name: string;
  model: string;
  provider: string;
}

interface EstimatedCost {
  function_name: string;
  avg_cost: number | null;
  avg_tokens: number | null;
}

function ModelsTab() {
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [prefs, setPrefs] = useState<ModelPrefRow[]>([]);
  const [costs, setCosts] = useState<EstimatedCost[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");

  // Key form state
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});
  const [keyVisible, setKeyVisible] = useState<Record<string, boolean>>({});
  const [keySaving, setKeySaving] = useState<Record<string, boolean>>({});
  const [keyError, setKeyError] = useState<string | null>(null);
  const [keySaved, setKeySaved] = useState<string | null>(null);

  // Pref saving state
  const [prefSaving, setPrefSaving] = useState<string | null>(null);

  const load = async () => {
    setLoadState("loading");
    try {
      const [k, p, c] = await Promise.all([
        api.get<KeyInfo[]>("/settings/keys"),
        api.get<ModelPrefRow[]>("/settings/model-prefs"),
        api.get<EstimatedCost[]>("/settings/estimated-costs"),
      ]);
      setKeys(k ?? []);
      setPrefs(p ?? []);
      setCosts(c ?? []);
      setLoadState("idle");
    } catch {
      setLoadState("error");
    }
  };

  useEffect(() => { void load(); }, []);

  async function saveKey(provider: string) {
    const val = keyValues[provider]?.trim();
    if (!val) return;
    setKeySaving((s) => ({ ...s, [provider]: true }));
    setKeyError(null);
    try {
      await api.post("/settings/keys", { provider, key: val });
      setKeyValues((s) => ({ ...s, [provider]: "" }));
      setKeySaved(provider);
      setTimeout(() => setKeySaved(null), 2000);
      await load();
    } catch (e) {
      setKeyError(e instanceof ApiError ? e.message : "Could not save key.");
    } finally {
      setKeySaving((s) => ({ ...s, [provider]: false }));
    }
  }

  async function deleteKey(provider: string) {
    try {
      await api.delete(`/settings/keys/${provider}`);
      await load();
    } catch (e) {
      setKeyError(e instanceof ApiError ? e.message : "Could not remove key.");
    }
  }

  async function updatePref(fn: string, model: string, provider: string) {
    setPrefSaving(fn);
    try {
      await api.put("/settings/model-prefs", { function_name: fn, model, provider });
      setPrefs((prev) => prev.map((r) => (r.function_name === fn ? { ...r, model, provider } : r)));
    } catch {
      // Model prefs fail silently — not critical
    } finally {
      setPrefSaving(null);
    }
  }

  const keyMap: Record<string, KeyInfo> = {};
  keys.forEach((k) => (keyMap[k.provider] = k));

  // Map image model keys to their actual provider buckets
  function effectiveProvider(_fn: string, p: string): string {
    return p === "image" ? "openai" : p;
  }

  const costMap: Record<string, EstimatedCost> = {};
  costs.forEach((c) => (costMap[c.function_name] = c));

  if (loadState === "loading") {
    return <p className="text-[13px] text-mist font-mono">loading…</p>;
  }

  return (
    <div className="space-y-8 max-w-[1100px]">
      {/* API Keys */}
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <SectionHeading label="API Keys" hint="encrypted at rest" />
        <p className="text-[13px] text-mist mb-5">
          Bring your own keys. Each provider key is stored encrypted. Without a key,
          functions default to the workspace keys configured in the backend.
        </p>
        <div className="space-y-3">
          {["anthropic", "openai", "google"].map((provider) => {
            const info = keyMap[provider];
            return (
              <div key={provider} className="flex items-end gap-3">
                <div className="flex-1">
                  <FieldLabel htmlFor={`key-${provider}`}>
                    {PROVIDER_LABELS[provider] ?? provider} API key
                  </FieldLabel>
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <Input
                        id={`key-${provider}`}
                        type={keyVisible[provider] ? "text" : "password"}
                        value={keyValues[provider] ?? ""}
                        onChange={(e) => setKeyValues((s) => ({ ...s, [provider]: e.target.value }))}
                        placeholder={info?.masked ? info.masked : `sk-...`}
                        autoComplete="off"
                        spellCheck={false}
                        className="pr-10 font-mono text-[12.5px]"
                      />
                      <button
                        type="button"
                        onClick={() => setKeyVisible((s) => ({ ...s, [provider]: !s[provider] }))}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-mist hover:text-white transition-colors"
                        tabIndex={-1}
                      >
                        {keyVisible[provider] ? <EyeSlash size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                  {info?.has_key ? (
                    <p className="text-[11px] text-mist mt-1 font-mono">Key saved: {info.masked}</p>
                  ) : null}
                </div>
                <Button
                  size="sm"
                  onClick={() => saveKey(provider)}
                  disabled={keySaving[provider] || !keyValues[provider]?.trim()}
                >
                  <FloppyDisk size={12} />
                  {keySaving[provider] ? "Saving…" : "Save"}
                </Button>
                {info?.has_key ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => deleteKey(provider)}
                    className="text-sienna hover:text-sienna"
                  >
                    <Trash size={12} />
                  </Button>
                ) : null}
                {keySaved === provider ? (
                  <span className="text-[11px] text-cinnabar font-mono shrink-0">saved</span>
                ) : null}
              </div>
            );
          })}
          {keyError ? (
            <p className="text-[12px] text-cinnabar flex items-start gap-1.5">
              <Warning size={14} className="shrink-0 mt-0.5" />{keyError}
            </p>
          ) : null}
        </div>
      </div>

      {/* Function → Model Mapping */}
      <div className="rounded-xl border border-hairline bg-surface overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
          <div className="col-span-4">function</div>
          <div className="col-span-5">model</div>
          <div className="col-span-3 text-right">est. cost / run</div>
        </div>
        <div className="divide-y divide-hairline">
          {prefs.map((pref) => {
            const info = keyMap[pref.provider] ?? keyMap[effectiveProvider(pref.function_name, pref.provider)];
            const hasKey = info?.has_key ?? true; // true for image (uses openai key)
            const cost = costMap[pref.function_name];
            const isSaving = prefSaving === pref.function_name;

            return (
              <div key={pref.function_name} className="grid grid-cols-12 gap-4 px-5 py-3 items-center text-[13px]">
                <div className="col-span-4 text-white">
                  {FUNCTION_LABELS[pref.function_name] ?? pref.function_name}
                </div>
                <div className="col-span-5">
                  {hasKey ? (
                    <select
                      value={`${pref.provider}:${pref.model}`}
                      onChange={(e) => {
                        const [provider, model] = e.target.value.split(":");
                        updatePref(pref.function_name, model, provider);
                      }}
                      disabled={isSaving}
                      className="w-full h-8 px-2 rounded-md bg-surface-input border border-transparent text-[12.5px] text-white focus:outline-none focus:border-cinnabar disabled:opacity-40"
                    >
                      {Object.entries(AVAILABLE_MODELS).map(([prov, models]) => (
                        <optgroup key={prov} label={PROVIDER_LABELS[prov] ?? prov}>
                          {models.map((m) => (
                            <option key={`${prov}:${m}`} value={`${prov}:${m}`}>
                              {m}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  ) : (
                    <span className="text-[12px] text-mist italic">
                      Add {PROVIDER_LABELS[pref.provider] ?? pref.provider} API key first
                    </span>
                  )}
                </div>
                <div className="col-span-3 text-right">
                  {isSaving ? (
                    <span className="font-mono text-[11px] text-mist">…</span>
                  ) : cost?.avg_cost != null ? (
                    <span className="font-mono text-[12px] text-mist">
                      ~${cost.avg_cost.toFixed(4)}
                    </span>
                  ) : (
                    <span className="font-mono text-[11px] text-mist">—</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Skills Tab ────────────────────────────────────────────────────────────────

interface SkillFile {
  id: string;
  filename: string;
  storage_path: string;
  file_summary: string | null;
  file_size_kb: number | null;
  created_at: string | null;
}

function SkillsTab() {
  const [files, setFiles] = useState<SkillFile[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoadState("loading");
    try {
      const data = await api.get<SkillFile[]>("/settings/skills");
      setFiles(data ?? []);
      setLoadState("idle");
    } catch {
      setLoadState("error");
    }
  };

  useEffect(() => { void load(); }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await api.post("/settings/skills", formData, true);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await api.delete(`/settings/skills/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed.");
    } finally {
      setDeletingId(null);
    }
  }

  const totalKb = files.reduce((sum, f) => sum + (f.file_size_kb ?? 0), 0);
  const atLimit = files.length >= 3 || totalKb >= 50;

  return (
    <div className="space-y-4 max-w-[820px]">
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <SectionHeading label="Skill Files" hint={`${files.length}/3 files · ${totalKb.toFixed(1)}/50 KB`} />
        <p className="text-[13px] text-mist mb-4">
          Upload up to 3 markdown (.md) files containing your frameworks, SOPs, or IP.
          These are injected on demand in the Studio AI chat — not automatically.
        </p>

        {!atLimit ? (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".md"
              onChange={handleUpload}
              className="hidden"
              id="skill-upload"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              <Upload size={12} />
              {uploading ? "Uploading…" : "Upload skill file"}
            </Button>
          </>
        ) : (
          <p className="text-[12px] text-sienna flex items-center gap-1.5">
            <Warning size={13} />
            Maximum reached: {files.length} files, {totalKb.toFixed(1)} KB combined. Delete one to upload more.
          </p>
        )}

        {error ? (
          <p className="text-[12px] text-cinnabar flex items-start gap-1.5 mt-3">
            <Warning size={14} className="shrink-0 mt-0.5" />{error}
          </p>
        ) : null}
      </div>

      {loadState === "loading" ? (
        <p className="text-[13px] text-mist font-mono">loading…</p>
      ) : loadState === "error" ? (
        <p className="text-[13px] text-cinnabar">Could not load skill files.</p>
      ) : files.length === 0 ? (
        <EmptyPanel
          icon={FileMd}
          title="No skill files yet."
          body="Upload up to 3 .md files (max 50 KB combined). They're injected into the studio's AI chat on demand."
        />
      ) : (
        <ul className="space-y-2">
          {files.map((f) => (
            <li key={f.id} className="rounded-xl border border-hairline bg-surface px-4 py-3 flex items-start gap-3">
              <FileMd size={16} className="text-mist shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] text-white truncate">{f.filename}</div>
                {f.file_summary ? (
                  <p className="mt-0.5 text-[12px] text-mist leading-[1.55] line-clamp-1">{f.file_summary}</p>
                ) : null}
                <div className="mt-1 font-mono text-[10.5px] text-mist/70 flex gap-3">
                  {f.file_size_kb != null ? <span>{f.file_size_kb} KB</span> : null}
                  {f.created_at ? <span>{new Date(f.created_at).toLocaleDateString()}</span> : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(f.id)}
                disabled={deletingId === f.id}
                className="h-7 w-7 flex items-center justify-center rounded hover:bg-sienna/20 text-mist hover:text-sienna transition-colors shrink-0"
                title="Delete skill file"
              >
                <Trash size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Integrations Tab ──────────────────────────────────────────────────────────

function IntegrationsTab() {
  const { profile, refreshProfile } = useAuth();
  const [ytClientId, setYtClientId] = useState("");
  const [ytClientSecret, setYtClientSecret] = useState("");
  const [ytBusy, setYtBusy] = useState(false);
  const [notionToken, setNotionToken] = useState("");
  const [notionBusy, setNotionBusy] = useState(false);
  const [gammaKey, setGammaKey] = useState("");
  const [gammaBusy, setGammaBusy] = useState(false);
  const [nbKey, setNbKey] = useState("");
  const [nbBusy, setNbBusy] = useState(false);
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [linkedinBusy, setLinkedinBusy] = useState(false);
  const [linkedinResult, setLinkedinResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [linkedinManualText, setLinkedinManualText] = useState("");
  const [linkedinManualBusy, setLinkedinManualBusy] = useState(false);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const ytConnected = profile?.youtube_connected ?? false;

  function flash(text: string, ok: boolean) {
    setMsg({ text, ok });
    setTimeout(() => setMsg(null), 2500);
  }

  async function saveYoutube(e: FormEvent) {
    e.preventDefault();
    setYtBusy(true);
    try {
      await api.post("/settings/integrations/youtube", {
        client_id: ytClientId,
        client_secret: ytClientSecret,
      });
      setYtClientId("");
      setYtClientSecret("");
      await refreshProfile();
      flash("YouTube credentials saved.", true);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Failed.", false);
    } finally {
      setYtBusy(false);
    }
  }

  async function saveToken(provider: string, setBusy: (b: boolean) => void, token: string) {
    setBusy(true);
    try {
      await api.post(`/settings/integrations/${provider}`, { token });
      await refreshProfile();
      flash(`${provider} token saved.`, true);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Failed.", false);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(provider: string) {
    setDisconnecting(provider);
    try {
      await api.delete(`/settings/integrations/${provider}`);
      await refreshProfile();
      flash(`${provider} disconnected.`, true);
    } catch (err) {
      flash(err instanceof ApiError ? err.message : "Failed.", false);
    } finally {
      setDisconnecting(null);
    }
  }

  return (
    <div className="space-y-4 max-w-[820px]">
      {msg ? (
        <div className={cn(
          "rounded-md px-3 py-2 text-[12.5px] font-medium",
          msg.ok ? "bg-cinnabar/15 text-cinnabar border border-cinnabar/30" : "bg-sienna/10 text-sienna border border-sienna/40",
        )}>
          {msg.text}
        </div>
      ) : null}

      {/* YouTube */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-[14px] text-white font-semibold">YouTube</h3>
            <p className="text-[12px] text-mist mt-0.5">Connect your channel for content insights.</p>
          </div>
          {ytConnected ? (
            <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />connected</Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>

        {ytConnected ? (
          <div className="space-y-1.5 mb-3">
            {profile?.youtube_channel_name ? (
              <p className="text-[13px] text-white">Channel: {profile.youtube_channel_name}</p>
            ) : null}
            {profile?.youtube_subscriber_count != null ? (
              <p className="text-[13px] text-mist">Subscribers: {profile.youtube_subscriber_count.toLocaleString()}</p>
            ) : null}
            {profile?.youtube_last_sync ? (
              <p className="text-[12px] text-mist font-mono">Last sync: {new Date(profile.youtube_last_sync).toLocaleString()}</p>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => disconnect("youtube")}
              disabled={disconnecting === "youtube"}
              className="text-sienna hover:text-sienna mt-2"
            >
              {disconnecting === "youtube" ? "Disconnecting…" : "Disconnect"}
            </Button>
          </div>
        ) : (
          <form onSubmit={saveYoutube} className="space-y-3">
            <div>
              <FieldLabel htmlFor="yt-cid">Client ID</FieldLabel>
              <Input id="yt-cid" value={ytClientId} onChange={(e) => setYtClientId(e.target.value)} placeholder="From Google Cloud Console" />
            </div>
            <div>
              <FieldLabel htmlFor="yt-cs">Client Secret</FieldLabel>
              <Input id="yt-cs" type="password" value={ytClientSecret} onChange={(e) => setYtClientSecret(e.target.value)} placeholder="••••••••" />
            </div>
            <p className="text-[11px] text-mist font-mono">
              Get credentials from{" "}
              <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" className="text-cinnabar underline">
                Google Cloud Console
              </a>{" "}
              → Create OAuth 2.0 Client ID.
            </p>
            <Button type="submit" size="sm" disabled={ytBusy}>
              {ytBusy ? "Saving…" : "Connect YouTube"}
            </Button>
          </form>
        )}
      </div>

      {/* Notion */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-[14px] text-white font-semibold flex items-center gap-2">
              Notion
              <Badge tone="muted">post-MVP</Badge>
            </h3>
            <p className="text-[12px] text-mist mt-0.5">Framework / How-to scene output.</p>
          </div>
          {profile?.notion_token ? (
            <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />connected</Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <FieldLabel htmlFor="notion-token">Integration token</FieldLabel>
            <Input
              id="notion-token"
              type="password"
              value={notionToken}
              onChange={(e) => setNotionToken(e.target.value)}
              placeholder={profile?.notion_token ? "•••••••• (saved)" : "secret_..."}
            />
          </div>
          <Button size="sm" onClick={() => saveToken("notion", setNotionBusy, notionToken)} disabled={notionBusy || !notionToken.trim()}>
            <FloppyDisk size={12} />{notionBusy ? "Saving…" : "Save"}
          </Button>
          {profile?.notion_token ? (
            <Button size="sm" variant="ghost" onClick={() => disconnect("notion")} disabled={disconnecting === "notion"}>
              <Trash size={12} />
            </Button>
          ) : null}
        </div>
        <p className="text-[11px] text-mist font-mono mt-2">
          Find your token in Notion Settings → Integrations → Develop or manage integrations.
        </p>
      </div>

      {/* Gamma */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-[14px] text-white font-semibold">Gamma</h3>
            <p className="text-[12px] text-mist mt-0.5">Pitch scene output. $15/month Pro plan required.</p>
          </div>
          {profile?.gamma_api_key ? (
            <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />connected</Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <FieldLabel htmlFor="gamma-key">API key</FieldLabel>
            <Input
              id="gamma-key"
              type="password"
              value={gammaKey}
              onChange={(e) => setGammaKey(e.target.value)}
              placeholder={profile?.gamma_api_key ? "•••••••• (saved)" : "sk-..."}
            />
          </div>
          <Button size="sm" onClick={() => saveToken("gamma", setGammaBusy, gammaKey)} disabled={gammaBusy || !gammaKey.trim()}>
            <FloppyDisk size={12} />{gammaBusy ? "Saving…" : "Save"}
          </Button>
          {profile?.gamma_api_key ? (
            <Button size="sm" variant="ghost" onClick={() => disconnect("gamma")} disabled={disconnecting === "gamma"}>
              <Trash size={12} />
            </Button>
          ) : null}
        </div>
        <p className="text-[11px] text-mist font-mono mt-2">
          Find your API key in Gamma Settings → Developer → API Keys.
        </p>
      </div>

      {/* NanoBanana Pro */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-[14px] text-white font-semibold">NanoBanana Pro</h3>
            <p className="text-[12px] text-mist mt-0.5">Thumbnail generation.</p>
          </div>
          {profile?.nano_banana_api_key ? (
            <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />connected</Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <FieldLabel htmlFor="nb-key">API key</FieldLabel>
            <Input
              id="nb-key"
              type="password"
              value={nbKey}
              onChange={(e) => setNbKey(e.target.value)}
              placeholder={profile?.nano_banana_api_key ? "•••••••• (saved)" : "nb-..."}
            />
          </div>
          <Button size="sm" onClick={() => saveToken("nano-banana", setNbBusy, nbKey)} disabled={nbBusy || !nbKey.trim()}>
            <FloppyDisk size={12} />{nbBusy ? "Saving…" : "Save"}
          </Button>
          {profile?.nano_banana_api_key ? (
            <Button size="sm" variant="ghost" onClick={() => disconnect("nano-banana")} disabled={disconnecting === "nano-banana"}>
              <Trash size={12} />
            </Button>
          ) : null}
        </div>
      </div>

      {/* LinkedIn */}
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-[14px] text-white font-semibold">LinkedIn</h3>
            <p className="text-[12px] text-mist mt-0.5">Your LinkedIn profile details feed into research and idea generation via the knowledge graph.</p>
          </div>
          {profile?.linkedin_url ? (
            <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />connected</Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>

        {profile?.linkedin_url ? (
          <div className="space-y-1.5 mb-3">
            <p className="text-[13px] text-white truncate">{profile.linkedin_url}</p>
            {profile?.linkedin_scraped_at ? (
              <p className="text-[12px] text-mist font-mono">Scraped: {new Date(profile.linkedin_scraped_at).toLocaleString()}</p>
            ) : (
              <p className="text-[12px] text-amber-400">Profile not yet scraped — it may be private. Paste your profile text below.</p>
            )}
            {linkedinResult ? (
              <p className={cn("text-[12px]", linkedinResult.ok ? "text-green-400" : "text-sienna")}>{linkedinResult.text}</p>
            ) : null}

            {/* Manual paste fallback for private profiles */}
            {!profile?.linkedin_scraped_at ? (
              <div className="pt-2 space-y-2">
                <FieldLabel htmlFor="linkedin-manual">Or paste your LinkedIn profile text</FieldLabel>
                <textarea
                  id="linkedin-manual"
                  value={linkedinManualText}
                  onChange={(e) => setLinkedinManualText(e.target.value)}
                  placeholder="Paste your LinkedIn About, Experience, Education, etc…"
                  rows={4}
                  className="w-full rounded-md border border-hairline bg-card text-[13px] text-white px-3 py-2 placeholder:text-mist/50 focus:outline-none focus:border-cinnabar/50 resize-none"
                />
                <Button
                  size="sm"
                  onClick={async () => {
                    setLinkedinManualBusy(true);
                    try {
                      const res = await api.post("/settings/integrations/linkedin/manual", { token: linkedinManualText });
                      if (res.ok) {
                        setLinkedinManualText("");
                        await refreshProfile();
                        setLinkedinResult({ ok: true, text: `Profile text stored — ${(res as any).chunks_created || "?"} knowledge chunks created.` });
                      } else {
                        setLinkedinResult({ ok: false, text: (res as any).error || "Failed." });
                      }
                    } catch (err) {
                      setLinkedinResult({ ok: false, text: err instanceof ApiError ? err.message : "Failed." });
                    } finally {
                      setLinkedinManualBusy(false);
                    }
                  }}
                  disabled={linkedinManualBusy || !linkedinManualText.trim()}
                >
                  {linkedinManualBusy ? "Saving…" : "Save Profile Text"}
                </Button>
              </div>
            ) : null}

            <Button
              variant="ghost"
              size="sm"
              onClick={() => disconnect("linkedin")}
              disabled={disconnecting === "linkedin"}
              className="text-sienna hover:text-sienna mt-2"
            >
              {disconnecting === "linkedin" ? "Disconnecting…" : "Disconnect"}
            </Button>
          </div>
        ) : (
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <FieldLabel htmlFor="linkedin-url">LinkedIn profile URL</FieldLabel>
              <Input
                id="linkedin-url"
                value={linkedinUrl}
                onChange={(e) => setLinkedinUrl(e.target.value)}
                placeholder="https://www.linkedin.com/in/your-profile/"
              />
            </div>
            <Button
              size="sm"
              onClick={async () => {
                setLinkedinBusy(true);
                setLinkedinResult(null);
                try {
                  const res = await api.post("/settings/integrations/linkedin", { token: linkedinUrl });
                  setLinkedinUrl("");
                  await refreshProfile();
                  if (res.ok === false) {
                    setLinkedinResult({ ok: false, text: (res as any).error || "Scraping failed." });
                  } else {
                    const created = (res as any)?.chunks_created;
                    setLinkedinResult({ ok: true, text: created ? `Profile scraped and stored — ${created} knowledge chunks created.` : "Profile connected." });
                  }
                } catch (err) {
                  setLinkedinResult({ ok: false, text: err instanceof ApiError ? err.message : "Failed to scrape LinkedIn profile." });
                } finally {
                  setLinkedinBusy(false);
                }
              }}
              disabled={linkedinBusy || !linkedinUrl.trim()}
            >
              <FloppyDisk size={12} />{linkedinBusy ? "Scraping…" : "Connect LinkedIn"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Appearance Tab ────────────────────────────────────────────────────────────

function AppearanceTab() {
  const { profile, refreshProfile } = useAuth();
  const [theme, setTheme] = useState(profile?.theme ?? "dark");
  const [fontScale, setFontScale] = useState(profile?.font_scale ?? "default");

  useEffect(() => {
    if (profile) {
      setTheme(profile.theme ?? "dark");
      setFontScale(profile.font_scale ?? "default");
    }
  }, [profile]);

  function applyTheme(t: string) {
    setTheme(t);
    localStorage.setItem("theme", t);
    document.documentElement.classList.toggle("light", t === "light");
    document.documentElement.style.colorScheme = t === "light" ? "light" : "dark";
  }

  function applyFontScale(fs: string) {
    setFontScale(fs);
    localStorage.setItem("font-scale", fs);
    const scales: Record<string, string> = { compact: "0.875", default: "1.0", comfortable: "1.125" };
    document.documentElement.style.setProperty("--font-scale", scales[fs] ?? "1.0");
  }

  async function persist() {
    try {
      await api.patch("/auth/profile", { theme, font_scale: fontScale });
      await refreshProfile();
    } catch {
      // non-critical
    }
  }

  return (
    <div className="space-y-6 max-w-[620px]">
      {/* Theme */}
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <SectionHeading label="Theme" />
        <div className="flex items-center gap-3">
          {[
            { value: "dark", label: "Dark" },
            { value: "light", label: "Light" },
          ].map((o) => (
            <label
              key={o.value}
              className={cn(
                "inline-flex items-center gap-2 px-4 py-2 rounded-md border cursor-pointer transition-colors",
                theme === o.value
                  ? "border-cinnabar bg-cinnabar/10 text-white"
                  : "border-hairline text-mist hover:text-white",
              )}
            >
              <input
                type="radio"
                name="theme"
                value={o.value}
                checked={theme === o.value}
                onChange={() => applyTheme(o.value)}
                className="hidden"
              />
              {o.value === "dark" ? <Sun size={14} /> : <Sun size={14} weight="fill" />}
              <span className="text-[13px] font-medium">{o.label}</span>
            </label>
          ))}
          <Button variant="ghost" size="sm" onClick={persist}>
            <FloppyDisk size={12} />Save preference
          </Button>
        </div>
      </div>

      {/* Font Size */}
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <SectionHeading label="Font Size" />
        <div className="flex items-center gap-3">
          {[
            { value: "compact", label: "Compact", scale: "0.875×" },
            { value: "default", label: "Default", scale: "1×" },
            { value: "comfortable", label: "Comfortable", scale: "1.125×" },
          ].map((o) => (
            <label
              key={o.value}
              className={cn(
                "inline-flex items-center gap-2 px-4 py-2 rounded-md border cursor-pointer transition-colors",
                fontScale === o.value
                  ? "border-cinnabar bg-cinnabar/10 text-white"
                  : "border-hairline text-mist hover:text-white",
              )}
            >
              <input
                type="radio"
                name="fontScale"
                value={o.value}
                checked={fontScale === o.value}
                onChange={() => applyFontScale(o.value)}
                className="hidden"
              />
              <span className="text-[13px] font-medium">{o.label}</span>
              <span className="text-[11px] text-mist font-mono">{o.scale}</span>
            </label>
          ))}
          <Button variant="ghost" size="sm" onClick={persist}>
            <FloppyDisk size={12} />Save preference
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Admin Tab ─────────────────────────────────────────────────────────────────

function AdminTab() {
  return (
    <div className="space-y-8 max-w-[1100px]">
      <AdminUsage />
      <AdminUsers />
      <AdminSystemHealth />
    </div>
  );
}

function AdminUsage() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");

  useEffect(() => {
    (async () => {
      setLoadState("loading");
      try {
        const data = await api.get<Record<string, unknown>[]>("/admin/usage");
        setRows(data ?? []);
        setLoadState("idle");
      } catch {
        setLoadState("error");
      }
    })();
  }, []);

  return (
    <div className="rounded-xl border border-hairline bg-surface overflow-hidden">
      <div className="px-5 py-3 border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
        Team usage — this month
      </div>
      {loadState === "loading" ? (
        <p className="px-5 py-4 text-[13px] text-mist font-mono">loading…</p>
      ) : loadState === "error" ? (
        <p className="px-5 py-4 text-[13px] text-cinnabar">Could not load usage data.</p>
      ) : rows.length === 0 ? (
        <p className="px-5 py-4 text-[13px] text-mist">No usage data yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.1em] text-mist">
                <th className="px-5 py-2 font-medium">Name</th>
                <th className="px-5 py-2 font-medium text-right">API calls</th>
                <th className="px-5 py-2 font-medium text-right">Cost (USD)</th>
                <th className="px-5 py-2 font-medium">Most used</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-white/[0.02]">
                  <td className="px-5 py-2.5 text-white">{String(r.name ?? "—")}</td>
                  <td className="px-5 py-2.5 text-mist text-right tabular-nums">{String(r.total_calls ?? "—")}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">
                    <span className={cn(
                      "font-mono text-[12.5px]",
                      Number(r.total_cost ?? 0) > 1 ? "text-sienna" : "text-mist",
                    )}>
                      ${Number(r.total_cost ?? 0).toFixed(2)}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-mist">{String(r.most_used_function ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AdminUsers() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");
  const [showInvite, setShowInvite] = useState(false);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("Member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const load = async () => {
    setLoadState("loading");
    try {
      const data = await api.get<Record<string, unknown>[]>("/admin/users");
      setRows(data ?? []);
      setLoadState("idle");
    } catch {
      setLoadState("error");
    }
  };

  useEffect(() => { void load(); }, []);

  async function sendInvite(e: FormEvent) {
    e.preventDefault();
    setInviteBusy(true);
    setInviteMsg(null);
    try {
      await api.post("/admin/invite", { name: inviteName, email: inviteEmail, role: inviteRole });
      setInviteMsg("Invite sent.");
      setInviteName("");
      setInviteEmail("");
      setInviteRole("Member");
      setShowInvite(false);
    } catch (err) {
      setInviteMsg(err instanceof ApiError ? err.message : "Invite failed.");
    } finally {
      setInviteBusy(false);
    }
  }

  async function action(endpoint: string, id: string) {
    setActionBusy(`${endpoint}:${id}`);
    try {
      await api.post(`/admin/users/${id}/${endpoint}`);
      await load();
    } catch {
      // ignore
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <div className="rounded-xl border border-hairline bg-surface overflow-hidden">
      <div className="px-5 py-3 border-b border-hairline flex items-center justify-between">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">Users</span>
        <Button size="sm" variant="secondary" onClick={() => setShowInvite(!showInvite)}>
          <Plus size={12} />Invite user
        </Button>
      </div>

      {showInvite ? (
        <form onSubmit={sendInvite} className="px-5 py-4 border-b border-hairline space-y-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <FieldLabel htmlFor="inv-name">Name</FieldLabel>
              <Input id="inv-name" value={inviteName} onChange={(e) => setInviteName(e.target.value)} placeholder="Jane Smith" required />
            </div>
            <div className="flex-1">
              <FieldLabel htmlFor="inv-email">Email</FieldLabel>
              <Input id="inv-email" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="jane@example.com" required />
            </div>
            <div>
              <FieldLabel htmlFor="inv-role">Role</FieldLabel>
              <select
                id="inv-role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="h-9 px-2 rounded-md bg-surface-input border border-transparent text-[13px] text-white focus:outline-none focus:border-cinnabar"
              >
                <option>Member</option>
                <option>Admin</option>
              </select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" disabled={inviteBusy}>
              {inviteBusy ? "Sending…" : "Send invite"}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowInvite(false)}>Cancel</Button>
            {inviteMsg ? <span className="text-[12px] text-mist">{inviteMsg}</span> : null}
          </div>
        </form>
      ) : null}

      {loadState === "loading" ? (
        <p className="px-5 py-4 text-[13px] text-mist font-mono">loading…</p>
      ) : loadState === "error" ? (
        <p className="px-5 py-4 text-[13px] text-cinnabar">Could not load users.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.1em] text-mist">
                <th className="px-5 py-2 font-medium">Name</th>
                <th className="px-5 py-2 font-medium">Email</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Joined</th>
                <th className="px-5 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-white/[0.02]">
                  <td className="px-5 py-2.5 text-white">
                    {String(r.name ?? "—")}
                    {r.is_admin ? <span className="ml-1.5 text-[10px] text-cinnabar font-mono">ADMIN</span> : null}
                  </td>
                  <td className="px-5 py-2.5 text-mist">{String(r.email ?? r.user_id ?? "—")}</td>
                  <td className="px-5 py-2.5">
                    {r.onboarded ? (
                      <Badge tone="neutral"><span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />onboarded</Badge>
                    ) : (
                      <Badge tone="muted">pending</Badge>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-mist text-[12px]">
                    {r.last_active ? new Date(String(r.last_active)).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => action("reset-onboarding", String(r.user_id))}
                        disabled={actionBusy === `reset-onboarding:${r.user_id}`}
                      >
                        Reset
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => action("resend-invite", String(r.user_id))}
                        disabled={actionBusy === `resend-invite:${r.user_id}`}
                      >
                        Resend
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-sienna hover:text-sienna"
                        onClick={() => action("deactivate", String(r.user_id))}
                        disabled={actionBusy === `deactivate:${r.user_id}`}
                      >
                        Deactivate
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AdminSystemHealth() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">("loading");

  useEffect(() => {
    (async () => {
      setLoadState("loading");
      try {
        const data = await api.get<Record<string, unknown>>("/admin/health");
        setHealth(data);
        setLoadState("idle");
      } catch {
        setLoadState("error");
      }
    })();
  }, []);

  return (
    <div className="rounded-xl border border-hairline bg-surface p-5">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist mb-3">System health</div>
      {loadState === "loading" ? (
        <p className="text-[13px] text-mist font-mono">loading…</p>
      ) : loadState === "error" ? (
        <p className="text-[13px] text-cinnabar">Could not load health data.</p>
      ) : health ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {Object.entries(health.apis as Record<string, string> ?? {}).map(([name, status]) => (
              <div key={name} className="flex items-center gap-2 text-[13px]">
                <span className={cn(
                  "h-2 w-2 rounded-full",
                  status === "healthy" ? "bg-cinnabar" : "bg-sienna",
                )} />
                <span className="text-white capitalize">{name}</span>
                <span className="text-mist font-mono text-[11px] ml-auto">{status}</span>
              </div>
            ))}
          </div>
          <div className="border-t border-hairline pt-3 text-[12px] text-mist flex gap-4">
            <span>
              Last newsletter ingest:{" "}
              <span className="text-white font-mono">
                {health.last_newsletter_ingest ? new Date(String(health.last_newsletter_ingest)).toLocaleString() : "never"}
              </span>
            </span>
            <span>
              pgvector:{" "}
              <span className={cn("font-mono", health.pgvector_ok ? "text-cinnabar" : "text-sienna")}>
                {health.pgvector_ok ? "ok" : "issue"}
              </span>
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
