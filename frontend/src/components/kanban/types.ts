export type KanbanStatus = "new" | "scripting" | "scene" | "ready" | "published";

export type KanbanColumn = {
  id: KanbanStatus;
  title: string;
  hint?: string;
};

export type KanbanCard = {
  id: string;
  columnId: KanbanStatus;
  position: number;
  title: string;
  score?: number | null;
  subtitle?: string;
  meta?: string;
};

export type KanbanMoveEvent = {
  cardId: string;
  fromColumnId: KanbanStatus;
  toColumnId: KanbanStatus;
  newPosition: number;
};

export const KANBAN_COLUMNS: KanbanColumn[] = [
  { id: "new", title: "Ideas" },
  { id: "scripting", title: "Scripting" },
  { id: "scene", title: "Scene" },
  { id: "ready", title: "Ready to record" },
  { id: "published", title: "Published" },
];
