export type Project = { id: string; name: string; goal: string; stack?: { technology: string; declared_version?: string | null; resolved_version?: string | null; docs_target?: string | null }[]; context_revision?: number; repository?: { repository_id: number; branch: string; application_path: string; commit_sha?: string } | null; sync_state?: string; docs_state?: string };
export type Citation = { id: string; title: string };
export type Turn = { id: string; message: string; status: string; answer?: string | null; citations?: Citation[]; context_revision?: number; progress?: string | null };
export type Conversation = { id: string; status: string; progress?: string | null };
export type Profile = { id: string; name?: string; display_name?: string; provider?: string; model?: string; enabled?: boolean };
export class ApiError extends Error { status: number; constructor(status: number) { super(status === 401 ? "Sign in with GitHub to continue." : status === 403 ? "Access was denied. Check your GitHub repository access and sign in again." : `Request failed (${status}). Please try again.`); this.status = status; } }
export async function api<T>(path: string, body?: unknown, csrf?: string, signal?: AbortSignal, method?: "POST" | "PUT" | "DELETE"): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { credentials: "same-origin", signal, ...(body === undefined ? {} : { method: method ?? "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" }, body: JSON.stringify(body) }) });
  if (!response.ok) throw new ApiError(response.status);
  if (response.status === 204) return undefined as T;
  if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("The API is unavailable. Please try again when the server is running.");
  return response.json();
}
export async function allItems<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null | undefined;
  do {
    const page: { items: T[]; next_cursor?: string | null } = await api(`${path}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, undefined, undefined, signal);
    if (!Array.isArray(page.items) || (page.next_cursor && seen.has(page.next_cursor))) throw new Error("The server returned an invalid page. Please retry the connection.");
    items.push(...page.items);
    cursor = page.next_cursor;
    if (cursor) seen.add(cursor);
  } while (cursor);
  return items;
}
export function statusLabel(status: string) { return status.replaceAll("_", " "); }
export function errorMessage(error: unknown) { return error instanceof Error ? error.message : "The request could not be completed. Please try again."; }


