import type { Ref } from "react";
import { Monitor, Moon, PanelLeftClose, PanelLeftOpen, Plus, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { WorkbenchView } from "@/routing/workbench";

type Props = {
  desktop: boolean;
  sidebarOpen: boolean;
  mobileSidebarOpen: boolean;
  sidebarToggle: Ref<HTMLButtonElement>;
  workspace: WorkbenchView["workspace"];
  theme: "light" | "dark";
  preference: "light" | "dark" | null;
  onToggleSidebar: () => void;
  onStartChat: () => void;
  onTheme: (theme: "light" | "dark" | null) => void;
};

export function WorkbenchHeader({ desktop, sidebarOpen, mobileSidebarOpen, sidebarToggle, workspace, theme, preference, onToggleSidebar, onStartChat, onTheme }: Props) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 px-3 sm:px-5">
      <div className="flex min-w-0 items-center gap-2">
        <Button ref={sidebarToggle} variant="ghost" size="icon" aria-label={(desktop ? sidebarOpen : mobileSidebarOpen) ? "Hide sidebar" : "Show sidebar"}
          aria-expanded={desktop ? sidebarOpen : mobileSidebarOpen} aria-controls="chat-sidebar" onClick={onToggleSidebar}>
          {(desktop ? sidebarOpen : mobileSidebarOpen) ? <PanelLeftClose aria-hidden="true" /> : <PanelLeftOpen aria-hidden="true" />}
        </Button>
        <span className="truncate text-sm font-medium">{desktop && sidebarOpen ? (workspace === "personal" ? "Personal" : "Engineering") : "DocWeave"}</span>
      </div>
      <div className="flex items-center gap-1">
        {(!sidebarOpen || !desktop) && <Button variant="ghost" onClick={onStartChat}><Plus aria-hidden="true" /><span className="hidden sm:inline">New chat</span><span className="sr-only sm:hidden">New chat</span></Button>}
        <Button variant="ghost" size="icon" onClick={() => onTheme(theme === "dark" ? "light" : "dark")}
          aria-pressed={theme === "dark"} aria-label={theme === "dark" ? "Light mode" : "Dark mode"}>
          {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
        </Button>
        {preference && <Button variant="ghost" size="icon" aria-label="Use device theme" onClick={() => onTheme(null)}><Monitor aria-hidden="true" /></Button>}
      </div>
    </header>
  );
}
