import { useCallback, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { Composer } from "@/components/Composer";
import { DiscardDraftDialog } from "@/components/DiscardDraftDialog";
import { EvidenceInspector } from "@/components/EvidenceInspector";
import { SampleConversation } from "@/components/SampleConversation";
import { Welcome } from "@/components/Welcome";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTheme } from "@/hooks/use-theme";
import { useWorkbenchNavigation } from "@/hooks/useWorkbenchNavigation";
import { WorkbenchHeader } from "@/layouts/WorkbenchHeader";
import { WorkbenchLayout } from "@/layouts/WorkbenchLayout";
import { WorkbenchSidebar } from "@/layouts/WorkbenchSidebar";
import { viewHref } from "@/routing/workbench";

export function WorkbenchPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [provider, setProvider] = useState("Gemini");
  const [error, setError] = useState("");
  const citationTrigger = useRef<HTMLElement | null>(null);
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLDivElement>(null);
  const desktop = useMediaQuery("(min-width: 768px)");
  const { theme, preference, chooseTheme } = useTheme();
  const clearError = useCallback(() => setError(""), []);
  const { view, navigate, requestNavigate, pending, cancelNavigation, discardNavigation } = useWorkbenchNavigation(draft, clearError);
  const fresh = view.conversation === "new";

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

  return (
    <>
      <WorkbenchLayout desktop={desktop} sidebarOpen={sidebarOpen} mobileSidebarOpen={mobileSidebarOpen}
        onMobileSidebarOpen={setMobileSidebarOpen} sidebarToggle={sidebarToggle}
        sidebar={<WorkbenchSidebar view={view} onNavigate={onNavigate} onStartChat={startChat} />}
        header={<WorkbenchHeader desktop={desktop} sidebarOpen={sidebarOpen} mobileSidebarOpen={mobileSidebarOpen}
          sidebarToggle={sidebarToggle} workspace={view.workspace} theme={theme} preference={preference}
          onToggleSidebar={() => desktop ? setSidebarOpen(!sidebarOpen) : setMobileSidebarOpen(!mobileSidebarOpen)}
          onStartChat={startChat} onTheme={chooseTheme} />}>
        <h1 className={fresh ? "sr-only" : "pt-6 text-xl"}>{fresh ? "New chat" : "Team files"}</h1>
        {fresh ? <Welcome draft={draft} onSuggestion={(text) => { setDraft(text); input.current?.querySelector("textarea")?.focus(); }} />
          : <div className="flex-1"><SampleConversation citation={view.citation} onNavigate={onNavigate} /></div>}
        <div ref={input} className="sticky bottom-0 mt-4 bg-background pt-3">
          <Composer draft={draft} onDraft={setDraft} fresh={fresh} provider={provider} onProvider={setProvider} error={error} onSubmit={setError} />
        </div>
      </WorkbenchLayout>
      <Sheet open={!!view.citation && !fresh} onOpenChange={(open) => { if (!open) navigate(viewHref(view.conversation, undefined, view.workspace)); }}>
        <SheetContent className="w-screen max-w-[100vw] gap-4 overscroll-contain pb-[env(safe-area-inset-bottom)] sm:w-[420px] sm:max-w-[420px]"
          onCloseAutoFocus={(event) => { event.preventDefault(); (citationTrigger.current?.isConnected ? citationTrigger.current : sidebarToggle.current)?.focus(); }}>
          <SheetHeader className="pr-14"><SheetTitle>Sources</SheetTitle><SheetDescription>Where this example answer comes from.</SheetDescription></SheetHeader>
          <EvidenceInspector citation={view.citation} onNavigate={onNavigate} />
        </SheetContent>
      </Sheet>
      <DiscardDraftDialog open={pending} onCancel={cancelNavigation} onDiscard={() => { setDraft(""); discardNavigation(); }} />
    </>
  );
}
