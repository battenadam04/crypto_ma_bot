import { test, expect } from "@playwright/test";

test.describe("SEO", () => {
  test("homepage has correct meta tags", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Adam Batten/);
    
    const metaDescription = page.locator('meta[name="description"]');
    await expect(metaDescription).toHaveAttribute("content", /.+/);

    const ogTitle = page.locator('meta[property="og:title"]');
    await expect(ogTitle).toHaveAttribute("content", /Adam Batten/);

    const ogDescription = page.locator('meta[property="og:description"]');
    await expect(ogDescription).toHaveAttribute("content", /.+/);
  });

  test("sitemap.xml is accessible", async ({ request }) => {
    const response = await request.get("/sitemap.xml");
    expect(response.status()).toBe(200);

    const body = await response.text();
    expect(body).toContain("<urlset");
    expect(body).toContain("<loc>");
    expect(body).toContain("/portfolio");
    expect(body).toContain("/services");
    expect(body).toContain("/about");
    expect(body).toContain("/contact");
  });

  test("robots.txt is accessible", async ({ request }) => {
    const response = await request.get("/robots.txt");
    expect(response.status()).toBe(200);

    const body = await response.text();
    expect(body).toContain("User-Agent");
    expect(body).toContain("Allow: /");
    expect(body).toContain("Disallow: /api/");
    expect(body).toContain("sitemap.xml");
  });

  test("pages have unique titles", async ({ page }) => {
    const titles: string[] = [];

    for (const path of ["/", "/portfolio", "/services", "/about", "/contact"]) {
      await page.goto(path);
      const title = await page.title();
      expect(titles).not.toContain(title);
      titles.push(title);
    }
  });

  test("security headers are set", async ({ request }) => {
    const response = await request.get("/");
    const headers = response.headers();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["referrer-policy"]).toBe(
      "strict-origin-when-cross-origin",
    );
  });
});
