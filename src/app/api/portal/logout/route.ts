import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  clearSessionCookie,
  destroySession,
  PORTAL_COOKIE,
} from "@/lib/portal-auth";

export async function POST() {
  try {
    const jar = await cookies();
    const token = jar.get(PORTAL_COOKIE)?.value;
    await destroySession(token);
    await clearSessionCookie();
    return NextResponse.json({ success: true });
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
