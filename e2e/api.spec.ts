import { test, expect } from "@playwright/test";

test.describe("API Endpoints", () => {
  test("GET /api/projects returns projects", async ({ request }) => {
    const response = await request.get("/api/projects");
    expect(response.status()).toBe(200);

    const projects = await response.json();
    expect(Array.isArray(projects)).toBe(true);
    expect(projects.length).toBeGreaterThan(0);
    expect(projects[0]).toHaveProperty("title");
    expect(projects[0]).toHaveProperty("slug");
    expect(projects[0]).toHaveProperty("description");
    expect(projects[0]).toHaveProperty("tags");
  });

  test("GET /api/services returns services", async ({ request }) => {
    const response = await request.get("/api/services");
    expect(response.status()).toBe(200);

    const services = await response.json();
    expect(Array.isArray(services)).toBe(true);
    expect(services.length).toBeGreaterThan(0);
    expect(services[0]).toHaveProperty("title");
    expect(services[0]).toHaveProperty("priceFrom");
    expect(services[0]).toHaveProperty("priceTo");
    expect(services[0]).toHaveProperty("estimatedDays");
  });

  test("POST /api/contact creates a contact message", async ({ request }) => {
    const response = await request.post("/api/contact", {
      data: {
        name: "E2E Test User",
        email: "e2e@test.com",
        subject: "E2E Test Subject",
        message: "This is an automated E2E test message for validation purposes.",
      },
    });
    expect(response.status()).toBe(201);

    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.id).toBeDefined();
  });

  test("POST /api/contact validates input", async ({ request }) => {
    const response = await request.post("/api/contact", {
      data: {
        name: "",
        email: "bad-email",
        subject: "Hi",
        message: "Short",
      },
    });
    expect(response.status()).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("Validation failed");
  });

  test("POST /api/service-requests creates a service request", async ({
    request,
  }) => {
    const servicesRes = await request.get("/api/services");
    const services = await servicesRes.json();
    const serviceId = services[0].id;

    const response = await request.post("/api/service-requests", {
      data: {
        name: "E2E Test Client",
        email: "client@e2e.com",
        company: "Test Corp",
        serviceId,
        budget: "10k-25k",
        timeline: "1-month",
        description:
          "This is an automated E2E test service request for validation.",
      },
    });
    expect(response.status()).toBe(201);

    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.id).toBeDefined();
    expect(body.estimate).toBeDefined();
    expect(body.estimate.priceFrom).toBeDefined();
    expect(body.estimate.priceTo).toBeDefined();
    expect(body.estimate.estimatedDays).toBeDefined();
  });

  test("POST /api/service-requests validates input", async ({ request }) => {
    const response = await request.post("/api/service-requests", {
      data: {
        name: "",
        email: "bad",
        serviceId: "",
        description: "Short",
      },
    });
    expect(response.status()).toBe(400);
  });

  test("POST /api/service-requests rejects invalid service", async ({
    request,
  }) => {
    const response = await request.post("/api/service-requests", {
      data: {
        name: "Test User",
        email: "test@example.com",
        serviceId: "nonexistent-id",
        description:
          "This request has an invalid service ID and should be rejected.",
      },
    });
    expect(response.status()).toBe(400);
  });

  test("GET /api/contact returns contact messages", async ({ request }) => {
    const response = await request.get("/api/contact");
    expect(response.status()).toBe(200);

    const messages = await response.json();
    expect(Array.isArray(messages)).toBe(true);
  });

  test("GET /api/service-requests returns requests", async ({ request }) => {
    const response = await request.get("/api/service-requests");
    expect(response.status()).toBe(200);

    const requests = await response.json();
    expect(Array.isArray(requests)).toBe(true);
  });
});
