import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("header is visible with logo", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation");
    await expect(nav.getByRole("link", { name: /DevCraft/ })).toBeVisible();
  });

  test("navigates to Portfolio page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Portfolio" }).first().click();
    await expect(page).toHaveURL("/portfolio");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Portfolio");
  });

  test("navigates to Services page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Services" }).first().click();
    await expect(page).toHaveURL("/services");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Services");
  });

  test("navigates to About page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "About" }).first().click();
    await expect(page).toHaveURL("/about");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("DevCraft Studio");
  });

  test("navigates to Contact page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Contact" }).first().click();
    await expect(page).toHaveURL("/contact");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Touch");
  });

  test("footer has navigation links", async ({ page }) => {
    await page.goto("/");
    const footer = page.locator("footer");
    await expect(footer.getByRole("link", { name: "Portfolio" })).toBeVisible();
    await expect(footer.getByRole("link", { name: "Services" })).toBeVisible();
    await expect(footer.getByRole("link", { name: "Contact" })).toBeVisible();
  });

  test("footer displays company info", async ({ page }) => {
    await page.goto("/");
    const footer = page.locator("footer");
    await expect(footer.getByText("hello@devcraft.studio")).toBeVisible();
    await expect(footer.getByText(/All rights reserved/)).toBeVisible();
  });
});
