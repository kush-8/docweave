import { useEffect, useRef } from "react";
import type { MouseEvent } from "react";
import { sampleSources, viewHref } from "./sample";

type Props = { citation: string | null; onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void };

export function EvidenceInspector({ citation, onNavigate }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  const source = sampleSources.find((item) => item.id === citation);
  useEffect(() => {
    if (!source) return;
    const frame = requestAnimationFrame(() => heading.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [source]);

  return (
    <section aria-label="Source details" className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-6">
      <nav aria-label="Sources in this answer" className="mb-6 flex flex-col gap-2">
        {sampleSources.map((item) => (
          <a key={item.id} href={viewHref("sample", item.id)} onClick={onNavigate}
            aria-label={`Source ${item.id}: ${item.title}`} aria-current={citation === item.id ? "location" : undefined}
            className="flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-accent aria-[current]:bg-accent aria-[current]:text-primary">
            <span className="font-semibold tabular-nums">{item.id}</span>{item.title}
          </a>
        ))}
      </nav>
      {source && <div className="space-y-4 border-t border-divider pt-6">
        <h3 ref={heading} tabIndex={-1} className="text-lg">{source.title}</h3>
        <blockquote className="border-l-2 border-primary pl-4 leading-7">{source.excerpt}</blockquote>
      </div>}
      <p className="mt-8 text-sm text-muted-foreground">Example sources for this preview.</p>
    </section>
  );
}
