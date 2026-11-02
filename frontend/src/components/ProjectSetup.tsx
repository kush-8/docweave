import { useEffect, useState } from "react";
import { api, allItems, errorMessage } from "@/data/api";
import type { Project } from "@/data/api";
import { Button } from "@/components/ui/button";
type Repository = { id: number; full_name: string; default_branch: string };
export function ProjectSetup({ csrf, onCreated, project }: { csrf: string; onCreated: (project: Project) => void; project?: Project }) {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repository, setRepository] = useState("");
  const [branches, setBranches] = useState<{ name: string }[]>([]);
  const [branch, setBranch] = useState("");
  const [goal, setGoal] = useState(project?.goal ?? "");
  const [folder, setFolder] = useState("");
  const [notes, setNotes] = useState("");
  const [constraints, setConstraints] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    allItems<Repository>("/connections/github/repositories", controller.signal).then(setRepositories).catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!repository) return;
    const controller = new AbortController();
    allItems<{ name: string }>(`/connections/github/repositories/${repository}/branches`, controller.signal).then(setBranches).catch((error) => { if (!controller.signal.aborted) setError(errorMessage(error)); });
    return () => controller.abort();
  }, [repository]);
  const fieldClass = "min-h-11 w-full rounded-md border border-input bg-background px-3 py-2";
  return <form className="my-auto space-y-5 py-10" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try { onCreated(await api<Project>(project ? `/projects/${project.id}/repository` : "/projects", { repository_id: Number(repository), branch, application_path: folder, goal, ...(notes ? { architecture_notes: notes } : {}), ...(constraints ? { constraints } : {}) }, csrf)); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }}>
    <h1 className="text-2xl">{project ? "Connect this project to GitHub" : "Create a project"}</h1>
    <p className="text-sm text-muted-foreground">Choose a repository available to your GitHub App. DocWeave checks its stack when you start a chat.</p>
    <div className="space-y-2"><label htmlFor="repository" className="block">Repository</label><select id="repository" required className={fieldClass} value={repository} onChange={(event) => { setBranches([]); setRepository(event.target.value); setBranch(repositories.find((item) => String(item.id) === event.target.value)?.default_branch ?? ""); }}><option value="">Choose repository</option>{repositories.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></div>
    <div className="space-y-2"><label htmlFor="branch" className="block">Branch</label><select id="branch" required className={fieldClass} value={branch} disabled={!branches.length} onChange={(event) => setBranch(event.target.value)}><option value="">Choose branch</option>{branches.map((item) => <option key={item.name}>{item.name}</option>)}</select></div>
    <label className="block space-y-2">Application folder (optional)<input className={fieldClass} value={folder} placeholder="Repository root" onChange={(event) => setFolder(event.target.value)} /></label>
    <p className="text-xs text-muted-foreground">Leave blank to discover apps across the repository, or choose a folder to limit discovery.</p>
    <label className="block space-y-2">Project goal<input required maxLength={500} className={fieldClass} value={goal} onChange={(event) => setGoal(event.target.value)} /></label>
    <details className="space-y-3"><summary className="flex min-h-11 cursor-pointer items-center">Optional notes and constraints</summary><label className="block space-y-2">Architecture notes<textarea className={fieldClass} maxLength={10000} value={notes} onChange={(event) => setNotes(event.target.value)} /></label><label className="block space-y-2">Constraints<textarea className={fieldClass} maxLength={10000} value={constraints} onChange={(event) => setConstraints(event.target.value)} /></label></details>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {!repositories.length && !error && <p role="status">Loading repositories…</p>}
    <Button disabled={busy || !branch || !branches.length}>{busy ? "Saving…" : project ? "Connect repository" : "Create project"}</Button>
  </form>;
}

