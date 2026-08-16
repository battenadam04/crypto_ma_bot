import { test, expect } from "@playwright/test";

test.describe("Contact Form", () => {
  test("displays contact form on contact page", async ({ page }) => {
    await page.goto("/contact");
    await expect(page.getByLabel("Name")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Subject")).toBeVisible();
    await expect(page.getByLabel("Message")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Send Message" }),
    ).toBeVisible();
  });

  test("shows validation errors for empty submission", async ({ page }) => {
    await page.goto("/contact");
    await page.getByRole("button", { name: "Send Message" }).click();

    await expect(page.getByText(/at least 2 characters/)).toBeVisible();
  });

  test("shows validation error for invalid email", async ({ page }) => {
    await page.goto("/contact");
    await page.getByLabel("Name").fill("John Doe");
    await page.getByLabel("Email").fill("invalid-email");
    await page.getByLabel("Subject").fill("Test Subject");
    await page.getByLabel("Message").fill("This is a test message that is long enough to pass validation.");
    await page.getByRole("button", { name: "Send Message" }).click();

    await expect(page.getByText(/valid email/)).toBeVisible();
  });

  test("submits contact form successfully", async ({ page }) => {
    await page.goto("/contact");
    await page.getByLabel("Name").fill("John Doe");
    await page.getByLabel("Email").fill("john@example.com");
    await page.getByLabel("Subject").fill("Project Inquiry");
    await page
      .getByLabel("Message")
      .fill(
        "I am interested in building a new web application for my business. Can you help?",
      );
    await page.getByRole("button", { name: "Send Message" }).click();

    await expect(page.getByText(/message has been sent/)).toBeVisible({
      timeout: 10000,
    });
  });

  test("displays contact info cards", async ({ page }) => {
    await page.goto("/contact");
    const main = page.getByRole("main");
    await expect(main.getByText("Northern Ireland")).toBeVisible();
    await expect(main.getByText("Within 24 hours")).toBeVisible();
    await expect(main.getByText("Contact form").first()).toBeVisible();
  });
});
