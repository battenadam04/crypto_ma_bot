import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  isEmailConfigured,
  sendServiceRequestNotification,
} from "@/lib/email";
import { serviceRequestSchema } from "@/lib/validations";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = serviceRequestSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    const service = await prisma.service.findUnique({
      where: { id: parsed.data.serviceId },
    });

    if (!service) {
      return NextResponse.json(
        { error: "Selected service not found" },
        { status: 400 },
      );
    }

    let emailId: string | null = null;
    let dbId: string | null = null;

    if (isEmailConfigured()) {
      try {
        const sent = await sendServiceRequestNotification({
          name: parsed.data.name,
          email: parsed.data.email,
          company: parsed.data.company,
          serviceTitle: service.title,
          budget: parsed.data.budget || "—",
          timeline: parsed.data.timeline || "—",
          description: parsed.data.description,
        });
        emailId = sent.id;
      } catch (err) {
        console.error("Service request email failed:", err);
        return NextResponse.json(
          {
            error:
              "Could not send your request right now. Please try again shortly.",
          },
          { status: 502 },
        );
      }
    }

    try {
      const serviceRequest = await prisma.serviceRequest.create({
        data: parsed.data,
      });
      dbId = serviceRequest.id;
    } catch (err) {
      console.error("Service request DB save failed:", err);
      if (!emailId) {
        return NextResponse.json(
          {
            error:
              "Could not save your request. Email delivery is not configured yet.",
          },
          { status: 500 },
        );
      }
    }

    return NextResponse.json(
      {
        success: true,
        id: dbId ?? emailId,
        emailed: Boolean(emailId),
        estimate: {
          priceFrom: service.priceFrom,
          priceTo: service.priceTo,
          estimatedDays: service.estimatedDays,
        },
      },
      { status: 201 },
    );
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}

export async function GET() {
  try {
    const requests = await prisma.serviceRequest.findMany({
      include: { service: true },
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json(requests);
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
