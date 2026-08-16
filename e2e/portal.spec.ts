import { test, expect } from "@playwright/test";

test.describe("Client portal OTP", () => {
  test("shows portal login", async ({ page }) => {
    await page.goto("/portal");
    await expect(page.getByRole("heading", { name: "Client portal" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByRole("button", { name: "Email me a PIN" })).toBeVisible();
  });

  test("demo client can request PIN and open workspace", async ({ page }) => {
    await page.goto("/portal");
    await page.getByLabel("Email").fill("client@example.com");
    await page.getByRole("button", { name: "Email me a PIN" }).click();

    await expect(page.getByLabel("6-digit PIN")).toBeVisible({ timeout: 10000 });
    const devHint = page.getByText(/Dev mode/);
    await expect(devHint).toBeVisible();
    const text = await devHint.textContent();
    const pin = text?.match(/\b(\d{6})\b/)?.[1];
    expect(pin).toBeTruthy();

    await page.getByLabel("6-digit PIN").fill(pin!);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/portal\/home/, { timeout: 10000 });
    await expect(page.getByText("Demo — SEO Landing Page")).toBeVisible();

    await page.getByRole("link", { name: /Demo — SEO Landing Page/ }).click();
    await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Progress" })).toBeVisible();
    await expect(page.getByText("Forgot PIN / send a new one")).toHaveCount(0);
  });

  test("forgot PIN control is available after requesting a code", async ({
    page,
  }) => {
    await page.goto("/portal");
    await page.getByLabel("Email").fill("client@example.com");
    await page.getByRole("button", { name: "Email me a PIN" }).click();
    await expect(
      page.getByRole("button", { name: "Forgot PIN / send a new one" }),
    ).toBeVisible();
  });
});
