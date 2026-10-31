import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/data/api";
type Processor = { id: string; provider: string; roles: string[] };
type Policy = { revision: number; processor_ids: string[]; available_processors: Processor[] };
export function ProcessingSettings({ project, csrf }: { project: string; csrf: string }) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<Policy>(`/projects/${project}/processing-policy`, undefined, undefined, controller.signal).then((value) => { setPolicy(value); setSelected(value.processor_ids); }).catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [project]);
  return <details className="rounded-lg border border-input p-4 text-sm"><summary className="cursor-pointer py-2">Processing permissions</summary>
    <p className="my-3 text-muted-foreground">Choose which configured services may process this project's private context, questions, and documents. Public documentation is indexed separately.</p>
    {error && <p role="alert">{error}</p>}
    {policy?.available_processors.map((processor) => <label className="flex min-h-11 items-center gap-3" key={processor.id}><input type="checkbox" checked={selected.includes(processor.id)} onChange={(event) => setSelected((values) => event.target.checked ? [...values, processor.id] : values.filter((id) => id !== processor.id))} /><span>{processor.provider} · {processor.roles.join(", ")}</span></label>)}
    {policy && !policy.available_processors.length && <p className="py-3">No verified processing services are configured yet.</p>}
    {policy && <Button variant="outline" disabled={busy} onClick={async () => { setBusy(true); setError(""); setStatus(""); try { const next = await api<Omit<Policy, "available_processors">>(`/projects/${project}/processing-policy`, { expected_revision: policy.revision, approved_processor_ids: selected }, csrf, undefined, "PUT"); setPolicy({ ...policy, ...next }); setStatus("Processing permissions saved."); } catch (error) { setError(errorMessage(error)); } finally { setBusy(false); } }}>{busy ? "Saving…" : "Save permissions"}</Button>}
    {status && <p role="status" className="pt-2">{status}</p>}
  </details>;
}
