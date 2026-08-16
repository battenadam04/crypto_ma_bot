import { describe, expect, it } from "vitest";
import {
  portalOtpRequestSchema,
  portalOtpVerifySchema,
  portalCreateSchema,
  portalMessageSchema,
} from "@/lib/portal-validations";

describe("portal validations", () => {
  it("accepts a valid OTP request email", () => {
    expect(
      portalOtpRequestSchema.safeParse({ email: "client@example.com" }).success,
    ).toBe(true);
  });

  it("requires a 6-digit PIN", () => {
    expect(
      portalOtpVerifySchema.safeParse({
        email: "client@example.com",
        code: "12345",
      }).success,
    ).toBe(false);
    expect(
      portalOtpVerifySchema.safeParse({
        email: "client@example.com",
        code: "123456",
      }).success,
    ).toBe(true);
  });

  it("validates portal creation fields", () => {
    expect(
      portalCreateSchema.safeParse({
        title: "Landing page",
        clientName: "Alex",
        clientEmail: "alex@example.com",
      }).success,
    ).toBe(true);
  });

  it("rejects empty chat messages", () => {
    expect(portalMessageSchema.safeParse({ body: "   " }).success).toBe(false);
    expect(portalMessageSchema.safeParse({ body: "Hello" }).success).toBe(true);
  });
});
