import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import ServicesContent from "./ServicesContent";

export const metadata: Metadata = {
  title: "Services",
  description:
    "Solo web development services with realistic pricing: SEO landing pages, website fixes, business sites, online stores, custom apps, and speed & SEO tune-ups. Get a free quote today.",
};

export const dynamic = "force-dynamic";

export default async function ServicesPage() {
  const services = await prisma.service.findMany({
    orderBy: { order: "asc" },
  });

  return <ServicesContent services={services} />;
}
