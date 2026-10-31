import type { MouseEvent } from "react";
import { Folder, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { viewHref } from "@/routing/workbench";
import type { WorkbenchView } from "@/routing/workbench";

type Props = {
  view: WorkbenchView;
  projects: { id: string; name: string }[];
  conversations: { id: string; name: string; project: string }[];
  onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void;
  onStartChat: () => void;
};
export function WorkbenchSidebar({ view, projects, conversations, onNavigate, onStartChat }: Props) {
  return <div className="flex min-h-0 flex-1 flex-col gap-7 px-3 pb-5">
    <Button variant="outline" className="w-full justify-start rounded-lg bg-background" onClick={onStartChat}><Plus aria-hidden="true" />New chat</Button>
    <nav aria-label="Projects" className="space-y-2">
      <h2 className="px-3 text-xs font-medium text-muted-foreground">Projects</h2>
      {projects.map((project) => <a key={project.id} href={viewHref("new", undefined, project.id)} onClick={onNavigate} aria-current={view.project === project.id ? "page" : undefined} className="flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm hover:bg-accent aria-[current]:bg-accent"><Folder aria-hidden="true" size={16} />{project.name}</a>)}
      <a href={viewHref("new")} onClick={onNavigate} className="flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm hover:bg-accent"><Plus aria-hidden="true" size={16} />Add project</a>
    </nav>
    <nav aria-label="Recent chats" className="space-y-2">
      <h2 className="px-3 text-xs font-medium text-muted-foreground">Recent chats</h2>
      {conversations.map((chat) => <a key={chat.id} href={viewHref(chat.id, undefined, chat.project)} onClick={onNavigate} aria-current={view.conversation === chat.id ? "page" : undefined} className="flex min-h-11 items-center rounded-lg px-3 text-sm hover:bg-accent aria-[current]:bg-accent">{chat.name}</a>)}
      {!conversations.length && <p className="px-3 text-xs text-muted-foreground">Your chats appear here after you start one.</p>}
    </nav>
  </div>;
}
