import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getPortalAuth } from "@/lib/portal-auth";
import {
  portalMilestoneCreateSchema,
  portalMilestoneUpdateSchema,
} from "@/lib/portal-validations";

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth?.isAdmin) {
      return NextResponse.json({ error: "Admin only" }, { status: 403 });
    }

    const { id: portalId } = await context.params;
    const body = await request.json();
    const parsed = portalMilestoneCreateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const max = await prisma.portalMilestone.aggregate({
      where: { portalId },
      _max: { order: true },
    });

    const milestone = await prisma.portalMilestone.create({
      data: {
        portalId,
        title: parsed.data.title,
        description: parsed.data.description || "",
        status: parsed.data.status || "pending",
        order: (max._max.order ?? -1) + 1,
      },
    });

    return NextResponse.json({ success: true, milestone }, { status: 201 });
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

    const { id: portalId } = await context.params;
    const body = await request.json();
    const milestoneId = body?.id as string | undefined;
    if (!milestoneId) {
      return NextResponse.json(
        { error: "Milestone id required" },
        { status: 400 },
      );
    }

    const parsed = portalMilestoneUpdateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const existing = await prisma.portalMilestone.findFirst({
      where: { id: milestoneId, portalId },
    });
    if (!existing) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const milestone = await prisma.portalMilestone.update({
      where: { id: milestoneId },
      data: {
        title: parsed.data.title,
        description: parsed.data.description,
        status: parsed.data.status,
        order: parsed.data.order,
      },
    });

    await prisma.clientPortal.update({
      where: { id: portalId },
      data: { updatedAt: new Date() },
    });

    return NextResponse.json({ success: true, milestone });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  try {
    const auth = await getPortalAuth();
    if (!auth?.isAdmin) {
      return NextResponse.json({ error: "Admin only" }, { status: 403 });
    }

    const { id: portalId } = await context.params;
    const milestoneId = request.nextUrl.searchParams.get("milestoneId");
    if (!milestoneId) {
      return NextResponse.json(
        { error: "milestoneId query required" },
        { status: 400 },
      );
    }

    const existing = await prisma.portalMilestone.findFirst({
      where: { id: milestoneId, portalId },
    });
    if (!existing) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    await prisma.portalMilestone.delete({ where: { id: milestoneId } });
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
