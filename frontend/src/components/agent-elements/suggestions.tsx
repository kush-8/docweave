// Adapted from 21st.dev Agent Elements (MIT); uses the existing shadcn Button.
import { Button } from "@/components/ui/button";

type SuggestionItem = { id: string; label: string };

export function Suggestions({ items, onSelect }: {
  items: SuggestionItem[];
  onSelect: (item: SuggestionItem) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="mt-4 flex flex-wrap justify-center gap-2">
      {items.map((item) => (
        <Button key={item.id} type="button" variant="outline"
          className="rounded-lg text-sm font-normal" onClick={() => onSelect(item)}>
          {item.label}
        </Button>
      ))}
    </div>
  );
}
