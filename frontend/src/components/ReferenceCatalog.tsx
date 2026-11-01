import { useState } from "react";
import { api, errorMessage } from "@/data/api";
import { Button } from "@/components/ui/button";

type Reference = { id: string; name: string; attribution: string; version_coverage: { description: string }; pages: { url: string; topics: string[] }[] };
export function ReferenceCatalog() {
  const [entries,setEntries]=useState<Reference[] | null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  async function load() {
    if(busy) return;
    setBusy(true); setError("");
    try { const result=await api<{ items:Reference[] }>("/catalog/references"); setEntries(result.items); }
    catch(error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <details onToggle={(event) => { if(event.currentTarget.open && !entries) void load(); }}>
    <summary className="cursor-pointer py-2">Browse official reference coverage</summary>
    <p className="py-3 text-muted-foreground">Verified publisher pages for the supported catalog topics. Rolling references are not automatic matches for an installed package version. Review version coverage before approving a source for your project.</p>
    {busy && <p role="status">Loading reference catalog…</p>}
    {error && <><p role="alert">{error}</p><Button variant="outline" onClick={load}>Reload reference catalog</Button></>}
    {entries?.map((entry) => <details key={entry.id} className="border-t border-input py-2"><summary className="cursor-pointer py-2">{entry.name}</summary><p className="py-2 text-muted-foreground">{entry.version_coverage.description}</p><p className="text-xs text-muted-foreground">{entry.attribution}</p><ul className="space-y-1">{entry.pages.map((page) => <li key={page.url}>{/^https:\/\//i.test(page.url) && <a className="block min-h-11 break-words py-2 text-primary underline" href={page.url} target="_blank" rel="noreferrer">{page.topics.join(", ")}</a>}</li>)}</ul></details>)}
  </details>;
}
