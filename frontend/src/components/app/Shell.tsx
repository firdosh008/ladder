import { type ReactNode } from "react";
import { Sidebar } from "./Sidebar";

export function Shell({
  children,
  unconstrained,
}: {
  children: ReactNode;
  /** Studio uses the full viewport with no max-width. */
  unconstrained?: boolean;
}) {
  return (
    <div className="flex h-[100dvh] w-full bg-night text-white overflow-hidden">
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col min-h-0">
        {unconstrained ? (
          children
        ) : (
          <div className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden">{children}</div>
        )}
      </main>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  right,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-6 mb-8">
      <div className="min-w-0">
        {eyebrow ? (
          <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-3">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="font-display font-bold text-[32px] md:text-[36px] leading-[1.05] tracking-tight text-white">
          {title}
        </h1>
        {description ? (
          <p className="mt-3 text-[14.5px] text-white/65 leading-[1.55] max-w-[62ch]">
            {description}
          </p>
        ) : null}
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  );
}

export function PageContainer({ children }: { children: ReactNode }) {
  return (
    <div className="px-8 py-8 max-w-[1440px] mx-auto w-full">{children}</div>
  );
}
