import { NextRequest, NextResponse } from "next/server";
import { sendPortalOtpEmail, isEmailConfigured } from "@/lib/email";
import {
  createAndStoreOtp,
  emailCanAccessPortal,
  normalizeEmail,
} from "@/lib/portal-auth";
import { portalOtpRequestSchema } from "@/lib/portal-validations";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = portalOtpRequestSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const email = normalizeEmail(parsed.data.email);
    const allowed = await emailCanAccessPortal(email);

    // Always return the same shape so emails are not enumerable.
    if (!allowed) {
      return NextResponse.json({
        success: true,
        message:
          "If that email has portal access, a PIN is on its way. Check your inbox.",
      });
    }

    const code = await createAndStoreOtp(email);
    const allowDevCode =
      process.env.NODE_ENV !== "production" ||
      process.env.PORTAL_DEV_OTP === "1";

    if (isEmailConfigured()) {
      try {
        await sendPortalOtpEmail({ to: email, code });
      } catch (err) {
        console.error("Portal OTP email failed:", err);
        return NextResponse.json(
          { error: "Could not send PIN email. Try again shortly." },
          { status: 502 },
        );
      }
    } else if (allowDevCode) {
      console.info(`[portal-otp] ${email} → ${code}`);
    } else {
      return NextResponse.json(
        { error: "Email delivery is not configured on the server." },
        { status: 503 },
      );
    }

    return NextResponse.json({
      success: true,
      message:
        "If that email has portal access, a PIN is on its way. Check your inbox.",
      // Shown only when Resend is off and PORTAL_DEV_OTP / non-production
      ...(allowDevCode && !isEmailConfigured() ? { devCode: code } : {}),
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
