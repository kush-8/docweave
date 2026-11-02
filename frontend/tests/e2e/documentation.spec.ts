import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "../support/api";

test("repository dependencies show the app folder beside each version", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/projects/p1/documentation", (route) => route.fulfill({ json: {
    context_revision: 2, items: [
      { dependency_id: "backend-react", technology: "React", docs_target: "18.3.1", application_path: "backend", status: "missing", candidates: [] },
      { dependency_id: "client-react", technology: "React", docs_target: "19.1.0", application_path: "client", status: "missing", candidates: [] },
    ],
  } }));
  await page.goto("/?project=p1&conversation=c1");
  await page.getByText("Project documentation", { exact: true }).click();
  const backend = page.getByRole("region", { name: "React documentation for backend", exact: true });
  const client = page.getByRole("region", { name: "React documentation for client", exact: true });
  await expect(backend.getByRole("heading", { name: "React 18.3.1", exact: true })).toBeVisible();
  await expect(backend.getByText("backend", { exact: true })).toBeVisible();
  await expect(client.getByRole("heading", { name: "React 19.1.0", exact: true })).toBeVisible();
  await expect(client.getByText("client", { exact: true })).toBeVisible();
});

test("documentation review accepts a version fallback explicitly and preserves the draft", async ({ page }) => {
  await mockApi(page);
  const entry = { revision_id: "revision-1", source_url: "https://docs.example.org/v1/guide.md", attribution: "Publisher", coverage: { granularity: "major", version: "1" } };
  let accepted = false;
  await page.route("**/api/v1/projects/p1/documentation**", async (route) => {
    if (route.request().method() === "PUT") {
      expect(route.request().postDataJSON()).toEqual({ expected_revision: 2, revision_id: "revision-1", accept_fallback: true });
      expect(route.request().headers()["x-csrf-token"]).toBe("csrf-test");
      accepted = true;
    }
    const match = { status: accepted ? "capacity" : "pending_review", reason: "version fallback approval required", entry };
    await route.fulfill({ json: { context_revision: accepted ? 3 : 2, items: [{ dependency_id: "dep", technology: "Example", docs_target: "1.2.3", ...match, selected_revision_id: accepted ? "revision-1" : null, candidates: [match] }] } });
  });
  await page.goto("/?project=p1&conversation=c1");
  await page.getByRole("textbox", { name: "Your message" }).fill("Keep this question");
  await page.getByText("Project documentation", { exact: true }).click();
  await expect(page.getByText("Version fallback approval required", { exact: false })).toBeVisible();
  const accept = page.getByRole("button", { name: "Use this documentation", exact: true });
  await expect(accept).toBeDisabled();
  await page.getByRole("checkbox", { name: "I accept major 1 documentation for Example 1.2.3" }).check();
  await accept.click();
  await expect(page.getByText("Waiting for capacity", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue("Keep this question");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
});

test("unknown public source review stays operator-only and errors can be retried", async ({ page }) => {
  await mockApi(page);
  let failed = true;
  await page.route("**/api/v1/projects/p1/documentation", (route) => {
    if (failed) { failed = false; return route.fulfill({ status: 503, json: {} }); }
    return route.fulfill({ json: { context_revision: 2, items: [{ dependency_id: "dep", technology: "Example", docs_target: "1.2.3", status: "pending_review", reason: "source approval required", candidates: [{ status: "pending_review", reason: "source approval required", entry: { revision_id: "candidate", source_approved: false, coverage: { granularity: "exact", version: "1.2.3" }, source_url: "https://docs.example.org/v1/guide.md", attribution: "Publisher" } }] }] } });
  });
  await page.goto("/?project=p1&conversation=c1");
  await page.getByText("Project documentation", { exact: true }).click();
  await page.getByRole("button", { name: "Reload documentation" }).click();
  await expect(page.getByText("Operator source approval required", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use this documentation" })).toHaveCount(0);
});

test("active documentation displays the actual safe worker stage", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/projects/p1/documentation", (route) => route.fulfill({ json: { context_revision: 2, items: [{ dependency_id: "dep", technology: "Example", docs_target: "1.2.3", status: "waiting_for_sources", reason: "current generation is not atomically indexed", entry: { progress: "Building documentation index" }, candidates: [] }] } }));
  await page.goto("/?project=p1&conversation=c1");
  await page.getByText("Project documentation", { exact: true }).click();
  await expect(page.getByText("Preparing documentation", { exact: true })).toBeVisible();
  await expect(page.getByText("Building documentation index", { exact: true })).toBeVisible();
});
