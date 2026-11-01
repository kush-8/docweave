import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/data/api";

type Candidate = { source_url: string; attribution: string; candidate_token: string };
export function DiscoverSource({ project, dependency, technology, target, revision, csrf, onSaved }: { project: string; dependency: string; technology: string; target?: string; revision: number; csrf: string; onSaved: () => void }) {
  const [consent, setConsent] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/projects/${encodeURIComponent(project)}/documentation/${encodeURIComponent(dependency)}`;
  return <details className="space-y-3 text-sm"><summary className="cursor-pointer py-2">Find another source</summary>
    <p className="text-muted-foreground">Publisher links are suggestions. Review the source and its actual version coverage before adding it to this project. Processing permissions still apply.</p>
    {!target ? <p>Resolve this dependency’s version in repository metadata before looking it up.</p> : <>
      <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" checked={consent} disabled={busy} onChange={(event) => setConsent(event.target.checked)} /><span>Send {technology} {target} to its public package registry</span></label>
      <Button variant="outline" disabled={!consent || busy} onClick={async () => { setBusy(true); setError(""); setCandidates(null); try { const result = await api<{ items: Candidate[] }>(`${path}/discover`, { expected_revision: revision, allow_public_lookup: true }, csrf); setCandidates(result.items); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } }}>Find publisher sources</Button>
      {candidates?.length === 0 && <p>No safe publisher link was found for this version. No source was imported.</p>}
      {candidates?.map((candidate) => <PrivateApproval key={candidate.candidate_token} candidate={candidate} path={path} technology={technology} target={target} revision={revision} csrf={csrf} onSaved={onSaved} />)}
    </>}
    {error && <p role="alert">{error}</p>}
  </details>;
}

function PrivateApproval({ candidate, path, technology, target, revision, csrf, onSaved }: { candidate: Candidate; path: string; technology: string; target: string; revision: number; csrf: string; onSaved: () => void }) {
  const [granularity, setGranularity] = useState("");
  const [version, setVersion] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [fallback, setFallback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <div className="space-y-3 border-l-2 border-input pl-3">
    <p className="text-muted-foreground">{candidate.attribution}</p>
    {/^https:\/\//i.test(candidate.source_url) && <a className="block min-h-11 break-all py-2 text-primary underline" href={candidate.source_url} target="_blank" rel="noreferrer">Review publisher documentation</a>}
    <p className="break-all text-xs text-muted-foreground">{candidate.source_url}</p>
    <label className="block">Actual documentation coverage<select className="mt-1 block min-h-11 w-full rounded-md border border-input bg-background px-3" value={granularity} onChange={(event) => { setGranularity(event.target.value); setReviewed(false); setFallback(false); }}><option value="">Choose after reviewing the publisher page</option><option value="exact">Exact release</option><option value="major">Major version</option><option value="minor">Minor version</option></select></label>
    <label className="block">Documented version<input className="mt-1 block min-h-11 w-full rounded-md border border-input bg-background px-3" maxLength={100} value={version} onChange={(event) => { setVersion(event.target.value); setReviewed(false); setFallback(false); }} /></label>
    <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span>I reviewed this publisher source and its version coverage</span></label>
    {granularity && granularity !== "exact" && <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" checked={fallback} onChange={(event) => setFallback(event.target.checked)} /><span>I accept broader documentation for {technology} {target}</span></label>}
    <Button variant="outline" disabled={busy || !reviewed || !granularity || !version.trim() || (granularity !== "exact" && !fallback)} onClick={async () => { setBusy(true); setError(""); try { await api(`${path}/review-source`, { expected_revision: revision, candidate_token: candidate.candidate_token, coverage: { granularity, version: version.trim() }, accept_fallback: fallback }, csrf); onSaved(); } catch (error) { setError(`${errorMessage(error)} A source proposal expires after ten minutes; discover again if needed.`); } finally { setBusy(false); } }}>Approve for this project</Button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
