import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import {
  BookOpen,
  ChevronDown,
  Layers3,
  MessageSquare,
  PanelRightOpen,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useMediaQuery } from "@/lib/use-media-query";
import { Composer } from "./Composer";
import { EvidenceInspector } from "./EvidenceInspector";
import { SampleConversation } from "./SampleConversation";
import { readView, viewHref } from "./sample";

export function Workbench() {
  const [view, setView] = useState(readView);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [draft, setDraft] = useState("");
  const [provider, setProvider] = useState("Gemini");
  const [error, setError] = useState("");
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const [pendingDelta, setPendingDelta] = useState(0);
  const citationTrigger = useRef<HTMLElement | null>(null);
  const evidenceButton = useRef<HTMLButtonElement>(null);
  const historyPosition = useRef(0);
  const restoringPosition = useRef(false);
  const allowTraversal = useRef(false);
  const desktop = useMediaQuery("(min-width: 1200px)");
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
      const position =
        history.state?.docweavePosition ?? historyPosition.current;
      const delta = position - historyPosition.current;
      if (
        draft &&
        next.conversation !== view.conversation &&
        delta &&
        !allowTraversal.current
      ) {
        setPendingHref(location.href);
        setPendingDelta(delta);
        restoringPosition.current = true;
        history.go(-delta);
        return;
      }
      allowTraversal.current = false;
      historyPosition.current = position;
      setView(next);
      setEvidenceOpen(true);
      setError("");
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [draft, view.conversation]);

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
    history.pushState(
      { docweavePosition: ++historyPosition.current },
      "",
      href,
    );
    setView(readView());
    setError("");
    setEvidenceOpen(true);
  }

  function requestNavigate(href: string) {
    const target =
      new URL(href, location.href).searchParams.get("conversation") ?? "sample";
    if (draft && target !== view.conversation) {
      setPendingDelta(0);
      setPendingHref(href);
    } else navigate(href);
  }

  function onNavigate(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    if (!event.currentTarget.closest('[aria-label="Evidence inspector"]')) {
      citationTrigger.current = event.currentTarget;
    }
    event.currentTarget.closest("details")?.removeAttribute("open");
    requestNavigate(event.currentTarget.href);
  }

  function closeEvidence() {
    navigate(viewHref(view.conversation));
    setEvidenceOpen(false);
    (citationTrigger.current?.isConnected
      ? citationTrigger.current
      : evidenceButton.current
    )?.focus();
  }

  const inspector = (
    <EvidenceInspector
      citation={view.citation}
      onNavigate={onNavigate}
      onClose={closeEvidence}
      modal={!desktop}
    />
  );

  return (
    <main
      className="col-start-1 flex min-h-[calc(100dvh-56px)] min-w-0 flex-col p-4 md:h-[calc(100dvh-56px)] md:p-6 min-[1200px]:col-start-2 max-[767px]:pb-[max(1rem,env(safe-area-inset-bottom))]"
      id="main-content"
      tabIndex={-1}
    >
      <header className="mb-4 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center [&_p]:mt-2 [&_p]:text-sm [&_p]:text-muted-foreground [&>button]:bg-background">
        <div>
          <h1>Ask your project</h1>
          <p>Work through the question. Keep the evidence in view.</p>
        </div>
        <Button
          variant="outline"
          onClick={() => requestNavigate(viewHref("new"))}
        >
          <Plus aria-hidden="true" />
          New conversation
        </Button>
      </header>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground [&>span:last-child]:max-sm:basis-full">
        <Badge variant="outline">Interactive preview</Badge>
        <span>
          Sample conversation and sources. Messages stay on this device and are
          not sent.
        </span>
      </div>
      <div className="flex items-center justify-between gap-1 py-3 [&>button]:max-sm:gap-1 [&>button]:max-sm:px-2 [&>button]:max-sm:text-sm">
        <details className="relative min-w-0 [&>summary]:flex [&>summary]:min-h-11 [&>summary]:list-none [&>summary]:items-center [&>summary]:gap-2 [&>summary]:rounded-md [&>summary]:px-2 [&>summary]:text-sm [&>summary]:font-medium [&>summary]:max-sm:gap-1 [&>summary]:max-sm:px-0 [&>summary]:max-sm:text-sm [&>summary:hover]:bg-accent [&>summary::-webkit-details-marker]:hidden [&>div]:absolute [&>div]:top-full [&>div]:left-0 [&>div]:z-20 [&>div]:grid [&>div]:w-[min(320px,calc(100vw-2rem))] [&>div]:gap-2 [&>div]:rounded-md [&>div]:border [&>div]:border-border [&>div]:bg-background [&>div]:p-3 [&>div]:shadow-lg [&_p]:text-sm [&_p]:text-muted-foreground [&_a]:flex [&_a]:min-h-11 [&_a]:items-center [&_a]:rounded-md [&_a]:bg-accent [&_a]:p-2 [&_a]:text-sm [&_a]:text-primary [&>div>span]:text-sm [&>div>span]:text-muted-foreground">
          <summary>
            <MessageSquare aria-hidden="true" size={16} />
            <span>{fresh ? "New conversation" : "Workspace isolation"}</span>
            <ChevronDown aria-hidden="true" size={16} />
          </summary>
          <div>
            <p>Recent conversations · sample</p>
            <a href={viewHref("sample")} onClick={onNavigate}>
              Workspace isolation
            </a>
            <span>
              Your conversations will appear here when the backend is connected.
            </span>
          </div>
        </details>
        <Button
          ref={evidenceButton}
          variant="ghost"
          onClick={(event) => {
            citationTrigger.current = event.currentTarget;
            navigate(
              viewHref(
                view.conversation,
                fresh ? undefined : (view.citation ?? "1"),
              ),
            );
          }}
          disabled={fresh}
        >
          <PanelRightOpen aria-hidden="true" />
          {desktop && evidenceOpen ? "Evidence open" : "Show evidence"}
        </Button>
      </div>
      <div
        className={`grid min-h-0 flex-1 gap-6 ${desktop && evidenceOpen && !fresh ? "grid-cols-[minmax(480px,1fr)_360px]" : "grid-cols-[minmax(0,1fr)]"}`}
      >
        <section
          className="flex min-h-0 min-w-0 flex-col rounded-md border border-divider bg-background"
          aria-label="Conversation"
        >
          {fresh ? (
            <div className="mx-auto flex min-h-60 max-w-[72ch] flex-1 flex-col items-start justify-center gap-4 overflow-y-auto px-4 py-6 md:p-8 [&>p]:text-muted-foreground [&>h2]:text-2xl">
              <span className="grid size-13 place-items-center rounded-md bg-accent text-primary">
                <Layers3 aria-hidden="true" size={28} />
              </span>
              <h2>Start with your project.</h2>
              <p>
                Ask about an integration, trace a decision, or work through an
                implementation with supporting sources.
              </p>
              <div className="mt-2 grid gap-3 [&>span]:text-sm [&>span]:text-muted-foreground [&>button]:justify-start [&>button]:p-3 [&>button]:text-left [&>button]:leading-normal [&>button]:whitespace-normal">
                <span>Try a question</span>
                {[
                  "How should we isolate knowledge between workspaces?",
                  "What happens when a source is revoked?",
                ].map((question) => (
                  <Button
                    key={question}
                    variant="outline"
                    onClick={() => setDraft(question)}
                  >
                    <BookOpen aria-hidden="true" />
                    {question}
                  </Button>
                ))}
              </div>
              <p className="text-sm text-muted-foreground">
                This preview keeps drafts in memory. No answer provider is
                connected.
              </p>
            </div>
          ) : (
            <SampleConversation
              citation={view.citation}
              onNavigate={onNavigate}
            />
          )}
          <Composer
            draft={draft}
            onDraft={setDraft}
            fresh={fresh}
            provider={provider}
            onProvider={setProvider}
            error={error}
            onSubmit={setError}
          />
        </section>
        {desktop && evidenceOpen && !fresh && inspector}
      </div>
      {!desktop && (
        <Sheet
          open={!!view.citation && !fresh}
          onOpenChange={(open) => {
            if (!open) closeEvidence();
          }}
        >
          <SheetContent
            className="w-screen max-w-[100vw] gap-0 overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)] sm:w-[440px] sm:max-w-[440px] [&>[data-slot=sheet-header]]:border-b [&>[data-slot=sheet-header]]:border-divider [&>[data-slot=sheet-header]]:py-4 [&>[data-slot=sheet-header]]:pr-14 [&>[data-slot=sheet-header]]:pl-5 [&>section]:flex-1 [&>section]:border-0"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              (citationTrigger.current?.isConnected
                ? citationTrigger.current
                : evidenceButton.current
              )?.focus();
            }}
          >
            <SheetHeader>
              <SheetTitle>Evidence inspector</SheetTitle>
              <SheetDescription>
                Inspect the sample source behind this claim.
              </SheetDescription>
            </SheetHeader>
            {inspector}
          </SheetContent>
        </Sheet>
      )}
      <AlertDialog
        open={!!pendingHref}
        onOpenChange={(open) => {
          if (!open) setPendingHref(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard your unsent message?</AlertDialogTitle>
            <AlertDialogDescription>
              Your draft has not been sent. Switching conversations will discard
              it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep writing</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingHref) {
                  setDraft("");
                  if (pendingDelta) {
                    allowTraversal.current = true;
                    history.go(pendingDelta);
                  } else navigate(pendingHref);
                }
                setPendingHref(null);
              }}
            >
              Discard draft
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
