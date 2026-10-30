import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { ChevronDown, Folder, Layers3, MessageSquare, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plus, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Suggestions } from "@/components/agent-elements/suggestions";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { useMediaQuery } from "@/lib/use-media-query";
import { useTheme } from "@/lib/use-theme";
import { Composer } from "./Composer";
import { EvidenceInspector } from "./EvidenceInspector";
import { SampleConversation } from "./SampleConversation";
import { readView, viewHref } from "./sample";

export function Workbench() {
  const [view, setView] = useState(readView);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [provider, setProvider] = useState("Gemini");
  const [error, setError] = useState("");
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const [pendingDelta, setPendingDelta] = useState(0);
  const citationTrigger = useRef<HTMLElement | null>(null);
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLDivElement>(null);
  const historyPosition = useRef(0);
  const restoringPosition = useRef(false);
  const allowTraversal = useRef(false);
  const desktop = useMediaQuery("(min-width: 768px)");
  const { theme, preference, chooseTheme } = useTheme();
  const fresh = view.conversation === "new";

  useEffect(() => {
    historyPosition.current = history.state?.docweavePosition ?? 0;
    history.replaceState({ docweavePosition: historyPosition.current }, "");
  }, []);

  useEffect(() => {
    const update = () => {
      if (restoringPosition.current) {
        restoringPosition.current = false;
        return;
      }
      const next = readView();
      const position = history.state?.docweavePosition ?? historyPosition.current;
      const delta = position - historyPosition.current;
      if (draft && (next.conversation !== view.conversation || next.workspace !== view.workspace) && delta && !allowTraversal.current) {
        setPendingHref(location.href);
        setPendingDelta(delta);
        restoringPosition.current = true;
        history.go(-delta);
        return;
      }
      allowTraversal.current = false;
      historyPosition.current = position;
      setView(next);
      setError("");
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [draft, view.conversation, view.workspace]);

  useEffect(() => {
    if (!draft) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft]);

  function navigate(href: string) {
    history.pushState({ docweavePosition: ++historyPosition.current }, "", href);
    setView(readView());
    setError("");
  }

  function requestNavigate(href: string, reset = false) {
    const params = new URL(href, location.href).searchParams;
    if (draft && (reset || params.get("conversation") !== view.conversation || (params.get("workspace") ?? "engineering") !== view.workspace)) {
      setPendingDelta(0);
      setPendingHref(href);
    } else navigate(href);
  }

  function onNavigate(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (event.currentTarget.closest('article[aria-label="Example answer"]')) citationTrigger.current = event.currentTarget;
    requestNavigate(event.currentTarget.href);
    if (!desktop) setMobileSidebarOpen(false);
  }

  function startChat() {
    requestNavigate(viewHref("new", undefined, view.workspace), true);
    if (!desktop) setMobileSidebarOpen(false);
  }

  function closeSources() {
    navigate(viewHref(view.conversation, undefined, view.workspace));
  }

  const sidebar = (
    <div className="flex min-h-0 flex-1 flex-col gap-7 px-3 pb-5">
      <Button variant="outline" className="w-full justify-start rounded-lg bg-background" onClick={startChat}><Plus aria-hidden="true" />New chat</Button>
      <nav aria-label="Workspaces" className="space-y-2">
        <h2 className="px-3 text-xs font-medium text-muted-foreground">Workspaces</h2>
        <details open className="group">
          <summary className="flex items-center gap-2 rounded-lg px-3 text-sm hover:bg-accent">
            <Folder aria-hidden="true" size={16} />Engineering<ChevronDown aria-hidden="true" size={14} className="ml-auto group-open:rotate-180" />
          </summary>
          <a href={viewHref("sample")} onClick={onNavigate} aria-current={!fresh ? "page" : undefined}
            className="ml-6 flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground hover:bg-accent hover:text-foreground aria-[current]:bg-accent aria-[current]:text-primary">
            <MessageSquare aria-hidden="true" size={15} />Team files
          </a>
        </details>
        <details className="group">
          <summary className="flex items-center gap-2 rounded-lg px-3 text-sm hover:bg-accent">
            <Folder aria-hidden="true" size={16} />Personal<ChevronDown aria-hidden="true" size={14} className="ml-auto group-open:rotate-180" />
          </summary>
          <p className="ml-6 px-3 py-2 text-xs text-muted-foreground">No chats yet</p>
          <a href={viewHref("new", undefined, "personal")} onClick={onNavigate}
            aria-current={view.workspace === "personal" ? "page" : undefined}
            className="ml-6 flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground hover:bg-accent hover:text-foreground aria-[current]:bg-accent">
            <Plus aria-hidden="true" size={15} />Start a chat
          </a>
        </details>
      </nav>
      <nav aria-label="Recent chats" className="space-y-2">
        <h2 className="px-3 text-xs font-medium text-muted-foreground">Recent chats</h2>
        <a href={viewHref("sample")} onClick={onNavigate} aria-current={!fresh ? "page" : undefined}
          className="flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground hover:bg-accent hover:text-foreground aria-[current]:bg-accent aria-[current]:text-primary">
          <MessageSquare aria-hidden="true" size={15} />Team files
        </a>
      </nav>
      <p className="mt-auto px-3 text-xs text-muted-foreground">Example workspaces & chats</p>
    </div>
  );

  return (
    <div className="flex h-dvh min-h-0 bg-background">
      <a href="#main-content" className="fixed -top-24 left-4 z-[100] rounded-md border-2 border-primary bg-background px-4 py-3 text-primary focus:top-4">Skip to chat</a>
      {desktop && sidebarOpen && <aside id="chat-sidebar" aria-label="Chat sidebar" className="flex w-64 shrink-0 flex-col overflow-y-auto border-r border-divider bg-canvas">
        <div className="flex h-16 shrink-0 items-center gap-2 px-6 font-semibold"><Layers3 aria-hidden="true" size={21} className="text-primary" /><span translate="no">DocWeave</span></div>
        {sidebar}
      </aside>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 px-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <Button ref={sidebarToggle} variant="ghost" size="icon" aria-label={(desktop ? sidebarOpen : mobileSidebarOpen) ? "Hide sidebar" : "Show sidebar"}
              aria-expanded={desktop ? sidebarOpen : mobileSidebarOpen} aria-controls="chat-sidebar" onClick={() => desktop ? setSidebarOpen(!sidebarOpen) : setMobileSidebarOpen(!mobileSidebarOpen)}>
              {(desktop ? sidebarOpen : mobileSidebarOpen) ? <PanelLeftClose aria-hidden="true" /> : <PanelLeftOpen aria-hidden="true" />}
            </Button>
            <span className="truncate text-sm font-medium">{desktop && sidebarOpen ? (view.workspace === "personal" ? "Personal" : "Engineering") : "DocWeave"}</span>
          </div>
          <div className="flex items-center gap-1">
            {(!sidebarOpen || !desktop) && <Button variant="ghost" onClick={startChat}><Plus aria-hidden="true" /><span className="hidden sm:inline">New chat</span><span className="sr-only sm:hidden">New chat</span></Button>}
            <Button variant="ghost" size="icon" onClick={() => chooseTheme(theme === "dark" ? "light" : "dark")}
              aria-pressed={theme === "dark"} aria-label={theme === "dark" ? "Light mode" : "Dark mode"}>
              {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            </Button>
            {preference && <Button variant="ghost" size="icon" aria-label="Use device theme" onClick={() => chooseTheme(null)}><Monitor aria-hidden="true" /></Button>}
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 sm:px-8">
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
            <h1 className={fresh ? "sr-only" : "pt-6 text-xl"}>{fresh ? "New chat" : "Team files"}</h1>
            {fresh ? <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
              <span className="mb-2 grid size-12 place-items-center rounded-xl bg-accent text-primary"><Layers3 aria-hidden="true" size={26} /></span>
              <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">What can I help you with?</h2>
              <p className="text-sm text-muted-foreground">Ask a question about your project.</p>
              {!draft && <Suggestions items={[
                { id: "summarize", label: "Summarize my project" },
                { id: "start", label: "Help me get started" },
              ]} onSelect={(item) => { setDraft(item.label); input.current?.querySelector("textarea")?.focus(); }} />}
            </div> : <div className="flex-1"><SampleConversation citation={view.citation} onNavigate={onNavigate} /></div>}
            <div ref={input} className="sticky bottom-0 mt-4 bg-background pt-3">
              <Composer draft={draft} onDraft={setDraft} fresh={fresh} provider={provider} onProvider={setProvider} error={error} onSubmit={setError} />
            </div>
          </div>
        </main>
      </div>
      {!desktop && <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
        <SheetContent id="chat-sidebar" side="left" className="w-72 max-w-[90vw] gap-3 overflow-y-auto overscroll-contain bg-canvas pb-[env(safe-area-inset-bottom)]"
          onCloseAutoFocus={(event) => { event.preventDefault(); sidebarToggle.current?.focus(); }}>
          <SheetHeader><SheetTitle>Your chats</SheetTitle><SheetDescription>Workspaces & recent chats</SheetDescription></SheetHeader>
          {sidebar}
        </SheetContent>
      </Sheet>}
      <Sheet open={!!view.citation && !fresh} onOpenChange={(open) => { if (!open) closeSources(); }}>
        <SheetContent className="w-screen max-w-[100vw] gap-4 overscroll-contain pb-[env(safe-area-inset-bottom)] sm:w-[420px] sm:max-w-[420px]"
          onCloseAutoFocus={(event) => { event.preventDefault(); (citationTrigger.current?.isConnected ? citationTrigger.current : sidebarToggle.current)?.focus(); }}>
          <SheetHeader className="pr-14"><SheetTitle>Sources</SheetTitle><SheetDescription>Where this example answer comes from.</SheetDescription></SheetHeader>
          <EvidenceInspector citation={view.citation} onNavigate={onNavigate} />
        </SheetContent>
      </Sheet>
      <AlertDialog open={!!pendingHref} onOpenChange={(open) => { if (!open) setPendingHref(null); }}>
        <AlertDialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain">
          <AlertDialogHeader><AlertDialogTitle>Discard your message?</AlertDialogTitle><AlertDialogDescription>Your message hasn’t been sent. Starting or switching chats will discard it.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep writing</AlertDialogCancel>
            <AlertDialogAction onClick={() => {
              if (pendingHref) {
                setDraft("");
                if (pendingDelta) { allowTraversal.current = true; history.go(pendingDelta); }
                else navigate(pendingHref);
              }
              setPendingHref(null);
            }}>Discard draft</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
