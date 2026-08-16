import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { assertPortalAccess, getPortalAuth } from "@/lib/portal-auth";
import { portalMessageSchema } from "@/lib/portal-validations";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await context.params;
    if (!(await assertPortalAccess(id, auth))) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const messages = await prisma.portalMessage.findMany({
      where: { portalId: id },
      orderBy: { createdAt: "asc" },
    });

    return NextResponse.json({ messages });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await context.params;
    if (!(await assertPortalAccess(id, auth))) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const body = await request.json();
    const parsed = portalMessageSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const portal = await prisma.clientPortal.findUnique({
      where: { id },
      select: { clientName: true },
    });
    if (!portal) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const message = await prisma.portalMessage.create({
      data: {
        portalId: id,
        senderRole: auth.isAdmin ? "admin" : "client",
        senderName: auth.isAdmin ? "Adam Batten" : portal.clientName,
        body: parsed.data.body,
      },
    });

    await prisma.clientPortal.update({
      where: { id },
      data: { updatedAt: new Date() },
    });

    return NextResponse.json({ success: true, message }, { status: 201 });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
