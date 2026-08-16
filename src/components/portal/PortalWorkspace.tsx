"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import PortalChat, { type PortalMessage } from "@/components/portal/PortalChat";
import PortalProgress, {
  type PortalMilestone,
} from "@/components/portal/PortalProgress";

interface PortalWorkspaceProps {
  portal: {
    id: string;
    title: string;
    clientName: string;
    clientEmail: string;
    status: string;
    summary: string;
    milestones: PortalMilestone[];
    messages: PortalMessage[];
  };
  isAdmin: boolean;
}

export default function PortalWorkspace({
  portal,
  isAdmin,
}: PortalWorkspaceProps) {
  const router = useRouter();

  const logout = async () => {
    await fetch("/api/portal/logout", { method: "POST" });
    router.push("/portal");
    router.refresh();
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/portal/home"
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            ← All projects
          </Link>
          <h1 className="mt-2 text-3xl font-bold text-surface-950">
            {portal.title}
          </h1>
          <p className="mt-1 text-sm text-surface-700">
            {portal.clientName} · {portal.clientEmail}
            {isAdmin ? " · editing as admin" : ""}
          </p>
        </div>
        <Button type="button" variant="ghost" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-stretch">
        <PortalChat
          portalId={portal.id}
          initialMessages={portal.messages}
          isAdmin={isAdmin}
        />
        <PortalProgress
          portalId={portal.id}
          initialMilestones={portal.milestones}
          isAdmin={isAdmin}
          portalStatus={portal.status}
          summary={portal.summary}
          title={portal.title}
        />
      </div>
    </div>
  );
}
