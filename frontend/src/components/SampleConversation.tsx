import { useState } from "react";
import type { MouseEvent } from "react";
import { Check, Copy, Layers3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { sampleAnswer, sampleSources } from "@/data/sample-conversation";
import { viewHref } from "@/routing/workbench";

type Props = { citation: string | null; onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void };

export function SampleConversation({ citation, onNavigate }: Props) {
  const [copyStatus, setCopyStatus] = useState("");

  async function copyAnswer() {
    try { await navigator.clipboard.writeText(sampleAnswer); setCopyStatus("Copied"); }
    catch { setCopyStatus("Couldn’t copy. Select the answer and copy it instead."); }
  }

  return (
    <div className="space-y-8 py-8 sm:py-12">
      <article aria-label="Your message" className="ml-auto max-w-[85%] rounded-2xl bg-canvas px-5 py-3">
        <h2 className="text-base font-normal">How can I keep my team’s files private?</h2>
      </article>
      <article aria-label="Example answer" className="space-y-5">
        <div className="flex items-center gap-2 text-sm font-semibold"><Layers3 aria-hidden="true" size={20} /><span translate="no">DocWeave</span><span className="font-normal text-muted-foreground">Example</span></div>
        <p className="leading-7">Keep each team’s files separate. Only use files that the person asking the question is allowed to read.</p>
        <p className="leading-7">Check access again before sharing an answer. If access is removed, stop using those files in the chat.</p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="mr-1 text-muted-foreground">Sources</span>
          {sampleSources.map((source) => (
            <a key={source.id} href={viewHref("sample", source.id)} onClick={onNavigate}
              aria-label={`Source ${source.id}: ${source.title}`}
              aria-current={citation === source.id ? "location" : undefined}
              className="inline-flex size-11 items-center justify-center rounded-lg border border-divider bg-canvas text-primary hover:border-primary hover:bg-accent aria-[current]:border-primary">
              {source.id}
            </a>
          ))}
          <Button variant="ghost" className="ml-auto" onClick={copyAnswer} aria-label="Copy answer">
            {copyStatus === "Copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}<span className="sr-only">Copy answer</span>
          </Button>
        </div>
        <p role="status" className="text-sm text-muted-foreground empty:hidden">{copyStatus}</p>
      </article>
    </div>
  );
}
