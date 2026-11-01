import { expect, test } from "@playwright/test";
import { mockApi } from "../support/api";

test("unknown source discovery and private approval require explicit decisions", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/projects/p1/documentation", (route) => route.fulfill({ json: { context_revision: 2, items: [{ dependency_id: "dep", technology: "Example", docs_target: "1.2.3", status: "missing", reason: "no eligible matching version coverage", candidates: [] }] } }));
  await page.route("**/api/v1/projects/p1/documentation/dep/discover", (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_revision: 2, allow_public_lookup: true });
    expect(route.request().headers()["x-csrf-token"]).toBe("csrf-test");
    return route.fulfill({ json: { context_revision: 2, items: [{ source_url: "https://publisher.example/docs/guide", attribution: "Publisher", candidate_token: "bound-proposal" }] } });
  });
  await page.route("**/api/v1/projects/p1/documentation/dep/review-source", (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_revision: 2, candidate_token: "bound-proposal", coverage: { granularity: "major", version: "1" }, accept_fallback: true });
    return route.fulfill({ status: 202, json: { job_id: "job" } });
  });
  await page.goto("/?project=p1&conversation=c1");
  await page.getByRole("textbox", { name: "Your message" }).fill("Keep my draft");
  await page.getByText("Project documentation", { exact: true }).click();
  await page.getByText("Find another source", { exact: true }).click();
  const discover = page.getByRole("button", { name: "Find publisher sources" });
  await expect(discover).toBeDisabled();
  await page.getByRole("checkbox", { name: "Send Example 1.2.3 to its public package registry" }).check();
  await discover.click();
  await expect(page.getByRole("link", { name: "Review publisher documentation" })).toHaveAttribute("href", "https://publisher.example/docs/guide");
  await page.getByLabel("Actual documentation coverage").selectOption("major");
  await page.getByLabel("Documented version").fill("1");
  const approve = page.getByRole("button", { name: "Approve for this project" });
  await expect(approve).toBeDisabled();
  await page.getByRole("checkbox", { name: "I reviewed this publisher source and its version coverage" }).check();
  await page.getByRole("checkbox", { name: "I accept broader documentation for Example 1.2.3" }).check();
  await approve.click();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue("Keep my draft");
});
