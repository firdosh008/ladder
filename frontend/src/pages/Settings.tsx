import { useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  User,
  Palette,
  Cpu,
  FileMd,
  LinkSimple,
  Check,
  Warning,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Input, FieldLabel, Textarea } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";
import { useAuth } from "../lib/auth";
import { api, ApiError } from "../lib/api";

const TABS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "brands", label: "Brands", icon: Palette },
  { id: "models", label: "Models", icon: Cpu },
  { id: "skills", label: "Skill files", icon: FileMd },
  { id: "integrations", label: "Integrations", icon: LinkSimple },
];

const MODELS = [
  { fn: "Script generation", model: "Claude Sonnet 4.5", provider: "Anthropic", ok: true },
  { fn: "Scene generation", model: "Claude Sonnet 4.5", provider: "Anthropic", ok: true },
  { fn: "Scene editing (Vision)", model: "Claude Sonnet 4.5", provider: "Anthropic", ok: true },
  { fn: "Research agent", model: "GPT-4o", provider: "OpenAI", ok: true },
  { fn: "Content extraction", model: "Gemini 1.5 Pro", provider: "Google", ok: false },
  { fn: "Thumbnail generation", model: "NanoBanana Pro", provider: "NB", ok: true },
  { fn: "Newsletter extraction", model: "Claude Haiku", provider: "Anthropic", ok: true },
];

export default function SettingsPage() {
  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /settings"
          title="Settings"
          description="Your profile, brands, model routing, skill files, and integrations. All keys stored encrypted."
        />

        <Tabs.Root defaultValue="models">
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
  const { profile, refreshProfile, loading } = useAuth();
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

  const showSaved = savedAt !== null && Date.now() - savedAt < 2000;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-[1100px]">
      <div className="space-y-5">
        <div>
          <FieldLabel htmlFor="name">Name</FieldLabel>
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
            <span className="text-white/80">stream_script</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">sharpen_this</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">research_agent</span>
          </li>
          <li>
            <span className="text-cinnabar">›</span>{" "}
            <span className="text-white/80">content_extract</span>
          </li>
        </ul>
      </div>
    </div>
  );
}

function BrandsTab() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-[1100px]">
      {[
        { name: "Ladder", color: "#E8442A", current: true, videos: 23 },
        { name: "Kim Labs", color: "#8B4A3A", current: false, videos: 8 },
      ].map((b) => (
        <div
          key={b.name}
          className="rounded-xl border border-hairline bg-surface p-5"
        >
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <span
                className="h-9 w-9 rounded-md"
                style={{ backgroundColor: b.color }}
              />
              <div>
                <div className="font-sans font-semibold text-[15px] text-white">
                  {b.name}
                </div>
                <div className="font-mono text-[11px] text-mist">
                  {b.videos} videos
                </div>
              </div>
            </div>
            {b.current ? <Badge tone="cinnabar">current</Badge> : null}
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary">
              Edit
            </Button>
            {!b.current ? (
              <Button size="sm" variant="ghost">
                Set as current
              </Button>
            ) : null}
          </div>
        </div>
      ))}
      <button className="rounded-xl border border-dashed border-hairline-strong bg-transparent p-5 h-full min-h-[140px] text-[13px] text-mist hover:text-white hover:border-cinnabar/40 transition-colors">
        + Add a brand
      </button>
    </div>
  );
}

function ModelsTab() {
  return (
    <div className="rounded-xl border border-hairline bg-surface overflow-hidden max-w-[1100px]">
      <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-hairline font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
        <div className="col-span-4">function</div>
        <div className="col-span-4">model</div>
        <div className="col-span-2">provider</div>
        <div className="col-span-2 text-right">status</div>
      </div>
      <div className="divide-y divide-hairline">
        {MODELS.map((m) => (
          <div
            key={m.fn}
            className="grid grid-cols-12 gap-4 px-5 py-3.5 items-center text-[13px] hover:bg-white/[0.015] transition-colors"
          >
            <div className="col-span-4 text-white">{m.fn}</div>
            <div className="col-span-4 font-mono text-[12.5px] text-white/85">
              {m.model}
            </div>
            <div className="col-span-2 font-mono text-[11.5px] text-mist">
              {m.provider}
            </div>
            <div className="col-span-2 text-right">
              {m.ok ? (
                <Badge tone="neutral">
                  <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
                  ready
                </Badge>
              ) : (
                <Badge tone="warn">key missing</Badge>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SkillsTab() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-[1100px]">
      {[
        { name: "hormozi-hook.skill.md", size: "2.1 kb", used: 8 },
        { name: "editorial-structure.skill.md", size: "1.8 kb", used: 3 },
        { name: "thumbnail-rules.skill.md", size: "0.9 kb", used: 14 },
        { name: "interview-prep.skill.md", size: "3.2 kb", used: 0 },
      ].map((s) => (
        <div
          key={s.name}
          className="rounded-xl border border-hairline bg-surface p-4 hover:border-l-[3px] hover:border-l-cinnabar hover:pl-[calc(1rem-2px)] transition-all duration-150"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-mono text-[12.5px] text-white truncate">
                {s.name}
              </div>
              <div className="mt-1 font-mono text-[11px] text-mist">
                {s.size} · injected {s.used}×
              </div>
            </div>
            <Button size="sm" variant="ghost">
              edit
            </Button>
          </div>
        </div>
      ))}
      <button className="rounded-xl border border-dashed border-hairline-strong bg-transparent p-4 min-h-[80px] text-[13px] text-mist hover:text-white hover:border-cinnabar/40 transition-colors">
        + Upload .skill.md
      </button>
    </div>
  );
}

function IntegrationsTab() {
  return (
    <div className="space-y-3 max-w-[820px]">
      {[
        { name: "YouTube (read-only)", status: "connected", hint: "@laddercreator · synced 15m ago" },
        { name: "Cloudflare Email Routing", status: "connected", hint: "alex+ladder@ingest.ladder.so" },
        { name: "Supabase (Storage + DB)", status: "connected", hint: "project ladder-prod" },
        { name: "TubeLab", status: "not connected", hint: "optional — for competitive research" },
        { name: "n8n", status: "connected", hint: "ingestion pipeline" },
      ].map((i) => (
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
          {i.status === "connected" ? (
            <Badge tone="neutral">
              <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
              connected
            </Badge>
          ) : (
            <Button size="sm" variant="secondary">
              Connect
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
