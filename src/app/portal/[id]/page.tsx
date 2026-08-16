import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import PortalWorkspace from "@/components/portal/PortalWorkspace";
import { prisma } from "@/lib/db";
import { assertPortalAccess, getPortalAuth } from "@/lib/portal-auth";

export const metadata: Metadata = {
  title: "Project portal",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ id: string }> };

export default async function PortalProjectPage({ params }: PageProps) {
  const auth = await getPortalAuth();
  if (!auth) redirect("/portal");

  const { id } = await params;
  if (!(await assertPortalAccess(id, auth))) {
    redirect("/portal/home");
  }

  const portal = await prisma.clientPortal.findUnique({
    where: { id },
    include: {
      milestones: { orderBy: { order: "asc" } },
      messages: { orderBy: { createdAt: "asc" } },
    },
  });

  if (!portal) notFound();

  return (
    <section className="bg-surface-50 min-h-[70vh]">
      <PortalWorkspace
        isAdmin={auth.isAdmin}
        portal={{
          ...portal,
          milestones: portal.milestones.map((m) => ({
            ...m,
          })),
          messages: portal.messages.map((m) => ({
            ...m,
            createdAt: m.createdAt.toISOString(),
          })),
        }}
      />
    </section>
  );
}
