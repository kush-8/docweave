import { useState } from "react";
import type { MouseEvent } from "react";
import { Check, Copy, Layers3, LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { sampleCode, sampleSources, viewHref } from "./sample";

type Props = {
  citation: string | null;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void;
};

function Cite({ id, citation, onNavigate }: Props & { id: string }) {
  const source = sampleSources.find((item) => item.id === id)!;
  return (
    <a
      className="mx-0.5 inline-flex size-11 items-center justify-center rounded-md border border-border bg-accent align-middle text-sm font-semibold text-primary hover:border-primary hover:bg-primary hover:text-primary-foreground aria-[current=location]:border-primary aria-[current=location]:bg-primary aria-[current=location]:text-primary-foreground"
      href={viewHref("sample", id)}
      onClick={onNavigate}
      aria-label={`Source ${id}: ${source.title}`}
      aria-current={citation === id ? "location" : undefined}
    >
      {id}
    </a>
  );
}

export function SampleConversation({ citation, onNavigate }: Props) {
  const [copyStatus, setCopyStatus] = useState("");

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(sampleCode);
      setCopyStatus("Copied");
    } catch {
      setCopyStatus("Copy unavailable. Select and copy the code below.");
    }
  }

  return (
    <>
      <div className="flex min-h-13 flex-wrap items-center justify-between gap-2 border-b border-divider px-4 py-3 text-sm font-semibold [&>span:last-child]:hidden min-[1360px]:[&>span:last-child]:flex min-[1360px]:[&>span:last-child]:text-sm min-[1360px]:[&>span:last-child]:font-normal">
        <span>Workspace isolation</span>
        <span className="text-sm text-muted-foreground flex items-center gap-2">
          <LockKeyhole aria-hidden="true" size={14} /> Private conversation
          preview
        </span>
      </div>
      <div className="min-h-40 flex-1 overflow-y-auto px-4 py-6 md:px-6 min-[1360px]:px-8 min-[1360px]:py-8 max-md:overflow-visible [scrollbar-gutter:stable]">
        <article className="mx-auto max-w-[72ch] border-b border-divider pb-7 [&>p]:mt-2">
          <span className="mb-2 block text-sm font-semibold text-muted-foreground">
            You
          </span>
          <h2>How should we keep each workspace’s knowledge isolated?</h2>
          <p className="text-sm text-muted-foreground">
            Consider retrieval, provider calls, and conversation memory.
          </p>
        </article>
        <article
          className="mx-auto max-w-[72ch] pt-7"
          aria-label="Sample assistant response"
        >
          <header className="mb-4 flex flex-wrap items-center gap-2 text-sm font-semibold [&>svg]:mr-1 [&>svg]:text-primary [&>[data-slot=badge]]:ml-auto [&>[data-slot=badge]]:text-muted-foreground">
            <Layers3 aria-hidden="true" size={20} />
            <span translate="no">DocWeave</span>
            <Badge variant="secondary">Sample response</Badge>
          </header>
          <div className="text-base leading-[1.6] [&>h3]:mt-6 [&>h3]:mb-2 [&>h3]:text-base">
            <p>
              Carry the workspace’s access boundaries through the entire answer
              flow. Start with the user’s current permissions, restrict
              retrieval, and check again before releasing the answer.
            </p>
            <h3>Start with permitted knowledge</h3>
            <p>
              Resolve workspace membership and collection grants before
              searching. Scope every retrieval to the current project; knowing a
              project’s ID is never enough to access it.{" "}
              <Cite id="1" citation={citation} onNavigate={onNavigate} />
            </p>
            <h3>Filter before ranking</h3>
            <p>
              Apply the same restrictions to lexical and vector candidates. Rank
              only eligible chunks from ready sources, rather than filtering an
              unrestricted result afterward.{" "}
              <Cite id="2" citation={citation} onNavigate={onNavigate} />
            </p>
            <div className="my-4 overflow-hidden rounded-md border border-divider bg-canvas [&_pre]:overflow-x-auto [&_pre]:p-4 [&_pre]:text-sm [&_pre]:leading-7 [&_code]:font-mono [&_code]:whitespace-pre">
              <div className="flex items-center justify-between border-b border-divider px-3 py-1 text-sm text-muted-foreground [&>button]:px-2 [&>button]:text-sm">
                <span translate="no">SQL · illustrative query</span>
                <Button
                  variant="ghost"
                  onClick={copyCode}
                  aria-label={copyStatus === "Copied" ? "Copied" : "Copy code"}
                >
                  {copyStatus === "Copied" ? (
                    <Check aria-hidden="true" />
                  ) : (
                    <Copy aria-hidden="true" />
                  )}
                  {copyStatus === "Copied" ? "Copied" : "Copy code"}
                </Button>
              </div>
              <pre tabIndex={0} aria-label="Illustrative workspace-scoped SQL">
                <code translate="no">{sampleCode}</code>
              </pre>
              <span
                className="block px-4 pb-2 text-sm text-muted-foreground empty:hidden"
                role="status"
              >
                {copyStatus}
              </span>
            </div>
            <h3>Recheck before external calls and release</h3>
            <p>
              Permissions can change while a job waits. Revalidate source access
              and processor approvals before sending context to a provider, then
              recheck before exposing the answer and citations. Pause
              conversations whose remembered sources are no longer available.{" "}
              <Cite id="3" citation={citation} onNavigate={onNavigate} />
            </p>
            <div className="mt-6 flex items-start gap-3 border-l-[3px] border-primary bg-accent px-4 py-3 [&>svg]:mt-1 [&>svg]:text-primary [&>p]:text-sm">
              <LockKeyhole aria-hidden="true" size={18} />
              <p>
                Conversation memory follows the same rules as retrieved
                evidence.
              </p>
            </div>
          </div>
          <div className="mt-6 [&>div]:mt-2 [&>div]:flex [&>div]:flex-wrap [&>div]:gap-2">
            <span className="text-sm text-muted-foreground">
              Explore the sample evidence
            </span>
            <div>
              {sampleSources.map((source) => (
                <a
                  key={source.id}
                  href={viewHref("sample", source.id)}
                  onClick={onNavigate}
                  className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:border-primary hover:bg-accent hover:text-primary aria-[current=location]:border-primary aria-[current=location]:bg-accent aria-[current=location]:text-primary [&>span]:font-semibold [&>span]:text-primary"
                  aria-label={`Source ${source.id}: ${source.title}`}
                  aria-current={citation === source.id ? "location" : undefined}
                >
                  <span>{source.id}</span>
                  {source.title}
                </a>
              ))}
            </div>
          </div>
          <details className="mt-6 border-t border-divider pt-2 text-sm text-muted-foreground [&>summary]:flex [&>summary]:min-h-11 [&>summary]:items-center [&>summary]:gap-2 [&>summary]:before:content-['+'] open:[&>summary]:before:content-['−'] [&_dl>div]:grid [&_dl>div]:grid-cols-[120px_minmax(0,1fr)] [&_dl>div]:gap-3 [&_dl>div]:py-1 [&_dd]:text-foreground">
            <summary>Response details</summary>
            <dl>
              <div>
                <dt>Answer provider</dt>
                <dd translate="no">Gemini (sample)</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>Not configured</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>Synthetic architecture notes</dd>
              </div>
              <div>
                <dt>Execution</dt>
                <dd>No provider request made</dd>
              </div>
            </dl>
          </details>
        </article>
      </div>
    </>
  );
}
