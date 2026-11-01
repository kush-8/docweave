import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/data/api";
import { DiscoverSource } from "@/components/DiscoverSource";
import { ReferenceCatalog } from "@/components/ReferenceCatalog";

type Entry = { revision_id: string; source_url: string; attribution: string; source_approved?: boolean; progress?: string | null; coverage: { granularity: string; version: string } };
type Match = { status: string; reason: string; entry?: Entry | null };
type Dependency = Match & { dependency_id: string; technology: string; docs_target?: string; selected_revision_id?: string; candidates: Match[] };
type Coverage = { context_revision: number; items: Dependency[] };
const labels: Record<string, string> = { ready: "Ready", waiting_for_sources: "Preparing documentation", missing: "Documentation missing", pending_review: "Approval required", capacity: "Waiting for capacity", failed: "Documentation processing failed", consent_required: "Processing permission required" };
const reasons: Record<string, string> = {
  "version fallback approval required": "Version fallback approval required. Review the broader version below.",
  "unknown documentation version": "The repository did not establish a documentation version. Correct its dependency metadata and retry repository sync.",
  "no eligible matching version coverage": "No matching version is available. The operator can review a publisher source for the catalog.",
  "no active indexing work": "This source has no active indexing work. Select it to request preparation.",
  "documentation selection removed": "You removed this documentation selection. Choose a source below to use it again.",
};

export function DocumentationReview({ project, contextRevision, csrf }: { project: string; contextRevision?: number; csrf: string }) {
  const [open, setOpen] = useState(false);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const path = `/projects/${encodeURIComponent(project)}/documentation`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await api<Coverage>(path, undefined, undefined, controller.signal);
        if (controller.signal.aborted) return;
        setCoverage(next); setError("");
        if (next.items.some((item) => item.status === "waiting_for_sources")) timer = setTimeout(refresh, 1500);
      } catch (error) { if (!controller.signal.aborted) { setCoverage(null); setError(errorMessage(error)); } }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [open, path, contextRevision, reload]);

  async function choose(dependency: string, revision?: string, fallback = false) {
    if (!coverage || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const next = await api<Coverage>(`${path}/${encodeURIComponent(dependency)}`, { expected_revision: coverage.context_revision, ...(revision ? { revision_id: revision } : {}), accept_fallback: fallback }, csrf, undefined, "PUT");
      setCoverage(next); setNotice(revision ? "Documentation selection saved." : "Documentation selection removed.");
      setReload((value) => value + 1);
    } catch (error) { setError(`${errorMessage(error)} Reload documentation before making another choice.`); setCoverage(null); }
    finally { setBusy(false); }
  }

  return <details className="mb-4 rounded-lg border border-input p-4 text-sm" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer py-2">Project documentation</summary>
    {open && <div className="space-y-4 pt-3">
      <p className="text-muted-foreground">Review the available sources and their version coverage. Shared sources need operator approval; accepting a broader version applies only to this project version.</p>
      <Button variant="outline" disabled={busy} onClick={() => setReload((value) => value + 1)}>Reload documentation</Button>
      <ReferenceCatalog />
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!coverage && !error && <p role="status">Loading documentation coverage…</p>}
      {coverage && !coverage.items.length && <p>No dependencies have been detected yet. Start a chat to check the repository.</p>}
      {coverage?.items.map((item) => <section key={item.dependency_id} aria-label={`${item.technology} documentation`} className="space-y-3 border-t border-input pt-4">
        <h2 className="font-medium">{item.technology} {item.docs_target ?? "· Version unresolved"}</h2>
        <p role="status">{labels[item.status] ?? "Documentation unavailable"}</p>
        {item.status === "waiting_for_sources" && item.entry?.progress && <p role="status" className="text-muted-foreground">{item.entry.progress}</p>}
        {reasons[item.reason] && <p className="text-muted-foreground">{reasons[item.reason]}</p>}
        {item.status === "capacity" && <p className="text-muted-foreground">The operator needs to configure an eligible index generation, embedding profile, or processing capacity. This source is not actively indexing.</p>}
        {item.status === "failed" && <p className="text-muted-foreground">Processing stopped. The operator must inspect the failed source; your question will not be replayed automatically.</p>}
        {item.candidates.map((candidate) => candidate.entry && <SourceChoice key={`${candidate.entry.revision_id}:${coverage.context_revision}`} dependency={item} candidate={candidate} busy={busy} onChoose={choose} />)}
        {item.selected_revision_id && <Button variant="outline" disabled={busy} onClick={() => void choose(item.dependency_id)}>Remove selection</Button>}
        <DiscoverSource key={`${item.dependency_id}:${coverage.context_revision}`} project={project} dependency={item.dependency_id} technology={item.technology} target={item.docs_target} revision={coverage.context_revision} csrf={csrf} onSaved={() => { setNotice("Private source approved and queued for preparation."); setReload((value) => value + 1); }} />
      </section>)}
    </div>}
  </details>;
}

function SourceChoice({ dependency, candidate, busy, onChoose }: { dependency: Dependency; candidate: Match; busy: boolean; onChoose: (dependency: string, revision: string, fallback: boolean) => Promise<void> }) {
  const [accepted, setAccepted] = useState(false);
  const entry = candidate.entry!;
  const fallback = entry.coverage.granularity !== "exact";
  const selected = dependency.selected_revision_id === entry.revision_id && candidate.reason !== "version fallback approval required";
  return <div className="space-y-2 pl-3 border-l-2 border-input">
    <p>{entry.coverage.granularity} {entry.coverage.version} coverage{selected ? " · Selected" : ""}</p>
    <p className="text-muted-foreground">{entry.attribution}</p>
    {/^https:\/\//i.test(entry.source_url) && <a className="block min-h-11 break-all py-2 text-primary underline" href={entry.source_url} target="_blank" rel="noreferrer">Review source: {entry.source_url}</a>}
    {entry.source_approved === false || candidate.reason === "source approval required" ? <p>Operator source approval required</p> : !selected && <>
      {fallback && <label className="flex min-h-11 items-start gap-3 py-2"><input className="mt-1" type="checkbox" checked={accepted} disabled={busy} onChange={(event) => setAccepted(event.target.checked)} /><span>I accept {entry.coverage.granularity} {entry.coverage.version} documentation for {dependency.technology} {dependency.docs_target}</span></label>}
      <Button variant="outline" disabled={busy || (fallback && !accepted)} onClick={() => void onChoose(dependency.dependency_id, entry.revision_id, fallback)}>Use this documentation</Button>
    </>}
  </div>;
}
