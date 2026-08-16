import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import {
  isEmailConfigured,
  sendContactNotification,
} from "@/lib/email";
import { contactFormSchema } from "@/lib/validations";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = contactFormSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 },
      );
    }

    let emailId: string | null = null;
    let dbId: string | null = null;

    if (isEmailConfigured()) {
      try {
        const sent = await sendContactNotification(parsed.data);
        emailId = sent.id;
      } catch (err) {
        console.error("Contact email failed:", err);
        return NextResponse.json(
          {
            error:
              "Could not send your message right now. Please try again shortly.",
          },
          { status: 502 },
        );
      }
    }

    try {
      const message = await prisma.contactMessage.create({
        data: parsed.data,
      });
      dbId = message.id;
    } catch (err) {
      console.error("Contact DB save failed:", err);
      // On Vercel, SQLite may be unavailable — email alone is enough.
      if (!emailId) {
        return NextResponse.json(
          {
            error:
              "Could not save your message. Email delivery is not configured yet.",
          },
          { status: 500 },
        );
      }
    }

    if (!emailId && !dbId) {
      return NextResponse.json(
        { error: "Internal server error" },
        { status: 500 },
      );
    }

    return NextResponse.json(
      {
        success: true,
        id: dbId ?? emailId,
        emailed: Boolean(emailId),
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
    const messages = await prisma.contactMessage.findMany({
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json(messages);
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
