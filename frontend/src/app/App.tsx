import { useState } from "react";
import {
  Activity,
  BookOpen,
  CircleHelp,
  FileText,
  FolderOpen,
  Layers3,
  LayoutGrid,
  Menu,
  MessageSquare,
  Monitor,
  Moon,
  Settings,
  Sun,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useTheme } from "@/lib/use-theme";
import { Workbench } from "@/features/conversations/Workbench";

function ProjectNavigation({ onAsk }: { onAsk?: () => void }) {
  return (
    <>
      <div className="flex items-center gap-3 px-4 py-6 text-sm [&_strong]:block [&_strong]:text-sm [&_strong]:font-semibold [&_div>span]:block [&_div>span]:text-sm [&_div>span]:text-muted-foreground">
        <span className="grid size-8 shrink-0 place-items-center rounded-md border border-divider bg-canvas font-semibold text-muted-foreground">
          E
        </span>
        <div>
          <strong>Engineering workspace</strong>
          <span>Local preview</span>
        </div>
      </div>
      <div className="flex items-center gap-2 px-6 pt-2 pb-3 text-sm">
        <FolderOpen aria-hidden="true" size={16} />
        <strong translate="no">DocWeave</strong>
      </div>
      <nav
        className="flex flex-col gap-1 px-3 [&>a]:flex [&>a]:min-h-11 [&>a]:items-center [&>a]:gap-3 [&>a]:rounded-md [&>a]:bg-accent [&>a]:px-3 [&>a]:py-2 [&>a]:text-sm [&>a]:font-semibold [&>a]:text-primary [&>a]:shadow-[inset_3px_0_var(--primary)] [&>a:hover]:outline [&>a:hover]:outline-primary [&>span]:flex [&>span]:min-h-11 [&>span]:items-center [&>span]:gap-3 [&>span]:px-3 [&>span]:py-2 [&>span]:text-sm [&>span]:text-muted-foreground"
        aria-label="Project navigation"
      >
        {[
          { label: "Overview", Icon: LayoutGrid },
          { label: "Ask", Icon: MessageSquare },
          { label: "Sources", Icon: BookOpen },
          { label: "Documents", Icon: FileText },
          { label: "Activity", Icon: Activity },
          { label: "Settings", Icon: Settings },
        ].map(({ label, Icon }) =>
          label === "Ask" ? (
            <a
              key={label}
              href="#main-content"
              aria-current="page"
              onClick={onAsk}
            >
              <Icon aria-hidden="true" size={18} />
              {label}
            </a>
          ) : (
            <span key={label} aria-disabled="true">
              <Icon aria-hidden="true" size={18} />
              {label}
            </span>
          ),
        )}
      </nav>
      <div className="mx-6 my-8 border-t border-divider pt-5 [&_h2]:mb-3 [&_h2]:text-sm [&_p]:text-sm [&_p]:text-muted-foreground">
        <h2>Project context</h2>
        <p>
          A documentation assistant with project-aware answers and inspectable
          evidence.
        </p>
        <div
          className="mt-4 flex flex-wrap gap-2 [&>span]:rounded [&>span]:border [&>span]:border-divider [&>span]:px-2 [&>span]:py-1 [&>span]:text-sm [&>span]:text-muted-foreground"
          translate="no"
        >
          <span>React</span>
          <span>FastAPI</span>
          <span>PostgreSQL</span>
        </div>
      </div>
      <div className="mt-auto flex items-start gap-2 border-t border-divider p-6 text-muted-foreground [&_svg]:mt-0.5 [&_p]:text-sm">
        <CircleHelp aria-hidden="true" size={17} />
        <p>
          Only Ask is available in this preview. Other project screens come
          next.
        </p>
      </div>
    </>
  );
}

export default function App() {
  const { theme, preference, chooseTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="grid min-h-dvh grid-cols-1 grid-rows-[56px_minmax(0,1fr)] min-[1200px]:grid-cols-[224px_minmax(0,1fr)]">
      <a
        href="#main-content"
        className="fixed -top-24 left-4 z-[100] rounded-md border-2 border-primary bg-background px-4 py-3 text-primary focus:top-4"
      >
        Skip to main content
      </a>
      <aside
        className="col-start-1 row-span-2 row-start-1 hidden min-h-dvh flex-col border-r border-divider bg-background min-[1200px]:flex"
        aria-label="Project sidebar"
      >
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-divider px-5 text-lg font-semibold tracking-tight">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <Layers3 aria-hidden="true" size={22} />
          </span>
          <span translate="no">DocWeave</span>
        </div>
        <ProjectNavigation />
      </aside>
      <header className="col-start-1 flex min-w-0 items-center justify-between gap-2 border-b border-divider bg-background px-2 md:gap-4 md:px-6 min-[1200px]:col-start-2">
        <div className="flex min-w-0 items-center gap-2 text-sm md:gap-3">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="min-[1200px]:hidden"
                aria-label="Open project navigation"
              >
                <Menu aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent
              side="left"
              className="w-[280px] max-w-[90vw] gap-0 overscroll-contain overflow-y-auto pb-[env(safe-area-inset-bottom)] [&>[data-slot=sheet-header]]:min-h-20 [&>[data-slot=sheet-header]]:pr-14"
            >
              <SheetHeader>
                <SheetTitle>DocWeave</SheetTitle>
                <SheetDescription>
                  Engineering workspace · local preview
                </SheetDescription>
              </SheetHeader>
              <ProjectNavigation onAsk={() => setMenuOpen(false)} />
            </SheetContent>
          </Sheet>
          <span className="hidden text-muted-foreground min-[1200px]:inline">
            Engineering workspace
            <span className="ml-3 text-muted-foreground">/</span>
          </span>
          <strong translate="no">DocWeave</strong>
          <span className="hidden rounded border border-divider px-2 text-sm text-muted-foreground md:inline">
            Project
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-0 md:gap-2 [&>button]:size-11 [&>button]:p-0 md:[&>button]:w-auto md:[&>button]:px-3 [&>button>span]:hidden md:[&>button>span]:inline">
          <Button
            variant="ghost"
            onClick={() => chooseTheme(theme === "dark" ? "light" : "dark")}
            aria-pressed={theme === "dark"}
            aria-label={theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme === "dark" ? (
              <Sun aria-hidden="true" />
            ) : (
              <Moon aria-hidden="true" />
            )}
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          </Button>
          {preference && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Use device theme"
              onClick={() => chooseTheme(null)}
            >
              <Monitor aria-hidden="true" />
            </Button>
          )}
          <span
            className="hidden size-7 place-items-center rounded-full border border-divider bg-canvas text-sm text-muted-foreground md:grid"
            aria-label="Preview account"
          >
            P
          </span>
        </div>
      </header>
      <Workbench />
    </div>
  );
}
