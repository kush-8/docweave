import { useRef } from "react";
import { ArrowUp, ChevronDown, LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Props = {
  draft: string;
  onDraft: (value: string) => void;
  fresh: boolean;
  provider: string;
  onProvider: (value: string) => void;
  error: string;
  onSubmit: (error: string) => void;
};

export function Composer({
  draft,
  onDraft,
  fresh,
  provider,
  onProvider,
  error,
  onSubmit,
}: Props) {
  const input = useRef<HTMLTextAreaElement>(null);
  const shortcut = /Mac|iPhone|iPad/.test(navigator.platform)
    ? "Command+Enter"
    : "Ctrl+Enter";

  function submit() {
    onSubmit(
      draft.trim()
        ? "Answers are unavailable in this preview. Your draft has not been sent. Connect the backend and configure an inference profile to send messages."
        : "Enter a message before sending.",
    );
    input.current?.focus();
  }

  return (
    <form
      className="shrink-0 rounded-b-md border-t border-divider bg-background px-4 pt-4 pb-3 md:px-6"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="mb-2 flex items-center justify-between text-sm font-semibold [&>span]:text-sm [&>span]:font-normal">
        <label htmlFor="message">Your message</label>
        <span className="text-sm text-muted-foreground">
          {fresh ? "New conversation" : "Follow-up"}
        </span>
      </div>
      <Textarea
        ref={input}
        className="min-h-20 max-h-40 resize-y border-input bg-background p-3 text-base text-foreground shadow-none placeholder:text-muted-foreground md:text-base"
        id="message"
        name="message"
        autoComplete="off"
        placeholder="Ask about your project…"
        value={draft}
        aria-describedby={`composer-help${error ? " composer-error" : ""}`}
        aria-invalid={!!error}
        onChange={(event) => {
          onDraft(event.target.value);
          if (error) onSubmit("");
        }}
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            (event.ctrlKey || event.metaKey) &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            submit();
          }
        }}
      />
      {error && (
        <p
          id="composer-error"
          className="mt-2 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        {fresh ? (
          <div className="flex items-center gap-3 text-sm max-sm:w-full max-sm:justify-between [&_[data-slot=select-trigger]]:min-w-36">
            <label htmlFor="provider">Answer provider</label>
            <Select value={provider} onValueChange={onProvider}>
              <SelectTrigger id="provider" aria-label="Answer provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Gemini", "Groq", "Hugging Face"].map((name) => (
                  <SelectItem value={name} key={name}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <span className="flex flex-wrap items-center gap-2 text-sm [&>span:last-child]:text-sm max-sm:[&>span:last-child]:basis-full max-sm:[&>span:last-child]:pl-5">
            <LockKeyhole aria-hidden="true" size={14} />
            <span translate="no">Gemini</span>
            <span className="text-sm text-muted-foreground">Sample model</span>
          </span>
        )}
        <Button type="submit" className="ml-auto shrink-0">
          <span>Send message</span>
          <ArrowUp aria-hidden="true" />
        </Button>
      </div>
      <div
        id="composer-help"
        className="mt-2 flex flex-col justify-between gap-1 text-sm text-muted-foreground sm:flex-row sm:gap-4 [&>span:last-child]:whitespace-nowrap"
      >
        <span>
          {fresh
            ? "No model configured. Gemini retrieval approval is also required for Groq and Hugging Face."
            : "Provider is fixed for this sample conversation."}
        </span>
        <span>{shortcut} to send</span>
      </div>
      <details className="mt-1 text-sm text-muted-foreground [&>summary]:flex [&>summary]:min-h-11 [&>summary]:w-fit [&>summary]:items-center [&>summary]:gap-1 [&>p]:py-2">
        <summary>
          <ChevronDown aria-hidden="true" size={14} />
          Knowledge in this preview
        </summary>
        <p>
          3 synthetic architecture notes. No private collections or real
          provider approvals are connected.
        </p>
      </details>
    </form>
  );
}
