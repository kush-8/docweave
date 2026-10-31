import { Layers3 } from "lucide-react";
import { Suggestions } from "@/components/agent-elements/suggestions";

type Props = { draft: string; onSuggestion: (text: string) => void };

export function Welcome({ draft, onSuggestion }: Props) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
      <span className="mb-2 grid size-12 place-items-center rounded-xl bg-accent text-primary"><Layers3 aria-hidden="true" size={26} /></span>
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">What can I help you with?</h2>
      <p className="text-sm text-muted-foreground">Ask a question about your project.</p>
      {!draft && <Suggestions items={[
        { id: "summarize", label: "Summarize my project" },
        { id: "start", label: "Help me get started" },
      ]} onSelect={(item) => onSuggestion(item.label)} />}
    </div>
  );
}
