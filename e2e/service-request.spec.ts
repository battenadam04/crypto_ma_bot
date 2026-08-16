import { test, expect } from "@playwright/test";

test.describe("Service Request Form", () => {
  test("displays the service request form", async ({ page }) => {
    await page.goto("/services#request");
    await expect(page.getByLabel("Full Name *")).toBeVisible();
    await expect(page.getByLabel("Email *")).toBeVisible();
    await expect(page.getByLabel("Service *")).toBeVisible();
    await expect(page.getByLabel("Project Description *")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Submit Request/ }),
    ).toBeVisible();
  });

  test("shows validation errors for empty required fields", async ({ page }) => {
    await page.goto("/services#request");
    await page.getByRole("button", { name: /Submit Request/ }).click();

    await expect(page.getByText(/at least 2 characters/)).toBeVisible();
  });

  test("shows pricing estimate when service is selected", async ({ page }) => {
    await page.goto("/services#request");
    await page.getByLabel("Service *").selectOption({ index: 1 });

    await expect(page.getByText("Estimated Price Range")).toBeVisible();
    await expect(page.getByText("Estimated Delivery")).toBeVisible();
  });

  test("submits service request successfully", async ({ page }) => {
    await page.goto("/services#request");

    await page.getByLabel("Full Name *").fill("Jane Smith");
    await page.getByLabel("Email *").fill("jane@company.com");
    await page.getByLabel("Company").fill("Acme Corp");
    await page.getByLabel("Service *").selectOption({ index: 1 });
    await page.getByLabel("Budget Range").selectOption({ index: 1 });
    await page.getByLabel("Preferred Timeline").selectOption({ index: 1 });
    await page
      .getByLabel("Project Description *")
      .fill(
        "We need a custom web application for inventory management with real-time tracking.",
      );
    await page.getByRole("button", { name: /Submit Request/ }).click();

    await expect(page.getByText(/request has been submitted/)).toBeVisible({
      timeout: 10000,
    });
  });
});
