import { cn } from "../../lib/cn";
import type { Source } from "../../lib/agents";

type Props = {
  text: string;
  sources?: Source[] | null;
};

/**
 * Renders text with [source:N] citation tags as clickable badges.
 * [source:3] links to sources[2] (0-indexed array).
 */
export function CitedText({ text, sources }: Props) {
  const sourceMap = sources || [];
  const parts = text.split(/(\[source:\d+\])/g);

  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\[source:(\d+)\]$/);
        if (m) {
          const idx = parseInt(m[1]) - 1;
          const source = sourceMap[idx];
          if (source?.url) {
            return (
              <a
                key={i}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(
                  "inline-flex items-center gap-0.5 px-1 rounded",
                  "text-[11px] font-mono font-medium",
                  "bg-blue-50 text-blue-700 border border-blue-200",
                  "hover:bg-blue-100 hover:underline",
                  "align-middle mx-0.5",
                )}
                title={source.title || source.url}
              >
                [{m[1]}]
              </a>
            );
          }
          // Source not in map — show as plain text
          return (
            <span key={i} className="text-mist text-[11px] font-mono align-middle mx-0.5">
              [{m[1]}]
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
