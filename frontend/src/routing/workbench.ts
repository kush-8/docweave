export type WorkbenchView = {
  workspace: "engineering" | "personal";
  conversation: "new" | "sample";
  citation: string | null;
};

export function readView(search: string): WorkbenchView {
  const params = new URLSearchParams(search);
  const workspace = params.get("workspace") === "personal" ? "personal" : "engineering";
  const conversation = workspace === "engineering" && params.get("conversation") === "sample" ? "sample" : "new";
  const citation = params.get("citation");
  return {
    workspace,
    conversation,
    citation: conversation === "sample" && citation !== null && ["1", "2", "3"].includes(citation) ? citation : null,
  };
}

export function viewHref(conversation: WorkbenchView["conversation"], citation?: string, workspace: WorkbenchView["workspace"] = "engineering") {
  const params = new URLSearchParams({ workspace, conversation });
  if (citation) params.set("citation", citation);
  return `?${params}`;
}
