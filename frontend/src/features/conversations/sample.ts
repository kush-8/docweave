// Synthetic fixtures for the labeled UI preview; these are not indexed documents.
export const sampleSources = [
  {
    id: "1",
    title: "Who can see your files",
    file: "architecture/access.md",
    section: "Authorization boundaries",
    excerpt:
      "Only people who belong to the team and have permission to read a file can use it in a chat.",
    note: "Establish the permitted workspace, project, and collections before searching.",
  },
  {
    id: "2",
    title: "Finding the right files",
    file: "architecture/retrieval.md",
    section: "Candidate filtering",
    excerpt:
      "Search only the files the current person can read. Files from other teams are kept separate.",
    note: "Keep the same access boundaries throughout search, fusion, and reranking.",
  },
  {
    id: "3",
    title: "When access changes",
    file: "architecture/processing.md",
    section: "Revalidate before release",
    excerpt:
      "Check file access again before sharing an answer. Stop the chat if it depends on a file the person can no longer read.",
    note: "Queued work and remembered context must respect current access.",
  },
];

export const sampleAnswer = "Keep each team’s files separate. Only use files that the person asking the question is allowed to read. Check access again before sharing an answer. If access is removed, stop using those files in the chat.";

export function readView() {
  const params = new URLSearchParams(window.location.search);
  const workspace = params.get("workspace") === "personal" ? "personal" : "engineering";
  const conversation = workspace === "engineering" && params.get("conversation") === "sample" ? "sample" : "new";
  const citation =
    conversation === "sample" &&
    sampleSources.some((source) => source.id === params.get("citation"))
      ? params.get("citation")
      : null;
  return { workspace, conversation, citation };
}

export function viewHref(conversation: string, citation?: string, workspace = "engineering") {
  const params = new URLSearchParams({ workspace, conversation });
  if (citation) params.set("citation", citation);
  return `?${params}`;
}
