import AccumulatedFeed from "./AccumulatedFeed";
import ManualKnowledgeForm from "./ManualKnowledgeForm";

export default function GraphTab() {
  return (
    <div className="space-y-6 max-w-[1100px]">
      <AccumulatedFeed />
      <div className="border-t border-hairline" />
      <ManualKnowledgeForm />
    </div>
  );
}
