import { describe, it, expect } from "vitest";
import { contactFormSchema, serviceRequestSchema } from "@/lib/validations";

describe("contactFormSchema", () => {
  it("validates a correct contact form submission", () => {
    const valid = {
      name: "John Doe",
      email: "john@example.com",
      subject: "Project inquiry",
      message: "I need a new website built for my business, can you help?",
    };
    const result = contactFormSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });

  it("rejects missing name", () => {
    const invalid = {
      name: "",
      email: "john@example.com",
      subject: "Hello",
      message: "I need a new website built for my business",
    };
    const result = contactFormSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it("rejects invalid email", () => {
    const invalid = {
      name: "John",
      email: "not-an-email",
      subject: "Hello there",
      message: "I need a new website built for my business",
    };
    const result = contactFormSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it("rejects short subject", () => {
    const invalid = {
      name: "John",
      email: "john@example.com",
      subject: "Hi",
      message: "I need a new website built for my business",
    };
    const result = contactFormSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it("rejects short message", () => {
    const invalid = {
      name: "John",
      email: "john@example.com",
      subject: "Hello there",
      message: "Short",
    };
    const result = contactFormSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });
});

describe("serviceRequestSchema", () => {
  it("validates a correct service request", () => {
    const valid = {
      name: "Jane Smith",
      email: "jane@company.com",
      company: "Acme Corp",
      phone: "+1234567890",
      serviceId: "some-uuid-here",
      budget: "2.5k-5k",
      timeline: "1-month",
      description: "We need a custom web application for managing our inventory and orders.",
    };
    const result = serviceRequestSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });

  it("allows optional fields to be omitted", () => {
    const valid = {
      name: "Jane Smith",
      email: "jane@company.com",
      serviceId: "some-uuid-here",
      description: "We need a custom web application for managing our inventory.",
    };
    const result = serviceRequestSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });

  it("rejects missing serviceId", () => {
    const invalid = {
      name: "Jane",
      email: "jane@company.com",
      serviceId: "",
      description: "We need a custom web application for managing our inventory.",
    };
    const result = serviceRequestSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it("rejects short description", () => {
    const invalid = {
      name: "Jane",
      email: "jane@company.com",
      serviceId: "some-uuid",
      description: "Too short",
    };
    const result = serviceRequestSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });
});
