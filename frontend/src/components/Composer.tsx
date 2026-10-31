import { useRef } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Props = {
  draft: string;
  onDraft: (value: string) => void;
  fresh: boolean;
  provider: string;
  onProvider: (value: string) => void;
  error: string;
  onSubmit: (error: string) => void;
};

export function Composer({ draft, onDraft, fresh, provider, onProvider, error, onSubmit }: Props) {
  const input = useRef<HTMLTextAreaElement>(null);
  const shortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ Enter" : "Ctrl+Enter";

  function submit() {
    onSubmit(draft.trim()
      ? "Chat isn’t connected yet. Your message hasn’t been sent."
      : "Write a message first.");
    input.current?.focus();
  }

  return (
    <form className="shrink-0 pb-[max(1rem,env(safe-area-inset-bottom))]" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      <div className="rounded-3xl border border-input bg-card p-2 shadow-sm focus-within:border-primary">
        <label htmlFor="message" className="sr-only">Your message</label>
        <Textarea
          ref={input}
          id="message"
          name="message"
          autoComplete="off"
          placeholder="Message DocWeave…"
          className="min-h-10 max-h-40 resize-none border-0 bg-transparent px-3 py-2 text-base shadow-none md:text-base"
          value={draft}
          aria-describedby={`composer-help${error ? " composer-error" : ""}`}
          aria-invalid={!!error && !draft.trim()}
          onChange={(event) => { onDraft(event.target.value); if (error) onSubmit(""); }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) {
              event.preventDefault(); submit();
            }
          }}
        />
        <div className="flex items-end justify-between gap-3">
          <details className="min-w-0 text-sm text-muted-foreground">
            <summary className="flex min-h-11 items-center rounded-md px-2 hover:bg-accent">Chat options</summary>
            <div className="flex flex-wrap items-center gap-2 px-2 py-2">
              {fresh ? <>
                <label htmlFor="provider">Model</label>
                <Select value={provider} onValueChange={onProvider}>
                  <SelectTrigger id="provider" aria-label="Model"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["Gemini", "Groq", "Hugging Face"].map((name) => <SelectItem value={name} key={name}>{name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </> : <span translate="no">Gemini · example chat</span>}
            </div>
            <p className="px-2 pb-2">Preview only. No AI service is connected.</p>
          </details>
          <Button type="submit" className="shrink-0 rounded-full" aria-label="Send">
            <span className="sr-only sm:not-sr-only">Send</span><ArrowUp aria-hidden="true" />
          </Button>
        </div>
      </div>
      {error && <p id="composer-error" className="mt-2 text-sm text-destructive" role="alert">{error}</p>}
      <p id="composer-help" className="mt-3 text-center text-xs text-muted-foreground">Preview only · Messages aren’t sent. <span className="hidden sm:inline">{shortcut} to send.</span></p>
    </form>
  );
}
