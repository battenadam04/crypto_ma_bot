import { createHash, randomBytes, randomInt, timingSafeEqual } from "crypto";
import { cookies } from "next/headers";
import { prisma } from "@/lib/db";
import { CONTACT_TO_EMAIL } from "@/lib/email";

export const PORTAL_COOKIE = "portal_session";
const OTP_TTL_MS = 10 * 60 * 1000;
const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const MAX_OTP_ATTEMPTS = 5;

export function getAdminEmail(): string {
  return (
    process.env.ADMIN_EMAIL?.trim().toLowerCase() ||
    CONTACT_TO_EMAIL.toLowerCase()
  );
}

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function isAdminEmail(email: string): boolean {
  return normalizeEmail(email) === getAdminEmail();
}

function hashValue(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function safeEqualHex(a: string, b: string): boolean {
  try {
    const ba = Buffer.from(a, "hex");
    const bb = Buffer.from(b, "hex");
    if (ba.length !== bb.length) return false;
    return timingSafeEqual(ba, bb);
  } catch {
    return false;
  }
}

export function generateOtpCode(): string {
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}

export async function createAndStoreOtp(email: string): Promise<string> {
  const normalized = normalizeEmail(email);
  const code = generateOtpCode();
  const expiresAt = new Date(Date.now() + OTP_TTL_MS);

  await prisma.portalOtp.deleteMany({ where: { email: normalized } });
  await prisma.portalOtp.create({
    data: {
      email: normalized,
      codeHash: hashValue(code),
      expiresAt,
    },
  });

  return code;
}

export async function verifyOtpCode(
  email: string,
  code: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const normalized = normalizeEmail(email);
  const record = await prisma.portalOtp.findFirst({
    where: { email: normalized },
    orderBy: { createdAt: "desc" },
  });

  if (!record) {
    return { ok: false, error: "No PIN found. Request a new one." };
  }

  if (record.expiresAt.getTime() < Date.now()) {
    await prisma.portalOtp.delete({ where: { id: record.id } });
    return { ok: false, error: "PIN expired. Request a new one." };
  }

  if (record.attempts >= MAX_OTP_ATTEMPTS) {
    await prisma.portalOtp.delete({ where: { id: record.id } });
    return { ok: false, error: "Too many attempts. Request a new PIN." };
  }

  const match = safeEqualHex(record.codeHash, hashValue(code.trim()));
  if (!match) {
    await prisma.portalOtp.update({
      where: { id: record.id },
      data: { attempts: { increment: 1 } },
    });
    return { ok: false, error: "Incorrect PIN. Try again." };
  }

  await prisma.portalOtp.delete({ where: { id: record.id } });
  return { ok: true };
}

export async function createSession(email: string): Promise<string> {
  const normalized = normalizeEmail(email);
  const token = randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + SESSION_TTL_MS);

  await prisma.portalSession.create({
    data: {
      tokenHash: hashValue(token),
      email: normalized,
      isAdmin: isAdminEmail(normalized),
      expiresAt,
    },
  });

  return token;
}

export async function destroySession(token: string | undefined): Promise<void> {
  if (!token) return;
  await prisma.portalSession.deleteMany({
    where: { tokenHash: hashValue(token) },
  });
}

export type PortalAuth = {
  email: string;
  isAdmin: boolean;
};

export async function getPortalAuth(): Promise<PortalAuth | null> {
  const jar = await cookies();
  const token = jar.get(PORTAL_COOKIE)?.value;
  if (!token) return null;

  const session = await prisma.portalSession.findUnique({
    where: { tokenHash: hashValue(token) },
  });

  if (!session || session.expiresAt.getTime() < Date.now()) {
    if (session) {
      await prisma.portalSession.delete({ where: { id: session.id } });
    }
    return null;
  }

  return {
    email: session.email,
    isAdmin: session.isAdmin || isAdminEmail(session.email),
  };
}

export async function setSessionCookie(token: string): Promise<void> {
  const jar = await cookies();
  jar.set(PORTAL_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(PORTAL_COOKIE);
}

export async function emailCanAccessPortal(email: string): Promise<boolean> {
  const normalized = normalizeEmail(email);
  if (isAdminEmail(normalized)) return true;
  const count = await prisma.clientPortal.count({
    where: { clientEmail: normalized },
  });
  return count > 0;
}

export async function assertPortalAccess(
  portalId: string,
  auth: PortalAuth,
): Promise<boolean> {
  if (auth.isAdmin) return true;
  const portal = await prisma.clientPortal.findUnique({
    where: { id: portalId },
    select: { clientEmail: true },
  });
  return Boolean(portal && portal.clientEmail === auth.email);
}
