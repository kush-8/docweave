// Synthetic fixtures for the labeled UI preview; these are not indexed documents.
export const sampleSources = [
  {
    id: "1",
    title: "Workspace access rules",
    file: "architecture/access.md",
    section: "Authorization boundaries",
    excerpt:
      "Resolve the current user’s workspace membership and collection grants before retrieval. A project identifier alone never grants access to its knowledge.",
    note: "Establish the permitted workspace, project, and collections before searching.",
  },
  {
    id: "2",
    title: "Retrieval pipeline",
    file: "architecture/retrieval.md",
    section: "Candidate filtering",
    excerpt:
      "Filter candidate chunks by the active workspace, project, permitted collections, and source status before ranking. Keep those restrictions in both lexical and vector retrieval.",
    note: "Keep the same access boundaries throughout search, fusion, and reranking.",
  },
  {
    id: "3",
    title: "Provider processing policy",
    file: "architecture/processing.md",
    section: "Revalidate before release",
    excerpt:
      "Recheck source access and processing approvals before each external call and before releasing an answer or its evidence. If access has changed, pause the conversation.",
    note: "Queued work and remembered context must respect current access.",
  },
];

export const sampleCode = `SELECT id, content
FROM document_chunks
WHERE workspace_id = :workspace_id
  AND project_id = :project_id
  AND collection_id = ANY(:allowed_collections)
  AND source_status = 'ready'
ORDER BY embedding <=> :query_embedding
LIMIT :limit;`;

export function readView() {
  const params = new URLSearchParams(window.location.search);
  const conversation = params.get("conversation") === "new" ? "new" : "sample";
  const citation =
    conversation === "sample" &&
    sampleSources.some((source) => source.id === params.get("citation"))
      ? params.get("citation")
      : null;
  return { conversation, citation };
}

export function viewHref(conversation: string, citation?: string) {
  const params = new URLSearchParams({ conversation });
  if (citation) params.set("citation", citation);
  return `?${params}`;
}
