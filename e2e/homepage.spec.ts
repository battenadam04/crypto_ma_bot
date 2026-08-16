import { test, expect } from "@playwright/test";

test.describe("Homepage", () => {
  test("loads and displays hero section", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Adam Batten/);

    const hero = page.locator("h1");
    await expect(hero).toContainText("Digital Experiences");
    await expect(hero).toContainText("Drive Growth");
  });

  test("displays first-time user offer with discount code", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("WELCOME20", { exact: true })).toBeVisible();
    await expect(page.getByText("20% off your first project")).toBeVisible();
  });

  test("displays stats section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("50+")).toBeVisible();
    await expect(page.getByText("Projects Delivered")).toBeVisible();
    await expect(page.getByText("98%")).toBeVisible();
    await expect(page.getByText("Client Satisfaction")).toBeVisible();
  });

  test("displays featured projects section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Featured Projects")).toBeVisible();
    await expect(page.getByRole("heading", { name: "E-Commerce Platform" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "SaaS Analytics Dashboard" })).toBeVisible();
  });

  test("displays services overview section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("My Services")).toBeVisible();
    await expect(page.getByText("SEO Landing Page")).toBeVisible();
  });

  test("displays testimonials section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("What My Clients Say")).toBeVisible();
    await expect(page.getByText("Sarah Chen")).toBeVisible();
  });

  test("displays CTA section with offer", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByText("Ready to Build Something Amazing?"),
    ).toBeVisible();
  });

  test("has proper meta description for SEO", async ({ page }) => {
    await page.goto("/");
    const metaDescription = page.locator('meta[name="description"]');
    await expect(metaDescription).toHaveAttribute("content", /web applications/i);
  });
});
