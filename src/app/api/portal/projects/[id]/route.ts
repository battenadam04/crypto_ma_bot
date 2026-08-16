import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { assertPortalAccess, getPortalAuth } from "@/lib/portal-auth";
import { portalMetaUpdateSchema } from "@/lib/portal-validations";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await context.params;
    const allowed = await assertPortalAccess(id, auth);
    if (!allowed) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const portal = await prisma.clientPortal.findUnique({
      where: { id },
      include: {
        milestones: { orderBy: { order: "asc" } },
        messages: { orderBy: { createdAt: "asc" } },
      },
    });

    if (!portal) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    return NextResponse.json({
      auth: { email: auth.email, isAdmin: auth.isAdmin },
      portal,
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth?.isAdmin) {
      return NextResponse.json({ error: "Admin only" }, { status: 403 });
    }

    const { id } = await context.params;
    const body = await request.json();
    const parsed = portalMetaUpdateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const portal = await prisma.clientPortal.update({
      where: { id },
      data: parsed.data,
      include: {
        milestones: { orderBy: { order: "asc" } },
        messages: { orderBy: { createdAt: "asc" } },
      },
    });

    return NextResponse.json({ success: true, portal });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
