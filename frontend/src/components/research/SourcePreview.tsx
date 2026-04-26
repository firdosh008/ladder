import {
  Link as LinkIcon,
  PlayCircle,
  ChatCircle,
  ArrowFatUp,
  Heart,
  Eye,
  ArrowsClockwise,
  FilmReel,
} from "@phosphor-icons/react";
import type { Source } from "../../lib/agents";
import { cn } from "../../lib/cn";

/**
 * Platform-aware preview card for a research source.
 *
 * Renders rich previews per platform — YouTube thumbnails, Reddit score +
 * comments, X tweet text + engagement, Instagram caption + plays — instead of
 * bare URL chips. Older payloads (no `meta` / `thumbnail`) gracefully fall
 * back to a domain + title row.
 *
 * Two layouts are exposed:
 *   - `compact`  — used in the right-hand source rail on /make
 *   - `gallery`  — used in the Studio research panel where horizontal space
 *                  is at a premium and we want a denser scroll list
 */

type Variant = "compact" | "gallery";

const PLATFORM_LABEL: Record<NonNullable<Source["platform"]>, string> = {
  web: "web",
  reddit: "reddit",
  youtube: "yt",
  x: "x",
  instagram: "ig",
};

const PLATFORM_PILL: Record<NonNullable<Source["platform"]>, string> = {
  web: "bg-white/8 text-white/70",
  reddit: "bg-[#ff4500]/15 text-[#ff7a3d]",
  youtube: "bg-[#ff0000]/15 text-[#ff5c5c]",
  x: "bg-white/15 text-white",
  instagram: "bg-[#E1306C]/15 text-[#f06292]",
};

function PlatformPill({ platform }: { platform: NonNullable<Source["platform"]> }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-[1px] font-mono text-[9.5px] uppercase tracking-[0.12em]",
        PLATFORM_PILL[platform],
      )}
    >
      {PLATFORM_LABEL[platform]}
    </span>
  );
}

function fmtCompact(n: number | null | undefined): string | null {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  if (n < 1_000) return String(n);
  if (n < 1_000_000) return `${(n / 1_000).toFixed(n < 10_000 ? 1 : 0)}K`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(n < 10_000_000 ? 1 : 0)}M`;
  return `${(n / 1_000_000_000).toFixed(1)}B`;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function SourcePreview({
  source,
  index,
  variant = "compact",
}: {
  source: Source;
  index?: number;
  variant?: Variant;
}) {
  const platform = source.platform ?? "web";

  const Inner = (() => {
    switch (platform) {
      case "youtube":
        return <YouTubePreview source={source} variant={variant} />;
      case "reddit":
        return <RedditPreview source={source} variant={variant} />;
      case "x":
        return <XPreview source={source} variant={variant} />;
      case "instagram":
        return <InstagramPreview source={source} variant={variant} />;
      default:
        return <WebPreview source={source} variant={variant} />;
    }
  })();

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "group block rounded-md border border-hairline bg-white/[0.015]",
        "hover:border-hairline-strong hover:bg-white/[0.04] transition-colors",
        variant === "gallery" ? "p-2.5" : "p-2.5",
      )}
    >
      <div className="flex items-start gap-2.5 min-w-0">
        {typeof index === "number" ? (
          <span className="font-mono text-[10.5px] text-mist tabular-nums mt-[2px] shrink-0 w-5 text-right">
            {index}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <PlatformPill platform={platform} />
            {source.published_date ? (
              <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-mist">
                {source.published_date}
              </span>
            ) : null}
          </div>
          {Inner}
        </div>
      </div>
    </a>
  );
}

// ─── platform-specific bodies ──────────────────────────────────────────────

function WebPreview({ source }: { source: Source; variant: Variant }) {
  const domain = source.meta?.domain || domainOf(source.url);
  return (
    <>
      <div className="text-[12.5px] text-white/90 leading-[1.35] line-clamp-2 group-hover:text-white">
        {source.title || source.url}
      </div>
      <div className="mt-1 flex items-center gap-1.5 font-mono text-[10.5px] text-mist">
        <LinkIcon size={9} weight="bold" className="shrink-0" />
        <span className="truncate">{domain || source.url}</span>
      </div>
      {source.snippet ? (
        <p className="mt-1.5 text-[11.5px] text-white/65 leading-[1.45] line-clamp-2">
          {source.snippet}
        </p>
      ) : null}
    </>
  );
}

function YouTubePreview({
  source,
  variant,
}: {
  source: Source;
  variant: Variant;
}) {
  const channel = source.meta?.channel || domainOf(source.url);
  const views = source.meta?.view_count_text;
  const duration = source.meta?.duration;
  const thumb = source.thumbnail;

  return (
    <div className={cn("flex gap-2.5 min-w-0", variant === "gallery" && "items-start")}>
      {thumb ? (
        <div className="relative shrink-0 w-[88px] h-[50px] rounded overflow-hidden bg-black/40 border border-hairline">
          <img
            src={thumb}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <PlayCircle
              size={20}
              weight="fill"
              className="text-white/85 drop-shadow"
            />
          </div>
          {duration ? (
            <span className="absolute bottom-0.5 right-0.5 font-mono text-[9px] bg-black/80 text-white px-1 rounded">
              {duration}
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] text-white/90 leading-[1.3] line-clamp-2 group-hover:text-white">
          {source.title || "(untitled video)"}
        </div>
        <div className="mt-1 font-mono text-[10.5px] text-mist truncate">
          {channel}
          {views ? <span className="text-white/55"> · {views}</span> : null}
        </div>
      </div>
    </div>
  );
}

function RedditPreview({ source }: { source: Source; variant: Variant }) {
  const sub = source.meta?.subreddit;
  const score = source.meta?.score ?? null;
  const comments = source.meta?.num_comments ?? null;
  const author = source.meta?.author;

  return (
    <>
      <div className="text-[12.5px] text-white/90 leading-[1.35] line-clamp-2 group-hover:text-white">
        {source.title || "(reddit post)"}
      </div>
      <div className="mt-1 flex items-center gap-2 font-mono text-[10.5px] text-mist flex-wrap">
        {sub ? <span className="text-[#ff7a3d]">r/{sub}</span> : null}
        {author ? <span>· u/{author}</span> : null}
        {score !== null ? (
          <span className="inline-flex items-center gap-0.5">
            <ArrowFatUp size={10} weight="bold" />
            {fmtCompact(score)}
          </span>
        ) : null}
        {comments !== null ? (
          <span className="inline-flex items-center gap-0.5">
            <ChatCircle size={10} weight="bold" />
            {fmtCompact(comments)}
          </span>
        ) : null}
      </div>
      {source.snippet ? (
        <p className="mt-1.5 text-[11.5px] text-white/65 leading-[1.45] line-clamp-2">
          {source.snippet}
        </p>
      ) : null}
    </>
  );
}

function XPreview({ source }: { source: Source; variant: Variant }) {
  const handle = source.meta?.handle;
  const text = source.meta?.full_text || source.snippet || source.title || "";
  const likes = source.meta?.like_count;
  const views = source.meta?.view_count;
  const replies = source.meta?.reply_count;
  const reposts = source.meta?.retweet_count;

  return (
    <>
      {handle ? (
        <div className="font-mono text-[10.5px] text-white mb-1">@{handle}</div>
      ) : null}
      <p className="text-[12.5px] text-white/85 leading-[1.45] line-clamp-3 group-hover:text-white whitespace-pre-wrap">
        {text}
      </p>
      <div className="mt-1.5 flex items-center gap-3 font-mono text-[10.5px] text-mist flex-wrap">
        {views !== null && views !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <Eye size={10} weight="bold" />
            {fmtCompact(views)}
          </span>
        ) : null}
        {likes !== null && likes !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <Heart size={10} weight="bold" />
            {fmtCompact(likes)}
          </span>
        ) : null}
        {reposts !== null && reposts !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <ArrowsClockwise size={10} weight="bold" />
            {fmtCompact(reposts)}
          </span>
        ) : null}
        {replies !== null && replies !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <ChatCircle size={10} weight="bold" />
            {fmtCompact(replies)}
          </span>
        ) : null}
      </div>
    </>
  );
}

function InstagramPreview({
  source,
}: {
  source: Source;
  variant: Variant;
}) {
  const owner = source.meta?.owner_handle;
  const plays = source.meta?.play_count;
  const likes = source.meta?.like_count;
  const comments = source.meta?.comment_count;
  const duration = source.meta?.duration_sec;
  const text = source.snippet || source.title || "";

  return (
    <>
      <div className="flex items-center gap-2 mb-1 font-mono text-[10.5px] text-mist">
        <FilmReel size={11} weight="bold" className="text-[#f06292]" />
        {owner ? <span className="text-white">@{owner}</span> : null}
        {duration ? (
          <span className="text-white/55">· {Math.round(duration)}s</span>
        ) : null}
      </div>
      <p className="text-[12px] text-white/80 leading-[1.45] line-clamp-3 group-hover:text-white">
        {text}
      </p>
      <div className="mt-1.5 flex items-center gap-3 font-mono text-[10.5px] text-mist flex-wrap">
        {plays !== null && plays !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <PlayCircle size={10} weight="bold" />
            {fmtCompact(plays)}
          </span>
        ) : null}
        {likes !== null && likes !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <Heart size={10} weight="bold" />
            {fmtCompact(likes)}
          </span>
        ) : null}
        {comments !== null && comments !== undefined ? (
          <span className="inline-flex items-center gap-0.5">
            <ChatCircle size={10} weight="bold" />
            {fmtCompact(comments)}
          </span>
        ) : null}
      </div>
    </>
  );
}
