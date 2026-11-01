import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { Composer } from "@/components/Composer";
import { DiscardDraftDialog } from "@/components/DiscardDraftDialog";
import { ProcessingSettings } from "@/components/ProcessingSettings";
import { DocumentationReview } from "@/components/DocumentationReview";
import { ProjectSetup } from "@/components/ProjectSetup";
import { Welcome } from "@/components/Welcome";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, allItems, ApiError, errorMessage, statusLabel } from "@/data/api";
import type { Project, Conversation, Turn, Profile } from "@/data/api";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTheme } from "@/hooks/use-theme";
import { useWorkbenchNavigation } from "@/hooks/useWorkbenchNavigation";
import { WorkbenchHeader } from "@/layouts/WorkbenchHeader";
import { WorkbenchLayout } from "@/layouts/WorkbenchLayout";
import { WorkbenchSidebar } from "@/layouts/WorkbenchSidebar";
import { viewHref } from "@/routing/workbench";

const activeStatuses = new Set(["waiting_for_sources", "queued", "running"]);
export function WorkbenchPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [provider, setProvider] = useState("");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState("");
  const [session, setSession] = useState<{ display_name: string; csrf_token: string } | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [recent, setRecent] = useState<{ id: string; project: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [logoutRequested, setLogoutRequested] = useState(false);
  const [evidence, setEvidence] = useState<{ title: string; excerpt: string; url?: string } | null>(null);
  const [evidenceError, setEvidenceError] = useState("");
  const [revisionNotice, setRevisionNotice] = useState("");
  const [reload, setReload] = useState(0);
  const sessionEpoch = useRef(0);
  const requestKey = useRef<{ message: string; id: string } | null>(null);
  const lastRevision = useRef<number | undefined>(undefined);
  const citationTrigger = useRef<HTMLElement | null>(null);
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLDivElement>(null);
  const desktop = useMediaQuery("(min-width: 768px)");
  const { theme, preference, chooseTheme } = useTheme();
  const clearError = useCallback(() => setError(""), []);
  const { view, navigate, requestNavigate, pending, cancelNavigation, discardNavigation } = useWorkbenchNavigation(draft, clearError);
  const fresh = view.conversation === "new";
  const currentChat = useRef(view.conversation);
  const currentDraft = useRef(draft);
  useEffect(() => { currentChat.current = view.conversation; currentDraft.current = draft; }, [view.conversation, draft]);
  const path = `/projects/${encodeURIComponent(view.project)}`;

  function clearPrivateData() {
    sessionEpoch.current += 1;
    setSession(null); setProjects([]); setProject(null); setConversation(null); setTurns([]); setRecent([]); setEvidence(null); setProfiles([]); setProvider(""); setDraft(""); requestKey.current = null;
  }

  function showError(error: unknown) {
    setError(errorMessage(error));
    if (error instanceof ApiError && error.status === 401) { clearPrivateData(); setSignedOut(true); }
  }

  async function logout() {
    if (!session || busy) return;
    setBusy(true);
    try {
      await api<void>("/auth/logout", {}, session.csrf_token);
      clearPrivateData(); setSignedOut(true); setLogoutRequested(false); navigate(viewHref("new"));
    } catch (error) { setLogoutRequested(false); showError(error); }
    finally { setBusy(false); }
  }

  useEffect(() => { requestKey.current = null; lastRevision.current = undefined; }, [view.project, view.conversation]);

  useEffect(() => {
    const controller = new AbortController();
    const epoch = sessionEpoch.current;
    (async () => {
      try {
        const user = await api<{ display_name: string; csrf_token: string }>("/me", undefined, undefined, controller.signal);
        if (controller.signal.aborted || epoch !== sessionEpoch.current) return;
        setSession(user); setSignedOut(false);
        const [items, configured] = await Promise.all([allItems<Project>("/projects", controller.signal), allItems<Profile>("/providers", controller.signal)]);
        if (controller.signal.aborted || epoch !== sessionEpoch.current) return;
        setProjects(items); setProfiles(configured.filter((profile) => profile.enabled !== false)); setError("");
      } catch (error) { if (!controller.signal.aborted) showError(error); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => controller.abort();
  }, [reload]);

  useEffect(() => {
    // Clear the previous authorized chat while its replacement loads.
    // oxlint-disable-next-line react/set-state-in-effect
    setProject(null); setConversation(null); setTurns([]); setRevisionNotice("");
    if (!session || !view.project) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const current = await api<Project>(path, undefined, undefined, controller.signal);
        const chats = await allItems<Conversation & { name?: string }>(`${path}/conversations`, controller.signal);
        if (controller.signal.aborted) return;
        setRecent((items) => [...items.filter((item) => item.project !== current.id), ...chats.map((chat) => ({ id: chat.id, project: current.id, name: chat.name ?? current.name }))]);
        if (lastRevision.current !== undefined && lastRevision.current !== current.context_revision) setRevisionNotice("Project context changed. Your next answer will use the latest successful context; earlier answers retain their original context.");
        lastRevision.current = current.context_revision;
        setProject(current);
        if (!fresh) {
          const chat = await api<Conversation>(`/conversations/${encodeURIComponent(view.conversation)}`, undefined, undefined, controller.signal);
          const items = await allItems<Turn>(`/conversations/${encodeURIComponent(view.conversation)}/turns`, controller.signal);
          const updated = await Promise.all(items.map((turn) => activeStatuses.has(turn.status) ? api<Turn>(`/turns/${encodeURIComponent(turn.id)}`, undefined, undefined, controller.signal).then((result) => ({ ...turn, ...result })) : turn));
          if (updated.some((turn) => turn.context_revision !== undefined && turn.context_revision !== current.context_revision)) setRevisionNotice("Project context changed. Your next answer will use the latest successful context; earlier answers retain their original context.");
          if (controller.signal.aborted) return;
          setConversation(chat); setTurns(updated);
          if (chat.status === "initializing" || updated.some((turn) => activeStatuses.has(turn.status))) timer = setTimeout(refresh, 1500);
        }
      } catch (error) { if (!controller.signal.aborted) showError(error); }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [session, view.project, view.conversation, path, fresh, reload]);

  useEffect(() => {
    // Never show an old excerpt while another citation is being authorized.
    // oxlint-disable-next-line react/set-state-in-effect
    setEvidence(null); setEvidenceError("");
    if (!view.turn || !view.citation || fresh || !session) return;
    const controller = new AbortController();
    api<{ title: string; excerpt: string; url?: string }>(`/turns/${encodeURIComponent(view.turn)}/citations/${encodeURIComponent(view.citation)}`, undefined, undefined, controller.signal).then((value) => { if (!controller.signal.aborted) setEvidence(value); }).catch((error) => { if (!controller.signal.aborted) setEvidenceError(errorMessage(error)); });
    return () => controller.abort();
  }, [view.turn, view.citation, fresh, session]);

  function onNavigate(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); citationTrigger.current = event.currentTarget;
    requestNavigate(event.currentTarget.href);
    if (!desktop) setMobileSidebarOpen(false);
  }
  function startChat() { requestNavigate(viewHref("new", undefined, view.project), true); if (!desktop) setMobileSidebarOpen(false); }
  async function createChat() {
    if (!session || !project || busy) return;
    setBusy(true); setError("");
    try {
      const chat = await api<Conversation>(`${path}/conversations`, provider ? { answer_profile_id: provider } : {}, session.csrf_token);
      setRecent((items) => [{ id: chat.id, project: project.id, name: project.name }, ...items.filter((item) => item.id !== chat.id)]);
      navigate(viewHref(chat.id, undefined, project.id));
    } catch (error) { showError(error); }
    finally { setBusy(false); }
  }
  async function retrySync() {
    if (!session || !conversation || busy) return;
    const chatId = view.conversation;
    setBusy(true); setError("");
    try {
      const chat = await api<Conversation>(`/conversations/${encodeURIComponent(chatId)}/sync-retry`, {}, session.csrf_token);
      if (currentChat.current !== chatId) return;
      setConversation(chat); setReload((value) => value + 1);
    } catch (error) { if (currentChat.current === chatId) showError(error); }
    finally { setBusy(false); }
  }
  async function send() {
    if (!draft.trim()) { setError("Write a message first."); return; }
    if (!session || !conversation || conversation.status !== "ready" || busy) return;
    setBusy(true); setError("");
    const message = draft.trim();
    const chatId = view.conversation;
    if (requestKey.current?.message !== message) requestKey.current = { message, id: crypto.randomUUID() };
    try {
      await api<Turn>(`/conversations/${encodeURIComponent(view.conversation)}/turns`, { message, idempotency_key: requestKey.current.id }, session.csrf_token);
      if (currentChat.current !== chatId) return;
      if (currentDraft.current.trim() === message) setDraft("");
      requestKey.current = null; setReload((value) => value + 1);
    } catch (error) { if (currentChat.current !== chatId) return; if (error instanceof ApiError && error.status === 401) showError(error); else setError(`${errorMessage(error)} Your draft is preserved. Retrying the same message uses the same request key.`); }
    finally { setBusy(false); }
  }
  const active = turns.some((turn) => activeStatuses.has(turn.status));
  const unsafeToReplay = turns.some((turn) => turn.status === "completion_unknown");
  return <>
    <WorkbenchLayout desktop={desktop} sidebarOpen={sidebarOpen} mobileSidebarOpen={mobileSidebarOpen} onMobileSidebarOpen={setMobileSidebarOpen} sidebarToggle={sidebarToggle}
      sidebar={<WorkbenchSidebar view={view} projects={projects} conversations={recent} onNavigate={onNavigate} onStartChat={startChat} />}
      header={<WorkbenchHeader desktop={desktop} sidebarOpen={sidebarOpen} mobileSidebarOpen={mobileSidebarOpen} sidebarToggle={sidebarToggle} projectName={project?.name ?? ""} theme={theme} preference={preference} onToggleSidebar={() => desktop ? setSidebarOpen(!sidebarOpen) : setMobileSidebarOpen(!mobileSidebarOpen)} onStartChat={startChat} onTheme={chooseTheme} />}>
      {session && <div className="flex items-center justify-between gap-3 py-2 text-sm text-muted-foreground"><span className="truncate">{session.display_name}</span><Button variant="ghost" disabled={busy} onClick={() => draft ? setLogoutRequested(true) : void logout()}>Sign out</Button></div>}
      {error && (fresh || !project?.repository || !conversation) && <div className="space-y-2 py-4"><p role="alert" className="text-destructive">{error}</p><Button variant="outline" onClick={() => setReload((value) => value + 1)}>Retry connection</Button></div>}
      {loading && !session ? <p role="status" className="py-10">Connecting…</p> : !session ? <div className="my-auto space-y-4 py-10"><h1 className="text-2xl">Your projects, with the right documentation</h1><p>{signedOut ? "Sign in to choose your GitHub repositories and start a project." : "Connect to the DocWeave API to load your projects."}</p><a className="inline-flex min-h-11 items-center rounded-md border border-input px-4" href="/api/v1/auth/login">Sign in with GitHub</a></div> : !view.project ? <ProjectSetup csrf={session.csrf_token} onCreated={(item) => { setProjects((items) => [...items.filter((previous) => previous.id !== item.id), item]); navigate(viewHref("new", undefined, item.id)); }} /> : !project ? <p role="status" className="py-10">Loading project…</p> : !project.repository ? <ProjectSetup key={project.id} project={project} csrf={session.csrf_token} onCreated={(item) => { setProject(item); setReload((value) => value + 1); }} /> : <>
        <div className="space-y-2 py-5"><h1 className="text-xl">{project.name}</h1><p className="text-sm text-muted-foreground">{project.goal}</p><p className="break-all text-xs text-muted-foreground">{project.repository.branch} · {project.repository.application_path || "Repository root"}{project.repository.commit_sha ? ` · ${project.repository.commit_sha.slice(0, 12)}` : ""} · Context {project.context_revision ?? "pending"}</p><p className="text-xs text-muted-foreground">Repository: {statusLabel(project.sync_state ?? "pending")} · Documentation: {statusLabel(project.docs_state ?? "pending")}</p></div>
        {project.stack && project.stack.length > 0 && <ul aria-label="Project stack" className="flex flex-wrap gap-2 pb-3 text-xs text-muted-foreground">{project.stack.map((dependency, index) => <li key={`${dependency.technology}-${index}`} className="rounded-md border border-input px-2 py-1">{dependency.technology}{dependency.resolved_version ? ` ${dependency.resolved_version}` : dependency.declared_version ? ` ${dependency.declared_version}` : ""}{dependency.docs_target ? ` · Docs: ${dependency.docs_target}` : " · Documentation coverage pending"}</li>)}</ul>}
        <DocumentationReview key={project.id} project={project.id} contextRevision={project.context_revision} csrf={session.csrf_token} />
        {revisionNotice && <p role="status" className="rounded-md border border-input p-3 text-sm">{revisionNotice}</p>}
        {fresh ? <div className="my-auto space-y-5 py-8"><ProcessingSettings project={project.id} csrf={session.csrf_token} /><h2 className="text-2xl">Start a new chat</h2><p>Check the current branch and prepare your project’s documentation.</p>{profiles.length > 0 && <label className="block">Model<select className="ml-3 min-h-11 rounded-md border border-input bg-background px-3" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="">Server default</option>{profiles.map((item) => <option key={item.id} value={item.id}>{item.display_name ?? item.name ?? ([item.provider, item.model].filter(Boolean).join(" · ") || item.id)}</option>)}</select></label>}<Button disabled={busy} onClick={createChat}>{busy ? "Starting…" : "Start chat"}</Button></div> : <>
          {!conversation && <p role="status">Loading chat…</p>}
          {conversation?.status === "initializing" && <p role="status">Checking the repository and preparing project context…</p>}
          {conversation?.status === "blocked" && <div className="space-y-3"><p role="status">{conversation.progress ?? "Repository synchronization is blocked. Check GitHub access and dependency metadata, then retry."}</p><Button variant="outline" disabled={busy} onClick={retrySync}>{busy ? "Queuing retry…" : "Retry repository sync"}</Button></div>}
          {conversation?.status === "ready" && !turns.length && <Welcome draft={draft} onSuggestion={(text) => { setDraft(text); input.current?.querySelector("textarea")?.focus(); }} />}
          <div className="flex-1 space-y-8 py-5">{turns.map((turn) => <div key={turn.id} className="space-y-4"><article aria-label="Your message" className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl bg-canvas px-5 py-3">{turn.message}</article><article aria-label="DocWeave answer" className="space-y-3"><p className="whitespace-pre-wrap break-words leading-7">{turn.answer}</p>{turn.status !== "completed" && <p role="status" className="text-sm text-muted-foreground">{turn.status === "waiting_for_sources" ? (turn.progress ?? "Waiting for required documentation. This question will resume automatically when its sources are searchable.") : turn.status === "completion_unknown" ? "The provider result is uncertain. This question will not be replayed automatically." : turn.progress ?? statusLabel(turn.status)}</p>}<div className="flex flex-wrap gap-2">{turn.citations?.map((citation) => <a key={citation.id} className="inline-flex min-h-11 items-center rounded-md border border-input px-3 text-sm text-primary" href={viewHref(view.conversation, citation.id, view.project, turn.id)} onClick={onNavigate}>Source: {citation.title}</a>)}</div></article></div>)}</div>
          <div ref={input} className="sticky bottom-0 mt-4 bg-background pt-3"><Composer draft={draft} onDraft={setDraft} fresh={!turns.length} provider={provider} onProvider={setProvider} profiles={[]} error={conversation ? error : ""} disabled={busy || active || unsafeToReplay || conversation?.status !== "ready"} onSubmit={send} onClearError={clearError} />{error && conversation && <Button variant="outline" className="mb-4" onClick={() => setReload((value) => value + 1)}>Retry connection</Button>}</div>
        </>}
      </>}
    </WorkbenchLayout>
    <Sheet open={!!view.citation && !!view.turn && !fresh && !!session} onOpenChange={(open) => { if (!open) navigate(viewHref(view.conversation, undefined, view.project)); }}><SheetContent className="w-screen max-w-[100vw] gap-4 overscroll-contain pb-[env(safe-area-inset-bottom)] sm:w-[420px] sm:max-w-[420px]" onCloseAutoFocus={(event) => { event.preventDefault(); (citationTrigger.current?.isConnected ? citationTrigger.current : sidebarToggle.current)?.focus(); }}><SheetHeader className="pr-14"><SheetTitle>Sources</SheetTitle><SheetDescription>Authorized evidence for this answer.</SheetDescription></SheetHeader><section aria-label="Source details" className="space-y-4 overflow-y-auto px-5 pb-6">{evidenceError ? <p role="alert">{evidenceError}</p> : evidence ? <><h3 className="text-lg">{evidence.title}</h3><blockquote className="whitespace-pre-wrap border-l-2 border-primary pl-4 leading-7">{evidence.excerpt}</blockquote>{evidence.url && /^https?:\/\//i.test(evidence.url) && <a className="inline-flex min-h-11 items-center text-primary underline" href={evidence.url} target="_blank" rel="noreferrer">Open documentation</a>}</> : <p role="status">Loading evidence…</p>}</section></SheetContent></Sheet>
    <DiscardDraftDialog open={pending || logoutRequested} onCancel={() => { setLogoutRequested(false); cancelNavigation(); }} onDiscard={() => { if (logoutRequested) void logout(); else { setDraft(""); discardNavigation(); } }} />
  </>;
}
