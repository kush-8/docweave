import { expect, test } from "@playwright/test";
import { mockApi } from "../support/api";

test("GitHub sign in is the only login", async ({ page }) => {
  await mockApi(page, { signedOut: true }); await page.goto("/");
  await expect(page.getByRole("link", { name: "Sign in with GitHub" })).toHaveAttribute("href", "/api/v1/auth/login");
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveCount(0);
});
test("creates a repository-bound project and initializes a chat", async ({ page }) => {
  await mockApi(page); await page.goto("/");
  await page.getByLabel("Repository", { exact: true }).selectOption("42");
  await expect(page.getByLabel("Branch", { exact: true })).toHaveValue("main");
  await page.getByLabel("Project goal").fill("Build an API");
  const create = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/projects"));
  await page.getByRole("button", { name: "Create project" }).click();
  expect((await create).postDataJSON()).toEqual({ repository_id: 42, branch: "main", application_path: "", goal: "Build an API" });
  await page.getByRole("button", { name: "Start chat", exact: true }).click();
  await expect(page).toHaveURL(/conversation=c1/);
  await expect(page.getByRole("textbox", { name: "Your message" })).toBeVisible();
});
test("project navigation and New chat protect drafts", async ({ page }) => {
  await mockApi(page); await page.goto("/?project=p1&conversation=c1");
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Private unsent draft");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(input).toHaveValue("Private unsent draft");
  await page.getByRole("link", { name: "Add project", exact: true }).click();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create a project" })).toBeVisible();
});
test("failed sends preserve drafts and retry with one idempotency key", async ({ page }) => {
  await mockApi(page, { failSend: true }); await page.goto("/?project=p1&conversation=c1");
  const sent: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/turns")) { expect(request.headers()["x-csrf-token"]).toBe("csrf-test"); sent.push(request.postDataJSON().idempotency_key); } });
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Keep this private <script>alert(1)</script>");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Your draft is preserved");
  await expect(input).toHaveValue("Keep this private <script>alert(1)</script>");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => sent.length).toBe(2); expect(sent[0]).toBe(sent[1]);
  expect(await page.evaluate(() => Object.keys(localStorage))).not.toContain("draft");
  await expect(page).not.toHaveURL(/private|script/);
});

test("recent chats restore after reload and sign out protects the draft", async ({ page }) => {
  await mockApi(page); await page.goto("/?project=p1&conversation=c1");
  const recent = page.getByRole("navigation", { name: "Recent chats" });
  await expect(recent.getByRole("link", { name: "API chat" })).toBeVisible();
  await page.reload(); await expect(recent.getByRole("link", { name: "API chat" })).toBeVisible();
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Unsent private question");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(input).toHaveValue("Unsent private question");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  const logout = page.waitForRequest((request) => request.url().endsWith("/auth/logout"));
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  expect((await logout).headers()["x-csrf-token"]).toBe("csrf-test");
  await expect(page.getByRole("link", { name: "Sign in with GitHub" })).toBeVisible();
  await expect(recent.getByRole("link")).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveCount(0);
});


test("processing permissions require explicit selection and a protected update", async ({ page }) => {
  await mockApi(page); await page.goto("/?project=p1&conversation=new");
  await page.getByText("Processing permissions", { exact: true }).click();
  const choice = page.getByRole("checkbox", { name: "Groq · generation" });
  await expect(choice).not.toBeChecked();
  await choice.check();
  const saved = page.waitForRequest((request) => request.url().endsWith("/processing-policy") && request.method() === "PUT");
  await page.getByRole("button", { name: "Save permissions" }).click();
  const request = await saved;
  expect(request.headers()["x-csrf-token"]).toBe("csrf-test");
  expect(request.postDataJSON()).toEqual({ expected_revision: 1, approved_processor_ids: ["groq:configured"] });
  await expect(page.getByRole("status")).toContainText("Processing permissions saved.");
});
