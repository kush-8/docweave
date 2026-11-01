import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "../support/api";

test("waiting turns resume and citations request authorized evidence", async ({ page }) => {
  await mockApi(page, { waiting: true }); await page.goto("/?project=p1&conversation=c1");
  await page.getByRole("textbox", { name: "Your message" }).fill("How does the API work?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Waiting for required documentation.", { exact: false })).toBeVisible();
  await expect(page.getByText("Use the documented API.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Source: API documentation" }).click();
  const sheet = page.getByRole("dialog", { name: "Sources", exact: true });
  await expect(sheet.getByText("An exact authorized excerpt.")).toBeVisible();
  await page.reload(); await expect(sheet.getByText("An exact authorized excerpt.")).toBeVisible();
  await page.keyboard.press("Escape"); await expect(sheet).not.toBeVisible();
});
for (const width of [320, 768, 1024]) {
  test(`responsive layout, theme and accessibility at ${width}px`, async ({ page }) => {
    await mockApi(page); await page.setViewportSize({ width, height: 900 });
    await page.goto("/?project=p1&conversation=c1");
    await expect(page.getByRole("textbox", { name: "Your message" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Dark mode", exact: true }).click();
    await page.reload(); await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    if (width < 768) {
      await page.getByRole("button", { name: "Show sidebar" }).click();
      const sidebar = page.getByRole("dialog", { name: "Your chats", exact: true });
      await sidebar.getByRole("link", { name: "My repository", exact: true }).click();
      await expect(sidebar).not.toBeVisible();
    }
  });
}
test("unavailable API shows an honest connection failure", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.fulfill({ contentType: "text/html", body: "<html>fallback</html>" }));
  await page.goto("/"); await expect(page.getByRole("alert")).toContainText("API is unavailable");
  await expect(page.getByRole("article")).toHaveCount(0);
});

test("blocked repository sync retries asynchronously in the same chat", async ({ page }) => {
  await mockApi(page);
  let status = "blocked";
  let polls = 0;
  await page.route("**/api/v1/conversations/c1", async (route) => {
    if (status === "initializing" && ++polls > 1) status = "ready";
    await route.fulfill({ json: { id: "c1", status, progress: status === "blocked" ? "Dependency metadata is incomplete. Correct it, then retry." : null } });
  });
  await page.route("**/api/v1/conversations/c1/sync-retry", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-csrf-token"]).toBe("csrf-test");
    status = "initializing";
    await route.fulfill({ status: 202, json: { id: "c1", status } });
  });
  await page.goto("/?project=p1&conversation=c1");
  await expect(page.getByText("Dependency metadata is incomplete.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Retry repository sync", exact: true }).click();
  await expect(page.getByText("Checking the repository and preparing project context…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry repository sync", exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Your message" })).toBeEnabled();
  expect(new URL(page.url()).searchParams.get("conversation")).toBe("c1");
});
