import { NextRequest, NextResponse } from "next/server";
import {
  createSession,
  normalizeEmail,
  setSessionCookie,
  verifyOtpCode,
} from "@/lib/portal-auth";
import { portalOtpVerifySchema } from "@/lib/portal-validations";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = portalOtpVerifySchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const email = normalizeEmail(parsed.data.email);
    const result = await verifyOtpCode(email, parsed.data.code);
    if (!result.ok) {
      return NextResponse.json({ error: result.error }, { status: 401 });
    }

    const token = await createSession(email);
    await setSessionCookie(token);

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
