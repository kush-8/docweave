import type { Page } from "@playwright/test";
export async function mockApi(page: Page, options: { waiting?: boolean; failSend?: boolean; signedOut?: boolean } = {}) {
  let polls = 0;
  const project = { id: "p1", name: "My repository", goal: "Build an API", context_revision: 2, repository: { repository_id: 42, branch: "main", application_path: "", commit_sha: "abcdef123456789" }, sync_state: "ready", docs_state: "ready" };
  const turns: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    let body: unknown;
    if (path === "/me") {
      if (options.signedOut) return route.fulfill({ status: 401, json: { detail: "unauthorized" } });
      body = { id: "u1", display_name: "Developer", csrf_token: "csrf-test" };
    } else if (path === "/auth/logout") return route.fulfill({ status: 204 });
    else if (path === "/providers") body = { items: [{ id: "profile", display_name: "Configured model" }] };
    else if (path === "/projects" && request.method() === "GET") body = { items: [project] };
    else if (path === "/projects" && request.method() === "POST") { body = project; }
    else if (path === "/projects/p1") body = project;
    else if (path === "/projects/p1/processing-policy" && request.method() === "PUT") body = { revision: 2, processor_ids: request.postDataJSON().approved_processor_ids };
    else if (path === "/projects/p1/processing-policy") body = { revision: 1, processor_ids: [], available_processors: [{ id: "groq:configured", provider: "Groq", roles: ["generation"] }] };
    else if (path === "/connections/github/repositories") body = { items: [{ id: 42, full_name: "me/repository", default_branch: "main" }] };
    else if (path === "/connections/github/repositories/42/branches") body = { items: [{ name: "main" }, { name: "develop" }] };
    else if (path === "/projects/p1/conversations" && request.method() === "POST") body = { id: "c1", status: "initializing" };
    else if (path === "/projects/p1/conversations") body = { items: [{ id: "c1", status: "ready", name: "API chat" }] };
    else if (path === "/conversations/c1") body = { id: "c1", status: "ready" };
    else if (path === "/conversations/c1/turns" && request.method() === "POST") {
      if (options.failSend) return route.fulfill({ status: 503, json: {} });
      const data = request.postDataJSON();
      turns.push({ id: "t1", message: data.message, status: options.waiting ? "waiting_for_sources" : "completed", answer: options.waiting ? null : "Use the documented API.", citations: [{ id: "s1", title: "API documentation" }] });
      body = { id: "t1", status: "queued" };
    } else if (path === "/conversations/c1/turns") body = { items: turns };
    else if (path === "/turns/t1") {
      polls += 1;
      body = { ...turns[0], status: polls > 1 ? "completed" : "waiting_for_sources", answer: polls > 1 ? "Use the documented API." : null };
      if (polls > 1) turns[0] = body as Record<string, unknown>;
    } else if (path === "/turns/t1/citations/s1") body = { title: "API documentation", excerpt: "An exact authorized excerpt.", url: "https://example.com/docs" };
    else return route.fulfill({ status: 404, json: { detail: path } });
    await route.fulfill({ status: 200, json: body });
  });
}

