import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
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
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Input, FieldLabel, Textarea } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";
import { useAuth } from "../lib/auth";
import { api, ApiError } from "../lib/api";
import { supabase } from "../lib/supabase";

const TABS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "brands", label: "Brands", icon: Palette },
  { id: "models", label: "Models", icon: Cpu },
  { id: "skills", label: "Skill files", icon: FileMd },
  { id: "integrations", label: "Integrations", icon: LinkSimple },
] as const;

type SettingsTabId = (typeof TABS)[number]["id"];

const SETTINGS_TAB_IDS = TABS.map((t) => t.id) as readonly SettingsTabId[];

export default function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: SettingsTabId = SETTINGS_TAB_IDS.includes(tabParam as SettingsTabId)
    ? (tabParam as SettingsTabId)
    : "profile";

  function setTab(tab: SettingsTabId) {
    setSearchParams(tab === "profile" ? {} : { tab }, { replace: true });
  }

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /settings"
          title="Settings"
          description="Your profile, brands, model routing, skill files, and integrations. All keys stored encrypted."
        />

        <Tabs.Root value={activeTab} onValueChange={(v) => setTab(v as SettingsTabId)}>
          <Tabs.List className="flex items-center gap-1 border-b border-hairline mb-8">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <Tabs.Trigger
                  key={t.id}
                  value={t.id}
                  className={cn(
                    "group inline-flex items-center gap-2 px-3 h-9 text-[13px]",
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

          <Tabs.Content value="profile">
            <ProfileTab />
          </Tabs.Content>
          <Tabs.Content value="brands">
            <BrandsTab />
          </Tabs.Content>
          <Tabs.Content value="models">
            <ModelsTab />
          </Tabs.Content>
          <Tabs.Content value="skills">
            <SkillsTab />
          </Tabs.Content>
          <Tabs.Content value="integrations">
            <IntegrationsTab />
          </Tabs.Content>
        </Tabs.Root>
      </PageContainer>
    </Shell>
  );
}

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
        creators_followed: form.creators_followed
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      await refreshProfile();
      setSavedAt(Date.now());
      setTimeout(
        () => setSavedAt((t) => (t && Date.now() - t >= 2000 ? null : t)),
        2100,
      );
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

  const showSaved = savedAt !== null && Date.now() - savedAt < 2000;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-[1100px]">
      <div className="space-y-5">
        <div>
          <FieldLabel htmlFor="email" hint="from your sign-in identity">
            Email
          </FieldLabel>
          <Input
            id="email"
            value={user?.email ?? ""}
            readOnly
            className="opacity-80"
          />
        </div>
        <div>
          <FieldLabel htmlFor="alias" hint="forward newsletters here">
            Forwarding alias
          </FieldLabel>
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
            id="pos"
            rows={2}
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
            id="voice"
            rows={2}
            value={form.voice}
            onChange={(e) => setForm({ ...form, voice: e.target.value })}
          />
        </div>
        <div>
          <FieldLabel htmlFor="creators" hint="comma separated">
            Creators you sound closest to
          </FieldLabel>
          <Input
            id="creators"
            value={form.creators_followed}
            onChange={(e) =>
              setForm({ ...form, creators_followed: e.target.value })
            }
          />
        </div>
        <div>
          <FieldLabel htmlFor="avoid" hint="never do">
            Things to avoid
          </FieldLabel>
          <Textarea
            id="avoid"
            rows={2}
            value={form.things_to_avoid}
            onChange={(e) =>
              setForm({ ...form, things_to_avoid: e.target.value })
            }
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
              <Check size={10} weight="bold" />
              saved
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="rounded-xl border border-hairline bg-surface p-5 h-fit sticky top-6">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
          how this is used
        </div>
        <p className="text-[13.5px] text-white/80 leading-[1.6]">
          Every agent prompt interpolates these fields at call time. No agent
          has them hard-coded — a pre-commit lint on the agents directory
          enforces this.
        </p>
        <ul className="mt-4 space-y-1.5 font-mono text-[11.5px] text-mist">
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">research_agent</span>{" "}
            <span className="text-mist">(live)</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">stream_script</span>{" "}
            <span className="text-mist">(next)</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">sharpen_this</span>{" "}
            <span className="text-mist">(next)</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">content_extract</span>{" "}
            <span className="text-mist">(next)</span>
          </li>
        </ul>
      </div>
    </div>
  );
}

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
      <p className="text-[12px] text-mist font-mono leading-[1.6] max-w-[52ch] mx-auto">
        {body}
      </p>
    </div>
  );
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const DEFAULT_BRAND_COLOR = "#E8442A";

function normalizeBrandHex(raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  const h = v.startsWith("#") ? v : `#${v}`;
  return HEX_COLOR.test(h) ? h.toUpperCase() : null;
}

function BrandsTab() {
  type BrandRow = {
    id: string;
    name: string;
    primary_color: string | null;
    context_description: string | null;
  };

  const [rows, setRows] = useState<BrandRow[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "idle" | "error">(
    "loading",
  );
  const [name, setName] = useState("");
  const [accentHex, setAccentHex] = useState(DEFAULT_BRAND_COLOR);
  const [context, setContext] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  const reload = async () => {
    setLoadState("loading");
    const { data: auth } = await supabase.auth.getSession();
    if (!auth.session?.user?.id) {
      setRows([]);
      setLoadState("idle");
      return;
    }
    const { data, error } = await supabase
      .from("brands")
      .select("id,name,primary_color,context_description")
      .eq("user_id", auth.session.user.id)
      .order("name");
    if (error) {
      setLoadState("error");
      return;
    }
    setRows((data as BrandRow[]) ?? []);
    setLoadState("idle");
  };

  useEffect(() => {
    void reload();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setFormError("Brand name is required.");
      return;
    }
    const normalized = normalizeBrandHex(accentHex);
    if (!normalized) {
      setFormError("Primary color must be a value like #E8442A.");
      return;
    }
    setFormError(null);
    setBusy(true);
    try {
      const { data: auth } = await supabase.auth.getSession();
      const uid = auth.session?.user?.id;
      if (!uid) {
        setFormError("Sign in to create a brand.");
        return;
      }
      const payload = {
        user_id: uid,
        name: trimmed,
        primary_color: normalized,
        context_description:
          context.trim() ? context.trim() : null,
      };
      const { error } = await supabase.from("brands").insert(payload);
      if (error) {
        setFormError(error.message ?? "Could not save brand.");
        return;
      }
      setName("");
      setAccentHex(DEFAULT_BRAND_COLOR);
      setContext("");
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-[1100px]">
      <div className="rounded-xl border border-hairline bg-surface p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist mb-1">
          new brand
        </div>
        <h3 className="text-[14px] text-white mb-4">Create a brand</h3>
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
              <FieldLabel htmlFor="brand-accent" hint="scene + studio accent">
                Primary color
              </FieldLabel>
              <div className="flex items-center gap-2">
                <input
                  id="brand-accent"
                  type="color"
                  value={accentHex.startsWith("#") ? accentHex : DEFAULT_BRAND_COLOR}
                  onChange={(e) => setAccentHex(e.target.value.toUpperCase())}
                  className={cn(
                    "h-9 w-14 cursor-pointer rounded border border-hairline bg-transparent",
                    "p-0.5 shrink-0",
                  )}
                  aria-label="Pick primary color"
                />
                <Input
                  value={accentHex}
                  onChange={(e) => setAccentHex(e.target.value)}
                  className="w-[120px] font-mono text-[12.5px]"
                  placeholder="#E8442A"
                  spellCheck={false}
                />
              </div>
            </div>
          </div>
          <div>
            <FieldLabel htmlFor="brand-ctx" hint="optional · used in prompts">
              Brand context
            </FieldLabel>
            <Textarea
              id="brand-ctx"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              rows={4}
              placeholder="One paragraph: what you publish, tone, positioning…"
              className="text-[13px]"
            />
          </div>
          {formError ? (
            <p className="text-[12px] text-cinnabar flex items-start gap-1.5">
              <Warning size={14} className="shrink-0 mt-0.5" />
              {formError}
            </p>
          ) : null}
          <Button type="submit" disabled={busy} className="w-full sm:w-auto">
            {busy ? "Saving…" : "Add brand"}
          </Button>
          {savedFlash ? (
            <p className="text-[11.5px] text-mist font-mono">saved ✓</p>
          ) : null}
        </form>
      </div>

      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist mb-3">
          your brands
        </div>
        {loadState === "loading" ? (
          <p className="text-[13px] text-mist font-mono">loading…</p>
        ) : loadState === "error" ? (
          <p className="text-[13px] text-cinnabar">Could not load brands.</p>
        ) : rows.length === 0 ? (
          <EmptyPanel
            icon={Palette}
            title="No brands yet."
            body="Use the form to add one. Brands power the accent color in Studio and carry context into scene generation."
          />
        ) : (
          <ul className="space-y-2">
            {rows.map((b) => {
              const dot =
                normalizeBrandHex(String(b.primary_color ?? "")) ??
                DEFAULT_BRAND_COLOR;
              return (
                <li
                  key={b.id}
                  className="rounded-xl border border-hairline bg-surface px-4 py-3 flex gap-3 items-start"
                >
                  <span
                    aria-hidden
                    className="h-8 w-8 rounded-md border border-white/15 shrink-0 mt-0.5"
                    style={{ backgroundColor: dot }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-[14px] text-white truncate">
                      {b.name}
                    </div>
                    {b.context_description ? (
                      <p className="mt-1 text-[12px] text-mist leading-[1.55]">
                        {b.context_description}
                      </p>
                    ) : null}
                    <div className="mt-2 font-mono text-[10.5px] text-mist/80">
                      {normalizeBrandHex(String(b.primary_color ?? "")) ?? "—"}
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

function ModelsTab() {
  return (
    <div className="space-y-4 max-w-[1100px]">
      <EmptyPanel
        icon={Cpu}
        title="Server-default keys are active."
        body="BYOK (bring-your-own-key per function) ships in v2. Today, the research crew runs on the workspace Anthropic + Exa keys configured in backend/.env."
      />
      <div className="rounded-xl border border-hairline bg-surface overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
          <div className="col-span-5">function</div>
          <div className="col-span-5">model</div>
          <div className="col-span-2 text-right">status</div>
        </div>
        <div className="divide-y divide-hairline">
          <ModelRow fn="Research agent" model="Claude Sonnet 4.6 + Exa neural" live />
          <ModelRow fn="Script generation" model="—" />
          <ModelRow fn="Scene generation" model="—" />
          <ModelRow fn="Content extraction" model="—" />
          <ModelRow fn="Thumbnail generation" model="—" />
        </div>
      </div>
    </div>
  );
}

function ModelRow({
  fn,
  model,
  live,
}: {
  fn: string;
  model: string;
  live?: boolean;
}) {
  return (
    <div className="grid grid-cols-12 gap-4 px-5 py-3.5 items-center text-[13px]">
      <div className="col-span-5 text-white">{fn}</div>
      <div
        className={cn(
          "col-span-5 font-mono text-[12.5px]",
          live ? "text-white/85" : "text-mist",
        )}
      >
        {model}
      </div>
      <div className="col-span-2 text-right">
        {live ? (
          <Badge tone="neutral">
            <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
            live
          </Badge>
        ) : (
          <Badge tone="muted">pending</Badge>
        )}
      </div>
    </div>
  );
}

function SkillsTab() {
  return (
    <EmptyPanel
      icon={FileMd}
      title="No skill files yet."
      body="Upload up to 3 .md files (≤50 KB combined) — they're injected into the studio's AI chat on demand. Landing with the Studio vertical."
    />
  );
}

function IntegrationsTab() {
  const { profile } = useAuth();
  const youtubeConnected = Boolean(
    (profile as { youtube_connected?: boolean } | null)?.youtube_connected,
  );
  const rows = [
    {
      name: "YouTube (read-only)",
      hint: youtubeConnected
        ? "connected"
        : "needed for Published kanban + outlier scoring",
      connected: youtubeConnected,
    },
    {
      name: "Notion",
      hint: "post-MVP · Framework/How-to scene output",
      connected: false,
    },
    {
      name: "Gamma",
      hint: "post-MVP · Pitch scene output",
      connected: false,
    },
    {
      name: "NanoBanana Pro",
      hint: "thumbnail generation",
      connected: false,
    },
  ];
  return (
    <div className="space-y-3 max-w-[820px]">
      {rows.map((i) => (
        <div
          key={i.name}
          className="rounded-xl border border-hairline bg-surface p-4 flex items-center gap-4"
        >
          <div className="flex-1">
            <div className="text-[13.5px] text-white">{i.name}</div>
            <div className="font-mono text-[11.5px] text-mist mt-0.5">
              {i.hint}
            </div>
          </div>
          {i.connected ? (
            <Badge tone="neutral">
              <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
              connected
            </Badge>
          ) : (
            <Badge tone="muted">not connected</Badge>
          )}
        </div>
      ))}
    </div>
  );
}
