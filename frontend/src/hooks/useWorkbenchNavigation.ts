import { useEffect, useRef, useState } from "react";
import { readView } from "@/routing/workbench";

export function useWorkbenchNavigation(draft: string, onNavigate: () => void) {
  const [view, setView] = useState(() => readView(location.search));
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const [pendingDelta, setPendingDelta] = useState(0);
  const historyPosition = useRef(0);
  const restoringPosition = useRef(false);
  const allowTraversal = useRef(false);

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
      const next = readView(location.search);
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
      onNavigate();
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [draft, view.conversation, view.workspace, onNavigate]);

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
    setView(readView(location.search));
    onNavigate();
  }

  function requestNavigate(href: string, reset = false) {
    const params = new URL(href, location.href).searchParams;
    if (draft && (reset || params.get("conversation") !== view.conversation || (params.get("workspace") ?? "engineering") !== view.workspace)) {
      setPendingDelta(0);
      setPendingHref(href);
    } else navigate(href);
  }

  function discardNavigation() {
    if (pendingHref) {
      if (pendingDelta) { allowTraversal.current = true; history.go(pendingDelta); }
      else navigate(pendingHref);
    }
    setPendingHref(null);
  }

  return { view, navigate, requestNavigate, pending: !!pendingHref, cancelNavigation: () => setPendingHref(null), discardNavigation };
}
