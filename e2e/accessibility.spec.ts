import { test, expect } from "@playwright/test";

test.describe("Accessibility", () => {
  test("skip-to-content link is present and works via keyboard", async ({ page }) => {
    await page.goto("/");
    const skipLink = page.getByRole("link", { name: "Skip to main content" });
    await expect(skipLink).toBeAttached();

    await page.keyboard.press("Tab");
    await expect(skipLink).toBeFocused();
    await expect(skipLink).toBeVisible();

    await page.keyboard.press("Enter");
    const main = page.locator("#main-content");
    await expect(main).toBeAttached();
  });

  test("main landmark exists on every page", async ({ page }) => {
    for (const path of ["/", "/portfolio", "/services", "/about", "/contact"]) {
      await page.goto(path);
      const main = page.getByRole("main");
      await expect(main).toBeAttached();
    }
  });

  test("navigation landmark has aria-label", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator('nav[aria-label="Main navigation"]');
    await expect(nav).toBeAttached();
  });

  test("nav links have aria-current on active page", async ({ page }) => {
    await page.goto("/portfolio");
    const activeLink = page.locator('a[aria-current="page"]', {
      hasText: "Portfolio",
    });
    await expect(activeLink).toBeAttached();
  });

  test("mobile menu button has aria-expanded and aria-controls", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/");
    const menuBtn = page.getByLabel(/navigation menu/);
    await expect(menuBtn).toHaveAttribute("aria-expanded", "false");
    await expect(menuBtn).toHaveAttribute("aria-controls", "mobile-menu");

    await menuBtn.click();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "true");
  });

  test("form inputs have associated labels", async ({ page }) => {
    await page.goto("/contact");
    const nameInput = page.getByLabel("Name");
    await expect(nameInput).toBeAttached();
    const emailInput = page.getByLabel("Email");
    await expect(emailInput).toBeAttached();
    const subjectInput = page.getByLabel("Subject");
    await expect(subjectInput).toBeAttached();
    const messageTextarea = page.getByLabel("Message");
    await expect(messageTextarea).toBeAttached();
  });

  test("required fields have aria-required", async ({ page }) => {
    await page.goto("/services#request");
    const nameInput = page.getByLabel("Full Name *");
    await expect(nameInput).toHaveAttribute("aria-required", "true");
    const emailInput = page.getByLabel("Email *");
    await expect(emailInput).toHaveAttribute("aria-required", "true");
    const serviceSelect = page.getByLabel("Service *");
    await expect(serviceSelect).toHaveAttribute("aria-required", "true");
    const descriptionTextarea = page.getByLabel("Project Description *");
    await expect(descriptionTextarea).toHaveAttribute("aria-required", "true");
  });

  test("invalid fields get aria-invalid and aria-describedby", async ({ page }) => {
    await page.goto("/contact");
    await page.getByRole("button", { name: "Send Message" }).click();

    const nameInput = page.getByLabel("Name");
    await expect(nameInput).toHaveAttribute("aria-invalid", "true");

    const errorId = await nameInput.getAttribute("aria-describedby");
    expect(errorId).toBeTruthy();
    const errorEl = page.locator(`#${errorId}`);
    await expect(errorEl).toBeVisible();
    await expect(errorEl).toHaveAttribute("role", "alert");
  });

  test("submit button shows aria-busy when loading", async ({ page }) => {
    await page.goto("/contact");
    await page.getByLabel("Name").fill("John Doe");
    await page.getByLabel("Email").fill("john@example.com");
    await page.getByLabel("Subject").fill("Test Subject Here");
    await page.getByLabel("Message").fill("This is a test message that is long enough to pass validation checks.");

    await page.route("/api/contact", async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.fulfill({ status: 201, json: { success: true, id: "test" } });
    });

    const submitBtn = page.getByRole("button", { name: "Send Message" });
    await submitBtn.click();
    await expect(submitBtn).toHaveAttribute("aria-busy", "true");
  });

  test("success message is announced to screen readers", async ({ page }) => {
    await page.goto("/contact");
    await page.getByLabel("Name").fill("John Doe");
    await page.getByLabel("Email").fill("john@example.com");
    await page.getByLabel("Subject").fill("Test Subject Here");
    await page.getByLabel("Message").fill("This is a test message that is long enough to pass validation checks.");
    await page.getByRole("button", { name: "Send Message" }).click();

    const liveRegion = page.locator('[aria-live="polite"]');
    await expect(liveRegion).toBeAttached();
    await expect(liveRegion.getByRole("status")).toBeVisible({ timeout: 10000 });
  });

  test("service request form has fieldset and legend", async ({ page }) => {
    await page.goto("/services#request");
    const fieldsets = page.locator("fieldset");
    const count = await fieldsets.count();
    expect(count).toBeGreaterThanOrEqual(2);

    const legends = page.locator("legend");
    await expect(legends.first()).toContainText("Your Details");
  });

  test("pricing estimate region has aria-label", async ({ page }) => {
    await page.goto("/services#request");
    await page.getByLabel("Service *").selectOption({ index: 1 });

    const region = page.locator('[aria-label="Pricing estimate for selected service"]');
    await expect(region).toBeVisible();
  });

  test("decorative icons have aria-hidden", async ({ page }) => {
    await page.goto("/services");
    const hiddenSvgs = page.locator('svg[aria-hidden="true"]');
    const count = await hiddenSvgs.count();
    expect(count).toBeGreaterThan(0);
  });

  test("images and decorative elements are hidden from AT", async ({ page }) => {
    await page.goto("/");
    const headerLogo = page.locator('nav a[aria-label="Adam Batten home"] div[aria-hidden="true"]');
    await expect(headerLogo).toBeAttached();
  });

  test("footer has descriptive aria-label", async ({ page }) => {
    await page.goto("/");
    const footer = page.locator('footer[aria-label="Site footer"]');
    await expect(footer).toBeAttached();
  });

  test("all pages have h1 heading", async ({ page }) => {
    for (const path of ["/", "/portfolio", "/services", "/about", "/contact"]) {
      await page.goto(path);
      const h1 = page.locator("h1");
      const count = await h1.count();
      expect(count).toBe(1);
    }
  });

  test("form autocomplete attributes are set for personal fields", async ({ page }) => {
    await page.goto("/services#request");
    const nameInput = page.getByLabel("Full Name *");
    await expect(nameInput).toHaveAttribute("autocomplete", "name");
    const emailInput = page.getByLabel("Email *");
    await expect(emailInput).toHaveAttribute("autocomplete", "email");
    const phoneInput = page.getByLabel("Phone");
    await expect(phoneInput).toHaveAttribute("autocomplete", "tel");
    const companyInput = page.getByLabel("Company");
    await expect(companyInput).toHaveAttribute("autocomplete", "organization");
  });
});
