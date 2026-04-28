import { useEffect, useRef, useState, type RefObject } from "react";
import { cn } from "../../lib/cn";

export type SectionDef = {
  id: string;
  label: string;
  /** Optional micro-status, e.g. "ready" / "streaming" / "—" */
  status?: string;
};

type Props = {
  sections: SectionDef[];
  /** Element used as the IntersectionObserver root. Should be the scroll container. */
  scrollRootRef: RefObject<HTMLElement | null>;
};

/**
 * Sticky scroll-spy chips for the left pane.
 *
 * Watches each section's anchor element via IntersectionObserver against the
 * pane's scroll container, highlights the deepest section currently in view,
 * and jumps via `scrollIntoView` on click. Cheap to render — chips only.
 */
export function SectionNav({ sections, scrollRootRef }: Props) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");
  const visibleRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const root = scrollRootRef.current;
    if (!root) return;
    const observed = sections
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => !!el);
    if (observed.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            visibleRef.current.set(e.target.id, e.intersectionRatio);
          } else {
            visibleRef.current.delete(e.target.id);
          }
        }
        // Pick the section in DOM order that's currently visible. If none
        // are in view (between sections), fall back to the last we left.
        let next: string | null = null;
        for (const s of sections) {
          if (visibleRef.current.has(s.id)) {
            next = s.id;
            break;
          }
        }
        if (next) setActiveId(next);
      },
      {
        root,
        // Trigger active when the section's top crosses ~30% from the top.
        rootMargin: "0px 0px -65% 0px",
        threshold: [0, 0.1, 0.5, 1],
      },
    );
    for (const el of observed) observer.observe(el);
    return () => observer.disconnect();
  }, [sections, scrollRootRef]);

  const onJump = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(id);
  };

  return (
    <nav
      className={cn(
        "sticky top-0 z-10 -mx-6 px-6 h-10 flex items-center gap-0.5",
        "bg-night/85 backdrop-blur supports-[backdrop-filter]:bg-night/70",
        "border-b border-hairline",
      )}
      aria-label="Studio sections"
    >
      {sections.map((s) => {
        const isActive = s.id === activeId;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onJump(s.id)}
            aria-current={isActive ? "true" : undefined}
            className={cn(
              "group relative inline-flex items-center gap-1.5 h-7 px-2 rounded-md",
              "text-[12px] font-medium transition-colors",
              isActive
                ? "text-white"
                : "text-mist hover:text-white/85 hover:bg-white/[0.03]",
            )}
          >
            <span>{s.label}</span>
            {s.status ? (
              <span
                className={cn(
                  "font-mono text-[9px] uppercase tracking-[0.18em]",
                  isActive ? "text-cinnabar" : "text-mist/70",
                )}
              >
                {s.status}
              </span>
            ) : null}
            {isActive ? (
              <span
                className="absolute left-2 right-2 -bottom-px h-px bg-cinnabar"
                aria-hidden
              />
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
