import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import ServicesContent from "./ServicesContent";

export const metadata: Metadata = {
  title: "Services",
  description:
    "Explore our web development services including custom web applications, e-commerce solutions, API development, UI/UX design, and performance optimization. Get a free quote today.",
};

export const dynamic = "force-dynamic";

export default async function ServicesPage() {
  const services = await prisma.service.findMany({
    orderBy: { order: "asc" },
  });

  return <ServicesContent services={services} />;
}
