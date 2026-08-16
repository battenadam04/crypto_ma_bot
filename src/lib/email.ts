import { Resend } from "resend";
import type { ContactFormData } from "@/lib/validations";

/** Inbox for contact + service-request notifications */
export const CONTACT_TO_EMAIL =
  process.env.CONTACT_TO_EMAIL?.trim() || "adambatten@live.co.uk";

const FROM_EMAIL =
  process.env.CONTACT_FROM_EMAIL?.trim() ||
  "Adam Batten Portfolio <onboarding@resend.dev>";

function getResend(): Resend | null {
  const key = process.env.RESEND_API_KEY?.trim();
  if (!key) return null;
  return new Resend(key);
}

export function isEmailConfigured(): boolean {
  return Boolean(process.env.RESEND_API_KEY?.trim());
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMultiline(value: string): string {
  return escapeHtml(value).replaceAll("\n", "<br />");
}

export async function sendContactNotification(
  data: ContactFormData,
): Promise<{ id: string }> {
  const resend = getResend();
  if (!resend) {
    throw new Error("Email is not configured (missing RESEND_API_KEY)");
  }

  const subject = `[Portfolio] ${data.subject}`;
  const text = [
    `New contact form message`,
    ``,
    `Name: ${data.name}`,
    `Email: ${data.email}`,
    `Subject: ${data.subject}`,
    ``,
    data.message,
  ].join("\n");

  const html = `
    <div style="font-family: system-ui, sans-serif; line-height: 1.5; color: #0f172a;">
      <h2 style="margin: 0 0 12px;">New contact form message</h2>
      <p style="margin: 0 0 8px;"><strong>Name:</strong> ${escapeHtml(data.name)}</p>
      <p style="margin: 0 0 8px;"><strong>Email:</strong> ${escapeHtml(data.email)}</p>
      <p style="margin: 0 0 16px;"><strong>Subject:</strong> ${escapeHtml(data.subject)}</p>
      <div style="padding: 16px; background: #f8fafc; border-radius: 8px;">
        ${formatMultiline(data.message)}
      </div>
    </div>
  `;

  const { data: result, error } = await resend.emails.send({
    from: FROM_EMAIL,
    to: [CONTACT_TO_EMAIL],
    replyTo: data.email,
    subject,
    text,
    html,
  });

  if (error) {
    throw new Error(error.message || "Failed to send email");
  }

  return { id: result?.id ?? "sent" };
}

export async function sendServiceRequestNotification(input: {
  name: string;
  email: string;
  company?: string | null;
  serviceTitle: string;
  budget: string;
  timeline: string;
  description: string;
}): Promise<{ id: string }> {
  const resend = getResend();
  if (!resend) {
    throw new Error("Email is not configured (missing RESEND_API_KEY)");
  }

  const subject = `[Portfolio] Service request — ${input.serviceTitle}`;
  const text = [
    `New service request`,
    ``,
    `Name: ${input.name}`,
    `Email: ${input.email}`,
    `Company: ${input.company || "—"}`,
    `Service: ${input.serviceTitle}`,
    `Budget: ${input.budget}`,
    `Timeline: ${input.timeline}`,
    ``,
    input.description,
  ].join("\n");

  const html = `
    <div style="font-family: system-ui, sans-serif; line-height: 1.5; color: #0f172a;">
      <h2 style="margin: 0 0 12px;">New service request</h2>
      <p style="margin: 0 0 8px;"><strong>Name:</strong> ${escapeHtml(input.name)}</p>
      <p style="margin: 0 0 8px;"><strong>Email:</strong> ${escapeHtml(input.email)}</p>
      <p style="margin: 0 0 8px;"><strong>Company:</strong> ${escapeHtml(input.company || "—")}</p>
      <p style="margin: 0 0 8px;"><strong>Service:</strong> ${escapeHtml(input.serviceTitle)}</p>
      <p style="margin: 0 0 8px;"><strong>Budget:</strong> ${escapeHtml(input.budget)}</p>
      <p style="margin: 0 0 16px;"><strong>Timeline:</strong> ${escapeHtml(input.timeline)}</p>
      <div style="padding: 16px; background: #f8fafc; border-radius: 8px;">
        ${formatMultiline(input.description)}
      </div>
    </div>
  `;

  const { data: result, error } = await resend.emails.send({
    from: FROM_EMAIL,
    to: [CONTACT_TO_EMAIL],
    replyTo: input.email,
    subject,
    text,
    html,
  });

  if (error) {
    throw new Error(error.message || "Failed to send email");
  }

  return { id: result?.id ?? "sent" };
}

export async function sendPortalOtpEmail(input: {
  to: string;
  code: string;
}): Promise<{ id: string }> {
  const resend = getResend();
  if (!resend) {
    throw new Error("Email is not configured (missing RESEND_API_KEY)");
  }

  const subject = "Your portal PIN — Adam Batten";
  const text = [
    `Your one-time portal PIN is: ${input.code}`,
    ``,
    `It expires in 10 minutes.`,
    `If you did not request this, you can ignore this email.`,
  ].join("\n");

  const html = `
    <div style="font-family: system-ui, sans-serif; line-height: 1.5; color: #0f172a;">
      <h2 style="margin: 0 0 12px;">Your portal PIN</h2>
      <p style="margin: 0 0 16px;">Use this code to open your project portal. It expires in <strong>10 minutes</strong>.</p>
      <p style="margin: 0 0 16px; font-size: 32px; font-weight: 700; letter-spacing: 0.2em;">${escapeHtml(input.code)}</p>
      <p style="margin: 0; color: #64748b; font-size: 14px;">If you did not request this, you can ignore this email.</p>
    </div>
  `;

  const { data: result, error } = await resend.emails.send({
    from: FROM_EMAIL,
    to: [input.to],
    subject,
    text,
    html,
  });

  if (error) {
    throw new Error(error.message || "Failed to send portal PIN email");
  }

  return { id: result?.id ?? "sent" };
}
