import { forwardRef } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import type { KanbanColumn, KanbanStatus } from "./types";

type Props = {
  search: string;
  onSearchChange: (v: string) => void;
  statusFilter: KanbanStatus | "all";
  onStatusFilterChange: (s: KanbanStatus | "all") => void;
  columns: KanbanColumn[];
  totalCount: number;
};

export const Toolbar = forwardRef<HTMLInputElement, Props>(function Toolbar(
  { search, onSearchChange, statusFilter, onStatusFilterChange, columns, totalCount },
  searchRef,
) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <FilterChip
          active={statusFilter === "all"}
          onClick={() => onStatusFilterChange("all")}
        >
          All
          <Count>{totalCount}</Count>
        </FilterChip>
        {columns.map((col) => (
          <FilterChip
            key={col.id}
            active={statusFilter === col.id}
            onClick={() => onStatusFilterChange(col.id)}
          >
            {col.title}
          </FilterChip>
        ))}
      </div>

      <label className="relative flex items-center">
        <MagnifyingGlass
          size={13}
          weight="bold"
          className="absolute left-2.5 text-mist pointer-events-none"
        />
        <input
          ref={searchRef}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search ideas…  (press /)"
          className={cn(
            "h-8 w-[260px] pl-7 pr-3 rounded-md bg-surface-input",
            "text-[12.5px] text-white placeholder:text-mist",
            "border border-transparent focus:border-cinnabar focus:outline-none",
            "transition-colors duration-150",
          )}
        />
      </label>
    </div>
  );
});

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 h-7 text-[12px] transition-colors",
        active
          ? "bg-cinnabar text-white border border-cinnabar"
          : "bg-transparent text-mist border border-hairline hover:text-white hover:border-hairline-strong",
      )}
    >
      {children}
    </button>
  );
}

function Count({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10.5px] text-white/70 tabular-nums">
      {children}
    </span>
  );
}
