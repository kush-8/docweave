export type WorkbenchView = { project: string; conversation: string; citation: string | null; turn: string | null };
export function readView(search: string): WorkbenchView {
  const params = new URLSearchParams(search);
  return { project: params.get("project") ?? "", conversation: params.get("conversation") ?? "new", citation: params.get("citation"), turn: params.get("turn") };
}
export function viewHref(conversation: string, citation?: string, project = "", turn?: string) {
  const params = new URLSearchParams({ project, conversation });
  if (citation && turn) { params.set("citation", citation); params.set("turn", turn); }
  return `?${params}`;
}
