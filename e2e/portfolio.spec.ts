import { test, expect } from "@playwright/test";

test.describe("Portfolio Page", () => {
  test("displays all projects", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByRole("heading", { name: "E-Commerce Platform" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "SaaS Analytics Dashboard" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Healthcare Booking System" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Real Estate Marketplace" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fitness Tracking App" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Restaurant Management System" })).toBeVisible();
  });

  test("has filter buttons for tags", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(
      page.getByRole("button", { name: "All Projects" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Next.js" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "TypeScript" }),
    ).toBeVisible();
  });

  test("filters projects by tag", async ({ page }) => {
    await page.goto("/portfolio");

    await page.getByRole("button", { name: "React Native" }).click();
    await expect(page.getByRole("heading", { name: "Fitness Tracking App" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "E-Commerce Platform" })).not.toBeVisible();

    await page.getByRole("button", { name: "All Projects" }).click();
    await expect(page.getByRole("heading", { name: "E-Commerce Platform" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fitness Tracking App" })).toBeVisible();
  });

  test("displays project tags as badges", async ({ page }) => {
    await page.goto("/portfolio");
    const projectCard = page.getByText("E-Commerce Platform").locator("..");
    await expect(projectCard).toBeVisible();
  });

  test("has proper page title", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page).toHaveTitle(/Portfolio/);
  });
});
