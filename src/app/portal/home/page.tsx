import type { Metadata } from "next";
import { redirect } from "next/navigation";
import PortalHomeClient from "@/components/portal/PortalHomeClient";
import { prisma } from "@/lib/db";
import { getPortalAuth } from "@/lib/portal-auth";

export const metadata: Metadata = {
  title: "Portal projects",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function PortalHomePage() {
  const auth = await getPortalAuth();
  if (!auth) redirect("/portal");

  const portals = await prisma.clientPortal.findMany({
    where: auth.isAdmin ? undefined : { clientEmail: auth.email },
    orderBy: { updatedAt: "desc" },
    include: {
      milestones: { select: { status: true } },
      _count: { select: { messages: true } },
    },
  });

  return (
    <section className="bg-surface-0 min-h-[70vh]">
      <PortalHomeClient
        email={auth.email}
        isAdmin={auth.isAdmin}
        portals={portals.map((p) => ({
          ...p,
          updatedAt: p.updatedAt.toISOString(),
        }))}
      />
    </section>
  );
}
