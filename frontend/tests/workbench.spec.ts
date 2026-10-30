import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("sources select exact excerpts and survive reload and history", async ({ page }) => {
  await page.goto("/?conversation=sample");
  await page.getByRole("link", { name: "Source 2: Finding the right files" }).click();
  await expect(page).toHaveURL(/citation=2/);
  const sources = page.getByRole("dialog", { name: "Sources", exact: true });
  await expect(sources.getByRole("heading", { name: "Finding the right files", exact: true })).toBeFocused();
  await expect(sources.getByText(/Search only the files the current person can read/)).toBeVisible();
  await page.reload();
  await expect(sources.getByRole("heading", { name: "Finding the right files", exact: true })).toBeVisible();
  await sources.getByRole("link", { name: "Source 1: Who can see your files" }).click();
  await page.goBack();
  await expect(sources.getByRole("heading", { name: "Finding the right files", exact: true })).toBeVisible();
});

test("model choices stay in chat options and unsent drafts stay private", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/api/")) requests.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("combobox", { name: "Model" })).not.toBeVisible();
  await page.locator("summary").filter({ hasText: "Chat options" }).click();
  await page.getByRole("combobox", { name: "Model" }).click();
  await page.getByRole("option", { name: "Groq", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Keep this private draft <script>test</script>");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Your message hasn’t been sent.");
  await expect(input).toHaveValue("Keep this private draft <script>test</script>");
  await expect(input).toHaveAttribute("aria-invalid", "false");
  await expect(page).not.toHaveURL(/private|script/);
  expect(requests).toEqual([]);
});

test("theme follows OS until overridden and survives reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");
});

test("theme works when browser storage is unavailable", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error("Storage unavailable"); };
    Storage.prototype.setItem = () => { throw new Error("Storage unavailable"); };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

for (const width of [320, 768, 1024]) {
  test(`sources are keyboard-contained and dismissible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/?conversation=sample");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const citation = page.getByRole("link", { name: "Source 1: Who can see your files" });
    await citation.click();
    const sheet = page.getByRole("dialog", { name: "Sources", exact: true });
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Tab");
    expect(await sheet.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await sheet.getByRole("link", { name: "Source 2: Finding the right files" }).click();
    await expect(sheet.getByRole("heading", { name: "Finding the right files", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).not.toBeVisible();
    await expect(citation).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("light, dark, mobile chat and sources pass automated accessibility checks", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/");
  await page.screenshot({ path: "test-results/chatbot-light.png", fullPage: true });
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await page.screenshot({ path: "test-results/chatbot-dark.png", fullPage: true });
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.goto("/?conversation=sample&citation=1");
  await page.setViewportSize({ width: 375, height: 900 });
  await expect(page.getByRole("dialog", { name: "Sources", exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  await page.screenshot({ path: "test-results/chatbot-mobile.png", fullPage: true });
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
  expect(errors).toEqual([]);
});

test("empty messages validate and example answers copy verbatim", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/?conversation=sample");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Write a message first.");
  await expect(page.getByRole("textbox", { name: "Your message" })).toBeFocused();
  await page.getByRole("button", { name: "Copy answer" }).click();
  await expect(page.getByRole("status")).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("Keep each team’s files separate. Only use files that the person asking the question is allowed to read. Check access again before sharing an answer. If access is removed, stop using those files in the chat.");
});

test("browser Back protects a draft and discard restores the previous chat", async ({ page }) => {
  await page.goto("/?conversation=sample");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Your message" });
  await input.fill("Unsent question");
  await page.goBack();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(input).toHaveValue("Unsent question");
  await page.goBack();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await expect(input).toHaveValue("");
  await expect(page.getByRole("article", { name: "Example answer" })).toBeVisible();
});

test("closed sources stay closed after reload and Back restores them", async ({ page }) => {
  await page.goto("/?conversation=sample");
  await page.getByRole("link", { name: "Source 1: Who can see your files" }).click();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Sources", exact: true })).not.toBeVisible();
  await page.goBack();
  await expect(page.getByRole("dialog", { name: "Sources", exact: true })).toBeVisible();
});
