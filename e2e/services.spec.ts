import { test, expect } from "@playwright/test";

test.describe("Services Page", () => {
  test("displays all services with pricing", async ({ page }) => {
    await page.goto("/services");

    await expect(page.getByRole("heading", { name: "SEO Landing Page" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Website Fixes & Improvements" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Online Store / E-Commerce" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Custom Web Application" })).toBeVisible();

    await expect(page.getByText("£650").first()).toBeVisible();
    await expect(page.getByText("£200").first()).toBeVisible();
  });

  test("toggles pricing between GBP and USD", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByText("£650").first()).toBeVisible();

    await page.getByRole("button", { name: "$ USD" }).first().click();
    // £650 × 1.27 ≈ $826
    await expect(page.getByText("$826").first()).toBeVisible();

    await page.getByRole("button", { name: "£ GBP" }).first().click();
    await expect(page.getByText("£650").first()).toBeVisible();
  });

  test("displays estimated delivery times", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByText("~8 days").first()).toBeVisible();
    await expect(page.getByText("~25 days").first()).toBeVisible();
  });

  test("shows popular badges on popular services", async ({ page }) => {
    await page.goto("/services");
    const popularBadges = page.getByText("Most Popular");
    const count = await popularBadges.count();
    expect(count).toBeGreaterThan(0);
  });

  test("displays service features", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByText("On-page SEO (titles, meta, headings, schema)").first()).toBeVisible();
    await expect(page.getByText("Bug & broken-link fixes").first()).toBeVisible();
  });

  test("displays first-time offer banner", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByText("WELCOME20")).toBeVisible();
  });

  test("has service request form section", async ({ page }) => {
    await page.goto("/services");
    await expect(page.getByText("Request a Service")).toBeVisible();
  });

  test("has proper page title", async ({ page }) => {
    await page.goto("/services");
    await expect(page).toHaveTitle(/Services/);
  });
});
