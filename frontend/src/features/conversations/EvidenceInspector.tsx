import { useEffect, useRef } from "react";
import type { MouseEvent } from "react";
import { BookOpen, FileText, Quote, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { sampleSources, viewHref } from "./sample";

type Props = {
  citation: string | null;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void;
  onClose: () => void;
  modal?: boolean;
};

export function EvidenceInspector({
  citation,
  onNavigate,
  onClose,
  modal = false,
}: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  const source = sampleSources.find((item) => item.id === citation);

  useEffect(() => {
    if (!source) return;
    const frame = requestAnimationFrame(() => heading.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [source, modal]);

  return (
    <section
      className="flex min-h-0 min-w-0 flex-col rounded-md border border-divider bg-background"
      aria-label="Evidence inspector"
    >
      {!modal && (
        <header className="flex min-h-13 items-center justify-between gap-2 border-b border-divider py-1 pr-3 pl-4 [&_h2]:text-sm [&_svg]:text-muted-foreground">
          <div className="flex items-center gap-2">
            <BookOpen aria-hidden="true" size={18} />
            <h2>Evidence</h2>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close evidence inspector"
          >
            <X aria-hidden="true" />
          </Button>
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto p-5 [scrollbar-gutter:stable] max-sm:p-4">
        <div className="[&>p]:mt-3 [&>p]:text-sm [&>p]:text-muted-foreground">
          <Badge variant="outline">3 sample sources</Badge>
          <p>Select a citation to inspect the excerpt behind a claim.</p>
        </div>
        <nav
          className="mt-4 flex flex-col [&>a]:flex [&>a]:min-h-18 [&>a]:items-center [&>a]:gap-3 [&>a]:border-b [&>a]:border-l-[3px] [&>a]:border-b-divider [&>a]:border-l-transparent [&>a]:px-2 [&>a]:py-3 [&>a]:text-foreground [&>a:hover]:border-l-primary [&>a:hover]:bg-accent [&>a[aria-current]]:border-l-primary [&>a[aria-current]]:bg-accent [&>a>span:nth-child(2)]:min-w-0 [&>a>span:nth-child(2)]:flex-1 [&_strong]:block [&_strong]:text-sm [&_strong]:font-semibold [&_small]:mt-1 [&_small]:block [&_small]:text-sm [&_small]:text-muted-foreground [&_svg]:text-muted-foreground"
          aria-label="Sources in this answer"
        >
          {sampleSources.map((item) => (
            <a
              key={item.id}
              href={viewHref("sample", item.id)}
              onClick={onNavigate}
              aria-label={`Source ${item.id}: ${item.title}`}
              aria-current={citation === item.id ? "location" : undefined}
            >
              <span className="grid size-6 shrink-0 place-items-center rounded border border-border text-sm font-semibold text-muted-foreground tabular-nums">
                {item.id}
              </span>
              <span>
                <strong>{item.title}</strong>
                <small>Synthetic project note</small>
              </span>
              <FileText aria-hidden="true" size={16} />
            </a>
          ))}
        </nav>
        {source ? (
          <div
            className="pt-6 [&>h3]:mt-4 [&>h3]:text-lg [&>h3]:leading-snug"
            key={source.id}
          >
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="grid size-6 shrink-0 place-items-center rounded border border-border text-sm font-semibold text-muted-foreground tabular-nums border-primary bg-primary text-primary-foreground">
                {source.id}
              </span>
              <span>Selected evidence</span>
            </div>
            <h3 ref={heading} tabIndex={-1}>
              {source.title}
            </h3>
            <p className="mt-2 flex items-start gap-2 text-sm text-muted-foreground [&>svg]:mt-0.5">
              <FileText aria-hidden="true" size={14} />
              <span translate="no">{source.file}</span>
            </p>
            <div className="mt-5 border-l-[3px] border-primary bg-accent p-4 [&>svg]:text-primary [&>blockquote]:mt-2 [&>blockquote]:text-sm [&>blockquote]:leading-7">
              <Quote aria-hidden="true" size={18} />
              <blockquote>{source.excerpt}</blockquote>
            </div>
            <dl className="mt-5 text-sm [&>div]:grid [&>div]:grid-cols-[72px_minmax(0,1fr)] [&>div]:gap-3 [&>div]:border-b [&>div]:border-divider [&>div]:py-3 [&_dt]:text-muted-foreground">
              <div>
                <dt>Section</dt>
                <dd>{source.section}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>Illustrative snapshot</dd>
              </div>
              <div>
                <dt>Captured</dt>
                <dd>Not captured — sample data</dd>
              </div>
            </dl>
            <div className="mt-5 [&>h4]:mb-1.5 [&>h4]:text-sm [&>p]:text-sm [&>p]:text-muted-foreground">
              <h4>Why this source</h4>
              <p>{source.note}</p>
            </div>
          </div>
        ) : (
          <div className="mt-8 text-muted-foreground [&>h3]:mt-4 [&>h3]:text-base [&>h3]:text-foreground [&>p]:mt-2 [&>p]:text-sm">
            <Quote aria-hidden="true" size={24} />
            <h3>Trace a claim to its source.</h3>
            <p>Choose a numbered citation in the answer, or a source above.</p>
          </div>
        )}
        <p className="mt-6 border-t border-divider pt-4 text-sm text-muted-foreground">
          These notes are authored examples for this preview. No documents have
          been imported or indexed.
        </p>
      </div>
    </section>
  );
}
