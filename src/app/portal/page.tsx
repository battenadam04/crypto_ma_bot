import type { Metadata } from "next";
import { redirect } from "next/navigation";
import PortalLoginForm from "@/components/portal/PortalLoginForm";
import { getPortalAuth } from "@/lib/portal-auth";

export const metadata: Metadata = {
  title: "Client portal",
  description:
    "Sign in with a one-time PIN to chat about your project and track progress.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function PortalLoginPage() {
  const auth = await getPortalAuth();
  if (auth) redirect("/portal/home");

  return (
    <section className="bg-gradient-to-b from-brand-50 to-surface-0 py-16">
      <div className="mx-auto max-w-7xl px-6">
        <PortalLoginForm />
      </div>
    </section>
  );
}
