import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
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

    const serviceRequest = await prisma.serviceRequest.create({
      data: parsed.data,
    });

    return NextResponse.json(
      {
        success: true,
        id: serviceRequest.id,
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
