import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getPortalAuth, normalizeEmail } from "@/lib/portal-auth";
import { portalCreateSchema } from "@/lib/portal-validations";

const DEFAULT_MILESTONES = [
  { title: "Kick-off & requirements", description: "Align on goals and scope" },
  { title: "Design / structure", description: "Layout and content plan" },
  { title: "Build in progress", description: "Implementation" },
  { title: "Review & revisions", description: "Your feedback round" },
  { title: "Launch & handover", description: "Go live and hand over" },
];

export async function GET() {
  try {
    const auth = await getPortalAuth();
    if (!auth) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const portals = await prisma.clientPortal.findMany({
      where: auth.isAdmin ? undefined : { clientEmail: auth.email },
      orderBy: { updatedAt: "desc" },
      include: {
        milestones: { orderBy: { order: "asc" } },
        _count: { select: { messages: true } },
      },
    });

    return NextResponse.json({
      auth: { email: auth.email, isAdmin: auth.isAdmin },
      portals,
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const auth = await getPortalAuth();
    if (!auth?.isAdmin) {
      return NextResponse.json({ error: "Admin only" }, { status: 403 });
    }

    const body = await request.json();
    const parsed = portalCreateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const milestones =
      parsed.data.milestones && parsed.data.milestones.length > 0
        ? parsed.data.milestones
        : DEFAULT_MILESTONES;

    const portal = await prisma.clientPortal.create({
      data: {
        title: parsed.data.title,
        clientName: parsed.data.clientName,
        clientEmail: normalizeEmail(parsed.data.clientEmail),
        summary: parsed.data.summary || "",
        milestones: {
          create: milestones.map((m, i) => ({
            title: m.title,
            description: m.description || "",
            order: i,
            status: i === 0 ? "in_progress" : "pending",
          })),
        },
      },
      include: { milestones: { orderBy: { order: "asc" } } },
    });

    return NextResponse.json({ success: true, portal }, { status: 201 });
  } catch (err) {
    console.error(err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
