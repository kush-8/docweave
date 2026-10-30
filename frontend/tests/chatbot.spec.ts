import { expect, test } from "@playwright/test";

test("opens a simple chat with sources hidden", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "What can I help you with?" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Your message" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Project navigation" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Evidence inspector" })).toHaveCount(0);
  await expect(page.getByText(/inference profile|retrieval approval|synthetic architecture/i)).toHaveCount(0);
});

test("suggestions do not replace an unsent message", async ({ page }) => {
  await page.goto("/");
  const suggestion = page.getByRole("button", { name: "Summarize my project" });
  await suggestion.click();
  const input = page.getByRole("textbox", { name: "Your message" });
  await expect(input).toHaveValue("Summarize my project");
  await input.fill("My own question");
  await expect(suggestion).not.toBeVisible();
  await expect(input).toHaveValue("My own question");
});

test("new chat protects an existing draft even on an empty chat", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("My unsent question");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(input).toHaveValue("My unsent question");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await expect(input).toHaveValue("");
});

test("sidebar toggles and groups workspace chats above recent chats", async ({ page }) => {
  await page.goto("/");
  const sidebar = page.getByRole("complementary", { name: "Chat sidebar" });
  await expect(sidebar.getByRole("button", { name: "New chat", exact: true })).toBeVisible();
  const workspaces = sidebar.getByRole("navigation", { name: "Workspaces" });
  await expect(workspaces.getByRole("link", { name: "Team files", exact: true })).toBeVisible();
  await expect(sidebar.getByRole("navigation", { name: "Recent chats" }).getByRole("link", { name: "Team files", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Hide sidebar" }).click();
  await expect(sidebar).not.toBeVisible();
  await page.getByRole("button", { name: "Show sidebar" }).click();
  await expect(sidebar).toBeVisible();
  await workspaces.locator("summary").filter({ hasText: "Engineering" }).click();
  await expect(workspaces.getByRole("link", { name: "Team files", exact: true })).not.toBeVisible();
});

test("mobile sidebar closes after choosing a workspace", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "Show sidebar" }).click();
  const sidebar = page.getByRole("dialog", { name: "Your chats", exact: true });
  await expect(sidebar).toBeVisible();
  await page.keyboard.press("Tab");
  expect(await sidebar.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await sidebar.locator("summary").filter({ hasText: "Personal" }).click();
  await sidebar.getByRole("link", { name: "Start a chat" }).click();
  await expect(sidebar).not.toBeVisible();
  await expect(page).toHaveURL(/workspace=personal/);
  await expect(page.getByRole("heading", { name: "What can I help you with?" })).toBeVisible();
  await page.getByRole("button", { name: "Show sidebar" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Show sidebar" })).toBeFocused();
});

test("switching workspaces protects drafts and browser Back restores the workspace", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Engineering question");
  const workspaces = page.getByRole("navigation", { name: "Workspaces" });
  await workspaces.locator("summary").filter({ hasText: "Personal" }).click();
  await workspaces.getByRole("link", { name: "Start a chat" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(input).toHaveValue("Engineering question");
  await workspaces.getByRole("link", { name: "Start a chat" }).click();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await expect(input).toHaveValue("");
  await expect(page).toHaveURL(/workspace=personal/);
  await input.fill("Personal question");
  await page.goBack();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await expect(page).not.toHaveURL(/workspace=personal/);
  await expect(input).toHaveValue("");
});
