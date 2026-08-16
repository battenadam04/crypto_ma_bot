import { afterEach, describe, expect, it, vi } from "vitest";

describe("email helpers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults CONTACT_TO_EMAIL to adambatten@live.co.uk", async () => {
    vi.stubEnv("CONTACT_TO_EMAIL", "");
    vi.stubEnv("RESEND_API_KEY", "");
    const { CONTACT_TO_EMAIL, isEmailConfigured } = await import("@/lib/email");
    expect(CONTACT_TO_EMAIL).toBe("adambatten@live.co.uk");
    expect(isEmailConfigured()).toBe(false);
  });

  it("detects when Resend is configured", async () => {
    vi.stubEnv("RESEND_API_KEY", "re_test_key");
    const { isEmailConfigured } = await import("@/lib/email");
    expect(isEmailConfigured()).toBe(true);
  });

  it("sends contact notification via Resend", async () => {
    vi.stubEnv("RESEND_API_KEY", "re_test_key");
    vi.stubEnv("CONTACT_TO_EMAIL", "adambatten@live.co.uk");

    const send = vi.fn().mockResolvedValue({
      data: { id: "email_123" },
      error: null,
    });

    vi.doMock("resend", () => ({
      Resend: class {
        emails = { send };
      },
    }));

    const { sendContactNotification } = await import("@/lib/email");
    const result = await sendContactNotification({
      name: "Jane Doe",
      email: "jane@example.com",
      subject: "Website quote",
      message: "Hello\nWorld",
    });

    expect(result.id).toBe("email_123");
    expect(send).toHaveBeenCalledOnce();
    const payload = send.mock.calls[0][0];
    expect(payload.to).toEqual(["adambatten@live.co.uk"]);
    expect(payload.replyTo).toBe("jane@example.com");
    expect(payload.subject).toContain("Website quote");
    expect(payload.html).toContain("Jane Doe");
    expect(payload.html).toContain("Hello<br />World");
  });
});
