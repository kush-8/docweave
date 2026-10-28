import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("citations select exact sample evidence and survive reload and history", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByText("Interactive preview", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Source 2: Retrieval pipeline" })
    .first()
    .click();
  await expect(page).toHaveURL(/citation=2/);
  const evidence = page.getByRole("region", { name: "Evidence inspector" });
  await expect(
    evidence.getByRole("heading", { name: "Retrieval pipeline", exact: true }),
  ).toBeFocused();
  await expect(
    evidence.getByText(/Filter candidate chunks by the active workspace/),
  ).toBeVisible();
  await page.reload();
  await expect(
    evidence.getByRole("heading", { name: "Retrieval pipeline", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Source 1: Workspace access rules" })
    .first()
    .click();
  await page.goBack();
  await expect(
    evidence.getByRole("heading", { name: "Retrieval pipeline", exact: true }),
  ).toBeVisible();
});

test("new conversations select a provider; unavailable sends retain private drafts", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requests.push(request.url());
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Start with your project." }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Answer provider" }).click();
  await page.getByRole("option", { name: "Groq", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("Keep this private draft <script>test</script>");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Your draft has not been sent",
  );
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "Keep this private draft <script>test</script>",
  );
  await expect(page).not.toHaveURL(/private|script/);
  await page.locator("summary").filter({ hasText: "New conversation" }).click();
  await page
    .getByRole("link", { name: "Workspace isolation", exact: true })
    .click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "Keep this private draft <script>test</script>",
  );
  expect(requests).toEqual([]);
});

test("theme follows OS until overridden and survives reload", async ({
  page,
}) => {
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
    Storage.prototype.getItem = () => {
      throw new Error("Storage unavailable");
    };
    Storage.prototype.setItem = () => {
      throw new Error("Storage unavailable");
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

for (const width of [320, 768, 1024]) {
  test(`evidence is a dismissible keyboard-contained sheet at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const citation = page
      .getByRole("link", { name: "Source 1: Workspace access rules" })
      .first();
    await citation.click();
    const sheet = page.getByRole("dialog", { name: "Evidence inspector" });
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Tab");
    expect(
      await sheet.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
    await sheet
      .getByRole("link", { name: "Source 2: Retrieval pipeline" })
      .click();
    await expect(
      sheet.getByRole("heading", { name: "Retrieval pipeline", exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).not.toBeVisible();
    await expect(citation).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
}

test("light, dark, and mobile views are accessible and render without console errors", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.goto("/?conversation=sample&citation=1");
  await expect(
    page.getByRole("heading", { name: "Workspace access rules", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workbench-light.png",
    fullPage: true,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await page.screenshot({
    path: "test-results/workbench-dark.png",
    fullPage: true,
  });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.setViewportSize({ width: 375, height: 900 });
  await expect(
    page.getByRole("dialog", { name: "Evidence inspector" }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/workbench-mobile-evidence.png" });
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.keyboard.press("Escape");
  await page.screenshot({
    path: "test-results/workbench-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("empty sends validate and code copies verbatim", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "Enter a message before sending.",
  );
  await expect(
    page.getByRole("textbox", { name: "Your message" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Copy code", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "workspace_id = :workspace_id",
  );
});

test("browser Back protects a draft and discard returns to the previous conversation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("Unsent question");
  await page.goBack();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep writing" }).click();
  await expect(
    page.getByRole("heading", { name: "Start with your project." }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "Unsent question",
  );
  await page.goBack();
  await page
    .getByRole("button", { name: "Discard draft", exact: true })
    .click();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "",
  );
  await expect(
    page.getByRole("article", { name: "Sample assistant response" }),
  ).toBeVisible();
});

test("Back restores a closed desktop inspector", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("link", { name: "Source 1: Workspace access rules" })
    .first()
    .click();
  await page.getByRole("button", { name: "Close evidence inspector" }).click();
  await expect(
    page.getByRole("region", { name: "Evidence inspector" }),
  ).not.toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("region", { name: "Evidence inspector" }),
  ).toBeVisible();
});
