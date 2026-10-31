import type { ReactNode, RefObject } from "react";
import { Layers3 } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type Props = {
  children: ReactNode;
  header: ReactNode;
  sidebar: ReactNode;
  desktop: boolean;
  sidebarOpen: boolean;
  mobileSidebarOpen: boolean;
  onMobileSidebarOpen: (open: boolean) => void;
  sidebarToggle: RefObject<HTMLButtonElement | null>;
};

export function WorkbenchLayout({ children, header, sidebar, desktop, sidebarOpen, mobileSidebarOpen, onMobileSidebarOpen, sidebarToggle }: Props) {
  return (
    <div className="flex h-dvh min-h-0 bg-background">
      <a href="#main-content" className="fixed -top-24 left-4 z-[100] rounded-md border-2 border-primary bg-background px-4 py-3 text-primary focus:top-4">Skip to chat</a>
      {desktop && sidebarOpen && <aside id="chat-sidebar" aria-label="Chat sidebar" className="flex w-64 shrink-0 flex-col overflow-y-auto border-r border-divider bg-canvas">
        <div className="flex h-16 shrink-0 items-center gap-2 px-6 font-semibold"><Layers3 aria-hidden="true" size={21} className="text-primary" /><span translate="no">DocWeave</span></div>
        {sidebar}
      </aside>}
      <div className="flex min-w-0 flex-1 flex-col">
        {header}
        <main id="main-content" tabIndex={-1} className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 sm:px-8">
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">{children}</div>
        </main>
      </div>
      {!desktop && <Sheet open={mobileSidebarOpen} onOpenChange={onMobileSidebarOpen}>
        <SheetContent id="chat-sidebar" side="left" className="w-72 max-w-[90vw] gap-3 overflow-y-auto overscroll-contain bg-canvas pb-[env(safe-area-inset-bottom)]"
          onCloseAutoFocus={(event) => { event.preventDefault(); sidebarToggle.current?.focus(); }}>
          <SheetHeader><SheetTitle>Your chats</SheetTitle><SheetDescription>Workspaces & recent chats</SheetDescription></SheetHeader>
          {sidebar}
        </SheetContent>
      </Sheet>}
    </div>
  );
}
