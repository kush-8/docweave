import type { MouseEvent } from "react";
import { ChevronDown, Folder, MessageSquare, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { viewHref } from "@/routing/workbench";
import type { WorkbenchView } from "@/routing/workbench";

type Props = {
  view: WorkbenchView;
  onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void;
  onStartChat: () => void;
};

export function WorkbenchSidebar({ view, onNavigate, onStartChat }: Props) {
  const fresh = view.conversation === "new";
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-7 px-3 pb-5">
      <Button variant="outline" className="w-full justify-start rounded-lg bg-background" onClick={onStartChat}><Plus aria-hidden="true" />New chat</Button>
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
}
