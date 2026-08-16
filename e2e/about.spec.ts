import { test, expect } from "@playwright/test";

test.describe("About Page", () => {
  test("displays company introduction", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "DevCraft Studio",
    );
    await expect(page.getByText(/passionate team/)).toBeVisible();
  });

  test("displays company values", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByText("What Drives Us")).toBeVisible();
    await expect(page.getByText("Quality First")).toBeVisible();
    await expect(page.getByText("Transparent Communication")).toBeVisible();
    await expect(page.getByText("Innovation Driven")).toBeVisible();
    await expect(page.getByText("Client Success")).toBeVisible();
  });

  test("displays process steps", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByText("How We Work")).toBeVisible();
    await expect(page.getByText("Discovery")).toBeVisible();
    await expect(page.getByText("Design").first()).toBeVisible();
    await expect(page.getByText("Development")).toBeVisible();
    await expect(page.getByText("Testing & Launch")).toBeVisible();
  });

  test("displays tech stack", async ({ page }) => {
    await page.goto("/about");
    await expect(page.getByText("Technologies We Use")).toBeVisible();
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Next.js").first()).toBeVisible();
    await expect(page.getByText("TypeScript").first()).toBeVisible();
  });

  test("has CTA buttons", async ({ page }) => {
    await page.goto("/about");
    await expect(
      page.getByRole("link", { name: /Free Quote/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Contact Us/ }),
    ).toBeVisible();
  });

  test("has proper page title", async ({ page }) => {
    await page.goto("/about");
    await expect(page).toHaveTitle(/About/);
  });
});
